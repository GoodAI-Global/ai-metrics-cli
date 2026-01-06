"""
PDF Report Generation for Good AI Metrics.

Generates professional PDF reports from analysis results.
Requires the 'reports' extra: pip install goodai-metrics[reports]
"""

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class ReportError(Exception):
    """Raised when report generation fails."""

    pass


# Report configuration limits (security)
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
MAX_METRICS_IN_REPORT = 500
MAX_OUTPUT_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _validate_output_path(filepath: Path) -> None:
    """
    Validate output path is safe.

    Raises:
        ReportError: If path is invalid or unsafe.
    """
    filepath = Path(filepath)

    # Check for path traversal
    if ".." in str(filepath):
        raise ReportError(f"Output path cannot contain '..': {filepath}")

    # Validate extension
    if filepath.suffix.lower() != ".pdf":
        raise ReportError(
            f"Output file must have .pdf extension, got: {filepath.suffix}"
        )

    # Check parent directory exists and is writable
    parent = filepath.parent
    if not parent.exists():
        raise ReportError(f"Output directory does not exist: {parent}")


def _sanitize_text(text: str, max_length: int = 1000) -> str:
    """
    Sanitize text for PDF output.

    Removes control characters and limits length.
    """
    if not text:
        return ""

    # Remove control characters except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Limit length
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."

    return text


def _check_reportlab_available() -> None:
    """
    Check if reportlab is installed.

    Raises:
        ReportError: If reportlab is not available.
    """
    try:
        import reportlab  # noqa: F401
    except ImportError:
        raise ReportError(
            "PDF report generation requires reportlab. "
            "Install with: pip install goodai-metrics[reports]"
        ) from None


