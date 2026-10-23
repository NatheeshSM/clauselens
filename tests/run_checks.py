"""Plain-Python checks (no pytest needed):  python tests/run_checks.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from doc_parser import parse_text
import pipeline
from rules import DEFAULT_POLICY
from verifier import verify_quote

TEXT = open(os.path.join(os.path.dirname(__file__), "../sample/nasty_contract.txt"), encoding="utf-8").read()
res = pipeline.analyze(parse_text(TEXT), DEFAULT_POLICY)
hit = {f.rule for f in res["flags"]}
for rule in ["Max payment delay = 30 days", "No auto-renewal", "Liability must be capped",
             "Allowed jurisdictions", "Payment clock start"]:
    assert rule in hit, f"missing flag: {rule}"
assert all(verify_quote(f.quote, TEXT) for f in res["flags"] if f.quote)
orig = pipeline.regex_extract
pipeline.regex_extract = lambda ch: [{"type": "payment", "chunk_id": ch[1].chunk_id, "quote": "made up text",
                                      "value": {"days": 5, "clock_starts": "invoice"}}]
assert pipeline.analyze(parse_text(TEXT), DEFAULT_POLICY)["stats"]["dropped"] == 1
print("ALL CHECKS PASSED")
