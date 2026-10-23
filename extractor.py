"""Step 2: extract clause facts. Two engines with the same output shape:
   - regex_extract(): offline, deterministic (privacy mode + test baseline + LLM fallback)
   - llm_extract():   Anthropic API, for messy real-world wording
Output: list of findings {type, chunk_id, quote, value:{...}}"""
import json
import os
import re

WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "one hundred": 100, "one hundred twenty": 120, "one hundred and twenty": 120,
    "one hundred eighty": 180, "one hundred and eighty": 180,
}
NUM = r"(\d+|" + "|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)) + r")"


def to_int(tok):
    if not tok:
        return None
    tok = str(tok).lower().strip()
    return int(tok) if tok.isdigit() else WORDS.get(tok)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(\"“])", text) if s.strip()]


def regex_extract(chunks):
    out = []
    for c in chunks:
        for s in sentences(c.text):
            low = s.lower()
            base = {"chunk_id": c.chunk_id, "quote": s}

            # ---- payment: covers invoice, pay, payable, remunerat*, fees, milestone payments
            if re.search(r"\b(invoice|pay|payment|paid|payable|fees?|remunerat\w*|compensation)\b", low):
                m = (
                    re.search(r"\bnet[\s-]*" + NUM + r"\b", low)
                    or re.search(r"\b(?:within|in|after|following)?\s*" + NUM + r"\s*(?:\(\d+\)\s*)?(?:calendar\s+|business\s+|working\s+)?(days?|months?)\b", low)
                    or re.search(NUM + r"\s*(?:\(\d+\)\s*)?(?:calendar\s+|business\s+|working\s+)?(days?|months?)\b", low)
                )
                if m:
                    n = to_int(m.group(1))
                    unit = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else "days"
                    if n is not None:
                        days = n * 30 if unit.startswith("month") else n
                        clock = "approval" if re.search(r"approv|accept", low) else \
                                "receipt" if "receipt" in low else "invoice"
                        out.append({**base, "type": "payment", "value": {"days": days, "clock_starts": clock}})

            # ---- auto renewal: covers auto-renew, automatically renew, renews automatically, evergreen, successive terms
            if re.search(r"auto-?\s?renews?|automatically\s+(?:be\s+)?renews?|renews?\s+automatically|evergreen|successive\s+(?:one[- ])?year\s+terms?", low):
                n = re.search(NUM + r"\s*(?:\(\d+\)\s*)?(?:calendar\s+|business\s+)?days?", low)
                out.append({**base, "type": "renewal", "value": {"renews": True,
                            "notice_days": to_int(n.group(1)) if n else None}})

            # ---- liability: capped, uncapped, and broad indemnity clauses
            if re.search(r"unlimited|without limit|not be limited|no cap", low) and re.search(r"liab|indemn", low):
                out.append({**base, "type": "liability", "value": {"capped": False}})
            elif re.search(r"liab", low) and re.search(r"shall not exceed|limited to|capped|aggregate liability", low):
                out.append({**base, "type": "liability", "value": {"capped": True}})
            elif re.search(r"indemnif", low) and re.search(r"any and all|all losses|all claims", low):
                out.append({**base, "type": "liability", "value": {"capped": False, "note": "broad indemnity"}})

            # ---- jurisdiction: state/country law and courts
            m = (
                re.search(r"(?:governed by|construed in accordance with)[^.]*?laws? of (?:the )?(?:[Ss]tate of |[Rr]epublic of )?([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)", s)
                or re.search(r"courts? (?:of|in|located in) ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)", s)
            )
            if m:
                out.append({**base, "type": "jurisdiction", "value": {"location": m.group(1)}})

            # ---- IP ownership and moral rights surrender
            if re.search(r"\b(work made for hire|moral rights|waive.*moral rights|exclusive property of client|assign.*all rights,?\s+title)\b", low):
                out.append({**base, "type": "ip_ownership", "value": {"broad_transfer": True}})

            # ---- non-compete and restrictive covenants
            if re.search(r"\b(non-compete|not engage in (?:any )?competing|restrictive covenant|non-solicitation of clients)\b", low):
                out.append({**base, "type": "non_compete", "value": {"restricted": True}})

            # ---- unilateral immediate termination for convenience
            if re.search(r"\b(terminate (?:this agreement )?(?:at any time|without cause|for convenience|immediately without notice))\b", low):
                out.append({**base, "type": "termination", "value": {"immediate_convenience": True}})

    return out


SYSTEM = """You extract contract facts. Return ONLY JSON: a list of objects
{"type": "payment|renewal|liability|jurisdiction", "chunk_id": "<id from input>", "quote": "<verbatim text copied from that chunk>",
 "value": {
   payment:      {"days": int, "clock_starts": "invoice"|"approval"|"receipt"},
   renewal:      {"renews": bool, "notice_days": int or null},
   liability:    {"capped": bool},
   jurisdiction: {"location": str}
 }}
Rules:
- Quote must be VERBATIM from the text. Never summarise or rephrase.
- Convert written numbers to integers. Convert months to days (1 month = 30 days).
- If a clause is absent, omit it. Never guess."""


def llm_extract(chunks):
    from anthropic import Anthropic
    client = Anthropic()
    payload = [{"chunk_id": c.chunk_id, "text": c.text} for c in chunks]
    resp = client.messages.create(
        model=os.getenv("CLAUSELENS_MODEL", "claude-sonnet-5-5"),
        max_tokens=4000,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    txt = resp.content[0].text
    if "```" in txt:
        txt = txt.split("```")[1].lstrip("json\n")
    return json.loads(txt)
