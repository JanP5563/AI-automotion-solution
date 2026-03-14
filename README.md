# FinServe Credit Assessment PoC

An AI-powered credit assessment tool built for the FinServe scenario.  
Turns manual credit analysis (2+ hours) into a 3-minute automated workflow.

## What it does

1. Credit officer fills in a short application form
2. Optionally uploads a PDF document (financial statement, bank statement)
3. A three-agent AI pipeline runs:
   - **Agent 1** — extracts and validates structured data from form + document
   - **Agent 2** — scores credit risk with a factor-by-factor breakdown
   - **Agent 3** — drafts a formal credit committee memo
4. Results are shown in a dashboard + downloadable as a PDF credit memo

## Tech stack

- **Streamlit** — web UI
- **Anthropic Claude API** — three-agent AI pipeline
- **PyMuPDF** — PDF text extraction
- **fpdf2** — PDF credit memo generation

## Run locally

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/finserve-credit-poc.git
cd finserve-credit-poc

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
# Edit .env and paste your Anthropic API key

# 5. Run
streamlit run app.py
```

## Deploy on Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo
4. In **Settings → Secrets**, add:
   ```
   ANTHROPIC_API_KEY = "your_key_here"
   ```
5. Deploy — share the link

## Business impact

| | Manual process | This tool |
|---|---|---|
| Time per credit memo | ~2 hours | ~3 minutes |
| Memos per day (per officer) | 3–4 | 15+ |
| Consistency | Varies by analyst | Standardised |
| Audit trail | Word/email files | Structured JSON + PDF |