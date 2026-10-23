"""Run the pipeline without the UI:  python cli.py path/to/contract.pdf"""
import sys
from doc_parser import parse_file
from pipeline import analyze
from rules import DEFAULT_POLICY

path = sys.argv[1] if len(sys.argv) > 1 else "sample/nasty_contract.txt"
mode = sys.argv[2] if len(sys.argv) > 2 else "offline"
res = analyze(parse_file(path), DEFAULT_POLICY, mode)
print(res["stats"], "\n")
for f in res["flags"]:
    print(f"[{f.severity}] {f.kind}: {f.rule}\n  {f.message}")
    if f.quote:
        print(f"  quote: \"{f.quote}\"\n  location: page {f.page}, section {f.section}")
    print(f"  fix: {f.suggestion}\n")
