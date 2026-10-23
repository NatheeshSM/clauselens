"""Database box from the architecture diagram (SQLite, local file, nothing leaves the machine)."""
import json, os, sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = os.getenv("CLAUSELENS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "clauselens.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, created_at TEXT, pages INTEGER, full_text TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, chunk_id TEXT, page INTEGER, section TEXT,
                                  char_start INTEGER, source TEXT, bbox TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, type TEXT, chunk_id TEXT, quote TEXT,
                                    char_start INTEGER, char_end INTEGER, page INTEGER, value_json TEXT);
CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, created_at TEXT, mode TEXT,
                                    policy_json TEXT, stats_json TEXT, summary TEXT, checks_json TEXT);
CREATE TABLE IF NOT EXISTS flags(id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, severity TEXT, kind TEXT, category TEXT,
                                 rule TEXT, message TEXT, quote TEXT, page INTEGER, section TEXT, flag_json TEXT);
"""


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def save_analysis(filename, chunks, res, policy):
    now = datetime.now().isoformat(timespec="seconds")
    from doc_parser import full_text
    with closing(_conn()) as c, c:  # `with c` = one transaction
        doc = c.execute("INSERT INTO documents(filename, created_at, pages, full_text) VALUES (?,?,?,?)",
                        (filename, now, max((x.page for x in chunks), default=1), full_text(chunks))).lastrowid
        c.executemany("INSERT INTO chunks(doc_id, chunk_id, page, section, char_start, source, bbox, text) VALUES (?,?,?,?,?,?,?,?)",
                      [(doc, x.chunk_id, x.page, x.section, getattr(x, "char_start", 0), getattr(x, "source", "text"),
                        json.dumps(getattr(x, "bbox", [])), x.text) for x in chunks])
        c.executemany("INSERT INTO findings(doc_id, type, chunk_id, quote, char_start, char_end, page, value_json) VALUES (?,?,?,?,?,?,?,?)",
                      [(doc, f["type"], f["chunk_id"], f["quote"], f.get("char_start", 0), f.get("char_end", 0), f.get("page", 0),
                        json.dumps(f.get("value", {}))) for f in res["findings"]])
        aid = c.execute("INSERT INTO analyses(doc_id, created_at, mode, policy_json, stats_json, summary, checks_json) VALUES (?,?,?,?,?,?,?)",
                        (doc, now, res["stats"]["mode"], json.dumps(policy), json.dumps(res["stats"]), res["summary"],
                         json.dumps(res["checks"]))).lastrowid
        c.executemany("INSERT INTO flags(analysis_id, severity, kind, category, rule, message, quote, page, section, flag_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      [(aid, f.severity, f.kind, f.category, f.rule, f.message, f.quote, f.page, f.section,
                        json.dumps(f.to_dict())) for f in res["flags"]])
    return aid


def list_analyses(search=""):
    sql = """SELECT a.id, d.filename, a.created_at, a.summary,
             (SELECT COUNT(*) FROM flags f WHERE f.analysis_id=a.id AND f.severity='High') AS high_flags
             FROM analyses a JOIN documents d ON d.id=a.doc_id"""
    args = []
    if search.strip():
        like = f"%{search.strip()}%"
        sql += """ WHERE d.filename LIKE ? OR d.full_text LIKE ? OR a.id IN
                   (SELECT analysis_id FROM flags WHERE quote LIKE ? OR rule LIKE ? OR message LIKE ?)"""
        args = [like] * 5
    with closing(_conn()) as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY a.id DESC", args)]


def load_analysis(aid):
    with closing(_conn()) as c:
        a = c.execute("SELECT a.*, d.filename FROM analyses a JOIN documents d ON d.id=a.doc_id WHERE a.id=?", (aid,)).fetchone()
        chunks = [{"chunk_id": r["chunk_id"], "page": r["page"], "section": r["section"], "text": r["text"],
                   "char_start": r["char_start"], "source": r["source"], "bbox": json.loads(r["bbox"])}
                  for r in c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY id", (a["doc_id"],))]
        flags = [json.loads(r["flag_json"]) for r in c.execute("SELECT flag_json FROM flags WHERE analysis_id=? ORDER BY id", (aid,))]
    return {"aid": aid, "name": a["filename"], "created_at": a["created_at"], "summary": a["summary"],
            "policy": json.loads(a["policy_json"]), "stats": json.loads(a["stats_json"]),
            "checks": json.loads(a["checks_json"]), "chunks": chunks, "flags": flags, "data": None}
