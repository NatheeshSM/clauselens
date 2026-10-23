"""SQLite persistence layer for ClauseLens.
Stores documents, parsed chunks, findings, analyses, and flags locally (zero telemetry)."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = os.getenv("CLAUSELENS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "clauselens.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    created_at TEXT,
    pages INTEGER,
    full_text TEXT
);

CREATE TABLE IF NOT EXISTS chunks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    chunk_id TEXT,
    page INTEGER,
    section TEXT,
    char_start INTEGER,
    source TEXT,
    bbox TEXT,
    text TEXT,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS findings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    type TEXT,
    chunk_id TEXT,
    quote TEXT,
    char_start INTEGER,
    char_end INTEGER,
    page INTEGER,
    value_json TEXT,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analyses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    created_at TEXT,
    mode TEXT,
    policy_json TEXT,
    stats_json TEXT,
    summary TEXT,
    checks_json TEXT,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flags(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER,
    severity TEXT,
    kind TEXT,
    category TEXT,
    rule TEXT,
    message TEXT,
    quote TEXT,
    page INTEGER,
    section TEXT,
    flag_json TEXT,
    FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_findings_doc ON findings(doc_id);
CREATE INDEX IF NOT EXISTS idx_analyses_doc ON analyses(doc_id);
CREATE INDEX IF NOT EXISTS idx_flags_analysis ON flags(analysis_id);
"""


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA)
    return c


def save_analysis(filename, chunks, res, policy):
    now = datetime.now().isoformat(timespec="seconds")
    from doc_parser import full_text

    with closing(_conn()) as c, c:
        doc = c.execute(
            "INSERT INTO documents(filename, created_at, pages, full_text) VALUES (?,?,?,?)",
            (filename, now, max((getattr(x, "page", 1) for x in chunks), default=1), full_text(chunks)),
        ).lastrowid

        c.executemany(
            "INSERT INTO chunks(doc_id, chunk_id, page, section, char_start, source, bbox, text) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    doc,
                    getattr(x, "chunk_id", ""),
                    getattr(x, "page", 1),
                    getattr(x, "section", ""),
                    getattr(x, "char_start", 0),
                    getattr(x, "source", "text"),
                    json.dumps(getattr(x, "bbox", [])),
                    getattr(x, "text", ""),
                )
                for x in chunks
            ],
        )

        c.executemany(
            "INSERT INTO findings(doc_id, type, chunk_id, quote, char_start, char_end, page, value_json) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    doc,
                    f.get("type", ""),
                    f.get("chunk_id", ""),
                    f.get("quote", ""),
                    f.get("char_start", 0),
                    f.get("char_end", 0),
                    f.get("page", 1),
                    json.dumps(f.get("value", {})),
                )
                for f in res.get("findings", [])
            ],
        )

        aid = c.execute(
            "INSERT INTO analyses(doc_id, created_at, mode, policy_json, stats_json, summary, checks_json) VALUES (?,?,?,?,?,?,?)",
            (
                doc,
                now,
                res.get("stats", {}).get("mode", "offline"),
                json.dumps(policy),
                json.dumps(res.get("stats", {})),
                res.get("summary", ""),
                json.dumps(res.get("checks", [])),
            ),
        ).lastrowid

        flag_rows = []
        for f in res.get("flags", []):
            f_dict = f.to_dict() if hasattr(f, "to_dict") else dict(f)
            flag_rows.append((
                aid,
                f_dict.get("severity", "Low"),
                f_dict.get("kind", "Issue"),
                f_dict.get("category", ""),
                f_dict.get("rule", ""),
                f_dict.get("message", ""),
                f_dict.get("quote", ""),
                f_dict.get("page", 1),
                f_dict.get("section", ""),
                json.dumps(f_dict),
            ))

        c.executemany(
            "INSERT INTO flags(analysis_id, severity, kind, category, rule, message, quote, page, section, flag_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            flag_rows,
        )

    return aid


def list_analyses(search=""):
    sql = """
        SELECT a.id, d.filename, a.created_at, a.summary, a.mode,
               (SELECT COUNT(*) FROM flags f WHERE f.analysis_id=a.id AND f.severity='High') AS high_flags,
               (SELECT COUNT(*) FROM flags f WHERE f.analysis_id=a.id) AS total_flags
        FROM analyses a
        JOIN documents d ON d.id=a.doc_id
    """
    args = []
    if search.strip():
        like = f"%{search.strip()}%"
        sql += """ WHERE d.filename LIKE ? OR d.full_text LIKE ? OR a.id IN
                   (SELECT analysis_id FROM flags WHERE quote LIKE ? OR rule LIKE ? OR message LIKE ?)"""
        args = [like] * 5

    sql += " ORDER BY a.id DESC"

    with closing(_conn()) as c:
        return [dict(r) for r in c.execute(sql, args)]


def load_analysis(aid):
    with closing(_conn()) as c:
        a = c.execute(
            "SELECT a.*, d.filename FROM analyses a JOIN documents d ON d.id=a.doc_id WHERE a.id=?",
            (aid,),
        ).fetchone()
        if not a:
            return None

        chunks = [
            {
                "chunk_id": r["chunk_id"],
                "page": r["page"],
                "section": r["section"],
                "text": r["text"],
                "char_start": r["char_start"],
                "source": r["source"],
                "bbox": json.loads(r["bbox"]),
            }
            for r in c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY id", (a["doc_id"],))
        ]

        flags = [
            json.loads(r["flag_json"])
            for r in c.execute("SELECT flag_json FROM flags WHERE analysis_id=? ORDER BY id", (aid,))
        ]

    return {
        "aid": aid,
        "name": a["filename"],
        "created_at": a["created_at"],
        "summary": a["summary"],
        "policy": json.loads(a["policy_json"]),
        "stats": json.loads(a["stats_json"]),
        "checks": json.loads(a["checks_json"]),
        "chunks": chunks,
        "flags": flags,
        "data": None,
    }


def delete_analysis(aid):
    with closing(_conn()) as c, c:
        row = c.execute("SELECT doc_id FROM analyses WHERE id=?", (aid,)).fetchone()
        if row:
            doc_id = row["doc_id"]
            c.execute("DELETE FROM analyses WHERE id=?", (aid,))
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            return True
    return False


def get_portfolio_stats():
    with closing(_conn()) as c:
        total_docs = c.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        total_analyses = c.execute("SELECT COUNT(*) AS c FROM analyses").fetchone()["c"]
        total_flags = c.execute("SELECT COUNT(*) AS c FROM flags").fetchone()["c"]
        high_flags = c.execute("SELECT COUNT(*) AS c FROM flags WHERE severity='High'").fetchone()["c"]
        med_flags = c.execute("SELECT COUNT(*) AS c FROM flags WHERE severity='Medium'").fetchone()["c"]
        low_flags = c.execute("SELECT COUNT(*) AS c FROM flags WHERE severity='Low'").fetchone()["c"]

    return {
        "total_docs": total_docs,
        "total_analyses": total_analyses,
        "total_flags": total_flags,
        "high_flags": high_flags,
        "med_flags": med_flags,
        "low_flags": low_flags,
    }
