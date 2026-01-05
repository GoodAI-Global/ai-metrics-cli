"""Tests for PDF report generation."""

import tempfile
from pathlib import Path

import pytest

from goodai_metrics.reports import (
    generate_pdf_report,
    generate_comparison_pdf_report,
    ReportError,
    _validate_output_path,
    _sanitize_text,
)


class TestValidateOutputPath:
    """Tests for output path validation."""

    def test_valid_pdf_path(self, tmp_path):
        """Valid PDF path passes validation."""
        output = tmp_path / "report.pdf"
        _validate_output_path(output)  # Should not raise

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal is blocked."""
        output = tmp_path / ".." / "report.pdf"
        with pytest.raises(ReportError, match="cannot contain"):
            _validate_output_path(output)

    def test_non_pdf_extension_blocked(self, tmp_path):
        """Non-PDF extension is blocked."""
        output = tmp_path / "report.txt"
        with pytest.raises(ReportError, match="must have .pdf extension"):
            _validate_output_path(output)

    def test_missing_parent_directory_blocked(self):
        """Missing parent directory raises error."""
        output = Path("/nonexistent/dir/report.pdf")
        with pytest.raises(ReportError, match="does not exist"):
            _validate_output_path(output)


class TestSanitizeText:
    """Tests for text sanitization."""

    def test_normal_text_unchanged(self):
        """Normal text is unchanged."""
        result = _sanitize_text("Hello World")
        assert result == "Hello World"

    def test_control_chars_removed(self):
        """Control characters are removed."""
        result = _sanitize_text("Hello\x00\x01\x02World")
        assert result == "HelloWorld"

    def test_newlines_preserved(self):
        """Newlines are preserved."""
        result = _sanitize_text("Hello\nWorld")
        assert result == "Hello\nWorld"

    def test_length_limited(self):
        """Long text is truncated."""
        long_text = "a" * 2000
        result = _sanitize_text(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_string(self):
        """Empty string returns empty."""
        result = _sanitize_text("")
        assert result == ""

    def test_none_returns_empty(self):
        """None returns empty string."""
        result = _sanitize_text(None)
        assert result == ""


class TestGeneratePdfReport:
    """Tests for PDF report generation."""

    @pytest.fixture
    def sample_analysis(self):
        """Sample analysis results."""
        return {
            "industry": "manufacturing",
            "metrics_analyzed": 3,
            "metrics_with_benchmarks": 2,
            "metrics_without_benchmarks": ["custom_metric"],
            "analysis": [
                {
                    "metric": "prediction_accuracy",
                    "current_value": 0.82,
                    "benchmark_p50": 0.85,
                    "benchmark_p75": 0.90,
                    "benchmark_p90": 0.95,
                    "gap_percent": 3.5,
                    "percentile_bracket": "p50_to_p75",
                },
                {
                    "metric": "defect_detection_rate",
                    "current_value": 0.88,
                    "benchmark_p50": 0.80,
                    "benchmark_p75": 0.88,
                    "benchmark_p90": 0.93,
                    "gap_percent": 0,
                    "percentile_bracket": "p75_to_p90",
                },
            ],
        }

    @pytest.fixture
    def sample_recommendations(self):
        """Sample recommendations."""
        return [
            {
                "metric": "prediction_accuracy",
                "priority": "MEDIUM",
                "current_value": 0.82,
                "benchmark_p50": 0.85,
                "gap_percent": 3.5,
                "effort": "MEDIUM",
                "recommendation": "Improve model training data quality.",
            },
            {
                "metric": "latency_ms",
                "priority": "HIGH",
                "current_value": 350,
                "benchmark_p50": 200,
                "gap_percent": 75.0,
                "effort": "HIGH",
                "recommendation": "Optimize inference pipeline.",
            },
        ]

    def test_generates_pdf_file(self, tmp_path, sample_analysis, sample_recommendations):
        """Generates a valid PDF file."""
        output = tmp_path / "test_report.pdf"

        result = generate_pdf_report(
            analysis_results=sample_analysis,
            recommendations=sample_recommendations,
            overall_health="NEEDS_ATTENTION",
            output_path=output,
        )

        assert result.exists()
        assert result.stat().st_size > 0
        # Check it's a valid PDF (starts with %PDF)
        content = result.read_bytes()
        assert content.startswith(b"%PDF")

    def test_with_custom_title(self, tmp_path, sample_analysis, sample_recommendations):
        """Generates PDF with custom title."""
        output = tmp_path / "custom_title.pdf"

        result = generate_pdf_report(
            analysis_results=sample_analysis,
            recommendations=sample_recommendations,
            overall_health="HEALTHY",
            output_path=output,
            title="Custom Report Title",
        )

        assert result.exists()

    def test_with_description(self, tmp_path, sample_analysis, sample_recommendations):
        """Generates PDF with description."""
        output = tmp_path / "with_desc.pdf"

        result = generate_pdf_report(
            analysis_results=sample_analysis,
            recommendations=sample_recommendations,
            overall_health="CRITICAL",
            output_path=output,
            description="This is a detailed description of the report.",
        )

        assert result.exists()

    def test_with_project_name(self, tmp_path, sample_analysis, sample_recommendations):
        """Generates PDF with project name."""
        output = tmp_path / "project.pdf"

        result = generate_pdf_report(
            analysis_results=sample_analysis,
            recommendations=sample_recommendations,
            overall_health="HEALTHY",
            output_path=output,
            project_name="my-project",
        )

        assert result.exists()

    def test_empty_recommendations(self, tmp_path, sample_analysis):
        """Handles empty recommendations."""
        output = tmp_path / "no_recs.pdf"

        result = generate_pdf_report(
            analysis_results=sample_analysis,
            recommendations=[],
            overall_health="HEALTHY",
            output_path=output,
        )

        assert result.exists()

    def test_empty_analysis(self, tmp_path):
        """Handles empty analysis."""
        output = tmp_path / "empty_analysis.pdf"

        result = generate_pdf_report(
            analysis_results={
                "industry": "general",
                "metrics_analyzed": 0,
                "metrics_with_benchmarks": 0,
                "analysis": [],
            },
            recommendations=[],
            overall_health="HEALTHY",
            output_path=output,
        )

        assert result.exists()

    def test_path_traversal_blocked(self, tmp_path, sample_analysis, sample_recommendations):
        """Path traversal in output is blocked."""
        output = tmp_path / ".." / "escape.pdf"

        with pytest.raises(ReportError, match="cannot contain"):
            generate_pdf_report(
                analysis_results=sample_analysis,
                recommendations=sample_recommendations,
                overall_health="HEALTHY",
                output_path=output,
            )

    def test_non_pdf_extension_blocked(self, tmp_path, sample_analysis, sample_recommendations):
        """Non-PDF extension is blocked."""
        output = tmp_path / "report.txt"

        with pytest.raises(ReportError, match="must have .pdf extension"):
            generate_pdf_report(
                analysis_results=sample_analysis,
                recommendations=sample_recommendations,
                overall_health="HEALTHY",
                output_path=output,
            )


class TestGenerateComparisonPdfReport:
    """Tests for comparison PDF report generation."""

    @pytest.fixture
    def sample_comparison(self):
        """Sample comparison results."""
        return {
            "industry": "manufacturing",
            "metrics_compared": 3,
            "only_in_before": ["old_metric"],
            "only_in_after": ["new_metric"],
            "comparisons": [
                {
                    "metric": "accuracy",
                    "before_value": 0.75,
                    "after_value": 0.82,
                    "change_percent": 9.3,
                    "improved": True,
                    "direction": "up",
                },
                {
                    "metric": "latency_ms",
                    "before_value": 200,
                    "after_value": 150,
                    "change_percent": -25.0,
                    "improved": True,
                    "direction": "down",
                },
                {
                    "metric": "error_rate",
                    "before_value": 0.05,
                    "after_value": 0.08,
                    "change_percent": 60.0,
                    "improved": False,
                    "direction": "up",
                },
            ],
            "summary": {
                "improved": 2,
                "declined": 1,
                "unchanged": 0,
            },
        }

    def test_generates_comparison_pdf(self, tmp_path, sample_comparison):
        """Generates a valid comparison PDF."""
        output = tmp_path / "comparison.pdf"

        result = generate_comparison_pdf_report(
            comparison_results=sample_comparison,
            output_path=output,
        )

        assert result.exists()
        assert result.stat().st_size > 0
        content = result.read_bytes()
        assert content.startswith(b"%PDF")

    def test_with_custom_title(self, tmp_path, sample_comparison):
        """Generates comparison PDF with custom title."""
        output = tmp_path / "custom_compare.pdf"

        result = generate_comparison_pdf_report(
            comparison_results=sample_comparison,
            output_path=output,
            title="Q1 vs Q2 Comparison",
        )

        assert result.exists()

    def test_with_project_name(self, tmp_path, sample_comparison):
        """Generates comparison PDF with project name."""
        output = tmp_path / "project_compare.pdf"

        result = generate_comparison_pdf_report(
            comparison_results=sample_comparison,
            output_path=output,
            project_name="my-project",
        )

        assert result.exists()

    def test_empty_comparisons(self, tmp_path):
        """Handles empty comparisons."""
        output = tmp_path / "empty_compare.pdf"

        result = generate_comparison_pdf_report(
            comparison_results={
                "industry": "general",
                "metrics_compared": 0,
                "only_in_before": [],
                "only_in_after": [],
                "comparisons": [],
                "summary": {"improved": 0, "declined": 0, "unchanged": 0},
            },
            output_path=output,
        )

        assert result.exists()


class TestReportSecurity:
    """Security tests for report generation."""

    def test_sanitizes_title(self, tmp_path):
        """Title is sanitized for control characters."""
        output = tmp_path / "test.pdf"

        # Should not raise, control chars should be stripped
        result = generate_pdf_report(
            analysis_results={"industry": "general", "metrics_analyzed": 0, "metrics_with_benchmarks": 0, "analysis": []},
            recommendations=[],
            overall_health="HEALTHY",
            output_path=output,
            title="Title\x00with\x01control\x02chars",
        )

        assert result.exists()

    def test_truncates_long_description(self, tmp_path):
        """Long descriptions are truncated."""
        output = tmp_path / "test.pdf"

        long_desc = "x" * 5000

        result = generate_pdf_report(
            analysis_results={"industry": "general", "metrics_analyzed": 0, "metrics_with_benchmarks": 0, "analysis": []},
            recommendations=[],
            overall_health="HEALTHY",
            output_path=output,
            description=long_desc,
        )

        assert result.exists()

    def test_limits_recommendations_count(self, tmp_path):
        """Too many recommendations raises error."""
        output = tmp_path / "test.pdf"

        many_recs = [
            {
                "metric": f"metric_{i}",
                "priority": "LOW",
                "current_value": 0.5,
                "benchmark_p50": 0.5,
                "gap_percent": 0,
                "effort": "LOW",
                "recommendation": "Test",
            }
            for i in range(600)  # Exceeds MAX_METRICS_IN_REPORT
        ]

        with pytest.raises(ReportError, match="Too many recommendations"):
            generate_pdf_report(
                analysis_results={"industry": "general", "metrics_analyzed": 0, "metrics_with_benchmarks": 0, "analysis": []},
                recommendations=many_recs,
                overall_health="HEALTHY",
                output_path=output,
            )
