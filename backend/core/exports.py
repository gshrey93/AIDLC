"""Report exports: full PDF, redacted PDF, CSV, draft zip, VS Code handoff zip."""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

FULL_PDF_MAX_PAGES = 40
REDACTED_PDF_MAX_PAGES = 25

BRAND = colors.HexColor("#0F766E")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
LINE = colors.HexColor("#CBD5E1")
BG = colors.HexColor("#F1F5F9")

VERDICT_COLORS = {
    "Lean": colors.HexColor("#047857"),
    "Watchlist": colors.HexColor("#B45309"),
    "Wasteful": colors.HexColor("#C2410C"),
    "Critical": colors.HexColor("#B91C1C"),
}


# ------------------------------------------------------------- redaction
def build_alias_map(paths: list) -> dict:
    dir_alias: dict = {}
    alias: dict = {}
    for i, path in enumerate(sorted(set(paths)), start=1):
        norm = path.replace("\\", "/")
        directory = os.path.dirname(norm)
        ext = os.path.splitext(norm)[1] or ""
        if directory:
            if directory not in dir_alias:
                dir_alias[directory] = f"dir-{len(dir_alias) + 1:02d}"
            alias[norm] = f"{dir_alias[directory]}/file-{i:03d}{ext}"
        else:
            alias[norm] = f"file-{i:03d}{ext}"
    return alias


def redact_text(text: str, alias: dict) -> str:
    if not text:
        return ""
    out = re.sub(r"\|\s*Sample:\s*\".*?\"", "", text, flags=re.S)
    out = re.sub(r"Sample:\s*\".*?\"", "", out, flags=re.S)
    for path in sorted(alias.keys(), key=len, reverse=True):
        if path in out:
            out = out.replace(path, alias[path])
    # Also alias bare file names and any shortened '...suffix' forms.
    for path, al in sorted(alias.items(), key=lambda kv: len(kv[0]), reverse=True):
        base = os.path.basename(path)
        if base and base in out:
            out = out.replace(base, os.path.basename(al))
    out = re.sub(r"\.\.\.[^\s,;]+", "[path hidden]", out)
    return out.strip()


# ------------------------------------------------------------------- CSV
CSV_COLUMNS = [
    "issue_id", "scan_id", "repo_name", "severity", "category", "title", "description",
    "evidence", "impacted_file_count", "impacted_files", "estimated_token_waste",
    "estimated_credit_waste", "estimated_dollar_waste", "impact", "effort",
    "formula", "recommendation",
]


def issues_csv(payload: dict, redacted: bool = False) -> str:
    scan = payload["scan"]
    alias = build_alias_map([f["path"] for f in payload.get("files", [])]) if redacted else {}
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for iss in payload.get("issues", []):
        files = iss.get("impacted_files") or []
        if redacted:
            files = [alias.get(p, "[path hidden]") for p in files]
        writer.writerow({
            "issue_id": iss.get("id"),
            "scan_id": scan.get("id"),
            "repo_name": scan.get("repo_name"),
            "severity": iss.get("severity"),
            "category": iss.get("category"),
            "title": redact_text(iss.get("title", ""), alias) if redacted else iss.get("title"),
            "description": iss.get("description"),
            "evidence": redact_text(iss.get("evidence", ""), alias) if redacted else iss.get("evidence"),
            "impacted_file_count": iss.get("impacted_file_count"),
            "impacted_files": "; ".join(files[:25]),
            "estimated_token_waste": iss.get("estimated_token_waste"),
            "estimated_credit_waste": iss.get("estimated_credit_waste"),
            "estimated_dollar_waste": iss.get("estimated_dollar_waste"),
            "impact": iss.get("impact"),
            "effort": iss.get("effort"),
            "formula": iss.get("formula"),
            "recommendation": iss.get("recommendation"),
        })
    return buf.getvalue()


