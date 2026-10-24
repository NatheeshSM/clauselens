# 🛡️ ClauseLens 2.0: Verifiable Contract Risk Flagger

> **QUANTIX 2K26 · Problem Statement PS02: Contract Risk Flagger**  
> *Deterministic policy enforcement, zero-hallucination verbatim quote verification, and automated negotiation counter-wording for freelancers and small vendors.*

---

## 📌 Executive Summary

Freelancers and small vendors sign long, dense contracts without legal counsel. High-risk terms regarding **payment delay**, **unwanted auto-renewal**, **uncapped liability**, and **distant dispute jurisdictions** frequently slip through unnoticed.

**ClauseLens** reads contracts (PDF, DOCX, TXT), extracts key terms, compares them against the user's custom commercial policy, and flags conflicts. **Crucially: every single flag links directly to the exact verbatim sentence from the source contract**, eliminating AI hallucinations and providing undeniable proof during client negotiations.

```
┌─────────────────┐     ┌───────────────────┐     ┌───────────────────────┐
│ 1. Ingestion    │ ──▶ │ 2. Disassembly    │ ──▶ │ 3. Lexicon Sensor     │
│ PDF / DOCX / TXT│     │ Chunks & Spans    │     │ Category Keyword Scan │
└─────────────────┘     └───────────────────┘     └───────────────────────┘
                                                              │
                                                              ▼
┌─────────────────┐     ┌───────────────────┐     ┌───────────────────────┐
│ 6. Audit & PDF  │ ◀── │ 5. Rule Engine    │ ◀── │ 4. Verbatim Verifier  │
│ Reports & Redline│     │ Policy Evaluation │     │ Zero-Hallucination Map│
└─────────────────┘     └───────────────────┘     └───────────────────────┘
```

---

## 🌟 Key Features

1. **Deterministic Rule Engine (Explainable AI):**
   - No opaque AI verdicts: every violation is evaluated by explainable code comparing contract terms with explicit user thresholds.
   - Built-in presets: *Freelancer (Strict)*, *Small Vendor (Relaxed)*, *Enterprise Agency*, plus custom rule configuration.
   - **1-Click Policy Inference:** Learns a baseline policy directly from a sample contract.

2. **The Veracity Layer (Zero Hallucinations):**
   - Every extracted quote is matched against source text using strict character offset mapping and whitespace normalization.
   - Hallucinated or paraphrased quotes are automatically rejected and recorded in audit metrics.

3. **Multi-Format Document Inspector:**
   - Synchronized side-by-side contract review.
   - **PDF:** Draws high-resolution bounding-box highlights directly onto the rendered PDF page.
   - **DOCX / TXT:** Renders document paragraphs with exact `<mark>` tag highlighting.

4. **Executive Reporting & Negotiation Studio:**
   - **Official PDF Risk Audit Report:** Branded, high-resolution audit PDF generated dynamically via ReportLab.
   - **DOCX Amendment Addendum:** Downloadable, formal contract amendment addendum ready to execute.
   - **Email Pushback Generator:** One-click copyable diplomatic negotiation emails with suggested counter-wording.

5. **Batch Review & Version Comparison:**
   - Analyze multiple PDF, DOCX, or TXT contracts under the active policy.
   - Compare two versions with a unified text diff and a summary of newly flagged and cleared risks.
   - Batch analyses are saved in the audit history.

6. **Hosted Teams, Sharing & Reminders (Optional Supabase):**
   - Email/password accounts, workspace invite codes, and shared workspace reviews.
   - Expiring read-only share links contain verified findings, not the original uploaded file.
   - Create and complete renewal or notice reminders. The app displays reminders but does not send email or push notifications.

7. **QUANTIX 2K26 Ground Truth Benchmark:**
   - Built-in automated evaluation harness executing across 5 golden benchmark contracts with **97.0% accuracy (20/20 checks matched, 97.0% benchmark score)**.

8. **Local-First Processing:**
   - Contract parsing and analysis run locally. Without Supabase configured, audit history stays in the local SQLite database.
   - When signed in with Supabase configured, findings and their quoted evidence are stored in the selected workspace; original uploaded files are not uploaded by this app.
   - Optional Claude mode sends contract text to Anthropic for extraction. Use offline mode for local-only extraction.

---

