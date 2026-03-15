# Broken

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