"""Risk report: one row per target clause with your rule vs the contract's value,
plus PDF report export and DOCX negotiation addendum generation."""

import html
import io
from datetime import datetime

CATEGORIES = [
    ("payment", "Payment"),
    ("renewal", "Auto-renewal"),
    ("liability", "Liability"),
    ("jurisdiction", "Jurisdiction"),
]


def _rule_text(key, p):
    max_pay = p.get("max_payment_days", 30)
    max_notice = p.get("max_renewal_notice_days", 30)
    allow_renew = p.get("allow_auto_renewal", False)
    req_cap = p.get("require_liability_cap", True)
    allowed_jur = p.get("allowed_jurisdictions", ["India"])
    if isinstance(allowed_jur, str):
        allowed_jur = [j.strip() for j in allowed_jur.split(",") if j.strip()]
    elif not isinstance(allowed_jur, list):
        allowed_jur = [str(allowed_jur)]

    return {
        "payment": f"≤ {max_pay} days",
        "renewal": "No auto-renewal" if not allow_renew else f"Cancel notice ≤ {max_notice} days",
        "liability": "Must be capped" if req_cap else "No requirement",
        "jurisdiction": ", ".join(str(j) for j in allowed_jur),
    }[key]


def _contract_text(key, items):
    if key == "renewal":
        r = [i for i in items if i.get("value", {}).get("renews")]
        if not r:
            return "No auto-renewal clause found"
        n = r[0].get("value", {}).get("notice_days")
        return "Auto-renews" + (f", {n} days' notice" if n else "")
    if not items:
        return "Not found"
    if key == "payment":
        parts = []
        for i in items:
            v = i.get("value", {})
            d = v.get("days")
            if d is not None:
                parts.append(f"{d} days")
            else:
                parts.append("Payment specified")
        return " / ".join(dict.fromkeys(parts)) if parts else "Not found"
    if key == "liability":
        return "Unlimited / uncapped" if any(not i.get("value", {}).get("capped") for i in items) else "Capped"
    return ", ".join(dict.fromkeys(str(i.get("value", {}).get("location", "")) for i in items if i.get("value", {}).get("location"))) or "Not found"


def build_checks(findings, flags, policy):
    rows = []
    for key, label in CATEGORIES:
        items = [f for f in findings if f["type"] == key]

        fl = []
        for f in flags:
            cat = getattr(f, "category", "")
            rule = getattr(f, "rule", "").lower()
            if cat == label:
                fl.append(f)
            elif key == "payment" and ("payment" in rule or "invoice" in rule):
                fl.append(f)
            elif key == "renewal" and ("auto" in rule or "renewal" in rule):
                fl.append(f)
            elif key == "liability" and ("liability" in rule or "indemn" in rule):
                fl.append(f)
            elif key == "jurisdiction" and ("jurisdiction" in rule or "governing law" in rule or "court" in rule):
                fl.append(f)

        # Unique flags for this category
        seen = set()
        uniq_fl = []
        for f in fl:
            k = (getattr(f, "rule", ""), getattr(f, "message", ""))
            if k not in seen:
                seen.add(k)
                uniq_fl.append(f)

        status = "FAIL" if any(getattr(f, "kind", "") in ("CONFLICT", "MISSING") for f in uniq_fl) else "WARN" if uniq_fl else "PASS"
        contract_desc = _contract_text(key, items)
        if not items and any(getattr(f, "kind", "") == "MISSING" for f in uniq_fl):
            contract_desc = "Not found (Missing)"

        rows.append({
            "category": label,
            "rule": _rule_text(key, policy),
            "contract": contract_desc,
            "status": status,
            "flags": len(uniq_fl),
        })
    return rows


def summarize(checks):
    n = sum(c["status"] != "PASS" for c in checks)
    return f"{n} of {len(checks)} clause types need action before signing" if n else "All clause types pass your rules"


# ==============================================================================
# PDF Audit Report Generator (ReportLab)
# ==============================================================================

