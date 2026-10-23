"""Clause-detection lexicon (the 'lexicon + rules' idea from the base paper).
Finds which chunks mention each of the 4 target clause types BEFORE values are extracted."""
import re

LEXICON = {
    "payment": [r"\binvoice", r"\bpayment", r"\bpay\b", r"\bpaid\b", r"\bnet\b", r"\bremunerat", r"\bfees?\b"],
    "renewal": [r"\brenew", r"\bevergreen", r"\bsuccessive\b", r"\bnon-renewal"],
    "liability": [r"\bliab", r"\bindemn", r"\bdamages\b", r"\bshall not exceed", r"\bcapped\b"],
    "jurisdiction": [r"\bgoverned by", r"\bgoverning law", r"\bjurisdiction", r"\bcourts?\b", r"\bvenue\b",
                     r"\barbitrat", r"\blaws? of\b"],
}
_RX = {k: re.compile("|".join(v), re.I) for k, v in LEXICON.items()}


def detect_clauses(chunks):
    """-> {category: [chunk_id, ...]}"""
    return {cat: [c.chunk_id for c in chunks if rx.search(c.text)] for cat, rx in _RX.items()}


def candidate_chunks(chunks):
    """Chunks worth sending to the LLM (any category hit)."""
    return [c for c in chunks if any(rx.search(c.text) for rx in _RX.values())]
