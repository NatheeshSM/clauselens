"""Step 3: the trust layer. A quote is only shown if it exists verbatim in the source chunk."""
import re


def norm(s: str) -> str:
    s = s.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, chunk_text: str) -> bool:
    return bool(quote) and norm(quote) in norm(chunk_text)


def locate(quote: str, chunk_text: str):
    """Return (start, end) of the quote inside chunk_text (case/space-insensitive), or None."""
    pattern = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(pattern, chunk_text, re.I)
    return (m.start(), m.end()) if m else None