def generate_pdf_report(
    analysis_results: dict[str, Any],
    recommendations: list[dict[str, Any]],
    overall_health: str,
    output_path: Path,
    title: Optional[str] = None,
    description: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Path:
    """
    Generate a PDF report from analysis results.

    Args:
        analysis_results: Results from MetricsAnalyzer.analyze().
        recommendations: List of recommendation dictionaries.
        overall_health: Overall health status string.
        output_path: Path for the output PDF file.
        title: Optional custom report title.
        description: Optional report description/notes.
        project_name: Optional project name for the header.

    Returns:
        Path to the generated PDF file.

    Raises:
        ReportError: If report generation fails.
    """
    _check_reportlab_available()

    output_path = Path(output_path)
    _validate_output_path(output_path)

    # Validate input size
    if len(recommendations) > MAX_METRICS_IN_REPORT:
        raise ReportError(
            f"Too many recommendations ({len(recommendations)}). "
            f"Maximum is {MAX_METRICS_IN_REPORT}"
        )

    # Sanitize inputs
    title = _sanitize_text(title or "AI Metrics Analysis Report", MAX_TITLE_LENGTH)
    description = _sanitize_text(description or "", MAX_DESCRIPTION_LENGTH)
    project_name = _sanitize_text(project_name or "", MAX_TITLE_LENGTH)

    # Generate the PDF
    try:
        pdf_content = _build_pdf_report(
            analysis_results=analysis_results,
            recommendations=recommendations,
            overall_health=overall_health,
            title=title,
            description=description,
            project_name=project_name,
        )

        # Validate output size
        if len(pdf_content) > MAX_OUTPUT_FILE_SIZE:
            raise ReportError(
                f"Generated PDF exceeds maximum size "
                f"({len(pdf_content) // (1024 * 1024)} MB)"
            )

        # Write to file
        output_path.write_bytes(pdf_content)

        return output_path

    except ReportError:
        raise
    except Exception as e:
        raise ReportError(f"Failed to generate PDF report: {e}") from e


def _build_pdf_report(
    analysis_results: dict[str, Any],
    recommendations: list[dict[str, Any]],
    overall_health: str,
    title: str,
    description: str,
    project_name: str,
) -> bytes:
    """
    Build the PDF content using reportlab.

    Returns:
        PDF content as bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()

    # Create document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a1a2e"),
    )

    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=6,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#4a4a6a"),
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=16,
        spaceBefore=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1a1a2e"),
    )

    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
        leading=14,
    )

    # Build story (content)
    story = []

    # Header
    story.append(Paragraph(title, title_style))

    if project_name:
        story.append(Paragraph(f"Project: {project_name}", subtitle_style))

    story.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", subtitle_style
        )
    )

    story.append(Spacer(1, 0.25 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"))
    )
    story.append(Spacer(1, 0.25 * inch))

    # Description if provided
    if description:
        story.append(Paragraph(description, body_style))
        story.append(Spacer(1, 0.25 * inch))

    # Executive Summary
    story.append(Paragraph("Executive Summary", heading_style))

    summary_data = [
        ["Industry", analysis_results.get("industry", "N/A")],
        ["Metrics Analyzed", str(analysis_results.get("metrics_analyzed", 0))],
        ["With Benchmarks", str(analysis_results.get("metrics_with_benchmarks", 0))],
        [
            "High Priority Gaps",
            str(sum(1 for r in recommendations if r.get("priority") == "HIGH")),
        ],
        ["Overall Health", overall_health],
    ]

    summary_table = Table(summary_data, colWidths=[2.5 * inch, 4 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.25 * inch))

    # Health status indicator
    health_color = _get_health_color(overall_health)
    health_style = ParagraphStyle(
        "HealthStatus",
        parent=body_style,
        fontSize=14,
        textColor=health_color,
        alignment=TA_CENTER,
    )
    story.append(Paragraph(f"<b>Status: {overall_health}</b>", health_style))
    story.append(Spacer(1, 0.5 * inch))

    # Recommendations
    if recommendations:
        story.append(Paragraph("Recommendations", heading_style))

        # Group by priority
        high_priority = [r for r in recommendations if r.get("priority") == "HIGH"]
        medium_priority = [r for r in recommendations if r.get("priority") == "MEDIUM"]
        low_priority = [r for r in recommendations if r.get("priority") == "LOW"]

        if high_priority:
            story.append(
                Paragraph(
                    "<font color='#dc3545'><b>High Priority</b></font>", body_style
                )
            )
            story.append(
                _build_recommendations_table(high_priority, colors.HexColor("#dc3545"))
            )
            story.append(Spacer(1, 0.2 * inch))

        if medium_priority:
            story.append(
                Paragraph(
                    "<font color='#ffc107'><b>Medium Priority</b></font>", body_style
                )
            )
            story.append(
                _build_recommendations_table(
                    medium_priority, colors.HexColor("#ffc107")
                )
            )
            story.append(Spacer(1, 0.2 * inch))

        if low_priority:
            story.append(
                Paragraph(
                    "<font color='#28a745'><b>Low Priority</b></font>", body_style
                )
            )
            story.append(
                _build_recommendations_table(low_priority, colors.HexColor("#28a745"))
            )
            story.append(Spacer(1, 0.2 * inch))

    # Detailed Analysis (if we have data)
    analysis_data = analysis_results.get("analysis", [])
    if analysis_data:
        story.append(PageBreak())
        story.append(Paragraph("Detailed Metric Analysis", heading_style))

        for metric_analysis in analysis_data[:MAX_METRICS_IN_REPORT]:
            story.append(_build_metric_detail(metric_analysis, body_style))
            story.append(Spacer(1, 0.15 * inch))

    # Metrics without benchmarks
    without_benchmarks = analysis_results.get("metrics_without_benchmarks", [])
    if without_benchmarks:
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph("Metrics Without Benchmarks", heading_style))
        story.append(
            Paragraph(
                "The following metrics were analyzed but have no industry benchmarks available:",
                body_style,
            )
        )
        for metric in without_benchmarks[:50]:  # Limit display
            story.append(Paragraph(f"  - {_sanitize_text(metric, 100)}", body_style))

    # Footer
    story.append(Spacer(1, 0.5 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"))
    )
    story.append(Spacer(1, 0.1 * inch))

    footer_style = ParagraphStyle(
        "Footer",
        parent=body_style,
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )
    story.append(
        Paragraph(
            "Generated by Good AI Metrics CLI | Evidence over opinions. Leverage, not lore.",
            footer_style,
        )
    )

    # Build PDF
    doc.build(story)

    return buffer.getvalue()


def _build_recommendations_table(
    recommendations: list[dict[str, Any]],
    priority_color: Any,
) -> Any:
    """Build a table of recommendations."""
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    data = [["Metric", "Current", "Target (P50)", "Gap", "Action"]]

    for rec in recommendations:
        data.append(
            [
                _sanitize_text(rec.get("metric", ""), 50),
                f"{rec.get('current_value', 'N/A')}",
                f"{rec.get('benchmark_p50', 'N/A')}",
                f"{rec.get('gap_percent', 0):.1f}%",
                _sanitize_text(rec.get("recommendation", "")[:60], 60),
            ]
        )

    table = Table(
        data, colWidths=[1.3 * inch, 0.8 * inch, 0.9 * inch, 0.6 * inch, 2.9 * inch]
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (1, 1), (3, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#fafafa")],
                ),
            ]
        )
    )

    return table


def _build_metric_detail(metric_analysis: dict[str, Any], style: Any) -> Any:
    """Build a paragraph with metric details."""
    from reportlab.platypus import Paragraph

    metric_name = _sanitize_text(metric_analysis.get("metric", "Unknown"), 100)
    current = metric_analysis.get("current_value", "N/A")
    p50 = metric_analysis.get("benchmark_p50", "N/A")
    p75 = metric_analysis.get("benchmark_p75", "N/A")
    p90 = metric_analysis.get("benchmark_p90", "N/A")
    bracket = metric_analysis.get("percentile_bracket", "N/A")

    text = (
        f"<b>{metric_name}</b><br/>"
        f"Current: {current} | P50: {p50} | P75: {p75} | P90: {p90}<br/>"
        f"Percentile Bracket: {bracket}"
    )

    return Paragraph(text, style)


def _get_health_color(health: str) -> Any:
    """Get color for health status."""
    from reportlab.lib import colors

    health_colors = {
        "HEALTHY": colors.HexColor("#28a745"),
        "NEEDS_ATTENTION": colors.HexColor("#ffc107"),
        "CRITICAL": colors.HexColor("#dc3545"),
    }
    return health_colors.get(health.upper(), colors.HexColor("#6c757d"))


def generate_comparison_pdf_report(
    comparison_results: dict[str, Any],
    output_path: Path,
    title: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Path:
    """
    Generate a PDF report for metric comparison.

    Args:
        comparison_results: Results from compare_metrics().
        output_path: Path for the output PDF file.
        title: Optional custom report title.
        project_name: Optional project name.

    Returns:
        Path to the generated PDF file.

    Raises:
        ReportError: If report generation fails.
    """
    _check_reportlab_available()

    output_path = Path(output_path)
    _validate_output_path(output_path)

    # Validate input size
    comparisons = comparison_results.get("comparisons", [])
    if len(comparisons) > MAX_METRICS_IN_REPORT:
        raise ReportError(
            f"Too many comparisons ({len(comparisons)}). "
            f"Maximum is {MAX_METRICS_IN_REPORT}"
        )

    title = _sanitize_text(title or "AI Metrics Comparison Report", MAX_TITLE_LENGTH)
    project_name = _sanitize_text(project_name or "", MAX_TITLE_LENGTH)

    try:
        pdf_content = _build_comparison_pdf(
            comparison_results=comparison_results,
            title=title,
            project_name=project_name,
        )

        # Validate output size
        if len(pdf_content) > MAX_OUTPUT_FILE_SIZE:
            raise ReportError(
                f"Generated PDF exceeds maximum size "
                f"({len(pdf_content) // (1024 * 1024)} MB)"
            )

        output_path.write_bytes(pdf_content)
        return output_path

    except ReportError:
        raise
    except Exception as e:
        raise ReportError(f"Failed to generate comparison PDF: {e}") from e


def _build_comparison_pdf(
    comparison_results: dict[str, Any],
    title: str,
    project_name: str,
) -> bytes:
    """Build comparison PDF content."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1a1a2e"),
    )

    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=16,
        spaceBefore=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1a1a2e"),
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
    )

    story = []

    # Title
    story.append(Paragraph(title, title_style))
    if project_name:
        story.append(Paragraph(f"Project: {project_name}", body_style))
    story.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", body_style
        )
    )
    story.append(Spacer(1, 0.25 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"))
    )
    story.append(Spacer(1, 0.25 * inch))

    # Summary
    story.append(Paragraph("Comparison Summary", heading_style))

    summary = comparison_results.get("summary", {})
    summary_data = [
        ["Industry", comparison_results.get("industry", "N/A")],
        ["Metrics Compared", str(comparison_results.get("metrics_compared", 0))],
        ["Improved", str(summary.get("improved", 0))],
        ["Declined", str(summary.get("declined", 0))],
        ["Unchanged", str(summary.get("unchanged", 0))],
    ]

    summary_table = Table(summary_data, colWidths=[2.5 * inch, 4 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f5f5")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.25 * inch))

    # Comparisons table
    comparisons = comparison_results.get("comparisons", [])
    if comparisons:
        story.append(Paragraph("Metric Changes", heading_style))

        comp_data = [["Metric", "Before", "After", "Change", "Status"]]
        for comp in comparisons:
            status = "Improved" if comp.get("improved") else "Declined"
            if comp.get("direction") == "unchanged":
                status = "Unchanged"

            comp_data.append(
                [
                    _sanitize_text(comp.get("metric", ""), 40),
                    f"{comp.get('before_value', 'N/A')}",
                    f"{comp.get('after_value', 'N/A')}",
                    f"{comp.get('change_percent', 0):+.1f}%",
                    status,
                ]
            )

        comp_table = Table(
            comp_data,
            colWidths=[2 * inch, 1.2 * inch, 1.2 * inch, 1 * inch, 1.1 * inch],
        )
        comp_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#fafafa")],
                    ),
                ]
            )
        )
        story.append(comp_table)

    # Footer
    story.append(Spacer(1, 0.5 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"))
    )

    footer_style = ParagraphStyle(
        "Footer",
        parent=body_style,
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )
    story.append(Paragraph("Generated by Good AI Metrics CLI", footer_style))

    doc.build(story)
    return buffer.getvalue()
