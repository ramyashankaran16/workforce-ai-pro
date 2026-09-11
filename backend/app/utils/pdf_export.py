"""Payslip PDF generation with reportlab."""

import os
from decimal import Decimal
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#d1d5db")
BAND = colors.HexColor("#f3f4f6")


def _rupees(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    whole, _, frac = f"{amount:.2f}".partition(".")
    negative = whole.startswith("-")
    whole = whole.lstrip("-")

    # Indian grouping: last three digits, then pairs
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])

    return f"{'-' if negative else ''}{whole}.{frac}"


def generate_payslip_pdf(payslip: Dict, output_dir: str, company_name: str) -> str:
    """Render one payslip and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{payslip['slip_number']}.pdf")

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Payslip {payslip['slip_number']}",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=16, textColor=INK, spaceAfter=2
    )
    subtitle = ParagraphStyle(
        "subtitle", parent=styles["Normal"], fontSize=9.5, textColor=MUTED
    )
    section = ParagraphStyle(
        "section", parent=styles["Heading2"], fontSize=11, textColor=INK,
        spaceBefore=10, spaceAfter=4,
    )

    story: List = [
        Paragraph(company_name, title),
        Paragraph(
            f"Payslip for {MONTHS[payslip['month']]} {payslip['year']}"
            f" &nbsp;|&nbsp; {payslip['slip_number']}",
            subtitle,
        ),
        Spacer(1, 8),
    ]

    details = [
        ["Employee", payslip.get("employee_name") or "-",
         "Employee code", payslip.get("employee_code") or "-"],
        ["Department", payslip.get("department_name") or "-",
         "Designation", payslip.get("designation_title") or "-"],
        ["Period", f"{payslip['period_start']} to {payslip['period_end']}",
         "Working days", str(payslip["working_days"])],
        ["Present days", str(payslip["present_days"]),
         "Paid leave", str(payslip["paid_leave_days"])],
        ["Loss of pay days", str(payslip["unpaid_leave_days"]),
         "Overtime hours", str(payslip["overtime_hours"])],
    ]
    detail_table = Table(details, colWidths=[30 * mm, 52 * mm, 30 * mm, 52 * mm])
    detail_table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("TEXTCOLOR", (2, 0), (2, -1), MUTED),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
            ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
        ])
    )
    story += [detail_table, Spacer(1, 6)]

    earnings = [i for i in payslip["line_items"] if i["component_type"] == "earning"]
    deductions = [i for i in payslip["line_items"] if i["component_type"] == "deduction"]

    rows = [["Earnings", "Amount", "Deductions", "Amount"]]
    for index in range(max(len(earnings), len(deductions))):
        left = earnings[index] if index < len(earnings) else None
        right = deductions[index] if index < len(deductions) else None
        rows.append([
            left["component_name"] if left else "",
            _rupees(left["amount"]) if left else "",
            right["component_name"] if right else "",
            _rupees(right["amount"]) if right else "",
        ])
    rows.append([
        "Gross earnings", _rupees(payslip["gross_earnings"]),
        "Total deductions", _rupees(payslip["total_deductions"]),
    ])

    breakdown = Table(rows, colWidths=[52 * mm, 30 * mm, 52 * mm, 30 * mm])
    breakdown.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), BAND),
            ("BACKGROUND", (0, -1), (-1, -1), BAND),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("TEXTCOLOR", (0, 0), (-1, -1), INK),
            ("GRID", (0, 0), (-1, -1), 0.25, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    story += [Paragraph("Salary breakdown", section), breakdown, Spacer(1, 8)]

    net = Table(
        [["Net pay", _rupees(payslip["net_pay"])]],
        colWidths=[134 * mm, 30 * mm],
    )
    net.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("BACKGROUND", (0, 0), (-1, -1), INK),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (0, 0), 10),
            ("RIGHTPADDING", (1, 0), (1, 0), 10),
        ])
    )
    story += [net, Spacer(1, 10)]

    story.append(
        Paragraph(
            "This is a computer-generated payslip and does not require a signature.",
            ParagraphStyle("foot", parent=styles["Normal"], fontSize=7.5, textColor=MUTED),
        )
    )

    doc.build(story)
    return path
