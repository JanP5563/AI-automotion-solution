import streamlit as st
import anthropic
import fitz  # PyMuPDF
import json
import os
from typing import Any, cast
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Safety limits ──────────────────────────────────────────────────────────────
MAX_PDF_CHARS = 8_000
MAX_PDF_MB    = 5
MAX_CALLS     = 10

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FinServe | Credit Assessment",
    page_icon=None,
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  .stApp { background: #0f1117; color: #e8eaf0; }
  h1, h2, h3 { font-family: 'IBM Plex Mono', monospace; }

  .hero {
    background: linear-gradient(135deg, #0f1117 0%, #1a1f2e 100%);
    border: 1px solid #2a3550;
    border-radius: 12px;
    padding: 2.5rem 3rem;
    margin-bottom: 2rem;
  }
  .hero h1 { font-size: 2rem; color: #4fc3f7; margin: 0; letter-spacing: -1px; }
  .hero p  { color: #8899aa; margin: .5rem 0 0; font-size: .95rem; }

  .risk-badge {
    display: inline-block;
    padding: .35rem 1.1rem;
    border-radius: 20px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: .85rem;
    font-weight: 600;
    letter-spacing: .05em;
  }
  .risk-low    { background: #0d2e1f; color: #4caf87; border: 1px solid #4caf87; }
  .risk-medium { background: #2e2200; color: #ffb347; border: 1px solid #ffb347; }
  .risk-high   { background: #2e0d0d; color: #ef5350; border: 1px solid #ef5350; }

  .card {
    background: #151a27;
    border: 1px solid #1e2d45;
    border-radius: 10px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }
  .card h3 { color: #4fc3f7; font-size: 1rem; margin: 0 0 .75rem; }

  .metric-row { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .metric {
    flex: 1; min-width: 120px;
    background: #0f1117;
    border: 1px solid #1e2d45;
    border-radius: 8px;
    padding: 1rem;
    text-align: center;
  }
  .metric .val { font-size: 1.6rem; font-weight: 600; color: #4fc3f7; font-family: 'IBM Plex Mono', monospace; }
  .metric .lbl { font-size: .75rem; color: #8899aa; margin-top: .25rem; }

  .factor-row { display: flex; justify-content: space-between; align-items: center; padding: .5rem 0; border-bottom: 1px solid #1e2d45; }
  .factor-row:last-child { border-bottom: none; }
  .factor-name  { color: #cdd5e0; font-size: .9rem; }
  .factor-score { font-family: 'IBM Plex Mono', monospace; font-size: .85rem; }
  .score-good { color: #4caf87; }
  .score-ok   { color: #ffb347; }
  .score-bad  { color: #ef5350; }

  .stButton > button {
    background: #1565c0; color: #fff; border: none;
    border-radius: 8px; padding: .65rem 2rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: .9rem; letter-spacing: .05em;
    transition: background .2s;
  }
  .stButton > button:hover { background: #1976d2; }

  .stTextInput > div > div > input,
  .stNumberInput > div > div > input,
  .stSelectbox > div > div,
  .stTextArea > div > div > textarea {
    background: #151a27 !important;
    border: 1px solid #1e2d45 !important;
    color: #e8eaf0 !important;
    border-radius: 8px !important;
  }
  div[data-testid="stFileUploader"] {
    background: #151a27;
    border: 2px dashed #1e2d45;
    border-radius: 10px;
    padding: 1rem;
  }
  h1 a, h2 a, h3 a, h4 a,
  [data-testid="stHeadingWithActionElements"] a,
  .stMarkdown a[href^="#"] svg { display: none !important; }
  a[data-testid="stHeaderActionElements"] { display: none !important; }

  /* Spinner fix */
  [data-testid="stSpinner"] > div { display: none !important; }
  [data-testid="stSpinner"]::after {
    content: "";
    display: block;
    width: 24px; height: 24px;
    margin: 8px auto;
    border: 3px solid #1e2d45;
    border-top-color: #4fc3f7;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_client() -> anthropic.Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not key:
        st.error("ANTHROPIC_API_KEY not set. Add it to .env or Streamlit secrets.")
        st.stop()
    return anthropic.Anthropic(api_key=key)


def extract_pdf_text(uploaded_file) -> str:
    raw     = uploaded_file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > MAX_PDF_MB:
        st.error(f"PDF is {size_mb:.1f} MB — maximum allowed is {MAX_PDF_MB} MB.")
        st.stop()
    doc  = fitz.open(stream=raw, filetype="pdf")
    text = "\n".join(str(page.get_text("text")) for page in doc)
    if len(text) > MAX_PDF_CHARS:
        st.info(f"Document is long — only the first {MAX_PDF_CHARS:,} characters will be analysed.")
        text = text[:MAX_PDF_CHARS]
    return text


def safe_json(text: str, agent_name: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1:
        st.error(f"{agent_name} returned unexpected output:\n\n{text[:500]}")
        st.stop()
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        st.error(f"{agent_name} returned invalid JSON: {e}\n\nRaw:\n{text[:500]}")
        st.stop()


# ── AI Pipelines ───────────────────────────────────────────────────────────────

def run_pipeline_business(form_data: dict, doc_text: str, status_box) -> dict:
    """Three-agent pipeline for SME / business clients."""
    client = get_client()
    combined_input = f"""
FORM DATA (filled by credit officer):
{json.dumps(form_data, indent=2, ensure_ascii=False)}

UPLOADED DOCUMENT TEXT:
{doc_text if doc_text else "No document uploaded."}
"""

    def show(msg: str) -> None:
        status_box.markdown(f"""
        <div class="card" style="text-align:center; padding: 2rem 1.5rem;">
          <p style="color:#4fc3f7; font-family:'IBM Plex Mono',monospace; font-size:.95rem;">
            {msg}<br><span style="color:#8899aa; font-size:.8rem;">This takes 15–30 seconds</span>
          </p>
        </div>
        """, unsafe_allow_html=True)

    show("Agent 1/3 — Extracting and validating data…")
    r1 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=(
            "You are a financial data extraction specialist for SME credit applications. "
            "Extract and validate client data. "
            "Return ONLY valid JSON — no markdown, no backticks. Start with { and end with }. "
            "Keys: company_name, loan_amount, loan_purpose, annual_revenue, "
            "years_in_business, credit_history, collateral, "
            "extracted_financials (dict with any figures found in the document), "
            "data_quality (string: Good/Partial/Poor), missing_fields (list)."
        ),
        messages=[{"role": "user", "content": combined_input}],
    )
    extracted = safe_json(cast(Any, r1.content[0]).text, "Agent 1 (extraction)")

    show("Agent 2/3 — Assessing risk…")
    r2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=(
            "You are a senior credit risk analyst specialising in SME lending. "
            "Analyse the business profile and score each risk factor. "
            "Return ONLY valid JSON — no markdown, no backticks. Start with { and end with }. "
            "Keys: overall_risk (Low/Medium/High), overall_score (0-100, higher = less risky), "
            "recommendation (Approve/Reject/Needs More Information), "
            "suggested_terms (dict: interest_rate string, tenor string, conditions list — max 3 conditions), "
            "factors (list of dicts: name, score 0-100, comment — max 20 words per comment) — include: "
            "Revenue Stability, Debt-to-Revenue Ratio, Years in Business, Credit History, "
            "Collateral Quality, Loan Purpose Viability, Cash Flow Adequacy. "
            "summary (2 sentences max)."
        ),
        messages=[{"role": "user", "content": f"Extracted SME profile:\n{json.dumps(extracted, indent=2)}"}],
    )
    risk = safe_json(cast(Any, r2.content[0]).text, "Agent 2 (risk scoring)")

    show("Agent 3/3 — Drafting credit memo…")
    r3 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=(
            "You are a professional credit writer at FinServe. "
            "Write a formal credit committee memo for an SME loan application. "
            "Sections: 1. Executive Summary, 2. Company Profile, "
            "3. Financial Analysis, 4. Risk Assessment, "
            "5. Recommended Terms, 6. Conclusion & Recommendation. "
            "Be concise, factual, and professional. No markdown."
        ),
        messages=[{"role": "user", "content": (
            f"SME Profile:\n{json.dumps(extracted, indent=2)}\n\n"
            f"Risk assessment:\n{json.dumps(risk, indent=2)}"
        )}],
    )
    memo_text = cast(Any, r3.content[0]).text

    return {"extracted": extracted, "risk": risk, "memo": memo_text}


def run_pipeline_individual(form_data: dict, doc_text: str, status_box) -> dict:
    """Three-agent pipeline for individual / retail clients."""
    client = get_client()
    combined_input = f"""
FORM DATA (filled by credit officer):
{json.dumps(form_data, indent=2, ensure_ascii=False)}

UPLOADED DOCUMENT TEXT:
{doc_text if doc_text else "No document uploaded."}
"""

    def show(msg: str) -> None:
        status_box.markdown(f"""
        <div class="card" style="text-align:center; padding: 2rem 1.5rem;">
          <p style="color:#4fc3f7; font-family:'IBM Plex Mono',monospace; font-size:.95rem;">
            {msg}<br><span style="color:#8899aa; font-size:.8rem;">This takes 15–30 seconds</span>
          </p>
        </div>
        """, unsafe_allow_html=True)

    show("Agent 1/3 — Extracting and validating data…")
    r1 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=(
            "You are a financial data extraction specialist for retail credit applications. "
            "Extract and validate applicant data. "
            "Return ONLY valid JSON — no markdown, no backticks. Start with { and end with }. "
            "Keys: full_name, loan_amount, loan_purpose, net_monthly_income, "
            "employment_type, employment_tenure_years, monthly_obligations, "
            "credit_history, collateral, "
            "extracted_financials (dict with any figures found in the document), "
            "data_quality (string: Good/Partial/Poor), missing_fields (list)."
        ),
        messages=[{"role": "user", "content": combined_input}],
    )
    extracted = safe_json(cast(Any, r1.content[0]).text, "Agent 1 (extraction)")

    show("Agent 2/3 — Assessing risk…")
    r2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=(
            "You are a senior credit risk analyst specialising in retail / consumer lending. "
            "Analyse the individual applicant profile and score each risk factor. "
            "Return ONLY valid JSON — no markdown, no backticks. Start with { and end with }. "
            "Keys: overall_risk (Low/Medium/High), overall_score (0-100, higher = less risky), "
            "recommendation (Approve/Reject/Needs More Information), "
            "dti_ratio (debt-to-income ratio as a number, e.g. 32.5), "
            "suggested_terms (dict: interest_rate string, tenor string, max_loan_amount string, conditions list — max 3 conditions), "
            "factors (list of dicts: name, score 0-100, comment — max 20 words per comment) — include: "
            "Income Stability, Debt-to-Income Ratio, Employment Security, Credit History, "
            "Loan-to-Income Ratio, Repayment Capacity, Collateral. "
            "summary (2 sentences max)."
        ),
        messages=[{"role": "user", "content": f"Extracted individual profile:\n{json.dumps(extracted, indent=2)}"}],
    )
    risk = safe_json(cast(Any, r2.content[0]).text, "Agent 2 (risk scoring)")

    show("Agent 3/3 — Drafting credit memo…")
    r3 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=(
            "You are a professional credit writer at FinServe. "
            "Write a formal credit committee memo for a retail / individual loan application. "
            "Sections: 1. Executive Summary, 2. Applicant Profile, "
            "3. Income & Obligations Analysis, 4. Risk Assessment, "
            "5. Recommended Terms, 6. Conclusion & Recommendation. "
            "Be concise, factual, and professional. No markdown."
        ),
        messages=[{"role": "user", "content": (
            f"Individual Profile:\n{json.dumps(extracted, indent=2)}\n\n"
            f"Risk assessment:\n{json.dumps(risk, indent=2)}"
        )}],
    )
    memo_text = cast(Any, r3.content[0]).text

    return {"extracted": extracted, "risk": risk, "memo": memo_text}


# ── PDF builder ────────────────────────────────────────────────────────────────

def build_pdf(result: dict, form_data: dict, client_type: str) -> bytes:

    def s(text) -> str:
        """Sanitize: replace typographic/unicode chars, then encode to latin-1."""
        t = str(text)
        # Common typographic replacements
        replacements = {
            "\u2014": "-", "\u2013": "-",   # em/en dash
            "\u2019": "'", "\u2018": "'",   # smart single quotes
            "\u201c": '"', "\u201d": '"',   # smart double quotes
            "\u2026": "...",                 # ellipsis
            "\u00e2\u0080\u0094": "-",       # UTF-8 mangled em dash
            "\u2022": "*",                   # bullet
            "\u00b7": "*",                   # middle dot
            "\u2212": "-",                   # minus sign
            "\u00a0": " ",                   # non-breaking space
        }
        for old, new in replacements.items():
            t = t.replace(old, new)
        # Strip anything still outside latin-1
        return t.encode("latin-1", errors="replace").decode("latin-1").strip()

    W           = 170
    COL_FACTOR  = 75
    COL_SCORE   = 20
    COL_COMMENT = W - COL_FACTOR - COL_SCORE  # 75

    class PDF(FPDF):
        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(W, 5,
                "FinServe Credit Assessment PoC - AI-assisted draft, subject to human review",
                align="C")

    pdf = PDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Header ─────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(21, 101, 192)
    pdf.cell(W, 9, "FINSERVE FINANCIAL SERVICES", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    memo_label = "SME CREDIT COMMITTEE MEMORANDUM" if client_type == "Business" else "RETAIL CREDIT COMMITTEE MEMORANDUM"
    pdf.cell(W, 7, memo_label, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(W, 5,
        f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}  |  CONFIDENTIAL  |  Client type: {client_type}",
        new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── Risk summary bar ───────────────────────────────────────────────────────
    risk_level = s(result["risk"].get("overall_risk", "N/A"))
    score      = s(result["risk"].get("overall_score", "N/A"))
    rec        = s(result["risk"].get("recommendation", "N/A"))

    pdf.set_fill_color(235, 242, 255)
    pdf.set_draw_color(21, 101, 192)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(21, 101, 192)
    pdf.cell(W, 8,
        f"Risk: {risk_level}   |   Score: {score}/100   |   Recommendation: {rec}",
        border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    if client_type == "Individual":
        dti = s(result["risk"].get("dti_ratio", "N/A"))
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(W, 5, f"Debt-to-Income Ratio: {dti}%", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # ── Memo body ──────────────────────────────────────────────────────────────
    memo = result.get("memo") or "No memo generated."
    # Remove any separator lines (rows of repeated special chars)
    clean_lines = []
    for line in memo.split("\n"):
        line = s(line)
        # Skip lines that are mostly punctuation/separators after sanitizing
        stripped = line.replace("-", "").replace("=", "").replace("*", "").replace("_", "").strip()
        if len(line) > 4 and len(stripped) == 0:
            continue
        clean_lines.append(line)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    for line in clean_lines:
        if not line:
            pdf.ln(2)
            continue
        # Section heading: digit followed by dot (e.g. "1. Executive Summary")
        if len(line) > 2 and line[0].isdigit() and line[1] == ".":
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(21, 101, 192)
            pdf.multi_cell(W, 7, line)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(30, 30, 30)
        else:
            pdf.multi_cell(W, 5, line)

    # ── Risk factors table ─────────────────────────────────────────────────────
    factors = result["risk"].get("factors") or []
    if factors:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(21, 101, 192)
        pdf.cell(W, 7, "Risk Factor Breakdown", new_x="LMARGIN", new_y="NEXT")

        # Header row
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(255, 255, 255)
        pdf.set_fill_color(21, 101, 192)
        pdf.cell(COL_FACTOR,  7, "Factor",  border=0, fill=True)
        pdf.cell(COL_SCORE,   7, "Score",   border=0, fill=True, align="C")
        pdf.cell(COL_COMMENT, 7, "Comment", border=0, fill=True, new_x="LMARGIN", new_y="NEXT")

        # Data rows
        pdf.set_font("Helvetica", "", 9)
        for i, f in enumerate(factors):
            fill = i % 2 == 0
            pdf.set_fill_color(240, 245, 255) if fill else pdf.set_fill_color(255, 255, 255)

            score_raw = f.get("score", 0)
            score_val = int(score_raw) if str(score_raw).lstrip("-").isdigit() else 0
            r_c = 76  if score_val >= 70 else (220 if score_val >= 40 else 200)
            g_c = 175 if score_val >= 70 else (150 if score_val >= 40 else 60)
            b_c = 74  if score_val >= 70 else (50  if score_val >= 40 else 60)

            name    = s(f.get("name", ""))
            comment = s(f.get("comment", ""))

            # Use multi_cell for all three — record y before, restore after
            x_start = pdf.get_x()
            y_start = pdf.get_y()

            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(COL_FACTOR, 5, name, fill=fill, new_x="RIGHT", new_y="TOP")
            pdf.set_xy(x_start + COL_FACTOR, y_start)

            pdf.set_text_color(r_c, g_c, b_c)
            pdf.multi_cell(COL_SCORE, 5, str(score_val), fill=fill, align="C", new_x="RIGHT", new_y="TOP")
            pdf.set_xy(x_start + COL_FACTOR + COL_SCORE, y_start)

            pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(COL_COMMENT, 5, comment, fill=fill, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


# ── UI ─────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hero">
  <h1>FinServe Credit Assessment</h1>
  <p>AI-powered credit analysis · Multi-agent pipeline · Instant credit memo generation</p>
</div>
""", unsafe_allow_html=True)

col_form, col_result = st.columns([1, 1.4], gap="large")

with col_form:
    client_type = st.radio(
        "Client type",
        ["Business", "Individual"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown("### Application Form")

    # ── Business form ──────────────────────────────────────────────────────────
    if client_type == "Business":
        company_name   = st.text_input("Company Name", placeholder="e.g. Acme Sp. z o.o.")
        loan_amount    = st.number_input("Loan Amount (PLN)", min_value=10_000, max_value=10_000_000, value=500_000, step=10_000)
        loan_purpose   = st.selectbox("Purpose of Loan", [
            "Working Capital", "Equipment Purchase", "Real Estate",
            "Business Expansion", "Refinancing", "Other"
        ])
        annual_revenue = st.number_input("Annual Revenue (PLN)", min_value=0, max_value=500_000_000, value=2_000_000, step=50_000)
        years_in_biz   = st.number_input("Years in Business", min_value=0, max_value=100, value=5)
        credit_history = st.selectbox("Credit History", ["Good", "Average", "Poor", "No History"])
        collateral     = st.text_area("Collateral / Security",
            placeholder="e.g. Real estate at ul. Marszalkowska 10, Warsaw — valued at PLN 800,000",
            height=80)

    # ── Individual form ────────────────────────────────────────────────────────
    else:
        full_name           = st.text_input("Full Name", placeholder="e.g. Jan Kowalski")
        loan_amount         = st.number_input("Loan Amount (PLN)", min_value=1_000, max_value=2_000_000, value=50_000, step=1_000)
        loan_purpose        = st.selectbox("Purpose of Loan", [
            "Home Purchase", "Home Renovation", "Car Purchase",
            "Debt Consolidation", "Education", "Consumer Goods", "Other"
        ])
        net_monthly_income  = st.number_input("Net Monthly Income (PLN)", min_value=0, max_value=500_000, value=8_000, step=500)
        employment_type     = st.selectbox("Employment Type", [
            "Permanent Employment", "Fixed-term Contract", "B2B / Self-employed",
            "Civil law contract", "Retired / Pension", "Other"
        ])
        employment_tenure   = st.number_input("Employment Tenure (years)", min_value=0, max_value=50, value=3)
        monthly_obligations = st.number_input(
            "Existing Monthly Obligations (PLN)", min_value=0, max_value=100_000, value=500, step=100,
            help="Total of existing loan repayments, credit card minimums, etc.")
        credit_history      = st.selectbox("Credit History", ["Good", "Average", "Poor", "No History"])
        collateral          = st.text_area("Collateral (optional)",
            placeholder="e.g. Car, property — or leave blank for unsecured loan",
            height=60)

    st.markdown("#### Upload Supporting Document *(optional)*")
    uploaded_file = st.file_uploader(
        "Bank statement, payslip, or financial statement (PDF)", type=["pdf"])

    run = st.button("Run Credit Assessment", use_container_width=True)


# ── Results ────────────────────────────────────────────────────────────────────
with col_result:
    if "call_count" not in st.session_state:
        st.session_state["call_count"] = 0

    if run:
        errors = []

        if client_type == "Business":
            if not company_name or not company_name.strip():
                errors.append("Company Name is required.")
            if loan_amount <= 0:
                errors.append("Loan Amount must be greater than 0.")
            if annual_revenue < 0:
                errors.append("Annual Revenue cannot be negative.")
            if years_in_biz < 0:
                errors.append("Years in Business cannot be negative.")
            if loan_amount > 0 and annual_revenue > 0 and loan_amount > annual_revenue * 20:
                errors.append("Loan amount is more than 20x annual revenue — please verify the figures.")
        else:
            if not full_name or not full_name.strip():
                errors.append("Full Name is required.")
            if loan_amount <= 0:
                errors.append("Loan Amount must be greater than 0.")
            if net_monthly_income <= 0:
                errors.append("Net Monthly Income must be greater than 0.")
            if monthly_obligations < 0:
                errors.append("Monthly Obligations cannot be negative.")
            if monthly_obligations >= net_monthly_income:
                errors.append("Monthly obligations exceed or equal income — please verify the figures.")
            if loan_amount > net_monthly_income * 12 * 10:
                errors.append("Loan amount exceeds 10x annual income — please verify the figures.")

        if errors:
            for e in errors:
                st.warning(e)
            st.stop()

        if st.session_state["call_count"] >= MAX_CALLS:
            st.error(f"Session limit reached ({MAX_CALLS} assessments). Refresh the page to start a new session.")
            st.stop()

        doc_text = extract_pdf_text(uploaded_file) if uploaded_file else ""

        status_box = col_result.empty()
        status_box.markdown("""
        <div class="card" style="text-align:center; padding: 2rem 1.5rem;">
          <p style="color:#4fc3f7; font-family:'IBM Plex Mono',monospace; font-size:.95rem;">
            Running assessment...<br>
            <span style="color:#8899aa; font-size:.8rem;">This takes 15-30 seconds</span>
          </p>
        </div>
        """, unsafe_allow_html=True)

        if client_type == "Business":
            form_data = {
                "client_type":       "Business",
                "company_name":      company_name.strip(),
                "loan_amount":       loan_amount,
                "loan_purpose":      loan_purpose,
                "annual_revenue":    annual_revenue,
                "years_in_business": years_in_biz,
                "credit_history":    credit_history,
                "collateral":        collateral.strip() if collateral else "None provided",
            }
            try:
                result = run_pipeline_business(form_data, doc_text, status_box)
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.stop()
        else:
            form_data = {
                "client_type":             "Individual",
                "full_name":               full_name.strip(),
                "loan_amount":             loan_amount,
                "loan_purpose":            loan_purpose,
                "net_monthly_income":      net_monthly_income,
                "employment_type":         employment_type,
                "employment_tenure_years": employment_tenure,
                "monthly_obligations":     monthly_obligations,
                "credit_history":          credit_history,
                "collateral":              collateral.strip() if collateral else "None provided",
            }
            try:
                result = run_pipeline_individual(form_data, doc_text, status_box)
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.stop()

        st.session_state["result"]      = result
        st.session_state["form_data"]   = form_data
        st.session_state["client_type"] = client_type
        st.session_state["call_count"] += 1
        status_box.empty()

        remaining = MAX_CALLS - st.session_state["call_count"]
        st.caption(f"{remaining} assessment(s) remaining in this session.")

    if "result" in st.session_state:
        result      = st.session_state["result"]
        form_data   = st.session_state["form_data"]
        client_type = st.session_state.get("client_type", "Business")
        risk        = result["risk"]
        extracted   = result["extracted"]

        # Risk badge + recommendation
        rl        = risk.get("overall_risk", "").lower()
        badge_cls = {"low": "risk-low", "medium": "risk-medium", "high": "risk-high"}.get(rl, "risk-medium")
        rec       = risk.get("recommendation", "N/A")
        rec_color = {"Approve": "#4caf87", "Reject": "#ef5350"}.get(rec, "#ffb347")

        st.markdown(f"""
        <div class="card">
          <h3>Assessment Result — {client_type} Client</h3>
          <span class="risk-badge {badge_cls}">{risk.get('overall_risk','N/A')} RISK</span>
          &nbsp;
          <span style="color:{rec_color}; font-family:'IBM Plex Mono',monospace; font-size:.9rem; font-weight:600;">
            -> {rec}
          </span>
        </div>
        """, unsafe_allow_html=True)

        # Key metrics
        score = risk.get("overall_score", 0)
        dq    = extracted.get("data_quality", "N/A")

        if client_type == "Business":
            annual_rev = form_data.get("annual_revenue", 1)
            ratio      = round(form_data["loan_amount"] / max(annual_rev, 1) * 100, 1)
            st.markdown(f"""
            <div class="metric-row">
              <div class="metric"><div class="val">{score}</div><div class="lbl">Risk Score / 100</div></div>
              <div class="metric"><div class="val">{ratio}%</div><div class="lbl">Loan / Revenue</div></div>
              <div class="metric"><div class="val">{dq}</div><div class="lbl">Data Quality</div></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            dti        = risk.get("dti_ratio", "N/A")
            monthly_inc = form_data.get("net_monthly_income", 1)
            lti        = round(form_data["loan_amount"] / max(monthly_inc * 12, 1) * 100, 1)
            st.markdown(f"""
            <div class="metric-row">
              <div class="metric"><div class="val">{score}</div><div class="lbl">Risk Score / 100</div></div>
              <div class="metric"><div class="val">{dti}%</div><div class="lbl">Debt-to-Income</div></div>
              <div class="metric"><div class="val">{lti}%</div><div class="lbl">Loan / Annual Income</div></div>
              <div class="metric"><div class="val">{dq}</div><div class="lbl">Data Quality</div></div>
            </div>
            """, unsafe_allow_html=True)

        # Suggested terms
        terms = risk.get("suggested_terms", {})
        if terms:
            rows_html = f"""
            <div class="factor-row">
              <span class="factor-name">Interest Rate</span>
              <span class="factor-score score-ok">{terms.get('interest_rate','—')}</span>
            </div>
            <div class="factor-row">
              <span class="factor-name">Tenor</span>
              <span class="factor-score score-ok">{terms.get('tenor','—')}</span>
            </div>"""
            if client_type == "Individual" and terms.get("max_loan_amount"):
                rows_html += f"""
            <div class="factor-row">
              <span class="factor-name">Max Loan Amount</span>
              <span class="factor-score score-ok">{terms.get('max_loan_amount','—')}</span>
            </div>"""
            st.markdown(f'<div class="card"><h3>Suggested Terms</h3>{rows_html}</div>', unsafe_allow_html=True)

        # Risk factors
        factors = risk.get("factors", [])
        if factors:
            rows = ""
            for f in factors:
                sv  = f.get("score", 0)
                cls = "score-good" if sv >= 70 else ("score-bad" if sv < 40 else "score-ok")
                rows += f"""
                <div class="factor-row">
                  <span class="factor-name">{f.get('name','')}</span>
                  <span class="factor-score {cls}">{sv}/100 — {f.get('comment','')}</span>
                </div>"""
            st.markdown(f'<div class="card"><h3>Risk Factors</h3>{rows}</div>', unsafe_allow_html=True)

        # Summary
        summary = risk.get("summary", "")
        if summary:
            st.markdown(
                f'<div class="card"><h3>Analyst Summary</h3>'
                f'<p style="color:#cdd5e0;font-size:.9rem;line-height:1.6">{summary}</p></div>',
                unsafe_allow_html=True)

        # Credit memo preview
        with st.expander("Credit Memo Preview", expanded=False):
            st.text(result["memo"])

        # Download PDF
        # pdf_bytes = build_pdf(result, form_data, client_type)
        # client_id = form_data.get("company_name") or form_data.get("full_name", "client")
        # st.download_button(
        #     label="Download Credit Memo (PDF)",
        #     data=pdf_bytes,
        #     file_name=f"credit_memo_{client_id.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
        #     mime="application/pdf",
        #     use_container_width=True,
        # )
    else:
        st.markdown("""
        <div class="card" style="text-align:center; padding: 3rem 1.5rem;">
          <p style="color:#8899aa; font-size:1rem;">Fill in the form and click<br>
          <strong style="color:#4fc3f7">Run Credit Assessment</strong><br>to see results here.</p>
        </div>
        """, unsafe_allow_html=True)