def generate_pdf_report(run_data):
    """Build a professional, branded PDF risk audit report."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
    )
    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#334155"),
    )
    badge_pass = ParagraphStyle("PassBadge", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.HexColor("#15803d"))
    badge_fail = ParagraphStyle("FailBadge", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.HexColor("#b91c1c"))
    badge_warn = ParagraphStyle("WarnBadge", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.HexColor("#b45309"))

    story = []

    # Header Banner
    story.append(Paragraph("CLAUSELENS · CONTRACT AUDIT REPORT", subtitle_style))
    story.append(Paragraph("Verifiable Legal Risk & Compliance Assessment", title_style))
    story.append(Spacer(1, 4))

    doc_name = run_data.get("name", "Contract Document")
    now_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")
    stats = run_data.get("stats", {})
    summary_text = run_data.get("summary", "Analysis completed.")

    meta_text = (
        f"<b>Target Document:</b> {html.escape(doc_name)} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Audit Date:</b> {now_str} &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"<b>Engine:</b> {stats.get('mode', 'offline')}"
    )
    story.append(Paragraph(meta_text, subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#7c5cff"), spaceBefore=4, spaceAfter=10))

    # Executive Summary Card
    failing = any(c.get("status") != "PASS" for c in run_data.get("checks", []))
    card_bg = colors.HexColor("#fef2f2") if failing else colors.HexColor("#f0fdf4")
    card_border = colors.HexColor("#f87171") if failing else colors.HexColor("#34d399")

    summary_para = Paragraph(
        f"<b>Executive Finding:</b> {html.escape(summary_text)}<br/>"
        f"Cash-flow exposure assessment: <b>{stats.get('cashflow_label', 'Standard')}</b> "
        f"({stats.get('cashflow_days', '—')} payment days). "
        f"Total verified quotes: {stats.get('verified', 0)}/{stats.get('extracted', 0)} (Hallucinations dropped: {stats.get('dropped', 0)}).",
        body_style,
    )
    summary_box = Table([[summary_para]], colWidths=[530])
    summary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), card_bg),
        ("BOX", (0, 0), (-1, -1), 1, card_border),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_box)
    story.append(Spacer(1, 12))

    # Policy Check Matrix Table
    story.append(Paragraph("1. Policy Compliance Matrix", h2_style))
    checks = run_data.get("checks", [])
    matrix_data = [["Clause Category", "Your Rule Policy", "Contract Term", "Status", "Flags"]]
    for ck in checks:
        st_style = badge_fail if ck["status"] == "FAIL" else badge_warn if ck["status"] == "WARN" else badge_pass
        matrix_data.append([
            Paragraph(f"<b>{ck['category']}</b>", body_style),
            Paragraph(ck["rule"], body_style),
            Paragraph(ck["contract"], body_style),
            Paragraph(ck["status"], st_style),
            Paragraph(str(ck.get("flags", 0)), body_style),
        ])

    table = Table(matrix_data, colWidths=[95, 140, 195, 60, 40])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ALIGN", (3, 0), (4, -1), "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))

    # Detailed Findings & Verbatim Source Evidence
    story.append(Paragraph("2. Flagged Risks & Verbatim Contract Evidence", h2_style))
    flags = run_data.get("flags", [])
    if not flags:
        story.append(Paragraph("No risk flags or policy violations detected.", body_style))
    else:
        findings_data = [["Sev.", "Issue & Rule", "Verbatim Quoted Text & Location", "Recommended Fix"]]
        for f in flags:
            sev = f.get("severity") if isinstance(f, dict) else getattr(f, "severity", "Low")
            rule = f.get("rule") if isinstance(f, dict) else getattr(f, "rule", "")
            msg = f.get("message") if isinstance(f, dict) else getattr(f, "message", "")
            quote = f.get("quote") if isinstance(f, dict) else getattr(f, "quote", "")
            sugg = f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", "")
            p = f.get("page") if isinstance(f, dict) else getattr(f, "page", 1)
            sec = f.get("section") if isinstance(f, dict) else getattr(f, "section", "")

            if isinstance(f, dict) and f.get("dismissed"):
                continue
            sugg = (f.get("custom_suggestion") if isinstance(f, dict) else None) or (f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", ""))

            sev_style = badge_fail if sev == "High" else badge_warn if sev == "Medium" else badge_pass
            loc_str = f"Page {p}" + (f", Sec. {sec}" if sec else "")
            quote_cell = Paragraph(f"<i>“{html.escape(quote[:180])}{'...' if len(quote)>180 else ''}”</i><br/><font color='#64748b' size='7.5'>Verified from {loc_str}</font>" if quote else "<i>[Clause Absent from Contract]</i>", body_style)

            findings_data.append([
                Paragraph(sev, sev_style),
                Paragraph(f"<b>{html.escape(rule)}</b><br/><font size='7.5'>{html.escape(msg)}</font>", body_style),
                quote_cell,
                Paragraph(f"<b>Suggested wording:</b><br/>{html.escape(sugg)}", body_style),
            ])

        f_table = Table(findings_data, colWidths=[40, 150, 190, 150])
        f_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(f_table)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=8))
    story.append(Paragraph(
        "<b>Disclaimer:</b> ClauseLens is an automated contract intelligence tool for risk identification and negotiation alignment. "
        "It does not provide formal legal representation or binding legal counsel.",
        subtitle_style,
    ))

    doc.build(story)
    return buf.getvalue()


# ==============================================================================
# DOCX Redline Counter-Proposal & Addendum Generator
# ==============================================================================

def generate_counter_proposal_docx(run_data):
    """Build a formal .docx contract amendment addendum ready to send to the client."""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = docx.Document()

    # Style definitions
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor(0x1e, 0x29, 0x3b)

    # Document Header
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_title.add_run("PROPOSED CONTRACT AMENDMENT & NEGOTIATION ADDENDUM")
    run_t.bold = True
    run_t.font.size = Pt(16)
    run_t.font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)

    doc_name = run_data.get("name", "Original Contract")
    date_str = datetime.now().strftime("%B %d, %Y")
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run(f"Regarding: {doc_name} · Date: {date_str}")
    run_sub.font.size = Pt(10)
    run_sub.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)

    doc.add_paragraph()

    # Preamble
    p_preamble = doc.add_paragraph(
        "This Addendum sets forth proposed clarifications and policy-aligned amendments "
        f"to the agreement referenced above ({doc_name}). The following adjustments are respectfully "
        "submitted to ensure fair commercial balance, clear performance obligations, and mutual protection:"
    )
    p_preamble.runs[0].font.size = Pt(11)

    doc.add_paragraph()

    # Clauses
    flags = run_data.get("flags", [])
    if not flags:
        doc.add_paragraph("All terms in the reviewed agreement align with standard policy. No modifications are requested.")
    else:
        active_flags = [f for f in flags if not (isinstance(f, dict) and f.get("dismissed"))]
        for idx, f in enumerate(active_flags, 1):
            rule = f.get("rule") if isinstance(f, dict) else getattr(f, "rule", "")
            msg = f.get("message") if isinstance(f, dict) else getattr(f, "message", "")
            quote = f.get("quote") if isinstance(f, dict) else getattr(f, "quote", "")
            sugg = (f.get("custom_suggestion") if isinstance(f, dict) else None) or (f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", ""))
            p_num = f.get("page") if isinstance(f, dict) else getattr(f, "page", 1)
            sec = f.get("section") if isinstance(f, dict) else getattr(f, "section", "")

            loc = f"Page {p_num}" + (f", Section {sec}" if sec else "")

            h = doc.add_heading(level=2)
            run_h = h.add_run(f"Item {idx}: {rule}")
            run_h.font.size = Pt(13)
            run_h.font.color.rgb = RGBColor(0x7c, 0x5c, 0xff)

            # Original text
            if quote:
                p_curr = doc.add_paragraph()
                r_c_lbl = p_curr.add_run("Current Agreement Language (" + loc + "): ")
                r_c_lbl.bold = True
                p_curr.add_run(f'“{quote}”')

            # Issue
            p_issue = doc.add_paragraph()
            r_i_lbl = p_issue.add_run("Commercial Concern: ")
            r_i_lbl.bold = True
            p_issue.add_run(msg)

            # Proposed Counter-Wording
            p_prop = doc.add_paragraph()
            r_p_lbl = p_prop.add_run("Proposed Replacement Language: ")
            r_p_lbl.bold = True
            r_p_txt = p_prop.add_run(f'“{sugg}”')
            r_p_txt.italic = True
            r_p_txt.font.color.rgb = RGBColor(0x0f, 0x76, 0x6e)

            doc.add_paragraph()

    # Signature blocks
    doc.add_paragraph("Agreed and accepted in confirmation of the amended terms:")
    doc.add_paragraph()
    sig_table = doc.add_table(rows=3, cols=2)
    sig_table.rows[0].cells[0].text = "CLIENT REPRESENTATIVE:"
    sig_table.rows[0].cells[1].text = "CONTRACTOR / VENDOR:"
    sig_table.rows[1].cells[0].text = "\n\nSignature: __________________________"
    sig_table.rows[1].cells[1].text = "\n\nSignature: __________________________"
    sig_table.rows[2].cells[0].text = "Date: _______________________________"
    sig_table.rows[2].cells[1].text = "Date: _______________________________"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ==============================================================================
# Markdown Counter-Proposal
# ==============================================================================

def generate_counter_proposal_markdown(run_data):
    """Generate a clean markdown email and redline text for quick copying."""
    doc_name = run_data.get("name", "the agreement")
    flags = run_data.get("flags", [])

    lines = [
        f"### Negotiation Counter-Proposal for {doc_name}",
        "",
        "**Email Template to Client:**",
        "> Dear [Client Name],",
        ">",
        f"> Thank you for sending over {doc_name}. I have reviewed the terms and appreciate the opportunity to work together.",
        "> To align the contract with standard commercial operating guidelines, I would like to propose a few minor adjustments:",
        ">",
    ]

    for f in flags:
        if isinstance(f, dict) and f.get("dismissed"):
            continue
        rule = f.get("rule") if isinstance(f, dict) else getattr(f, "rule", "")
        sugg = (f.get("custom_suggestion") if isinstance(f, dict) else None) or (f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", ""))
        lines.append(f"> • **{rule}**: {sugg}")

    lines.extend([
        ">",
        "> Please let me know if these proposed revisions work for your team so we can finalize and execute.",
        ">",
        "> Best regards,",
        "> [Your Name / Company]",
        "",
        "---",
        "### Redline Clause Amendments",
    ])

    idx = 1
    for f in flags:
        if isinstance(f, dict) and f.get("dismissed"):
            continue
        rule = f.get("rule") if isinstance(f, dict) else getattr(f, "rule", "")
        quote = f.get("quote") if isinstance(f, dict) else getattr(f, "quote", "")
        sugg = (f.get("custom_suggestion") if isinstance(f, dict) else None) or (f.get("suggestion") if isinstance(f, dict) else getattr(f, "suggestion", ""))
        lines.append(f"#### {idx}. {rule}")
        if quote:
            lines.append(f"- **Current Language**: *\"{quote}\"*")
        lines.append(f"- **Proposed Amendment**: **\"{sugg}\"**\n")
        idx += 1

    return "\n".join(lines)
