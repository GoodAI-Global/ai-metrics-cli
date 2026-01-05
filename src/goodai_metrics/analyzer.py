"""
Metrics analysis engine.

Loads CSV data, validates columns, and compares against industry benchmarks.
"""

import csv
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .benchmarks import (
    load_benchmarks,
    load_benchmarks_with_custom,
    get_benchmark_for_industry,
    get_percentile_rank,
    BenchmarkError,
)

# Import consolidated utility functions (single source of truth)
# Note: Imported here to avoid duplication; recommendations.py is the authoritative source
from .recommendations import is_higher_better, calculate_gap


class AnalysisError(Exception):
    """Raised when metrics analysis fails."""
    pass


@dataclass
class MetricValue:
    """A single metric measurement."""
    name: str
    value: float
    timestamp: Optional[str] = None


class MetricsAnalyzer:
    """
    Analyzes AI implementation metrics against industry benchmarks.

    Implements the 'Evidence over opinions' principle by comparing
    actual values to real-world percentile data.
    """

    REQUIRED_COLUMNS = {"metric", "value"}

    def __init__(
        self,
        industry: str = "general",
        custom_benchmarks: Optional[Dict[str, Dict[str, Any]]] = None,
        benchmark_files: Optional[List[Path]] = None,
    ):
        """
        Initialize analyzer for a specific industry.

        Args:
            industry: Industry name for benchmark comparison.
            custom_benchmarks: Optional custom benchmark overrides (from config).
            benchmark_files: Optional list of additional benchmark files to load.
        """
        self.industry = industry
        self._custom_benchmarks = custom_benchmarks
        self._benchmark_files = benchmark_files
        self._benchmarks = None
        self._industry_benchmarks = None

    @property
    def benchmarks(self) -> Dict:
        """Lazy-load benchmarks, including any custom sources."""
        if self._benchmarks is None:
            if self._custom_benchmarks or self._benchmark_files:
                # Load with custom sources merged in
                self._benchmarks = load_benchmarks_with_custom(
                    base_filepath=None,
                    additional_files=self._benchmark_files,
                    custom_benchmarks=self._custom_benchmarks,
                )
            else:
                # Load base benchmarks only
                self._benchmarks = load_benchmarks()
        return self._benchmarks

    @property
    def industry_benchmarks(self) -> Dict:
        """Get benchmarks for the configured industry."""
        if self._industry_benchmarks is None:
            self._industry_benchmarks = get_benchmark_for_industry(
                self.industry, self.benchmarks
            )
        return self._industry_benchmarks

    def load_csv(self, filepath: Path) -> List[MetricValue]:
        """
        Load metrics from CSV file.

        Args:
            filepath: Path to CSV file.

        Returns:
            List of MetricValue objects.

        Raises:
            AnalysisError: If file cannot be loaded or is invalid.
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise AnalysisError(f"File not found: {filepath}")

        if not filepath.suffix.lower() == ".csv":
            raise AnalysisError(f"Expected CSV file, got: {filepath.suffix}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                if reader.fieldnames is None:
                    raise AnalysisError("CSV file is empty or has no headers")

                # Validate required columns
                columns = set(reader.fieldnames)
                missing = self.REQUIRED_COLUMNS - columns
                if missing:
                    raise AnalysisError(
                        f"Missing required columns: {', '.join(sorted(missing))}. "
                        f"Found columns: {', '.join(sorted(columns))}"
                    )

                metrics = []
                for row_num, row in enumerate(reader, start=2):  # Start at 2 for header
                    try:
                        value = float(row["value"])
                    except (ValueError, TypeError):
                        raise AnalysisError(
                            f"Invalid value on row {row_num}: '{row.get('value')}' "
                            "is not a number"
                        )

                    metrics.append(MetricValue(
                        name=row["metric"].strip(),
                        value=value,
                        timestamp=row.get("timestamp", "").strip() or None
                    ))

                if not metrics:
                    raise AnalysisError("CSV file contains no data rows")

                return metrics

        except csv.Error as e:
            raise AnalysisError(f"CSV parsing error: {e}")

    def analyze(self, metrics: List[MetricValue]) -> Dict[str, Any]:
        """
        Analyze metrics against industry benchmarks.

        Args:
            metrics: List of MetricValue objects.

        Returns:
            Analysis results dictionary.
        """
        results = {
            "industry": self.industry,
            "metrics_analyzed": 0,
            "metrics_with_benchmarks": 0,
            "metrics_without_benchmarks": [],
            "analysis": []
        }

        for metric in metrics:
            results["metrics_analyzed"] += 1

            if metric.name in self.industry_benchmarks:
                results["metrics_with_benchmarks"] += 1
                benchmark = self.industry_benchmarks[metric.name]

                analysis = self._analyze_metric(metric, benchmark)
                results["analysis"].append(analysis)
            else:
                results["metrics_without_benchmarks"].append(metric.name)

        return results

    def analyze_dict(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        Analyze metrics from a dictionary.

        Convenience method for API usage where metrics come as key-value pairs.

        Args:
            metrics: Dictionary mapping metric names to values.

        Returns:
            Analysis results dictionary.
        """
        metric_values = [
            MetricValue(name=name, value=value)
            for name, value in metrics.items()
        ]
        return self.analyze(metric_values)

    def _analyze_metric(self, metric: MetricValue, benchmark: Dict) -> Dict[str, Any]:
        """
        Analyze a single metric against its benchmark.

        Args:
            metric: The metric to analyze.
            benchmark: Benchmark percentile data.

        Returns:
            Analysis dictionary for this metric.
        """
        # Determine if higher is better based on metric name
        higher_better = is_higher_better(metric.name)

        # Calculate gap from p50 (median) using consolidated function
        gap = calculate_gap(metric.value, benchmark["p50"], higher_better)

        # Determine percentile bracket using consolidated function
        percentile_bracket = get_percentile_rank(
            metric.value, benchmark, higher_better
        )

        return {
            "metric": metric.name,
            "current_value": metric.value,
            "timestamp": metric.timestamp,
            "benchmark_p25": benchmark["p25"],
            "benchmark_p50": benchmark["p50"],
            "benchmark_p75": benchmark["p75"],
            "benchmark_p90": benchmark["p90"],
            "gap_from_p50": gap,
            "gap_percent": abs(gap) * 100,
            "percentile_bracket": percentile_bracket,
            "higher_is_better": higher_better,
            "needs_improvement": gap > 0
        }


