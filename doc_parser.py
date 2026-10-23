"""Step 1: turn PDF / DOCX / TXT into numbered chunks that remember where they came from."""
import re
from dataclasses import dataclass, field, asdict

SECTION_RE = re.compile(r"^\s*((?:section|article|clause)\s+)?(\d+(?:\.\d+)*)[.)]?\s+", re.I)


@dataclass
class Chunk:
    chunk_id: str
    page: int
    section: str
    text: str
    bbox: list = field(default_factory=list)  # [x0, y0, x1, y1] for PDFs, else []
    source: str = "text"
    char_start: int = 0
    char_end: int = 0

    def to_dict(self):
        return asdict(self)


def _section_of(text, last):
    m = SECTION_RE.match(text)
    return m.group(2) if m else last


def parse_text(raw: str):
    """Plain text: one chunk per paragraph. Page = 1 (no pages in txt)."""
    chunks, last = [], ""
    pos = 0
    for i, para in enumerate(re.split(r"\n\s*\n", raw)):
        para = " ".join(para.split())
        if not para:
            continue
        last = _section_of(para, last)
        start = pos
        end = start + len(para)
        chunks.append(Chunk(f"c{i}", 1, last, para, source="text", char_start=start, char_end=end))
        pos = end + 2
    return chunks


def parse_docx(path):
    import docx
    d = docx.Document(path)
    raw = "\n\n".join(p.text for p in d.paragraphs if p.text.strip())
    return parse_text(raw)


def parse_pdf(path):
    import fitz  # PyMuPDF
    chunks, last = [], ""
    pos = 0
    doc = fitz.open(path)
    for pno, page in enumerate(doc, start=1):
        blocks = page.get_text("blocks")  # (x0,y0,x1,y1,text,block_no,type)
        if not blocks or not any(b[4].strip() for b in blocks):
            raise ValueError(f"Page {pno} has no text layer: scanned PDF, add OCR (pytesseract).")
        for b in blocks:
            text = " ".join(b[4].split())
            if not text:
                continue
            last = _section_of(text, last)
            start = pos
            end = start + len(text)
            chunks.append(Chunk(f"p{pno}_b{b[5]}", pno, last, text, [b[0], b[1], b[2], b[3]], source="pdf", char_start=start, char_end=end))
            pos = end + 2
    return chunks


def parse_file(path):
    p = path.lower()
    if p.endswith(".pdf"):
        return parse_pdf(path)
    if p.endswith(".docx"):
        return parse_docx(path)
    return parse_text(open(path, encoding="utf-8").read())


def full_text(chunks):
    """Return the concatenated text from parsed chunks for storage or display."""
    return "\n\n".join(chunk.text for chunk in chunks if getattr(chunk, "text", "").strip())