# ------------------------------------------------------------------- PDF
def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("bgH1", parent=ss["Title"], fontSize=22, leading=26, textColor=INK, spaceAfter=4),
        "sub": ParagraphStyle("bgSub", parent=ss["Normal"], fontSize=10, leading=14, textColor=MUTED),
        "h2": ParagraphStyle("bgH2", parent=ss["Heading2"], fontSize=14, leading=18, textColor=BRAND, spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("bgH3", parent=ss["Heading3"], fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("bgBody", parent=ss["Normal"], fontSize=9, leading=12.5, textColor=INK, alignment=TA_LEFT),
        "small": ParagraphStyle("bgSmall", parent=ss["Normal"], fontSize=7.5, leading=10, textColor=INK),
        "cell": ParagraphStyle("bgCell", parent=ss["Normal"], fontSize=7.2, leading=9.2, textColor=INK),
        "cellb": ParagraphStyle("bgCellB", parent=ss["Normal"], fontSize=7.2, leading=9.2, textColor=colors.white),
        "mono": ParagraphStyle("bgMono", parent=ss["Normal"], fontName="Courier", fontSize=6.8, leading=8.6, textColor=INK),
    }


def _esc(text) -> str:
    s = "" if text is None else str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _kv_table(rows, st, col1=58 * mm, col2=104 * mm):
    data = [[Paragraph(f"<b>{_esc(k)}</b>", st["cell"]), Paragraph(_esc(v), st["cell"])] for k, v in rows]
    t = Table(data, colWidths=[col1, col2])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (0, -1), BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _grid_table(header, rows, widths, st):
    data = [[Paragraph(f"<b>{_esc(h)}</b>", st["cellb"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_esc(c), st["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _fmt_money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _fmt_int(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "0"


def _header_footer(canvas, doc, title):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, A4[1] - 11 * mm, title)
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 11 * mm, "Bloat Guardian")
    canvas.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
    canvas.drawString(18 * mm, 9 * mm, datetime.now(timezone.utc).strftime("Generated %Y-%m-%d %H:%M UTC"))
    canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _build(story, title) -> tuple:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=title, author="Bloat Guardian",
    )
    doc.build(
        story,
        onFirstPage=lambda c, d: _header_footer(c, d, title),
        onLaterPages=lambda c, d: _header_footer(c, d, title),
    )
    return buf.getvalue(), doc.page


def _score_banner(payload, st):
    scan = payload["scan"]
    verdict = scan.get("verdict") or scan.get("status") or "No verdict"
    colour = VERDICT_COLORS.get(verdict, MUTED)
    badge = verdict + ("  +  PartialScan" if scan.get("partial_scan") else "")
    data = [[
        Paragraph(f"<font size=30 color='white'><b>{_esc(scan.get('overall_score', 0))}</b></font>"
                  f"<font size=9 color='white'> / 100</font>", st["cell"]),
        Paragraph(f"<font size=13 color='white'><b>{_esc(badge)}</b></font><br/>"
                  f"<font size=8 color='white'>Weighted efficiency verdict</font>", st["cell"]),
    ]]
    t = Table(data, colWidths=[42 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colour),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _common_sections(payload, st, redacted, alias, issue_limit, file_limit):
    scan = payload["scan"]
    det = payload.get("detections", {}) or {}
    assumptions = payload.get("assumptions", {}) or {}
    story = []

    story.append(Paragraph("Agentic Efficiency Report" + (" (Redacted)" if redacted else ""), st["h1"]))
    story.append(Paragraph(
        f"{_esc(scan.get('repo_name'))}"
        + (f" &nbsp;·&nbsp; branch {_esc(scan.get('branch'))}" if scan.get("branch") else "")
        + f" &nbsp;·&nbsp; {_esc(scan.get('source_type'))} import &nbsp;·&nbsp; scan {_esc(scan.get('id'))}",
        st["sub"]))
    story.append(Spacer(1, 8))
    story.append(_score_banner(payload, st))
    story.append(Spacer(1, 10))

    if redacted:
        story.append(Paragraph("Redaction rules applied", st["h2"]))
        story.append(Paragraph(
            "File contents and code samples are removed. Exact file and folder names are replaced with "
            "path aliases such as dir-01/file-007.md. Counts, scores, category findings, penalties and "
            "savings estimates are preserved exactly as in the full report.", st["body"]))
        story.append(Spacer(1, 6))

    story.append(Paragraph("What we found", st["h2"]))
    savings_rows = [
        ("Overall efficiency score", f"{scan.get('overall_score', 0)} / 100"),
        ("Verdict", (scan.get("verdict") or scan.get("status") or "-")
            + ("  (PartialScan)" if scan.get("partial_scan") else "")),
        ("Files discovered", _fmt_int(scan.get("total_files"))),
        ("Files parsed", _fmt_int(scan.get("parsed_files"))),
        ("Files skipped", _fmt_int(scan.get("skipped_files"))),
        ("Tokens analysed", _fmt_int(scan.get("analyzed_tokens"))),
        ("Estimated monthly token waste", _fmt_int(scan.get("estimated_monthly_token_waste"))),
        ("Estimated monthly credit waste", f"{scan.get('estimated_monthly_credit_waste', 0):,.2f} credits"),
        ("Estimated monthly dollar waste", _fmt_money(scan.get("estimated_monthly_dollar_waste"))),
        ("Savings range (low / high)",
         f"{_fmt_money(scan.get('estimated_savings_low'))}  -  {_fmt_money(scan.get('estimated_savings_high'))}"),
        ("Duplicate clusters found", _fmt_int(det.get("duplicate_clusters_found"))),
        ("Oversized context files", _fmt_int(det.get("oversized_context_files"))),
        ("Overlapping agent groups", _fmt_int(det.get("overlapping_agent_groups"))),
        ("Review stages inferred", _fmt_int(det.get("review_stages_inferred"))),
        ("Agent-like files detected", _fmt_int(det.get("agent_like_files"))),
    ]
    story.append(_kv_table(savings_rows, st))

    story.append(Paragraph("Category scores", st["h2"]))
    rows = [
        (c.get("label") or c.get("category"), f"{c.get('score')}/100",
         f"{int(round(float(c.get('weight', 0)) * 100))}%", f"-{c.get('penalty_points', 0)}",
         redact_text(c.get("summary", ""), alias) if redacted else c.get("summary", ""))
        for c in payload.get("category_scores", [])
    ]
    story.append(_grid_table(
        ["Category", "Score", "Weight", "Penalty", "What this means"],
        rows, [34 * mm, 14 * mm, 14 * mm, 16 * mm, 84 * mm], st))

    drivers = payload.get("top_drivers", [])
    story.append(Paragraph("Top 5 waste drivers, in plain language", st["h2"]))
    if drivers:
        for d in drivers[:5]:
            title = redact_text(d.get("title", ""), alias) if redacted else d.get("title", "")
            story.append(KeepTogether([
                Paragraph(f"{d.get('rank')}. {_esc(title)}", st["h3"]),
                Paragraph(_esc(d.get("plain_language", "")), st["body"]),
                Paragraph(
                    f"<font color='#475569'>{_esc(d.get('category'))} · "
                    f"{_fmt_int(d.get('estimated_token_waste'))} tokens/month · "
                    f"{d.get('estimated_credit_waste', 0):,.2f} credits · "
                    f"{_fmt_money(d.get('estimated_dollar_waste'))}</font>", st["small"]),
                Spacer(1, 4),
            ]))
    else:
        story.append(Paragraph("No waste drivers were detected for this scan.", st["body"]))

    story.append(Paragraph("Savings assumptions and formulas", st["h2"]))
    for note in assumptions.get("notes", []):
        story.append(Paragraph("• " + _esc(note), st["body"]))
    story.append(Spacer(1, 4))
    story.append(_grid_table(
        ["Setting", "Value"],
        [
            ("Tokens per report credit", _fmt_int(assumptions.get("tokens_per_report_credit"))),
            ("Vendor credits per dollar", str(assumptions.get("vendor_credits_per_dollar"))),
            ("Input tokens per vendor credit", _fmt_int(assumptions.get("input_tokens_per_vendor_credit"))),
            ("Output tokens per vendor credit", _fmt_int(assumptions.get("output_tokens_per_vendor_credit"))),
            ("$ per 1M input tokens", _fmt_money(assumptions.get("input_dollars_per_million"))),
            ("$ per 1M output tokens", _fmt_money(assumptions.get("output_dollars_per_million"))),
            ("Agent runs per month", _fmt_int(assumptions.get("agent_runs_per_month"))),
            ("Output token share of waste", f"{float(assumptions.get('output_token_share', 0)) * 100:.0f}%"),
            ("Aggregate variance", f"+/-{float(assumptions.get('variance_pct', 0)) * 100:.0f}%"),
            ("Rates last refreshed", str(assumptions.get("rates_last_refreshed") or "never")),
            ("Rates source", str(assumptions.get("rates_source") or "-")),
        ], [60 * mm, 102 * mm], st))

    ledger = payload.get("penalty_ledger", [])
    if ledger:
        story.append(Paragraph("How the score was calculated", st["h2"]))
        story.append(_grid_table(
            ["Penalty rule", "Hits", "Points each", "Cap", "Applied", "Category"],
            [(r["rule"], _fmt_int(r["hits"]), _fmt_int(r["points_each"]), _fmt_int(r["cap"]),
              f"-{r['applied']}", r["category"]) for r in ledger],
            [72 * mm, 12 * mm, 18 * mm, 12 * mm, 16 * mm, 32 * mm], st))

    issues = payload.get("issues", [])
    story.append(PageBreak())
    story.append(Paragraph(f"Findings ({len(issues)} issues)", st["h2"]))
    if issues:
        rows = []
        for iss in issues[:issue_limit]:
            files = iss.get("impacted_files") or []
            if redacted:
                shown = ", ".join(alias.get(p, "[hidden]") for p in files[:4])
            else:
                shown = ", ".join(files[:4])
            if len(files) > 4:
                shown += f" (+{len(files) - 4} more)"
            rows.append((
                iss.get("id"), iss.get("severity"), iss.get("category"),
                redact_text(iss.get("title", ""), alias) if redacted else iss.get("title", ""),
                shown or "-",
                _fmt_int(iss.get("estimated_token_waste")),
                f"{iss.get('estimated_credit_waste', 0):,.2f}",
                _fmt_money(iss.get("estimated_dollar_waste")),
            ))
        story.append(_grid_table(
            ["Issue", "Severity", "Category", "Title", "Impacted files", "Tokens/mo", "Credits/mo", "$/mo"],
            rows, [23 * mm, 14 * mm, 22 * mm, 40 * mm, 33 * mm, 12 * mm, 10 * mm, 8 * mm], st))
        if len(issues) > issue_limit:
            story.append(Paragraph(
                f"Showing the {issue_limit} highest impact issues of {len(issues)}. "
                "The CSV export contains every issue.", st["small"]))
    else:
        story.append(Paragraph("No issues were recorded for this scan.", st["body"]))

    if not redacted and issues:
        story.append(Paragraph("Evidence detail", st["h2"]))
        for iss in issues[:min(issue_limit, 40)]:
            story.append(KeepTogether([
                Paragraph(f"{_esc(iss.get('id'))} — {_esc(iss.get('title'))}", st["h3"]),
                Paragraph(_esc(iss.get("description")), st["body"]),
                Paragraph(f"<b>Evidence:</b> {_esc(iss.get('evidence'))}", st["small"]),
                Paragraph(f"<b>Formula:</b> {_esc(iss.get('formula'))}", st["small"]),
                Paragraph(f"<b>Recommendation:</b> {_esc(iss.get('recommendation'))} "
                          f"(impact {_esc(iss.get('impact'))}, effort {_esc(iss.get('effort'))})", st["small"]),
                Spacer(1, 4),
            ]))

    actions = payload.get("recommended_actions", [])
    if actions:
        story.append(Paragraph("Recommended actions, ranked by impact then effort", st["h2"]))
        story.append(_grid_table(
            ["#", "Action", "Category", "Impact", "Effort", "Tokens/mo saved", "$/mo saved"],
            [(str(i + 1), redact_text(a["action"], alias) if redacted else a["action"], a["category"],
              a["impact"], a["effort"], _fmt_int(a["estimated_token_reduction"]),
              _fmt_money(a["estimated_dollar_savings"]))
             for i, a in enumerate(actions)],
            [8 * mm, 62 * mm, 30 * mm, 15 * mm, 14 * mm, 20 * mm, 13 * mm], st))

    story.append(PageBreak())
    story.append(Paragraph("File inventory by category", st["h2"]))
    inv = payload.get("inventory_summary") or {}
    if inv:
        story.append(_grid_table(
            ["Group", "Files", "Parsed", "Skipped", "Tokens"],
            [(g, _fmt_int(v.get("count")), _fmt_int(v.get("parsed")), _fmt_int(v.get("skipped")),
              _fmt_int(v.get("tokens"))) for g, v in inv.items()],
            [56 * mm, 22 * mm, 22 * mm, 24 * mm, 38 * mm], st))

    files = payload.get("files", [])
    if files:
        shown = sorted(files, key=lambda f: -(f.get("estimated_tokens") or 0))[:file_limit]
        story.append(Paragraph(f"Largest {len(shown)} files by estimated tokens", st["h3"]))
        story.append(_grid_table(
            ["Path", "Category", "Status", "Lines", "Size (KB)", "Tokens", "Dup group"],
            [((alias.get(f["path"], "[hidden]") if redacted else f["path"]),
              f.get("category"), f.get("parse_status"), _fmt_int(f.get("line_count")),
              f"{(f.get('size_bytes') or 0) / 1024:.1f}", _fmt_int(f.get("estimated_tokens")),
              f.get("similarity_group") or "-") for f in shown],
            [62 * mm, 22 * mm, 24 * mm, 13 * mm, 16 * mm, 16 * mm, 19 * mm], st))

    skipped = [f for f in files if f.get("parse_status") != "Scanned"]
    story.append(Paragraph("Skipped files and warnings", st["h2"]))
    for w in payload.get("warnings", []) or []:
        story.append(Paragraph("• " + _esc(w), st["body"]))
    if skipped:
        counts: dict = {}
        for f in skipped:
            counts[f.get("parse_status")] = counts.get(f.get("parse_status"), 0) + 1
        story.append(Paragraph(
            "Skipped by reason: " + ", ".join(f"{k} = {v}" for k, v in sorted(counts.items())), st["body"]))
        story.append(Spacer(1, 4))
        story.append(_grid_table(
            ["Path", "Status", "Size (KB)", "Reason"],
            [((alias.get(f["path"], "[hidden]") if redacted else f["path"]), f.get("parse_status"),
              f"{(f.get('size_bytes') or 0) / 1024:.1f}",
              redact_text(f.get("skip_reason") or "", alias) if redacted else (f.get("skip_reason") or ""))
             for f in skipped[:min(file_limit, 200)]],
            [58 * mm, 26 * mm, 18 * mm, 60 * mm], st))
        if len(skipped) > min(file_limit, 200):
            story.append(Paragraph(f"...and {len(skipped) - min(file_limit, 200)} more skipped files.", st["small"]))
    else:
        story.append(Paragraph("Every discovered file was parsed successfully.", st["body"]))

    return story


def full_pdf(payload: dict) -> bytes:
    st = _styles()
    issue_limit, file_limit, draft_limit = 200, 120, 25
    for _ in range(5):
        story = _common_sections(payload, st, False, {}, issue_limit, file_limit)
        drafts = payload.get("drafts", [])
        if drafts:
            story.append(PageBreak())
            story.append(Paragraph("Draft replacement files", st["h2"]))
            story.append(Paragraph(
                "Each draft is a refined version of a file that already exists in your repository. "
                "Filenames carry an -optimised suffix so nothing is overwritten.", st["body"]))
            for d in drafts[:draft_limit]:
                story.append(Paragraph(
                    f"{_esc(d.get('target_filename'))} "
                    f"<font size=7 color='#475569'>(from {_esc(d.get('source_path'))}, "
                    f"{_fmt_int(d.get('original_tokens'))} -> {_fmt_int(d.get('draft_tokens'))} tokens, "
                    f"-{d.get('reduction_pct', 0)}%)</font>", st["h3"]))
                body = (d.get("draft_content") or "")[:6000]
                for line in body.splitlines() or [""]:
                    story.append(Paragraph(_esc(line) or "&nbsp;", st["mono"]))
                story.append(Spacer(1, 6))
        data, pages = _build(story, f"Full efficiency report · {payload['scan'].get('id')}")
        if pages <= FULL_PDF_MAX_PAGES:
            return data
        issue_limit = max(20, issue_limit // 2)
        file_limit = max(20, file_limit // 2)
        draft_limit = max(1, draft_limit // 2)
    return data


def redacted_pdf(payload: dict) -> bytes:
    st = _styles()
    alias = build_alias_map([f["path"] for f in payload.get("files", [])])
    issue_limit, file_limit = 120, 60
    for _ in range(5):
        story = _common_sections(payload, st, True, alias, issue_limit, file_limit)
        drafts = payload.get("drafts", [])
        if drafts:
            story.append(Paragraph("Draft replacement files", st["h2"]))
            story.append(Paragraph(
                f"{len(drafts)} draft replacement files were generated. Draft contents are removed from "
                "the redacted report. Aggregate reduction is preserved below.", st["body"]))
            story.append(_grid_table(
                ["Alias", "Type", "Impact", "Effort", "Original tokens", "Draft tokens", "Reduction"],
                [(alias.get(d.get("source_path", ""), f"file-{i + 1:03d}.md"), d.get("target_type"),
                  d.get("impact"), d.get("effort"), _fmt_int(d.get("original_tokens")),
                  _fmt_int(d.get("draft_tokens")), f"-{d.get('reduction_pct', 0)}%")
                 for i, d in enumerate(drafts)],
                [40 * mm, 24 * mm, 16 * mm, 16 * mm, 24 * mm, 22 * mm, 20 * mm], st))
        data, pages = _build(story, f"Redacted efficiency report · {payload['scan'].get('id')}")
        if pages <= REDACTED_PDF_MAX_PAGES:
            return data
        issue_limit = max(15, issue_limit // 2)
        file_limit = max(15, file_limit // 2)
    return data


# ------------------------------------------------------------------ HTML
def print_view_html(payload: dict, redacted: bool = False) -> str:
    scan = payload["scan"]
    alias = build_alias_map([f["path"] for f in payload.get("files", [])]) if redacted else {}
    det = payload.get("detections", {}) or {}
    rows = "".join(
        f"<tr><td>{_esc(i.get('id'))}</td><td>{_esc(i.get('severity'))}</td>"
        f"<td>{_esc(i.get('category'))}</td>"
        f"<td>{_esc(redact_text(i.get('title', ''), alias) if redacted else i.get('title'))}</td>"
        f"<td style='text-align:right'>{_fmt_int(i.get('estimated_token_waste'))}</td>"
        f"<td style='text-align:right'>{_fmt_money(i.get('estimated_dollar_waste'))}</td></tr>"
        for i in payload.get("issues", [])
    )
    cats = "".join(
        f"<tr><td>{_esc(c.get('label'))}</td><td style='text-align:right'>{c.get('score')}</td>"
        f"<td style='text-align:right'>-{c.get('penalty_points')}</td>"
        f"<td>{_esc(redact_text(c.get('summary', ''), alias) if redacted else c.get('summary'))}</td></tr>"
        for c in payload.get("category_scores", [])
    )
    notes = "".join(f"<li>{_esc(n)}</li>" for n in (payload.get("assumptions", {}) or {}).get("notes", []))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Bloat Guardian {'Redacted ' if redacted else ''}Report {_esc(scan.get('id'))}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;background:#fff;margin:32px;}}
h1{{margin:0 0 4px}} .sub{{color:#475569;margin-bottom:18px}}
.badge{{display:inline-block;padding:6px 14px;border-radius:999px;background:#0f766e;color:#fff;font-weight:600}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:12px}}
th,td{{border:1px solid #cbd5e1;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#0f766e;color:#fff}} tr:nth-child(even) td{{background:#f1f5f9}}
@media print{{body{{margin:12mm}}}}
</style></head><body>
<h1>Agentic Efficiency Report{' (Redacted)' if redacted else ''}</h1>
<div class="sub">{_esc(scan.get('repo_name'))} · {_esc(scan.get('source_type'))} · {_esc(scan.get('id'))}</div>
<p><span class="badge">{_esc(scan.get('verdict') or scan.get('status'))} · {_esc(scan.get('overall_score'))}/100</span></p>
<h2>Key numbers</h2>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Files discovered</td><td>{_fmt_int(scan.get('total_files'))}</td></tr>
<tr><td>Files parsed</td><td>{_fmt_int(scan.get('parsed_files'))}</td></tr>
<tr><td>Files skipped</td><td>{_fmt_int(scan.get('skipped_files'))}</td></tr>
<tr><td>Tokens analysed</td><td>{_fmt_int(scan.get('analyzed_tokens'))}</td></tr>
<tr><td>Monthly token waste</td><td>{_fmt_int(scan.get('estimated_monthly_token_waste'))}</td></tr>
<tr><td>Monthly dollar waste</td><td>{_fmt_money(scan.get('estimated_monthly_dollar_waste'))}</td></tr>
<tr><td>Savings range</td><td>{_fmt_money(scan.get('estimated_savings_low'))} - {_fmt_money(scan.get('estimated_savings_high'))}</td></tr>
<tr><td>Duplicate clusters</td><td>{_fmt_int(det.get('duplicate_clusters_found'))}</td></tr>
<tr><td>Oversized context files</td><td>{_fmt_int(det.get('oversized_context_files'))}</td></tr>
<tr><td>Review stages inferred</td><td>{_fmt_int(det.get('review_stages_inferred'))}</td></tr>
</table>
<h2>Category scores</h2>
<table><tr><th>Category</th><th>Score</th><th>Penalty</th><th>Summary</th></tr>{cats}</table>
<h2>Findings</h2>
<table><tr><th>Issue</th><th>Severity</th><th>Category</th><th>Title</th><th>Tokens/mo</th><th>$/mo</th></tr>{rows}</table>
<h2>Assumptions</h2><ul>{notes}</ul>
<p style="color:#475569;font-size:12px">Use your browser print dialog and choose "Save as PDF".</p>
</body></html>"""


# ------------------------------------------------------------------- ZIPs
DRAFT_README = """# Bloat Guardian draft replacement files

Each file in this package is a refined version of a file that already exists in your repository.
The original file is named in the header comment of every draft. Filenames use an `-optimised`
suffix so nothing in your repository is overwritten.

How to use these drafts:

1. Open the draft next to the original file.
2. Check that every rule you still need is present.
3. Replace the original content when you are happy, then delete the near duplicate files listed
   in the report.

Drafts were generated by {model}.
Scan: {scan_id} · Repository: {repo_name} · Generated {generated}
"""


def drafts_zip(payload: dict) -> bytes:
    drafts = payload.get("drafts", [])
    scan = payload["scan"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", DRAFT_README.format(
            model=(drafts[0].get("model") if drafts else "n/a"),
            scan_id=scan.get("id"), repo_name=scan.get("repo_name"),
            generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        ))
        used: dict = {}
        for d in drafts:
            name = d.get("target_filename") or "draft-optimised.md"
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                stem, ext = os.path.splitext(name)
                name = f"{stem}-{used[name]}{ext}"
            header = (
                f"<!-- Bloat Guardian optimised draft\n"
                f"     Original file: {d.get('source_path')}\n"
                f"     Type: {d.get('target_type')} | Impact: {d.get('impact')} | Effort: {d.get('effort')}\n"
                f"     Tokens: {d.get('original_tokens')} -> {d.get('draft_tokens')} "
                f"({d.get('reduction_pct')}% smaller)\n"
                f"     Model: {d.get('model')}\n-->\n\n"
            )
            zf.writestr(f"drafts/{name}", header + (d.get("draft_content") or ""))
        if not drafts:
            zf.writestr(
                "drafts/NO-DRAFTS.md",
                "# No draft replacement files\n\nThis scan did not contain any agent, instruction, "
                "orchestration, context or memory files that were eligible for rewriting.\n",
            )
    return buf.getvalue()


def efficiency_summary_md(payload: dict) -> str:
    scan = payload["scan"]
    det = payload.get("detections", {}) or {}
    a = payload.get("assumptions", {}) or {}
    lines = [
        f"# Agentic efficiency summary — {scan.get('repo_name')}",
        "",
        f"- Scan: `{scan.get('id')}`",
        f"- Source: {scan.get('source_type')}"
        + (f" · branch `{scan.get('branch')}`" if scan.get("branch") else ""),
        f"- Overall efficiency score: **{scan.get('overall_score')} / 100**",
        f"- Verdict: **{scan.get('verdict') or scan.get('status')}**"
        + (" `PartialScan`" if scan.get("partial_scan") else ""),
        f"- Files parsed / skipped: {scan.get('parsed_files')} / {scan.get('skipped_files')}",
        f"- Tokens analysed: {int(scan.get('analyzed_tokens') or 0):,}",
        f"- Estimated monthly waste: {int(scan.get('estimated_monthly_token_waste') or 0):,} tokens "
        f"(~{float(scan.get('estimated_monthly_credit_waste') or 0):,.2f} credits, "
        f"${float(scan.get('estimated_monthly_dollar_waste') or 0):,.2f})",
        f"- Savings range: ${float(scan.get('estimated_savings_low') or 0):,.2f} to "
        f"${float(scan.get('estimated_savings_high') or 0):,.2f} per month",
        "",
        "## Category scores",
        "",
        "| Category | Score | Penalty | What this means |",
        "| --- | --- | --- | --- |",
    ]
    for c in payload.get("category_scores", []):
        lines.append(f"| {c.get('label')} | {c.get('score')}/100 | -{c.get('penalty_points')} | {c.get('summary')} |")
    lines += ["", "## Top waste drivers", ""]
    for d in payload.get("top_drivers", [])[:5]:
        lines.append(f"{d.get('rank')}. **{d.get('title')}** — {d.get('plain_language')}")
        lines.append(f"   - {int(d.get('estimated_token_waste') or 0):,} tokens/month, "
                     f"${float(d.get('estimated_dollar_waste') or 0):,.2f}/month")
    lines += ["", "## Signals", "",
              f"- Duplicate clusters: {det.get('duplicate_clusters_found', 0)}",
              f"- Repeated instruction blocks: {det.get('repeated_block_groups', 0)}",
              f"- Oversized context files: {det.get('oversized_context_files', 0)}",
              f"- Overlapping agent groups: {det.get('overlapping_agent_groups', 0)}",
              f"- Review stages inferred: {det.get('review_stages_inferred', 0)}",
              f"- Agent-like files: {det.get('agent_like_files', 0)}",
              "", "## Recommended actions", "",
              "| # | Action | Impact | Effort | Tokens/mo saved |", "| --- | --- | --- | --- | --- |"]
    for i, act in enumerate(payload.get("recommended_actions", []), start=1):
        lines.append(f"| {i} | {act['action']} | {act['impact']} | {act['effort']} | "
                     f"{int(act['estimated_token_reduction']):,} |")
    lines += ["", "## Assumptions", ""] + [f"- {n}" for n in a.get("notes", [])]
    lines += ["", "---", "Generated by Bloat Guardian."]
    return "\n".join(lines)


def handoff_prompt(payload: dict) -> str:
    scan = payload["scan"]
    drivers = payload.get("top_drivers", [])[:5]
    actions = payload.get("recommended_actions", [])[:8]
    lines = [
        "You are helping me reduce token waste in an agentic coding repository.",
        "",
        f"Repository: {scan.get('repo_name')}",
        f"Efficiency score: {scan.get('overall_score')}/100 ({scan.get('verdict') or scan.get('status')})",
        f"Estimated monthly waste: {int(scan.get('estimated_monthly_token_waste') or 0):,} tokens "
        f"(~${float(scan.get('estimated_monthly_dollar_waste') or 0):,.2f})",
        "",
        "Top waste drivers:",
    ]
    for d in drivers:
        lines.append(f"{d.get('rank')}. {d.get('title')} — {int(d.get('estimated_token_waste') or 0):,} tokens/month")
    lines += ["", "Please help me apply these changes, one at a time, smallest effort first:"]
    for i, a in enumerate(actions, start=1):
        lines.append(f"{i}. {a['action']} (impact {a['impact']}, effort {a['effort']})")
    lines += [
        "",
        "Rules: do not delete any real requirement. Keep one source of truth per instruction. "
        "Show me a diff before changing files.",
    ]
    return "\n".join(lines)


def _pick_draft(drafts: list, wanted: str) -> dict | None:
    for d in drafts:
        if d.get("target_type") == wanted:
            return d
    return None


HANDOFF_MISSING = """# No {kind} draft was generated

This scan did not find a {kind} file that needed rewriting, so there is no draft to hand off.

What you can do instead:

{actions}

Scan: {scan_id} · Repository: {repo_name}
"""

HANDOFF_README = """# Open in VS Code

1. Unzip this package somewhere inside your project, for example `./bloat-guardian/`.
2. Open the folder in VS Code:
   - macOS / Linux / Windows with the `code` command installed: `code ./bloat-guardian`
   - Or use the URI: `vscode://file/<absolute-path-to-this-folder>`
   - Or in VS Code use **File → Open Folder…** and pick the unzipped folder.
3. Open `efficiency-summary.md` first, then paste `summary-prompt.txt` into your coding agent.

If your browser blocked the `vscode://` link, that is expected in many browsers. Use step 2
manually instead — nothing else is required.

This package never edits your repository. Every draft has an `-optimised` name.
"""


def handoff_zip(payload: dict) -> bytes:
    scan = payload["scan"]
    drafts = payload.get("drafts", [])
    actions_md = "\n".join(
        f"- {a['action']} (impact {a['impact']}, effort {a['effort']})"
        for a in payload.get("recommended_actions", [])[:6]
    ) or "- No actions were required for this area."
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("efficiency-summary.md", efficiency_summary_md(payload))
        for filename, kind in (
            ("recommended-instruction.md", "instruction"),
            ("recommended-orchestrator.md", "orchestrator"),
            ("recommended-context.md", "context"),
        ):
            d = _pick_draft(drafts, kind) or (_pick_draft(drafts, "memory") if kind == "context" else None)
            if d:
                zf.writestr(filename, (
                    f"<!-- Optimised {kind} draft generated from {d.get('source_path')} by "
                    f"{d.get('model')}. Tokens {d.get('original_tokens')} -> {d.get('draft_tokens')} "
                    f"({d.get('reduction_pct')}% smaller). -->\n\n"
                ) + (d.get("draft_content") or ""))
            else:
                zf.writestr(filename, HANDOFF_MISSING.format(
                    kind=kind, actions=actions_md, scan_id=scan.get("id"), repo_name=scan.get("repo_name")))
        zf.writestr("findings.csv", issues_csv(payload))
        zf.writestr("summary-prompt.txt", handoff_prompt(payload))
        zf.writestr("README.md", HANDOFF_README)
        for d in drafts:
            zf.writestr(f"drafts/{d.get('target_filename')}", d.get("draft_content") or "")
    return buf.getvalue()