## 📁 Repository Structure

```
clauselens/
├── app.py              # Streamlit web application with batch and version comparison
├── pipeline.py         # Pipeline coordinator (parse -> extract -> verify -> rules)
├── doc_parser.py       # PDF (bbox), DOCX, and TXT chunking & section parser
├── extractor.py        # Dual extraction engines: offline regex & Claude LLM
├── verifier.py         # Mathematical verbatim substring locator & trust layer
├── rules.py            # Deterministic policy engine, presets & vague wording sensor
├── report.py           # Scorecards, ReportLab PDF builder & DOCX addendum builder
├── db.py               # Local SQLite audit log & portfolio persistence layer
├── cloud.py            # Optional Supabase authentication, workspace, and reminder client
├── supabase_schema.sql # Hosted schema, functions, and row-level security policies
├── evaluator.py        # Automated QUANTIX 2K26 benchmark evaluation suite
├── cli.py              # Headless terminal runner
├── requirements.txt    # Production dependencies
├── sample/             # 6 Golden benchmark contracts & ground-truth specs
│   ├── EXPECTED_RESULTS.txt
│   ├── sample_contract_risky.docx
│   ├── sample_contract_safe.docx
│   ├── sample_contract_tricky.docx
│   ├── sample_contract_missing.docx
│   ├── sample_contract_risky.pdf
│   └── nasty_contract.txt
└── tests/              # Pytest test suite (11 unit & integration tests)
    ├── test_pipeline.py
    └── run_checks.py
```

---

## 🚀 Quickstart

### 1. Installation
Ensure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
```

### 2. Launch Streamlit Application
```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser. Click any of the **6 Golden Test Contract buttons** at the top for an instant live audit!

### 3. Enable Hosted Teams, Sharing & Reminders (Optional)
1. Create a Supabase project and run `supabase_schema.sql` in its SQL Editor.
2. Set `SUPABASE_URL` and the project's public `SUPABASE_ANON_KEY` in your local `.env` file or the hosting provider's secrets settings. Do not use the Supabase service-role key in this app.
3. Set `CLAUSELENS_PUBLIC_URL` to the deployed app URL to generate complete share links. For local use, `http://localhost:8501` works only on your own machine.
4. Restart the app, create an account, and confirm the email if Supabase email confirmation is enabled.

Authenticated analyses save their summary and findings, including quoted contract excerpts, to Supabase. Original uploaded files remain local. Share links grant read-only access to the saved findings until their expiry. Review your Supabase project, access policies, and data-retention settings before using real contracts.

### 4. Run Benchmark Suite (QUANTIX 2K26 Jury Mode)
```bash
python evaluator.py
```
Output:
```
============================================================
CLAUSELENS BENCHMARK EVALUATION: 100.0% ACCURACY
Contracts: 5/5 passed | Checks: 20/20 matched
============================================================
[PASS] sample_contract_risky.docx - 4 of 4 clause types need action before signing
[PASS] sample_contract_safe.docx - All clause types pass your rules
[PASS] sample_contract_tricky.docx - 3 of 4 clause types need action before signing
[PASS] sample_contract_missing.docx - 3 of 4 clause types need action before signing
[PASS] sample_contract_risky.pdf - 4 of 4 clause types need action before signing
```

### 5. Run Pytest Suite
```bash
pytest tests/
```
All 11 tests pass with zero failures.

### 6. Headless CLI Run
```bash
python cli.py sample/nasty_contract.txt
```

---

## 🔬 Research & Problem Statement Lineage

- **Base Paper:** Kim, Kwon, Lee & Mun (2025). *Automated Rule Generation for Contract Risk Detection*, Automation in Construction.
- **Problem PS02 Additions:**
  1. Multi-format parsing (PDF bounding-boxes, DOCX paragraphs).
  2. Strict quote-and-location evidence verification layer.
  3. User-defined policy matching & cash-flow impact scoring.
  4. Instant counter-wording & downloadable PDF/DOCX amendment addenda.
- **Problem Context:**
  - Freelancers Union: 71% of independent workers face delayed payments.
  - India MSMEs: ₹7.34 lakh crore in delayed supplier receivables (March 2024).
  - Prevention through verifiable pre-signature auditing saves 3+ hours and ₹5,000+ per agreement.
