"""Streamlit UI. Run: streamlit run app.py"""
from dotenv import load_dotenv
load_dotenv()
import hashlib, html, json, os, tempfile
import streamlit as st
import db
from doc_parser import parse_file
from pipeline import analyze
from rules import DEFAULT_POLICY, PRESETS, infer_policy_from_example

st.set_page_config(page_title="ClauseLens", layout="wide")
BASE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = {"Sample: nasty contract": "nasty_contract.txt"}
ICON = {"FAIL": "🔴", "WARN": "🟠", "PASS": "🟢"}
SEV = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}


def inject_css():
    st.markdown(
        """
        <style>
            :root {
                --bg: #081120;
                --panel: rgba(15, 23, 42, 0.76);
                --panel-strong: rgba(17, 24, 39, 0.95);
                --panel-soft: rgba(30, 41, 59, 0.72);
                --primary: #7c5cff;
                --primary-2: #3dd9b3;
                --warning: #f59e0b;
                --danger: #f87171;
                --success: #34d399;
                --text: #e2e8f0;
                --muted: #93a4c3;
                --border: rgba(148, 163, 184, 0.18);
            }

            html, body, [data-testid="stAppViewContainer"] {
                background: radial-gradient(circle at top left, rgba(124, 92, 255, 0.22), transparent 30%),
                            radial-gradient(circle at bottom right, rgba(61, 217, 179, 0.18), transparent 25%),
                            var(--bg);
                color: var(--text);
            }

            .stApp { background: transparent; }
            [data-testid="stSidebar"] {
                background: rgba(15, 23, 42, 0.78);
                border-right: 1px solid var(--border);
            }
            .block-container {
                padding-top: 1.5rem;
                padding-bottom: 2rem;
                max-width: 1400px;
            }
            .hero {
                background: linear-gradient(135deg, rgba(124, 92, 255, 0.24), rgba(61, 217, 179, 0.12));
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 1.2rem 1.5rem;
                margin-bottom: 1.4rem;
                box-shadow: 0 18px 45px rgba(15, 23, 42, 0.28);
            }
            .hero h1 {
                margin: 0;
                font-size: clamp(2.2rem, 3vw, 3rem);
                line-height: 1.1;
                letter-spacing: -0.04em;
            }
            .subtle {
                color: var(--muted);
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.12em;
                margin-bottom: 0.4rem;
            }
            .metric-card {
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 0.9rem 1rem;
                box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
                height: 100%;
            }
            .metric-label {
                color: var(--muted);
                font-size: 0.74rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }
            .metric-value {
                font-size: 1.5rem;
                font-weight: 700;
                margin-top: 0.35rem;
            }
            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.45rem;
                padding: 0.5rem 0.8rem;
                border-radius: 999px;
                font-weight: 600;
                border: 1px solid rgba(255,255,255,0.08);
                background: rgba(15, 23, 42, 0.4);
            }
            .success { background: rgba(52, 211, 153, 0.14); color: #baf7dc; }
            .warn { background: rgba(245, 158, 11, 0.14); color: #fde68a; }
            .danger { background: rgba(248, 113, 113, 0.14); color: #fecaca; }
            .dashboard-panel {
                background: linear-gradient(180deg, rgba(15, 23, 42, 0.85), rgba(17, 24, 39, 0.75));
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 1rem;
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.22);
            }
            .dashboard-panel .stMetric {
                background: rgba(15, 23, 42, 0.5);
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 0.7rem 0.8rem;
            }
            .stDataFrame, .stTable { border-radius: 16px; overflow: hidden; }
            [data-testid="stFileUploaderDropzone"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-primary"] { border-radius: 12px; }
            .stButton > button {
                background: linear-gradient(135deg, rgba(124, 92, 255, 0.16), rgba(61, 217, 179, 0.15));
                color: var(--text);
                border: 1px solid rgba(167, 139, 250, 0.45);
                border-radius: 12px;
                box-shadow: none;
                transition: 0.2s ease;
                font-weight: 600;
            }
            .stButton > button:hover {
                border-color: rgba(167, 139, 250, 0.9);
                transform: translateY(-1px);
                box-shadow: 0 8px 22px rgba(124, 92, 255, 0.22);
            }
            .stTextInput > div > div > input,
            .stNumberInput input,
            .stSelectbox > div > div > div,
            .stRadio > div {
                background: rgba(15, 23, 42, 0.7);
                color: var(--text);
                border: 1px solid var(--border);
                border-radius: 10px;
            }
            .stContainer { background: transparent; }
            [data-testid="stVerticalBlockBorderWrapper"],
            [data-testid="stVerticalBlock"] > div { border-radius: 14px; }
            .flag-card {
                background: rgba(15, 23, 42, 0.64);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 0.9rem 1rem;
                margin-top: 0.75rem;
            }
            .quote-box {
                background: rgba(124, 92, 255, 0.08);
                border-left: 3px solid rgba(124, 92, 255, 0.9);
                border-radius: 10px;
                padding: 0.75rem 0.9rem;
                color: #dfe7ff;
                margin: 0.6rem 0;
            }
            .feature-card {
                background: rgba(15, 23, 42, 0.75);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 1rem;
                height: 100%;
            }
            .feature-card h3 { margin-top: 0.2rem; }
            .assistant-box {
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 1rem;
            }
            .analysis-shell {
                background: linear-gradient(180deg, rgba(15, 23, 42, 0.78), rgba(15, 23, 42, 0.58));
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 1.1rem;
                box-shadow: 0 18px 40px rgba(15, 23, 42, 0.20);
            }
            .glass-card {
                background: rgba(17, 24, 39, 0.7);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 1rem;
                height: 100%;
            }
            .kpi-strip {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 0.9rem;
                margin-top: 1rem;
                margin-bottom: 1rem;
            }
            .kpi-box {
                background: rgba(15, 23, 42, 0.66);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 1rem;
            }
            .kpi-label {
                color: var(--muted);
                font-size: 0.72rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }
            .kpi-value {
                font-size: 1.8rem;
                font-weight: 700;
                margin-top: 0.35rem;
            }
            .upload-card {
                background: rgba(10, 15, 26, 0.7);
                border: 1px dashed rgba(167, 139, 250, 0.6);
                border-radius: 18px;
                padding: 1rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def policy_form():
    st.header("Your rules")
    preset = st.selectbox("Preset", list(PRESETS))
    p = PRESETS[preset]
    policy = {
        "max_payment_days": st.number_input("Payment limit (days)", 1, 365, p["max_payment_days"]),
        "allow_auto_renewal": st.checkbox("Allow auto-renewal", p["allow_auto_renewal"]),
        "max_renewal_notice_days": st.number_input("Max cancellation notice (days)", 1, 365, p["max_renewal_notice_days"]),
        "require_liability_cap": st.checkbox("Require liability cap", p["require_liability_cap"]),
        "allowed_jurisdictions": [x.strip() for x in st.text_input(
            "Preferred jurisdictions (comma-separated)", ", ".join(p["allowed_jurisdictions"])).split(",") if x.strip()],
    }
    mode = st.radio(
        "Engine",
        ["offline", "llm"],
        format_func=lambda m: "Offline (private, no data leaves this PC)" if m == "offline" else "LLM (needs ANTHROPIC_API_KEY)",
    )
    return policy, mode


def text_view(chunks, f):
    """Document text with the flagged sentence highlighted using its stored character offsets."""
    with st.container(height=620):
        for c in chunks:
            t, s = c["text"], c["char_start"]
            if f and f.get("quote") and s <= f.get("char_start", -1) < s + len(t):
                a, b = f["char_start"] - s, f["char_end"] - s
                body = f"{html.escape(t[:a])}<mark>{html.escape(t[a:b])}</mark>{html.escape(t[b:])}"
            else:
                body = html.escape(t)
            st.markdown(
                f"<small>§{html.escape(c['section'])} · p{c['page']}"
                f"{' · OCR' if c.get('source') == 'ocr' else ''}</small><br>{body}",
                unsafe_allow_html=True,
            )


def pdf_view(data, f):
    import fitz
    page = fitz.open(stream=data, filetype="pdf")[f["page"] - 1]
    rects = page.search_for(f["quote"][:80])
    if not rects and f.get("bbox"):
        rects = [fitz.Rect(*f["bbox"])]
    for r in rects:
        page.draw_rect(r, color=None, fill=(1, 0.85, 0), fill_opacity=0.4, overlay=True)
    st.image(page.get_pixmap(dpi=110).tobytes("png"), caption=f"Page {f['page']}")


def show_report(run, kp):
    flags, checks, stats = run["flags"], run["checks"], run["stats"]
    failing = sum(1 for ck in checks if ck["status"] != "PASS")
    status_class = "danger" if failing else "success"
    status_text = "Review required" if failing else "Within policy"

    st.markdown(
        f"""
        <div class="hero">
            <div class="subtle">Analysis summary</div>
            <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:1rem;">
                <h1>{html.escape(run['summary'])}</h1>
                <div class="status-badge {status_class}">{ICON['FAIL' if failing else 'PASS']} {status_text}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metrics = st.columns(3)
    with metrics[0]:
        st.metric("Flags", len(flags))
    with metrics[1]:
        st.metric("Payment risk", f"{stats.get('cashflow_days', '—')} days" if stats.get('cashflow_days') is not None else "—")
    with metrics[2]:
        st.metric("Verified quotes", f"{stats.get('verified', 0)}/{stats.get('extracted', 0)}")

    st.markdown('<div class="dashboard-panel">', unsafe_allow_html=True)
    cols = st.columns(len(checks) if checks else 1)
    for col, ck in zip(cols, checks):
        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{html.escape(ck['category'])}</div>
                    <div class="metric-value">{ICON[ck['status']]} {html.escape(ck['status'])}</div>
                    <div style="margin-top:0.35rem; color: var(--muted);">Your rule: {html.escape(ck['rule'])}</div>
                    <div style="margin-top:0.35rem;"><strong>Contract says:</strong> {html.escape(ck['contract'])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown('</div>', unsafe_allow_html=True)

    det = ", ".join(f"{k} {v}" for k, v in stats.get("detected", {}).items())
    ocr = f" · OCR used on pages {stats['ocr_pages']}" if stats.get("ocr_pages") else ""
    st.caption(
        f"Engine: {stats['mode']} · Quotes verified {stats['verified']}/{stats['extracted']} "
        f"(dropped {stats['dropped']}) · Clause sentences detected: {det}{ocr}"
    )

    if stats.get("cashflow_days") is not None:
        st.metric("Cash-flow impact", f"{stats['cashflow_days']} days", stats['cashflow_label'])

    sel = min(st.session_state.get(f"sel_{kp}", 0), max(len(flags) - 1, 0))
    left, right = st.columns([1.1, 1.4])
    with left:
        st.subheader("Risk flags")
        if not flags:
            st.success("No conflicts with your rules.")
        for i, f in enumerate(flags):
            severity = f.get("severity") if isinstance(f, dict) else getattr(f, "severity", "Low")
            kind = f.get("kind") if isinstance(f, dict) else getattr(f, "kind", "Issue")
            rule = f.get("rule") if isinstance(f, dict) else getattr(f, "rule", "")
            message = f.get("message") if isinstance(f, dict) else getattr(f, "message", "")
            quote = f.get("quote") if isinstance(f, dict) else getattr(f, "quote", "")
            suggestion = f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", "")
            page = f.get("page") if isinstance(f, dict) else getattr(f, "page", 0)
            section = f.get("section") if isinstance(f, dict) else getattr(f, "section", "")
            char_start = f.get("char_start") if isinstance(f, dict) else getattr(f, "char_start", 0)
            char_end = f.get("char_end") if isinstance(f, dict) else getattr(f, "char_end", 0)
            rule_value = f.get("rule_value") if isinstance(f, dict) else getattr(f, "rule_value", None)
            contract_value = f.get("contract_value") if isinstance(f, dict) else getattr(f, "contract_value", None)
            if rule_value is None:
                rule_value = rule
            if contract_value is None:
                contract_value = "—"

            with st.container():
                st.markdown(
                    f"""
                    <div class="flag-card">
                        <div style="display:flex; justify-content:space-between; gap:0.5rem; align-items:center; flex-wrap:wrap; margin-bottom:0.5rem;">
                            <div><strong>{SEV[severity]} {html.escape(str(kind))}: {html.escape(str(rule))}</strong></div>
                            <div class="status-badge {'danger' if severity == 'High' else 'warn' if severity == 'Medium' else 'success'}">{html.escape(str(severity))}</div>
                        </div>
                        <div>{html.escape(str(message))}</div>
                        <div style="margin-top:0.5rem; color: var(--muted);">Your rule: <code>{html.escape(str(rule_value))}</code> → Contract: <code>{html.escape(str(contract_value))}</code></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if quote:
                    st.markdown(f"<div class='quote-box'>“{html.escape(str(quote))}”</div>", unsafe_allow_html=True)
                    st.caption(
                        f"✔ Verified against source · Page {page} · Section {section} · "
                        f"characters {char_start}–{char_end}"
                    )
                st.markdown(f"*Suggested wording:* {suggestion}")
                if quote and st.button("Show in document", key=f"b_{kp}_{i}"):
                    st.session_state[f"sel_{kp}"] = sel = i
    with right:
        st.subheader("Document")
        f = flags[sel] if flags else None
        if f and f["quote"] and run.get("data") and run["name"].lower().endswith(".pdf"):
            pdf_view(run["data"], f)
        else:
            text_view(run["chunks"], f)


def render_home_page():
    st.markdown(
        """
        <div class="hero">
            <div class="subtle">Legal AI for smarter reviews</div>
            <h1>ClauseLens helps you spot risk before it becomes a negotiation problem.</h1>
            <div style="color: var(--muted); margin-top: 0.6rem; max-width: 940px;">
                Review contracts against your preferred policy, verify quoted text against the source, and surface the issues that matter most to your deal team.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    for col, title, body in [
        (c1, "Policy-aware review", "Set standards for payment terms, renewal clauses, liability caps, and jurisdiction.") ,
        (c2, "Source-verified evidence", "Every risk flag connects to the exact contract wording, not an AI summary alone."),
        (c3, "Negotiation direction", "Turn red flags into concrete suggested wording and follow-up actions."),
    ]:
        with col:
            st.markdown(
                f"""
                <div class="feature-card">
                    <div class="subtle">Feature</div>
                    <h3>{html.escape(title)}</h3>
                    <div style="color: var(--muted);">{html.escape(body)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("What this app catches")
        st.write("• Vague wording that weakens enforceability")
        st.write("• Cash-flow drag from payment schedule risk")
        st.write("• Policy drift such as auto-renewal or unfriendly notice windows")
        st.write("• One-example rule inference to speed up first-pass review")
    with right:
        st.subheader("Fast workflow")
        steps = [
            "Upload a PDF, DOCX, or TXT contract",
            "Choose a policy or infer one from the deal example",
            "Review quotes, rule checks, and suggested wording",
            "Save the report to your local history",
        ]
        for i, step in enumerate(steps, 1):
            st.markdown(f"**{i}.** {step}")

    st.markdown("<br>", unsafe_allow_html=True)
    home_cols = st.columns(2)
    with home_cols[0]:
        if st.button("Open the analyzer"):
            st.session_state["page_nav"] = "Analyze"
            st.rerun()
    with home_cols[1]:
        if st.button("View latest report"):
            st.session_state["page_nav"] = "Reports"
            st.rerun()


def render_dashboard():
    rows = db.list_analyses("")
    latest = st.session_state.get("run")

    if not rows and not latest:
        st.info("No saved analyses yet. Run a review to populate the dashboard.")
        return

    if latest:
        st.subheader("Latest analysis")
        show_report(latest, "latest_dashboard")
        st.markdown("<hr>", unsafe_allow_html=True)

    st.subheader("Portfolio overview")
    total = len(rows)
    high = sum(int(r.get("high_flags", 0) or 0) for r in rows)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Analyses saved", total)
    with c2:
        st.metric("High-risk flags", high)
    with c3:
        st.metric("Latest status", "Live" if latest else "Ready")

    if rows:
        st.dataframe(rows)


def render_reports_page():
    q = st.text_input("Search past analyses (file name, rule, quoted text)")
    rows = db.list_analyses(q)
    if not rows:
        st.info("No saved analyses yet. Analyze a contract first.")
        return
    st.dataframe(rows)
    label = {r["id"]: f"#{r['id']} · {r['filename']} · {r['created_at']}" for r in rows}
    sid = st.selectbox("Open analysis", list(label), format_func=label.get)
    show_report(db.load_analysis(sid), f"report_{sid}")


def build_ai_summary(prompt, run=None):
    if not run:
        return "Upload and analyze a contract first so I can summarize the legal risks and negotiation priorities."

    flags = run.get("flags", [])
    if not flags:
        return "This review is clean on the current policy. The next best move is to verify your preferred risk thresholds and test a tougher draft."

    top_issues = sorted(flags, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x.get("severity", "Low"), 2))[:3]
    top_lines = []
    for item in top_issues:
        top_lines.append(f"- {item.get('kind', 'Issue')}: {item.get('rule', 'Rule')} — {item.get('message', '').split('.')[0]}")

    stats = run.get("stats", {})
    cash = stats.get("cashflow_days")
    cash_line = f"Cash-flow pressure is around {cash} days." if cash is not None else "No clear payment trigger was detected."

    return (
        f"Here is the quick AI brief based on your latest review:\n\n"
        f"Prompt context: {prompt.strip() or 'General review'}\n"
        f"The contract currently has {len(flags)} flagged issues.\n"
        f"{cash_line}\n\n"
        f"Top risks to address first:\n"
        + "\n".join(top_lines)
        + "\n\nRecommended next move: tighten the contract language on the strongest items, confirm any payment timing assumptions, and then re-run the review against your preferred policy before sending the draft."
    )


def render_ai_assistant():
    run = st.session_state.get("run")
    prompt = st.text_area(
        "Ask ClauseLens",
        value="Summarize the biggest risks and tell me what to fix first.",
        height=120,
    )
    if st.button("Generate brief"):
        summary = build_ai_summary(prompt, run)
        st.markdown(f"<div class='assistant-box'>{html.escape(summary).replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)

    if run:
        st.caption("Current record: " + run.get("name", "Untitled review"))
        d = run.get("stats", {})
        st.write(f"Flags: {len(run.get('flags', []))} | Verified quotes: {d.get('verified', 0)}/{d.get('extracted', 0)} | Payment risk: {d.get('cashflow_days', '—')} days")
    else:
        st.info("Analyze a contract first to unlock the assistant summary.")


def render_analysis_page():
    policy = None
    mode = None
    with st.sidebar:
        policy, mode = policy_form()

    st.markdown(
        """
        <div class="hero">
            <div class="subtle">Contract review workspace</div>
            <h1>ClauseLens: smarter legal risk review</h1>
            <div style="color: var(--muted); margin-top: 0.35rem;">Upload a document, define the rules, and surface the issues that matter most before the deal moves forward.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="analysis-shell">', unsafe_allow_html=True)
    cols = st.columns([1.25, 0.75])
    with cols[0]:
        st.markdown('<div class="upload-card">', unsafe_allow_html=True)
        up = st.file_uploader("Upload contract", type=["pdf", "docx", "txt"], help="PDF, DOCX, or TXT files only")
        if up and st.session_state.get("up_id") != (up.name, up.size):
            st.session_state["up_id"] = (up.name, up.size)
            st.session_state["src"] = ("upload", up.name)
        st.caption("Source-verified review with policy enforcement and clause-level evidence.")
        st.markdown('</div>', unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            """
            <div class="glass-card">
                <div class="subtle">AI-ready workflow</div>
                <div style="font-size:1.05rem; font-weight:600;">Review, verify, and negotiate faster.</div>
                <ul style="color: var(--muted); margin-bottom:0; padding-left:1.1rem;">
                    <li>Vague wording detection</li>
                    <li>Cash-flow impact scoring</li>
                    <li>Example-driven policy inference</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    src = st.session_state.get("src")
    if src and src[0] == "upload" and not up:
        src = None
    if not src:
        st.info("Upload a contract to begin the review.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    if src[0] == "sample":
        sample_name = src[1]
        sample_path = os.path.join(BASE, "sample", sample_name)
        if not os.path.exists(sample_path):
            st.warning("That sample file is not available in this workspace. Please upload a contract instead.")
            st.session_state["src"] = None
            st.markdown('</div>', unsafe_allow_html=True)
            return
        name, data = sample_name, open(sample_path, "rb").read()
    else:
        name, data = up.name, up.getvalue()

    kpi = st.columns(3)
    with kpi[0]:
        st.markdown('<div class="kpi-box"><div class="kpi-label">Document</div><div class="kpi-value">'+html.escape(name)[:18]+'</div></div>', unsafe_allow_html=True)
    with kpi[1]:
        st.markdown('<div class="kpi-box"><div class="kpi-label">Review mode</div><div class="kpi-value">'+(mode or 'offline')+'</div></div>', unsafe_allow_html=True)
    with kpi[2]:
        st.markdown('<div class="kpi-box"><div class="kpi-label">Policy</div><div class="kpi-value">'+str(len((policy or {}).get('allowed_jurisdictions', [])) or 3)+'</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Infer policy from this contract", key="infer_policy_btn", use_container_width=True):
        tmp = os.path.join(tempfile.mkdtemp(), name)
        with open(tmp, "wb") as f:
            f.write(data)
        chunks = parse_file(tmp)
        inferred = infer_policy_from_example(analyze(chunks, DEFAULT_POLICY if policy is None else policy, mode or "offline")["findings"])
        st.session_state["draft_policy"] = inferred
        st.success("Policy inferred from the contract example. Review and tweak if needed.")

    active_policy = st.session_state.get("draft_policy", policy)
    key = hashlib.md5(data + json.dumps(active_policy, sort_keys=True).encode() + (mode or "offline").encode()).hexdigest()
    if st.session_state.get("run_key") != key:
        tmp = os.path.join(tempfile.mkdtemp(), name)
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            chunks = parse_file(tmp)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            st.stop()
        with st.spinner("Parsing, extracting, verifying..."):
            res = analyze(chunks, active_policy, mode or "offline")
            aid = db.save_analysis(name, chunks, res, active_policy)
        st.session_state.update(
            run_key=key,
            sel_cur=0,
            run={
                "aid": aid,
                "name": name,
                "data": data,
                "chunks": [c.to_dict() for c in chunks],
                "flags": [f.to_dict() for f in res["flags"]],
                "checks": res["checks"],
                "summary": res["summary"],
                "stats": res["stats"],
            },
        )

    st.caption(f"Saved to history as analysis #{st.session_state['run']['aid']}")
    show_report(st.session_state["run"], "cur")
    st.markdown('</div>', unsafe_allow_html=True)


inject_css()
if "page_nav" not in st.session_state:
    st.session_state["page_nav"] = "Home"

with st.sidebar:
    st.markdown("<div class='subtle'>Workspace</div>", unsafe_allow_html=True)
    st.session_state["page_nav"] = st.radio("Navigation", ["Home", "Dashboard", "Analyze", "Reports", "AI Assistant"], index=["Home", "Dashboard", "Analyze", "Reports", "AI Assistant"].index(st.session_state["page_nav"]))

page = st.session_state["page_nav"]
if page == "Home":
    render_home_page()
elif page == "Dashboard":
    render_dashboard()
elif page == "Analyze":
    render_analysis_page()
elif page == "Reports":
    render_reports_page()
else:
    render_ai_assistant()
