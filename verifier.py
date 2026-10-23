
"""Verify a quote and return its exact character range in the source text."""

import re

_TRANSLATION = str.maketrans({
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
})


def _normalize_with_map(text: str):
    """Normalize text while retaining a map to original character positions."""
    normalized = []
    spans = []
    in_whitespace = False
    whitespace_start = None

    for index, original_char in enumerate(text):
        char = original_char.translate(_TRANSLATION)

        if char.isspace():
            if not in_whitespace:
                whitespace_start = index
            in_whitespace = True
            continue

        # Represent a run of source whitespace as one normalized space.
        if in_whitespace and normalized:
            normalized.append(" ")
            spans.append((whitespace_start, index))

        in_whitespace = False
        whitespace_start = None

        # casefold() handles more Unicode case variations than lower().
        for normalized_char in char.casefold():
            normalized.append(normalized_char)
            spans.append((index, index + 1))

    # Trailing whitespace is deliberately omitted.
    return "".join(normalized), spans


def norm(text: str) -> str:
    """Return normalized text for comparison."""
    normalized, _ = _normalize_with_map(text or "")
    return normalized.strip()


def locate_quote(quote: str, source_text: str):
    """
    Return (start, end) offsets in source_text, or None if no match exists.

    Offsets refer to the original source, not the normalized text.
    """
    if not quote or not source_text:
        return None

    normalized_source, source_spans = _normalize_with_map(source_text)
    normalized_quote, _ = _normalize_with_map(quote)

    normalized_source = normalized_source.strip()
    normalized_quote = normalized_quote.strip()

    if not normalized_quote:
        return None

    # Account for whitespace removed at the start of normalized source.
    source_leading = len(_normalize_with_map(source_text)[0]) - len(
        _normalize_with_map(source_text)[0].lstrip()
    )
    position = normalized_source.find(normalized_quote)

    if position < 0:
        return None

    mapped_start = source_leading + position
    mapped_end = mapped_start + len(normalized_quote) - 1

    if mapped_end >= len(source_spans):
        return None

    return (
        source_spans[mapped_start][0],
        source_spans[mapped_end][1],
    )


def verify_quote(quote: str, chunk_text: str) -> bool:
    """True only when the quote can be located in the source text."""
    return locate_quote(quote, chunk_text) is not None
