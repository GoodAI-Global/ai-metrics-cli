"""
Benchmark data loading and management.

Loads industry benchmarks from external JSON file - never hardcoded.
Supports custom benchmarks from config files and additional JSON/YAML files.
"""

import json
import math
import re
from pathlib import Path
from typing import Any, Optional


class BenchmarkError(Exception):
    """Raised when benchmark data cannot be loaded or is invalid."""

    pass


# Required percentile keys for validation
REQUIRED_PERCENTILE_KEYS = {"p25", "p50", "p75", "p90"}

# Security limits
MAX_BENCHMARK_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_INDUSTRIES = 500
MAX_METRICS_PER_INDUSTRY = 200

# Valid name pattern for industries and metrics
VALID_NAME_PATTERN = re.compile(r"^[\w][\w_-]{0,99}$")


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


def load_benchmarks(filepath: Optional[Path] = None) -> dict[str, Any]:
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
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise BenchmarkError(f"Benchmark file not found: {filepath}") from None
    except json.JSONDecodeError as e:
        raise BenchmarkError(f"Invalid JSON in benchmark file: {e}") from e

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


def get_benchmark_for_industry(
    industry: str, benchmarks: Optional[dict] = None
) -> dict[str, Any]:
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
        raise BenchmarkError(f"Unknown industry: '{industry}'. Available: {available}")

    return benchmarks[industry]


def get_available_industries(benchmarks: Optional[dict] = None) -> list:
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


def get_percentile_rank(
    value: float, benchmark: dict[str, float], higher_is_better: bool = True
) -> str:
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


def validate_benchmark_data(
    data: dict[str, Any],
    source: str = "unknown",
    validate_names: bool = True,
) -> None:
    """
    Validate benchmark data structure.

    Args:
        data: Benchmark data to validate.
        source: Description of data source for error messages.
        validate_names: If True, validate industry/metric name format.

    Raises:
        BenchmarkError: If data structure is invalid.
    """
    if not isinstance(data, dict):
        raise BenchmarkError(f"{source}: Benchmark data must be a JSON object")

    # Check industry count limit
    if len(data) > MAX_INDUSTRIES:
        raise BenchmarkError(
            f"{source}: Too many industries ({len(data)}). Maximum is {MAX_INDUSTRIES}"
        )

    for industry, metrics in data.items():
        # Validate industry name format
        if validate_names and not VALID_NAME_PATTERN.match(str(industry)):
            raise BenchmarkError(
                f"{source}: Invalid industry name '{industry}'. "
                "Use only letters, numbers, underscores, and hyphens (max 100 chars)."
            )

        if not isinstance(metrics, dict):
            raise BenchmarkError(
                f"{source}: Industry '{industry}' must contain a metrics object"
            )

        # Check metric count limit
        if len(metrics) > MAX_METRICS_PER_INDUSTRY:
            raise BenchmarkError(
                f"{source}: Too many metrics in '{industry}' ({len(metrics)}). "
                f"Maximum is {MAX_METRICS_PER_INDUSTRY}"
            )

        for metric_name, percentiles in metrics.items():
            # Validate metric name format
            if validate_names and not VALID_NAME_PATTERN.match(str(metric_name)):
                raise BenchmarkError(
                    f"{source}: Invalid metric name '{metric_name}' in '{industry}'. "
                    "Use only letters, numbers, underscores, and hyphens (max 100 chars)."
                )

            if not isinstance(percentiles, dict):
                raise BenchmarkError(
                    f"{source}: Metric '{metric_name}' in '{industry}' must contain percentile data"
                )

            missing = REQUIRED_PERCENTILE_KEYS - set(percentiles.keys())
            if missing:
                raise BenchmarkError(
                    f"{source}: Metric '{metric_name}' in '{industry}' missing percentiles: {missing}"
                )

            # Validate numeric values (check for NaN/Inf)
            for key in REQUIRED_PERCENTILE_KEYS:
                try:
                    val = float(percentiles[key])
                    if math.isnan(val) or math.isinf(val):
                        raise BenchmarkError(
                            f"{source}: {industry}.{metric_name}.{key} must be a finite number"
                        )
                except (ValueError, TypeError):
                    raise BenchmarkError(
                        f"{source}: {industry}.{metric_name}.{key} must be a number"
                    ) from None