def analyze_metrics(
    filepath: Path,
    industry: str = "general",
    custom_benchmarks: Optional[Dict[str, Dict[str, Any]]] = None,
    benchmark_files: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to analyze metrics from a CSV file.

    Args:
        filepath: Path to CSV file.
        industry: Industry for benchmark comparison.
        custom_benchmarks: Optional custom benchmark overrides.
        benchmark_files: Optional additional benchmark files.

    Returns:
        Analysis results dictionary.
    """
    analyzer = MetricsAnalyzer(
        industry=industry,
        custom_benchmarks=custom_benchmarks,
        benchmark_files=benchmark_files,
    )
    metrics = analyzer.load_csv(filepath)
    return analyzer.analyze(metrics)


def compare_metrics(
    before_file: Path,
    after_file: Path,
    industry: str = "general",
    custom_benchmarks: Optional[Dict[str, Dict[str, Any]]] = None,
    benchmark_files: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """
    Compare metrics between two time periods.

    Args:
        before_file: Path to CSV with earlier metrics.
        after_file: Path to CSV with later metrics.
        industry: Industry for context.
        custom_benchmarks: Optional custom benchmark overrides.
        benchmark_files: Optional additional benchmark files.

    Returns:
        Comparison results dictionary.
    """
    analyzer = MetricsAnalyzer(
        industry=industry,
        custom_benchmarks=custom_benchmarks,
        benchmark_files=benchmark_files,
    )

    before_metrics = analyzer.load_csv(before_file)
    after_metrics = analyzer.load_csv(after_file)

    # Create lookup dictionaries
    before_lookup = {m.name: m.value for m in before_metrics}
    after_lookup = {m.name: m.value for m in after_metrics}

    # Find common metrics
    common_metrics = set(before_lookup.keys()) & set(after_lookup.keys())

    comparisons = []
    for metric_name in sorted(common_metrics):
        before_val = before_lookup[metric_name]
        after_val = after_lookup[metric_name]

        # Calculate change
        if before_val != 0:
            change_percent = ((after_val - before_val) / abs(before_val)) * 100
        else:
            change_percent = 100.0 if after_val != 0 else 0.0

        higher_better = is_higher_better(metric_name)

        # Determine if this is an improvement
        if higher_better:
            improved = after_val > before_val
        else:
            improved = after_val < before_val

        comparisons.append({
            "metric": metric_name,
            "before_value": before_val,
            "after_value": after_val,
            "change_percent": change_percent,
            "improved": improved,
            "direction": "up" if after_val > before_val else "down" if after_val < before_val else "unchanged"
        })

    return {
        "industry": industry,
        "metrics_compared": len(comparisons),
        "only_in_before": list(set(before_lookup.keys()) - common_metrics),
        "only_in_after": list(set(after_lookup.keys()) - common_metrics),
        "comparisons": comparisons,
        "summary": {
            "improved": sum(1 for c in comparisons if c["improved"]),
            "declined": sum(1 for c in comparisons if not c["improved"] and c["direction"] != "unchanged"),
            "unchanged": sum(1 for c in comparisons if c["direction"] == "unchanged")
        }
    }
