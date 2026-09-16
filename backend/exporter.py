"""
exporter.py — Excel export with all lead data including bio details.
"""

import io
from datetime import datetime
from typing import List

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from detector import ExtractedLead

HEADER_BG  = "4F46E5"
HEADER_FG  = "FFFFFF"
ROW_ALT_BG = "EEF2FF"
ROW_EVN_BG = "FFFFFF"


def _thin_border() -> Border:
    s = Side(style="thin", color="D1D5DB")
    return Border(left=s, right=s, top=s, bottom=s)


def export_to_excel(leads: List[ExtractedLead], reel_url: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Business Leads"

    # ── Title row ──────────────────────────────────────────────────────────
    ws.merge_cells("A1:I1")
    tc = ws["A1"]
    tc.value = f"Instagram Reel Business Leads  |  {reel_url}"
    tc.font = Font(name="Calibri", bold=True, size=12, color="1E1B4B")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    tc.fill = PatternFill("solid", fgColor="EEF2FF")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:I2")
    mc = ws["A2"]
    mc.value = (
        f"Scraped: {datetime.now().strftime('%d %b %Y  %I:%M %p')}  |  "
        f"Total Leads: {len(leads)}"
    )
    mc.font = Font(name="Calibri", size=9, color="6B7280", italic=True)
    mc.alignment = Alignment(horizontal="center")
    ws.row_dimensions[2].height = 16

    # ── Headers ────────────────────────────────────────────────────────────
    headers = [
        "Sr.", "Company / Name", "Instagram Handle",
        "Contact Number(s)", "Email(s)", "Website(s)",
        "Instagram Bio", "Confidence", "Why Flagged",
    ]
    col_widths = [5, 28, 22, 22, 30, 32, 42, 13, 45]

    HR = 3
    for ci, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=HR, column=ci, value=h)
        cell.font = Font(name="Calibri", bold=True, color=HEADER_FG, size=10)
        cell.fill = PatternFill("solid", fgColor=HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _thin_border()
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[HR].height = 22

    # ── Data rows ──────────────────────────────────────────────────────────
    for i, lead in enumerate(leads, start=1):
        row = HR + i
        bg = ROW_ALT_BG if i % 2 == 0 else ROW_EVN_BG
        fill = PatternFill("solid", fgColor=bg)

        values = [
            i,
            lead.commenter_name,
            lead.instagram_handle,
            "\n".join(lead.phones) if lead.phones else "—",
            "\n".join(lead.emails) if lead.emails else "—",
            "\n".join(lead.websites) if lead.websites else "—",
            lead.comment_text,    # bio / comment text
            f"{lead.confidence_score}%",
            "; ".join(lead.detection_reasons) if lead.detection_reasons else "—",
        ]

        for ci, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=ci, value=val)
            cell.font = Font(name="Calibri", size=9)
            cell.fill = fill
            cell.border = _thin_border()
            cell.alignment = Alignment(
                vertical="center",
                horizontal="center" if ci in (1, 8) else "left",
                wrap_text=True,
            )

        ws.row_dimensions[row].height = 50

    ws.freeze_panes = f"A{HR + 1}"
    ws.auto_filter.ref = f"A{HR}:{get_column_letter(len(headers))}{HR + len(leads)}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