def load_benchmark_file(filepath: Path) -> dict[str, Any]:
    """
    Load benchmarks from a single JSON or YAML file.

    Args:
        filepath: Path to benchmark file.

    Returns:
        Dictionary containing benchmark data.

    Raises:
        BenchmarkError: If file cannot be loaded or is invalid.
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise BenchmarkError(f"Benchmark file not found: {filepath}")

    # Security: Validate path doesn't escape allowed directories
    if ".." in str(filepath):
        raise BenchmarkError(f"Benchmark file path cannot contain '..': {filepath}")

    # Security: Check file size before reading
    try:
        file_size = filepath.stat().st_size
        if file_size > MAX_BENCHMARK_FILE_SIZE:
            raise BenchmarkError(
                f"Benchmark file too large: {file_size} bytes "
                f"(max {MAX_BENCHMARK_FILE_SIZE // (1024 * 1024)} MB)"
            )
    except OSError as e:
        raise BenchmarkError(f"Cannot access benchmark file {filepath}: {e}") from e

    suffix = filepath.suffix.lower()

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BenchmarkError(f"Failed to read benchmark file {filepath}: {e}") from e

    if suffix == ".json":
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise BenchmarkError(f"Invalid JSON in {filepath}: {e}") from e

    elif suffix in (".yaml", ".yml"):
        try:
            import yaml

            data = yaml.safe_load(content)
        except ImportError:
            raise BenchmarkError(
                f"YAML file {filepath} requires PyYAML. Install with: pip install pyyaml"
            ) from None
        except Exception as e:
            raise BenchmarkError(f"Invalid YAML in {filepath}: {e}") from e
    else:
        raise BenchmarkError(
            f"Unsupported benchmark file format: {suffix}. Use .json, .yaml, or .yml"
        )

    if data is None:
        data = {}

    validate_benchmark_data(data, str(filepath))
    return data


def merge_benchmarks(*benchmark_dicts: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple benchmark dictionaries.

    Later dictionaries override earlier ones for matching industry/metric pairs.

    Args:
        *benchmark_dicts: Benchmark dictionaries to merge.

    Returns:
        Merged benchmark dictionary.
    """
    result: dict[str, dict[str, Any]] = {}

    for benchmarks in benchmark_dicts:
        if not benchmarks:
            continue

        for industry, metrics in benchmarks.items():
            if industry not in result:
                result[industry] = {}

            for metric_name, percentiles in metrics.items():
                result[industry][metric_name] = dict(percentiles)

    return result


def load_benchmarks_with_custom(
    base_filepath: Optional[Path] = None,
    additional_files: Optional[list[Path]] = None,
    custom_benchmarks: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Load benchmarks with optional custom overrides.

    Merges base benchmarks, additional files, and inline custom benchmarks.
    Later sources override earlier ones.

    Args:
        base_filepath: Path to base benchmark file. If None, uses default.
        additional_files: List of additional benchmark files to load.
        custom_benchmarks: Inline custom benchmarks (from config).

    Returns:
        Merged benchmark dictionary.

    Raises:
        BenchmarkError: If any benchmark file is invalid.
    """
    # Load base benchmarks
    base = load_benchmarks(base_filepath)

    # Collect all benchmark sources
    sources = [base]

    # Load additional files
    if additional_files:
        for filepath in additional_files:
            additional = load_benchmark_file(Path(filepath))
            sources.append(additional)

    # Add inline custom benchmarks
    if custom_benchmarks:
        sources.append(custom_benchmarks)

    # Merge all sources
    return merge_benchmarks(*sources)


def create_custom_industry(
    industry_name: str,
    metrics: dict[str, dict[str, float]],
) -> dict[str, dict[str, Any]]:
    """
    Create a custom industry benchmark definition.

    Convenience function for programmatically creating benchmarks.

    Args:
        industry_name: Name for the custom industry.
        metrics: Dict of metric_name -> {p25, p50, p75, p90}.

    Returns:
        Benchmark dict that can be merged with other benchmarks.

    Raises:
        BenchmarkError: If industry name or metric data is invalid.
    """
    # Validate industry name format
    if not VALID_NAME_PATTERN.match(str(industry_name)):
        raise BenchmarkError(
            f"Invalid industry name '{industry_name}'. "
            "Use only letters, numbers, underscores, and hyphens (max 100 chars)."
        )

    data = {industry_name: metrics}
    validate_benchmark_data(data, f"custom industry '{industry_name}'")
    return data
