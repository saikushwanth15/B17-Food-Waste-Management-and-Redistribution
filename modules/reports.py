"""
================================================================================
MODULE: reports.py
MEMBER 3 DELIVERABLE: L Sai Kushwanth
================================================================================
ReportLab PDF Generation Module for Food Waste Management and Redistribution
(SDG 2 - Zero Hunger).

Strict Architecture Rules:
- Generated in-memory via io.BytesIO() returning raw bytes.
- Clean styling with branded emerald green headers (#1B5E20) and alternating row colors.
- Includes Vector Bar Charts using reportlab.graphics.
- Covers Data Cleaning summaries, KPI tables, Narrative Insights, Limitations,
  and Project Evaluation / Viva Summaries.
- No hardcoded false metrics: Everything is computed dynamically.
================================================================================
"""

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional
import pandas as pd

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ------------------------------------------------------------------------------
# PALETTE & REPORT STYLES
# ------------------------------------------------------------------------------
PRIMARY_DARK = colors.HexColor("#1B5E20")    # Emerald Forest
PRIMARY_MED = colors.HexColor("#2E7D32")     # Vibrant Green
ACCENT_LIGHT = colors.HexColor("#E8F5E9")    # Soft Mint Green
NEUTRAL_LIGHT = colors.HexColor("#F9FBF9")   # Soft Off-white
TEXT_DARK = colors.HexColor("#1F2937")       # Charcoal
TEXT_MUTED = colors.HexColor("#4B5563")      # Medium Grey
BORDER_GREY = colors.HexColor("#D1D5DB")     # Border light

base_styles = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "DocTitle",
    parent=base_styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=20,
    leading=24,
    textColor=PRIMARY_DARK,
    alignment=0,  # Left-aligned
    spaceAfter=4,
)

SUBTITLE_STYLE = ParagraphStyle(
    "DocSubtitle",
    parent=base_styles["Normal"],
    fontName="Helvetica",
    fontSize=11,
    leading=14,
    textColor=TEXT_MUTED,
    spaceAfter=12,
)

H1_STYLE = ParagraphStyle(
    "Header1",
    parent=base_styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=16,
    textColor=PRIMARY_DARK,
    spaceBefore=14,
    spaceAfter=6,
    keepWithNext=True,
)

H2_STYLE = ParagraphStyle(
    "Header2",
    parent=base_styles["Heading3"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=PRIMARY_MED,
    spaceBefore=10,
    spaceAfter=4,
    keepWithNext=True,
)

BODY_STYLE = ParagraphStyle(
    "Body",
    parent=base_styles["BodyText"],
    fontName="Helvetica",
    fontSize=9,
    leading=12.5,
    textColor=TEXT_DARK,
    spaceAfter=4,
)

BODY_BOLD = ParagraphStyle(
    "BodyBold",
    parent=BODY_STYLE,
    fontName="Helvetica-Bold",
)

NOTE_STYLE = ParagraphStyle(
    "Note",
    parent=BODY_STYLE,
    fontName="Helvetica-Oblique",
    fontSize=8.5,
    leading=11,
    textColor=TEXT_MUTED,
)


# ------------------------------------------------------------------------------
# REUSABLE REPORTLAB DRAWING & TABLE HELPERS
# ------------------------------------------------------------------------------

def _styled_table(data: List[List[Any]], col_widths: Optional[List[float]] = None) -> Table:
    """Constructs a neatly padded table with alternating row background colors."""
    string_data = [[str(cell) for cell in row] for row in data]
    tbl = Table(string_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_MED),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ]))
    return tbl


def _vector_bar_chart(labels: List[str], values: List[float], width: float = 480, height: float = 140) -> Drawing:
    """Generates an embedded vector bar chart in PDF using reportlab.graphics."""
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 25
    chart.width = width - 55
    chart.height = height - 40
    chart.data = [list(values) or [0]]
    # Truncate labels so they fit legibly
    chart.categoryAxis.categoryNames = [str(l)[:12] for l in labels] or ["None"]
    chart.categoryAxis.labels.fontSize = 7.5
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 7.5
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = PRIMARY_MED
    drawing.add(chart)
    return drawing


