"""Step 2: extract clause facts. Two engines with the same output shape:
   - regex_extract(): offline, deterministic (privacy mode + test baseline + LLM fallback)
   - llm_extract():   Anthropic API, for messy real-world wording
Output: list of findings {type, chunk_id, quote, value:{...}}"""
import json, os, re

WORDS = {"zero": 0, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45, "forty five": 45,
         "forty": 40, "sixty": 60, "ninety": 90, "one hundred twenty": 120, "one hundred and twenty": 120,
         "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "fourteen": 14, "twelve": 12}
NUM = r"(\d+|" + "|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)) + r")"


def to_int(tok):
    tok = tok.lower().strip()
    return int(tok) if tok.isdigit() else WORDS.get(tok)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(\"])", text) if s.strip()]


def regex_extract(chunks):
    out = []
    for c in chunks:
        for s in sentences(c.text):
            low = s.lower()
            base = {"chunk_id": c.chunk_id, "quote": s}
            # ---- payment
            if re.search(r"\b(invoice|pay|payment|paid)\b", low):
                m = re.search(r"\bnet[\s-]*" + NUM + r"\b", low) or \
                    re.search(NUM + r"\s*(?:\(\d+\)\s*)?(?:calendar\s+|business\s+|working\s+)?(days?|months?)\b", low)
                if m:
                    n = to_int(m.group(1))
                    unit = m.group(2) if m.lastindex and m.lastindex >= 2 else "days"
                    if n is not None:
                        days = n * 30 if unit.startswith("month") else n
                        clock = "approval" if re.search(r"approv|accept", low) else \
                                "receipt" if "receipt" in low else "invoice"
                        out.append({**base, "type": "payment", "value": {"days": days, "clock_starts": clock}})
            # ---- auto renewal
            if re.search(r"auto-?\s?renew|automatically\s+(?:be\s+)?renew|renew\s+automatically", low):
                n = re.search(NUM + r"\s*(?:\(\d+\)\s*)?days?", low)
                out.append({**base, "type": "renewal", "value": {"renews": True,
                            "notice_days": to_int(n.group(1)) if n else None}})
            # ---- liability
            if re.search(r"unlimited|without limit|not be limited|no cap", low) and re.search(r"liab|indemn", low):
                out.append({**base, "type": "liability", "value": {"capped": False}})
            elif re.search(r"liab", low) and re.search(r"shall not exceed|limited to|capped|aggregate liability", low):
                out.append({**base, "type": "liability", "value": {"capped": True}})
            elif re.search(r"indemnif", low) and re.search(r"any and all|all losses|all claims", low):
                out.append({**base, "type": "liability", "value": {"capped": False, "note": "broad indemnity"}})
            # ---- jurisdiction
            m = re.search(r"(?:governed by|construed in accordance with)[^.]*?laws? of (?:the )?(?:[Ss]tate of |[Rr]epublic of )?"
                          r"([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)", s) or \
                re.search(r"courts? (?:of|in|located in) ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*)", s)
            if m:
                out.append({**base, "type": "jurisdiction", "value": {"location": m.group(1)}})
    return out


SYSTEM = """You extract contract facts. Return ONLY JSON: a list of objects
{"type": "payment|renewal|liability|jurisdiction", "chunk_id": "<id from input>", "quote": "<verbatim text copied from that chunk>",
 "value": {...}}.
value schemas: payment {days:int, clock_starts:"invoice|approval|receipt|other"}; renewal {renews:bool, notice_days:int|null};
liability {capped:bool, note:str|null}; jurisdiction {location:str}.
Rules: copy quotes EXACTLY, never paraphrase. Convert written numbers/months to days (1 month = 30). If a clause is absent, output nothing for it. Do not guess."""

KEYWORDS = re.compile(r"pay|invoice|fee|renew|term|terminat|liab|indemn|govern|jurisdiction|court|law", re.I)


def llm_extract(chunks, model=None):
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    relevant = [c for c in chunks if KEYWORDS.search(c.text)]
    payload = json.dumps([{"chunk_id": c.chunk_id, "section": c.section, "text": c.text} for c in relevant])
    msg = client.messages.create(model=model or os.getenv("CLAUSELENS_MODEL", "claude-sonnet-5-5"),
                                 max_tokens=4000, temperature=0, system=SYSTEM,
                                 messages=[{"role": "user", "content": payload}])
    text = msg.content[0].text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)
