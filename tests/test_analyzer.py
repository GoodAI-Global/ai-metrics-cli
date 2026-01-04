"""Tests for the analyzer module."""

import csv
import tempfile
from pathlib import Path

import pytest

from goodai_metrics.analyzer import (
    MetricsAnalyzer,
    AnalysisError,
    analyze_metrics,
    compare_metrics,
    MetricValue
)
from goodai_metrics.benchmarks import load_benchmarks


def create_temp_csv(rows: list, headers: list = None) -> Path:
    """Create a temporary CSV file with given data."""
    if headers is None:
        headers = ["metric", "value", "timestamp"]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return Path(f.name)


class TestBenchmarkLoading:
    """Tests for benchmark loading functionality."""

    def test_benchmark_loading(self):
        """JSON loads correctly with expected structure."""
        benchmarks = load_benchmarks()

        # Check that main industries exist
        assert "manufacturing" in benchmarks
        assert "insurance" in benchmarks
        assert "general" in benchmarks

        # Check structure of manufacturing benchmarks
        mfg = benchmarks["manufacturing"]
        assert "accuracy" in mfg
        assert "latency_ms" in mfg

        # Check percentile structure
        accuracy = mfg["accuracy"]
        assert "p25" in accuracy
        assert "p50" in accuracy
        assert "p75" in accuracy
        assert "p90" in accuracy

        # Check values are sensible
        assert 0 < accuracy["p25"] < accuracy["p50"] < accuracy["p75"] < accuracy["p90"] <= 1


class TestMetricsAnalyzer:
    """Tests for MetricsAnalyzer class."""

    def test_load_valid_csv(self):
        """Loading valid CSV returns correct metrics."""
        rows = [
            {"metric": "accuracy", "value": "0.92", "timestamp": "2025-01-01"},
            {"metric": "latency_ms", "value": "150", "timestamp": "2025-01-01"},
        ]
        csv_path = create_temp_csv(rows)

        try:
            analyzer = MetricsAnalyzer(industry="manufacturing")
            metrics = analyzer.load_csv(csv_path)

            assert len(metrics) == 2
            assert metrics[0].name == "accuracy"
            assert metrics[0].value == 0.92
            assert metrics[1].name == "latency_ms"
            assert metrics[1].value == 150.0
        finally:
            csv_path.unlink()

    def test_missing_columns_error(self):
        """Missing required columns raise helpful error."""
        # Create CSV without 'value' column
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "other"])
            writer.writeheader()
            writer.writerow({"metric": "accuracy", "other": "123"})
            csv_path = Path(f.name)

        try:
            analyzer = MetricsAnalyzer()
            with pytest.raises(AnalysisError) as exc_info:
                analyzer.load_csv(csv_path)

            error_msg = str(exc_info.value)
            assert "Missing required columns" in error_msg
            assert "value" in error_msg
        finally:
            csv_path.unlink()

    def test_analyze_returns_correct_structure(self):
        """Analysis returns expected structure."""
        rows = [
            {"metric": "accuracy", "value": "0.85", "timestamp": "2025-01-01"},
        ]
        csv_path = create_temp_csv(rows)

        try:
            analyzer = MetricsAnalyzer(industry="manufacturing")
            metrics = analyzer.load_csv(csv_path)
            results = analyzer.analyze(metrics)

            assert "industry" in results
            assert results["industry"] == "manufacturing"
            assert "metrics_analyzed" in results
            assert results["metrics_analyzed"] == 1
            assert "analysis" in results
            assert len(results["analysis"]) == 1
        finally:
            csv_path.unlink()

    def test_empty_csv_error(self):
        """Empty CSV file raises error."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value"])
            writer.writeheader()  # Only header, no data
            csv_path = Path(f.name)

        try:
            analyzer = MetricsAnalyzer()
            with pytest.raises(AnalysisError) as exc_info:
                analyzer.load_csv(csv_path)

            assert "no data rows" in str(exc_info.value)
        finally:
            csv_path.unlink()


class TestCompareMetrics:
    """Tests for compare_metrics function."""

    def test_compare_metrics_improvement(self):
        """Compare detects improvement in metrics."""
        before_rows = [
            {"metric": "accuracy", "value": "0.80", "timestamp": "2025-01-01"},
            {"metric": "latency_ms", "value": "300", "timestamp": "2025-01-01"},
        ]
        after_rows = [
            {"metric": "accuracy", "value": "0.90", "timestamp": "2025-02-01"},
            {"metric": "latency_ms", "value": "150", "timestamp": "2025-02-01"},
        ]

        before_path = create_temp_csv(before_rows)
        after_path = create_temp_csv(after_rows)

        try:
            results = compare_metrics(before_path, after_path, industry="manufacturing")

            assert results["metrics_compared"] == 2
            assert results["summary"]["improved"] == 2

            # Check accuracy improved
            accuracy_comp = next(c for c in results["comparisons"] if c["metric"] == "accuracy")
            assert accuracy_comp["improved"] is True
            assert accuracy_comp["change_percent"] > 0

            # Check latency improved (lower is better)
            latency_comp = next(c for c in results["comparisons"] if c["metric"] == "latency_ms")
            assert latency_comp["improved"] is True
        finally:
            before_path.unlink()
            after_path.unlink()
