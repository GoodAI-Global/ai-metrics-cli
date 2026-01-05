"""Tests for the CLI module."""

import csv
import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from goodai_metrics.cli import main


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_csv():
    """Create a temporary sample CSV file."""
    rows = [
        {"metric": "accuracy", "value": "0.87", "timestamp": "2025-01-01"},
        {"metric": "latency_ms", "value": "350", "timestamp": "2025-01-01"},
        {"metric": "error_rate", "value": "0.11", "timestamp": "2025-01-01"},
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        path = Path(f.name)

    yield path

    # Cleanup
    if path.exists():
        path.unlink()


class TestCliSample:
    """Tests for --sample flag."""

    def test_sample_manufacturing(self, runner):
        """--sample manufacturing works without file."""
        result = runner.invoke(main, ["analyze", "--sample", "manufacturing"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Parse output as JSON
        output = json.loads(result.output)
        assert "summary" in output
        assert output["summary"]["industry"] == "manufacturing"

    def test_sample_insurance(self, runner):
        """--sample insurance works without file."""
        result = runner.invoke(main, ["analyze", "--sample", "insurance"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert output["summary"]["industry"] == "insurance"

    def test_sample_with_text_format(self, runner):
        """--sample works with text format."""
        result = runner.invoke(
            main, ["analyze", "--sample", "manufacturing", "-f", "text"]
        )

        assert result.exit_code == 0
        assert "GOOD AI METRICS ANALYSIS REPORT" in result.output
        assert "manufacturing" in result.output


class TestCliAnalyze:
    """Tests for analyze command."""

    def test_analyze_csv_file(self, runner, sample_csv):
        """Analyze command works with CSV file."""
        result = runner.invoke(
            main, ["analyze", str(sample_csv), "--industry", "manufacturing"]
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        output = json.loads(result.output)
        assert output["summary"]["metrics_analyzed"] == 3

    def test_analyze_missing_file(self, runner):
        """Missing file gives helpful error."""
        result = runner.invoke(main, ["analyze", "nonexistent.csv"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_analyze_no_args_error(self, runner):
        """No arguments gives error."""
        result = runner.invoke(main, ["analyze"])

        assert result.exit_code != 0
        assert "file" in result.output.lower() or "sample" in result.output.lower()


class TestCliHealth:
    """Tests for health command."""

    def test_health_pass(self, runner, sample_csv):
        """Health check can pass."""
        # Create a CSV that will pass (values close to benchmarks)
        rows = [
            {"metric": "accuracy", "value": "0.92", "timestamp": "2025-01-01"},
            {"metric": "latency_ms", "value": "200", "timestamp": "2025-01-01"},
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            good_csv = Path(f.name)

        try:
            result = runner.invoke(
                main,
                ["health", str(good_csv), "--industry", "manufacturing", "--max-high-priority", "0"]
            )

            assert "PASSED" in result.output
        finally:
            good_csv.unlink()

    def test_health_fail(self, runner):
        """Health check can fail."""
        # Create a CSV with poor values
        rows = [
            {"metric": "accuracy", "value": "0.50", "timestamp": "2025-01-01"},
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            bad_csv = Path(f.name)

        try:
            result = runner.invoke(
                main, ["health", str(bad_csv), "--industry", "manufacturing"]
            )

            assert result.exit_code == 1
            assert "FAILED" in result.output
        finally:
            bad_csv.unlink()


class TestCliCompare:
    """Tests for compare command."""

    def test_compare_two_files(self, runner):
        """Compare command works with two files."""
        before_rows = [
            {"metric": "accuracy", "value": "0.80", "timestamp": "2025-01-01"},
        ]
        after_rows = [
            {"metric": "accuracy", "value": "0.90", "timestamp": "2025-02-01"},
        ]

        before_path = None
        after_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
            ) as f:
                writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
                writer.writeheader()
                for row in before_rows:
                    writer.writerow(row)
                before_path = Path(f.name)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
            ) as f:
                writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
                writer.writeheader()
                for row in after_rows:
                    writer.writerow(row)
                after_path = Path(f.name)

            result = runner.invoke(
                main, ["compare", str(before_path), str(after_path)]
            )

            assert result.exit_code == 0
            output = json.loads(result.output)
            assert output["metrics_compared"] == 1
            assert output["summary"]["improved"] == 1

        finally:
            if before_path and before_path.exists():
                before_path.unlink()
            if after_path and after_path.exists():
                after_path.unlink()


class TestCliListIndustries:
    """Tests for list-industries command."""

    def test_list_industries(self, runner):
        """list-industries shows available industries."""
        result = runner.invoke(main, ["list-industries"])

        assert result.exit_code == 0
        assert "manufacturing" in result.output
        assert "insurance" in result.output
        assert "general" in result.output


class TestNotificationIntegration:
    """Tests for notification integration in CLI."""

    def test_analyze_without_notifications_config(self, runner, sample_csv):
        """Analyze works without notifications configured."""
        result = runner.invoke(
            main, ["analyze", str(sample_csv), "--industry", "manufacturing"]
        )

        assert result.exit_code == 0
        # Should not have any notification errors
        assert "Failed to send" not in result.output

    def test_send_analysis_notifications_no_config(self):
        """_send_analysis_notifications handles missing config gracefully."""
        from goodai_metrics.cli import _send_analysis_notifications
        from goodai_metrics.config import ProjectConfig

        # Should not raise when no notifications configured
        config = ProjectConfig()

        _send_analysis_notifications(
            config=config,
            analysis_results={"metrics_analyzed": 1, "industry": "general"},
            recommendations=[],
            overall_health="HEALTHY",
            regressions=[],
        )
        # Test passes if no exception raised

    def test_send_analysis_notifications_no_webhook(self):
        """_send_analysis_notifications handles empty webhook gracefully."""
        from goodai_metrics.cli import _send_analysis_notifications
        from goodai_metrics.config import ProjectConfig, NotificationsConfig

        config = ProjectConfig(
            notifications=NotificationsConfig(
                on_regression=True,
                on_threshold_breach=True,
                webhook_url=None,  # No webhook
            )
        )

        # Should not raise when webhook is None
        _send_analysis_notifications(
            config=config,
            analysis_results={"metrics_analyzed": 1, "industry": "general"},
            recommendations=[{"priority": "HIGH", "metric": "test", "current_value": 0.5}],
            overall_health="CRITICAL",
            regressions=[{"metric": "test", "current_gap_percent": 30}],
        )
        # Test passes if no exception raised