def _build_pdf(story: List[Any], title: str) -> bytes:
    """Build document into in-memory BytesIO and return raw bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=title,
        author="L Sai Kushwanth (Member 3)"
    )
    doc.build(story)
    return buf.getvalue()


# ==============================================================================
# REPORT 1: LIVE OPERATIONAL & ANALYTICS REPORT
# ==============================================================================

def build_analytics_report(
    kpis: Dict[str, Any],
    monthly: pd.DataFrame,
    categories: pd.DataFrame,
    cities: pd.DataFrame,
    statuses: pd.DataFrame,
    donors: pd.DataFrame,
    ngos: pd.DataFrame
) -> bytes:
    """
    Generate professional downloadable PDF report of operational food rescue
    and redistribution metrics.
    """
    gen_time = datetime.now().strftime("%d %B %Y, %H:%M")
    
    story = [
        Paragraph("Food Waste Management and Redistribution", TITLE_STYLE),
        Paragraph("Executive Analytics & Impact Report  |  <b>SDG 2: Zero Hunger</b>", SUBTITLE_STYLE),
        HRFlowable(width="100%", thickness=1.5, color=PRIMARY_DARK, spaceAfter=8),
        Paragraph(f"<b>Report Generated:</b> {gen_time} &nbsp;|&nbsp; <b>Module:</b> Analytics & Reporting (Member 3: L Sai Kushwanth)", NOTE_STYLE),
        Spacer(1, 8),
        
        # Section 1: KPIs
        Paragraph("1. Key Performance Indicators", H1_STYLE),
        Paragraph("Operational overview computed from validated application records in <code>donations.csv</code>, <code>requests.csv</code>, and <code>distributions.csv</code>:", BODY_STYLE),
        Spacer(1, 4),
    ]

    # Format KPI Table
    kpi_rows = [["Metric", "Value", "Unit / Context"]]
    units = {
        "Total donations": "Logged records",
        "Total food listed (kg)": "Kilograms (Gross)",
        "Food rescued & distributed (kg)": "Kilograms (Net)",
        "Food expired / wasted (kg)": "Kilograms (Lost)",
        "Food in redistribution pipeline (kg)": "Kilograms (Active)",
        "Meals delivered": "Estimated servings",
        "People served": "Recorded beneficiaries",
        "Rescue rate (%)": "Percentage of listed",
        "Wastage rate (%)": "Percentage of listed",
        "Request approval rate (%)": "NGO acceptance",
        "Avg. response time (hours)": "Donor turnaround",
        "Active donors": "Registered contributors",
        "Active NGOs": "Partner organizations",
    }
    for k, v in kpis.items():
        kpi_rows.append([k, str(v), units.get(k, "-")])
    
    story.append(_styled_table(kpi_rows, [7.5 * cm, 4.0 * cm, 5.5 * cm]))
    story.append(Spacer(1, 10))

    # Section 2: Trends
    story.append(Paragraph("2. Monthly Redistribution Trends", H1_STYLE))
    if monthly.empty:
        story.append(Paragraph("No donation records available for trend analysis.", NOTE_STYLE))
    else:
        story.append(_vector_bar_chart(list(monthly["month"]), list(monthly["food_kg"].round(1))))
        story.append(Spacer(1, 4))
        m_table = [["Month", "Donations Count", "Total Food (kg)"]]
        for _, row in monthly.iterrows():
            m_table.append([str(row["month"]), str(int(row["donations"])), f"{float(row['food_kg']):.1f} kg"])
        story.append(_styled_table(m_table, [6 * cm, 5.5 * cm, 5.5 * cm]))
    story.append(Spacer(1, 10))

    # Section 3: Categories & Locations
    story.append(Paragraph("3. Category & Geographic Analysis", H1_STYLE))
    c1_text = "Analysis of surplus food types and regional rescue performance across active cities."
    story.append(Paragraph(c1_text, BODY_STYLE))
    story.append(Spacer(1, 4))
    
    if not categories.empty:
        story.append(Paragraph("<b>Breakdown by Food Category:</b>", H2_STYLE))
        cat_table = [["Category", "Donations", "Weight (kg)", "Share (%)"]]
        for _, row in categories.iterrows():
            cat_table.append([
                str(row["category"]),
                str(int(row["donations"])),
                f"{float(row['food_kg']):.1f} kg",
                f"{float(row.get('percentage', 0)):.1f}%"
            ])
        story.append(_styled_table(cat_table, [5.5 * cm, 3.5 * cm, 4.0 * cm, 4.0 * cm]))
        story.append(Spacer(1, 8))

    if not cities.empty:
        story.append(Paragraph("<b>Listed vs Rescued by Location:</b>", H2_STYLE))
        city_table = [["City", "Donations", "Listed (kg)", "Rescued (kg)", "Rescue Rate (%)"]]
        for _, row in cities.iterrows():
            city_table.append([
                str(row["city"]),
                str(int(row["donations"])),
                f"{float(row['food_kg']):.1f} kg",
                f"{float(row['rescued_kg']):.1f} kg",
                f"{float(row.get('rescue_rate_pct', 0)):.1f}%"
            ])
        story.append(_styled_table(city_table, [4.5 * cm, 3.0 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm]))
    story.append(Spacer(1, 10))

    # Section 4: Top Contributors & Beneficiaries
    story.append(Paragraph("4. Stakeholder Contribution", H1_STYLE))
    if not donors.empty:
        story.append(Paragraph("<b>Top Donors (by weight contributed):</b>", H2_STYLE))
        donor_table = [["Donor Name / Organization", "Donations", "Food Supplied (kg)"]]
        for _, row in donors.iterrows():
            donor_table.append([str(row["donor_name"]), str(int(row["donations"])), f"{float(row['food_kg']):.1f} kg"])
        story.append(_styled_table(donor_table, [8.0 * cm, 4.0 * cm, 5.0 * cm]))
        story.append(Spacer(1, 6))

    if not ngos.empty:
        story.append(Paragraph("<b>Top NGO Beneficiary Impact:</b>", H2_STYLE))
        ngo_table = [["Recipient NGO", "Distributions Completed", "People Served"]]
        for _, row in ngos.iterrows():
            ngo_table.append([str(row["recipient_name"]), str(int(row["distributions"])), str(int(row["people_served"]))])
        story.append(_styled_table(ngo_table, [8.0 * cm, 4.5 * cm, 4.5 * cm]))
    story.append(Spacer(1, 10))

    # Section 5: Automated Insights & Limitations
    story.append(Paragraph("5. Analytical Findings & Data Limitations", H1_STYLE))
    
    findings = [
        f"<b>Total Rescue Volume:</b> Successfully recorded redistribution of <b>{kpis.get('Food rescued & distributed (kg)', 0)} kg</b> of food, delivering an estimated <b>{kpis.get('Meals delivered', 0)} meals</b>.",
        f"<b>System Rescue Rate:</b> Current rescue efficiency is <b>{kpis.get('Rescue rate (%)', 0)}%</b> with <b>{kpis.get('Wastage rate (%)', 0)}%</b> expired before collection.",
    ]
    if not categories.empty:
        top_cat = categories.iloc[0]
        findings.append(f"<b>Dominant Food Category:</b> <i>{top_cat['category']}</i> accounts for the largest volume with {top_cat['food_kg']:.1f} kg.")
    if not cities.empty:
        top_city = cities.iloc[0]
        findings.append(f"<b>Top Rescue Hub:</b> <i>{top_city['city']}</i> leads with {top_city['food_kg']:.1f} kg listed and {top_city['rescued_kg']:.1f} kg rescued.")
    if float(kpis.get("Wastage rate (%)", 0)) > 15.0:
        findings.append("<b>Recommendation:</b> Wastage rate exceeds 15%. Automated SMS/Email alerts for nearby NGOs when food is within 4 hours of expiry is advised.")

    for f in findings:
        story.append(Paragraph(f"&bull; {f}", BODY_STYLE))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Data Integrity Disclaimer:</b> This report summarizes operational entries recorded in the CSV "
        "storage layer. Historical waste metrics are isolated from live inventory to prevent double-counting. "
        "Calculated meal servings are modeled upon standard average portion sizes.",
        NOTE_STYLE
    ))

    return _build_pdf(story, "Food Waste Redistribution Analytics Report")


# ==============================================================================
# REPORT 2: PROJECT EVALUATION & VIVA SUMMARY
# ==============================================================================

def build_evaluation_summary(kpis: Dict[str, Any]) -> bytes:
    """
    Generate Project Evaluation & Viva defense document summarizing architecture,
    SDG 2 alignment, member roles, and results.
    """
    team_data = [
        ["Member Name", "Role", "Assigned Modules & Deliverables"],
        ["N Thulasi Krishna", "Member 1", "Streamlit core UI, Donor registration/login, Add/edit/delete donations, Search & filters"],
        ["N Charya Vishwa", "Member 2", "Recipient/NGO dashboard, Surplus food browsing, Request workflow, Distribution tracking"],
        ["L Sai Kushwanth", "Member 3 (Me)", "Data cleaning (Pandas), KPI engine, Plotly analytics dashboard, ReportLab PDF reports, Unit tests"],
    ]

    modules_data = [
        ["#", "Module Name", "Primary Purpose & Technology"],
        ["1", "User Authentication", "Role-based access (Donor, NGO, Admin) with salted SHA-256 password hashing"],
        ["2", "Donation Management", "Operational recording of surplus food with validation (Strict CSV storage, no SQL)"],
        ["3", "Donation Request Workflow", "NGO request submission, approval/rejection logic, reservation states"],
        ["4", "Distribution Tracking", "Records pickup, people served, and delivery timestamp verification"],
        ["5", "Analytics Dashboard", "Interactive Plotly visualisations, temporal trends, geographical heatmaps"],
        ["6", "Report Generation", "Dynamic vector PDF reports generated in-memory using ReportLab"],
    ]

    story = [
        Paragraph("Food Waste Management and Redistribution", TITLE_STYLE),
        Paragraph("Academic Project Evaluation & Viva Summary  |  <b>B.Tech CSE (AI) Semester 3</b>", SUBTITLE_STYLE),
        HRFlowable(width="100%", thickness=1.5, color=PRIMARY_DARK, spaceAfter=8),
        
        Paragraph("1. Project Goal & SDG Alignment", H1_STYLE),
        Paragraph(
            "<b>Objective:</b> Bridge the gap between surplus food generation in institutional establishments "
            "(restaurants, canteens, hotels) and local hunger relief organizations. "
            "Aligned with <b>United Nations Sustainable Development Goal 2: Zero Hunger</b>, "
            "the system enables data-driven redistribution, minimizes avoidable disposal, and provides "
            "measurable operational intelligence.",
            BODY_STYLE
        ),
        Spacer(1, 6),

        Paragraph("2. Technology Stack & Architectural Constraints", H1_STYLE),
        Paragraph(
            "&bull; <b>Frontend:</b> Streamlit 1.x (Reactive web interface, session state management)<br/>"
            "&bull; <b>Data Engine:</b> Pandas 2.x / 3.x (Clean transformation, aggregation, deduplication)<br/>"
            "&bull; <b>Visualization:</b> Plotly Express (Interactive charts, heatmaps, responsive layouts)<br/>"
            "&bull; <b>Reporting:</b> ReportLab (Dynamic in-memory PDF synthesis with vector drawings)<br/>"
            "&bull; <b>Storage Layer:</b> Flat CSV files (Pure Python/Pandas file CRUD — strictly <b>NO SQL</b>).",
            BODY_STYLE
        ),
        Spacer(1, 6),

        Paragraph("3. Team Division of Responsibilities", H1_STYLE),
        _styled_table(team_data, [4.5 * cm, 3.0 * cm, 9.5 * cm]),
        Spacer(1, 8),

        Paragraph("4. System Modules Breakdown", H1_STYLE),
        _styled_table(modules_data, [1.2 * cm, 5.0 * cm, 10.8 * cm]),
        Spacer(1, 8),

        Paragraph("5. Key Operational Results", H1_STYLE),
        Paragraph("Summary of operational metrics validated during demonstration:", BODY_STYLE),
        Spacer(1, 3),
    ]

    results_table = [["KPI Metric", "Recorded Result", "Description"]]
    results_table.append(["Total Food Listed", f"{kpis.get('Total food listed (kg)', 0)} kg", "Total surplus food entered by registered donors"])
    results_table.append(["Food Distributed", f"{kpis.get('Food rescued & distributed (kg)', 0)} kg", "Successfully collected and distributed by NGOs"])
    results_table.append(["Beneficiaries Served", f"{kpis.get('People served', 0)} persons", "Count of individuals fed through distributions"])
    results_table.append(["System Rescue Efficiency", f"{kpis.get('Rescue rate (%)', 0)}%", "Portion of listed surplus preserved from waste"])
    results_table.append(["Approval Turnaround", f"{kpis.get('Avg. response time (hours)', 0)} hrs", "Average turnaround between request and approval"])
    
    story.append(_styled_table(results_table, [5.5 * cm, 4.0 * cm, 7.5 * cm]))
    story.append(Spacer(1, 10))

    Paragraph("6. Member 3 Technical Contributions Summary", H1_STYLE)
    story.append(Paragraph(
        "As <b>Member 3 (L Sai Kushwanth)</b>, my core technical accomplishments encompass: <br/>"
        "1. Engineered <code>modules/analysis.py</code> for data cleaning, type coercion, and KPI calculations.<br/>"
        "2. Built dynamic Kaggle CSV ingestion with automated column inference and manual fallback.<br/>"
        "3. Developed <code>modules/analytics.py</code> featuring Plotly charts (trends, categories, heatmaps).<br/>"
        "4. Authored <code>modules/reports.py</code> generating styled, vector-drawn ReportLab PDF summaries.<br/>"
        "5. Formulated automated test suites in <code>tests/test_analytics.py</code> ensuring system resilience.",
        BODY_STYLE
    ))

    return _build_pdf(story, "Project Evaluation and Viva Summary")


# ==============================================================================
# REPORT 3: KAGGLE / EXTERNAL FOOD WASTE DATASET AUDIT REPORT
# ==============================================================================

def build_waste_dataset_report(
    dataset_name: str,
    cleaning_report: Dict[str, Any],
    waste_metrics: Dict[str, Any],
    category_summary: Optional[pd.DataFrame] = None
) -> bytes:
    """
    Generate downloadable PDF report specifically auditing an uploaded or Kaggle
    historical food waste dataset.
    """
    gen_time = datetime.now().strftime("%d %B %Y, %H:%M")
    
    story = [
        Paragraph("Historical Food Waste Dataset Audit Report", TITLE_STYLE),
        Paragraph(f"Dataset Analyzed: <b>{dataset_name}</b>  |  <b>SDG 2: Zero Hunger</b>", SUBTITLE_STYLE),
        HRFlowable(width="100%", thickness=1.5, color=PRIMARY_DARK, spaceAfter=8),
        Paragraph(f"<b>Generated:</b> {gen_time} &nbsp;|&nbsp; <b>Auditor:</b> L Sai Kushwanth (Member 3)", NOTE_STYLE),
        Spacer(1, 8),

        Paragraph("1. Data Cleaning & Quality Audit", H1_STYLE),
        Paragraph("Summary of automated hygiene checks, deduplication, and imputation performed on raw file:", BODY_STYLE),
        Spacer(1, 4),
    ]

    audit_data = [
        ["Audit Metric", "Count / Value", "Notes"],
        ["Initial Raw Rows", str(cleaning_report.get("rows_before", 0)), "Records before processing"],
        ["Duplicates Removed", str(cleaning_report.get("duplicates_removed", 0)), "Exact identical rows dropped"],
        ["Negative Rows Dropped", str(cleaning_report.get("negative_dropped", 0)), "Invalid negative waste quantities dropped"],
        ["Missing Cells Imputed", str(cleaning_report.get("missing_imputed", 0)), "Filled with column median (numeric) or 'Unknown'"],
        ["Final Retained Rows", str(cleaning_report.get("rows_after", 0)), "Usable records for analysis"],
        ["Detected Date Column", str(cleaning_report.get("date_col", "None")), "Used for temporal aggregation"],
        ["Detected Waste Column", str(cleaning_report.get("waste_col", "None")), "Primary waste measurement metric"],
    ]
    story.append(_styled_table(audit_data, [6.0 * cm, 4.0 * cm, 7.0 * cm]))
    story.append(Spacer(1, 10))

    Paragraph("2. Statistical Food Waste Indicators", H1_STYLE)
    waste_data = [
        ["Statistical Metric", "Value (kg)", "Description"],
        ["Total Recorded Waste", f"{waste_metrics.get('total_waste_kg', 0):,.2f} kg", "Cumulative food waste logged"],
        ["Average Waste per Record", f"{waste_metrics.get('avg_waste_kg', 0):.2f} kg", "Mean waste weight per observation"],
        ["Median Waste per Record", f"{waste_metrics.get('median_waste_kg', 0):.2f} kg", "50th percentile waste weight"],
        ["Maximum Waste in Observation", f"{waste_metrics.get('max_waste_kg', 0):.2f} kg", "Peak single-session waste recorded"],
        ["Standard Deviation", f"{waste_metrics.get('std_waste_kg', 0):.2f} kg", "Dispersion across observations"],
        ["Valid Observations Analyzed", str(waste_metrics.get("record_count", 0)), "Count of non-null numeric waste values"],
    ]
    story.append(_styled_table(waste_data, [6.0 * cm, 4.5 * cm, 6.5 * cm]))
    story.append(Spacer(1, 10))

    if category_summary is not None and not category_summary.empty:
        story.append(Paragraph("3. Waste Breakdown by Category", H1_STYLE))
        cols = list(category_summary.columns)
        cat_data = [cols]
        for _, row in category_summary.head(10).iterrows():
            cat_data.append([f"{v:.2f}" if isinstance(v, float) else str(v) for v in row])
        story.append(_styled_table(cat_data, [6.0 * cm, 5.5 * cm, 5.5 * cm] if len(cols) == 3 else None))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>Important Scientific Note:</b> This historical waste dataset reflects institutional log files "
        "and is analyzed strictly for pattern discovery and waste prevention. These quantities represent "
        "waste generated in establishments and are NOT available for live donation.",
        NOTE_STYLE
    ))

    return _build_pdf(story, f"Audit Report - {dataset_name}")
