"""Glue: parse -> extract -> VERIFY quotes -> rule engine."""
import re

from doc_parser import parse_file
from extractor import regex_extract, llm_extract
from verifier import verify_quote
from report import build_checks, summarize
from rules import Flag, evaluate, vague_language_hits
from lexicon import detect_clauses


def _quote_offset(chunk_text, quote):
    text = chunk_text or ""
    quote_text = quote or ""
    idx = text.find(quote_text)
    if idx >= 0:
        return idx, idx + len(quote_text)
    compact_text = re.sub(r"\s+", " ", text)
    compact_quote = re.sub(r"\s+", " ", quote_text)
    idx = compact_text.find(compact_quote)
    if idx >= 0:
        compact_pos = 0
        for i, ch in enumerate(text):
            if compact_pos == idx:
                return i, i + len(quote_text)
            if not ch.isspace():
                compact_pos += 1
        return 0, len(quote_text)
    return None, None


def analyze(chunks, policy, mode="offline"):
    """mode: 'offline' (regex) or 'llm' (falls back to regex if the API fails)."""
    detected_map = detect_clauses(chunks)
    detected_stats = {cat: len(ids) for cat, ids in detected_map.items()}

    try:
        raw = llm_extract(chunks) if mode == "llm" else regex_extract(chunks)
    except Exception as e:
        raw, mode = regex_extract(chunks), f"offline (LLM fallback: {e})"

    by_id = {c.chunk_id: c for c in chunks}
    verified, dropped = [], 0
    for f in raw:
        c = by_id.get(f.get("chunk_id"))
        if c and verify_quote(f.get("quote", ""), c.text):
            start, end = _quote_offset(c.text, f.get("quote", ""))
            chunk_start = getattr(c, "char_start", 0)
            verified.append({
                **f,
                "page": c.page,
                "section": c.section,
                "char_start": chunk_start + (start if start is not None else 0),
                "char_end": chunk_start + (end if end is not None else len(f.get("quote", ""))),
            })
        else:
            dropped += 1  # hallucinated / paraphrased quote: dropped from trust layer

    flags = evaluate(verified, policy)

    # Vague language scan
    for c in chunks:
        hits = vague_language_hits(c.text)
        if hits:
            phrase = hits[0]
            flags.append(Flag(
                "WARNING",
                "Vague wording",
                f"The clause uses vague language ('{phrase}'), which is hard to enforce and easy to dispute.",
                "Medium",
                "Replace vague wording with specific obligations, dates, and measurable thresholds.",
                quote=c.text,
                chunk_id=c.chunk_id,
                page=c.page,
                section=c.section,
                category="Clarity",
                rule_value="Precise commitments",
                contract_value=f"Vague: '{phrase}'",
            ))

    # Deduplicate flags
    seen, uniq = set(), []
    for f in flags:
        key = (getattr(f, "rule", None), getattr(f, "message", None), getattr(f, "quote", None))
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    flags = sorted(uniq, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(getattr(x, "severity", "Low"), 2))

    payment_days = [int(f["value"].get("days", 0) or 0) for f in verified if f["type"] == "payment"]
    cashflow_days = max(payment_days) if payment_days else None
    cashflow_label = (
        "No payment trigger detected"
        if cashflow_days is None
        else "Cash-flow strain (>60d)" if cashflow_days > 60
        else "Healthy payment cycle (≤30d)" if cashflow_days <= 30
        else "Moderate cash-flow lag (31-60d)"
    )

    ocr_pages = sorted(list(set(c.page for c in chunks if getattr(c, "source", "") == "ocr")))

    checks = build_checks(verified, flags, policy)
    summary = summarize(checks)
    stats = {
        "extracted": len(raw),
        "verified": len(verified),
        "dropped": dropped,
        "mode": mode,
        "cashflow_days": cashflow_days,
        "cashflow_label": cashflow_label,
        "detected": detected_stats,
        "ocr_pages": ocr_pages,
    }
    return {"flags": flags, "findings": verified, "stats": stats, "checks": checks, "summary": summary}
