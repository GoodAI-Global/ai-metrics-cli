"""
Benchmark data loading and management.

Loads industry benchmarks from external JSON file - never hardcoded.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class BenchmarkError(Exception):
    """Raised when benchmark data cannot be loaded or is invalid."""
    pass


def get_benchmarks_path() -> Path:
    """Get the path to the benchmarks directory."""
    # First check relative to this file (for installed package)
    package_dir = Path(__file__).parent
    benchmarks_path = package_dir.parent.parent / "benchmarks" / "industry_data.json"

    if benchmarks_path.exists():
        return benchmarks_path

    # Check relative to current working directory
    cwd_path = Path.cwd() / "benchmarks" / "industry_data.json"
    if cwd_path.exists():
        return cwd_path

    raise BenchmarkError(
        f"Benchmark file not found. Searched:\n"
        f"  - {benchmarks_path}\n"
        f"  - {cwd_path}\n"
        "Please ensure benchmarks/industry_data.json exists."
    )


def load_benchmarks(filepath: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load industry benchmarks from JSON file.

    Args:
        filepath: Optional path to benchmark file. If None, uses default location.

    Returns:
        Dictionary containing all industry benchmarks.

    Raises:
        BenchmarkError: If file cannot be loaded or parsed.
    """
    if filepath is None:
        filepath = get_benchmarks_path()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise BenchmarkError(f"Benchmark file not found: {filepath}")
    except json.JSONDecodeError as e:
        raise BenchmarkError(f"Invalid JSON in benchmark file: {e}")

    # Validate structure
    if not isinstance(data, dict):
        raise BenchmarkError("Benchmark file must contain a JSON object at root level")

    for industry, metrics in data.items():
        if not isinstance(metrics, dict):
            raise BenchmarkError(f"Industry '{industry}' must contain a metrics object")
        for metric_name, percentiles in metrics.items():
            if not isinstance(percentiles, dict):
                raise BenchmarkError(
                    f"Metric '{metric_name}' in '{industry}' must contain percentile data"
                )
            required_keys = {"p25", "p50", "p75", "p90"}
            if not required_keys.issubset(percentiles.keys()):
                missing = required_keys - set(percentiles.keys())
                raise BenchmarkError(
                    f"Metric '{metric_name}' in '{industry}' missing percentiles: {missing}"
                )

    return data


def get_benchmark_for_industry(industry: str, benchmarks: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Get benchmark data for a specific industry.

    Args:
        industry: Industry name (e.g., 'manufacturing', 'insurance')
        benchmarks: Optional pre-loaded benchmarks. If None, loads from file.

    Returns:
        Dictionary containing metrics and their percentile benchmarks.

    Raises:
        BenchmarkError: If industry not found.
    """
    if benchmarks is None:
        benchmarks = load_benchmarks()

    if industry not in benchmarks:
        available = ", ".join(sorted(benchmarks.keys()))
        raise BenchmarkError(
            f"Unknown industry: '{industry}'. Available: {available}"
        )

    return benchmarks[industry]


def get_available_industries(benchmarks: Optional[Dict] = None) -> list:
    """
    Get list of available industries.

    Args:
        benchmarks: Optional pre-loaded benchmarks.

    Returns:
        Sorted list of industry names.
    """
    if benchmarks is None:
        benchmarks = load_benchmarks()

    return sorted(benchmarks.keys())


def get_percentile_rank(value: float, benchmark: Dict[str, float], higher_is_better: bool = True) -> str:
    """
    Determine which percentile bracket a value falls into.

    Args:
        value: The metric value to rank.
        benchmark: Dictionary with p25, p50, p75, p90 values.
        higher_is_better: If True, higher values are better (e.g., accuracy).
                         If False, lower values are better (e.g., latency).

    Returns:
        String indicating percentile bracket (e.g., "below_p25", "p50_to_p75").
    """
    if higher_is_better:
        if value >= benchmark["p90"]:
            return "above_p90"
        elif value >= benchmark["p75"]:
            return "p75_to_p90"
        elif value >= benchmark["p50"]:
            return "p50_to_p75"
        elif value >= benchmark["p25"]:
            return "p25_to_p50"
        else:
            return "below_p25"
    else:
        # For metrics where lower is better (e.g., latency, error_rate)
        if value <= benchmark["p90"]:
            return "above_p90"
        elif value <= benchmark["p75"]:
            return "p75_to_p90"
        elif value <= benchmark["p50"]:
            return "p50_to_p75"
        elif value <= benchmark["p25"]:
            return "p25_to_p50"
        else:
            return "below_p25"
