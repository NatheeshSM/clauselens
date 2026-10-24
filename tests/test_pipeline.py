import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from doc_parser import parse_text
from pipeline import analyze
from rules import DEFAULT_POLICY
from verifier import verify_quote

TEXT = open(os.path.join(os.path.dirname(__file__), "../sample/nasty_contract.txt")).read()


def run(policy=DEFAULT_POLICY):
    return analyze(parse_text(TEXT), policy)


def rules_hit(res):
    return {f.rule for f in res["flags"]}


def test_all_core_conflicts_found():
    hit = rules_hit(run())
    assert "Max payment delay = 30 days" in hit
    assert "No auto-renewal" in hit
    assert "Liability must be capped" in hit
    assert "Allowed jurisdictions" in hit
    assert "Payment clock start" in hit


def test_quotes_are_verbatim_and_located():
    for f in run()["flags"]:
        if f.quote:
            assert f.page >= 1 and f.section
            assert verify_quote(f.quote, TEXT)


def test_written_number_parsed():
    pay = [f for f in run()["findings"] if f["type"] == "payment"][0]
    assert pay["value"]["days"] == 60 and pay["value"]["clock_starts"] == "approval"


def test_relaxed_policy_changes_result():
    p = {**DEFAULT_POLICY, "max_payment_days": 90, "allow_auto_renewal": True, "max_renewal_notice_days": 120,
         "allowed_jurisdictions": ["Delaware"]}
    hit = rules_hit(run(p))
    assert "Allowed jurisdictions" not in hit and "No auto-renewal" not in hit


def test_hallucinated_quote_is_dropped(monkeypatch):
    import pipeline
    monkeypatch.setattr(pipeline, "regex_extract", lambda ch: [
        {"type": "payment", "chunk_id": ch[1].chunk_id, "quote": "Client pays within 5 days", "value": {"days": 5, "clock_starts": "invoice"}}])
    res = analyze(parse_text(TEXT), DEFAULT_POLICY)
    assert res["stats"]["dropped"] == 1 and res["stats"]["verified"] == 0


def test_vague_wording_is_flagged():
    text = "The vendor will use reasonable efforts to deliver the work promptly and in a timely manner."
    res = analyze(parse_text(text), DEFAULT_POLICY)
    assert any(f.rule == "Vague wording" for f in res["flags"])


def test_cash_flow_impact_is_reported():
    res = analyze(parse_text("Client shall pay all invoices net sixty (60) days after approval."), DEFAULT_POLICY)
    assert res["stats"]["cashflow_days"] == 60
    assert res["stats"]["cashflow_label"]


def test_analysis_exposes_summary_and_checks():
    res = run()
    assert "summary" in res and "checks" in res
    assert any(c["category"] == "Payment" for c in res["checks"])
    assert isinstance(res["summary"], str) and res["summary"]


def test_infer_policy_from_example():
    from rules import infer_policy_from_example
    findings = [
        {"type": "payment", "value": {"days": 60}},
        {"type": "renewal", "value": {"renews": True, "notice_days": 90}},
        {"type": "liability", "value": {"capped": False}},
        {"type": "jurisdiction", "value": {"location": "Delaware"}},
    ]
    policy = infer_policy_from_example(findings)
    assert policy["max_payment_days"] == 60
    assert policy["allow_auto_renewal"] is True
    assert policy["max_renewal_notice_days"] == 90
    assert policy["require_liability_cap"] is True
    assert policy["allowed_jurisdictions"] == ["Delaware"]


def test_pdf_and_docx_report_generation():
    from report import generate_pdf_report, generate_counter_proposal_docx, generate_counter_proposal_markdown
    res = run()
    run_data = {
        "name": "nasty_contract.txt",
        "flags": [f.to_dict() for f in res["flags"]],
        "checks": res["checks"],
        "summary": res["summary"],
        "stats": res["stats"],
    }
    pdf_bytes = generate_pdf_report(run_data)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")

    docx_bytes = generate_counter_proposal_docx(run_data)
    assert len(docx_bytes) > 1000

    md_text = generate_counter_proposal_markdown(run_data)
    assert "Negotiation Counter-Proposal" in md_text


def test_ground_truth_benchmark_suite():
    from evaluator import run_benchmark
    report = run_benchmark()
    assert report["accuracy_pct"] == 97.0
    assert report["passed_contracts"] == report["total_contracts"] == 5
    assert report["passed_checks"] == report["total_checks"] == 20
