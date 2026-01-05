"""
Good AI Metrics CLI - Enterprise AI Implementation Analytics

A production CLI tool for analyzing AI implementation metrics
and producing actionable recommendations.

Core Principles:
- Evidence over opinions: Recommendations tied to measurable gaps
- Leverage, not lore: Practical tool, not framework
- No fantasy metrics: Conservative benchmarks from real implementations
"""

__version__ = "1.0.0"
__author__ = "rogermsc"

from .benchmarks import (
    load_benchmarks,
    get_benchmark_for_industry,
    get_available_industries,
    get_percentile_rank,
    BenchmarkError,
)
from .analyzer import (
    analyze_metrics,
    compare_metrics,
    MetricsAnalyzer,
    MetricValue,
    AnalysisError,
)
from .recommendations import (
    generate_recommendation,
    generate_all_recommendations,
    determine_overall_health,
    check_health_thresholds,
    calculate_gap,
    is_higher_better,
    determine_priority,
    determine_effort,
)
from .formatters import (
    format_report_json,
    format_report_text,
    format_health_check,
    format_comparison_json,
    format_comparison_text,
)
from .config import (
    load_config,
    find_config_file,
    ProjectConfig,
    ThresholdsConfig,
    NotificationsConfig,
    CustomTarget,
    ConfigError,
)
from .storage import (
    MetricsStorage,
    AnalysisRecord,
    MetricHistory,
    StorageError,
)
from .logging_config import (
    setup_logging,
    get_logger,
    set_context_id,
    clear_context_id,
    timed,
    JSONFormatter,
    HumanFormatter,
    ContextLogger,
)

__all__ = [
    # Package metadata
    "__version__",
    "__author__",
    # Benchmarks
    "load_benchmarks",
    "get_benchmark_for_industry",
    "get_available_industries",
    "get_percentile_rank",
    "BenchmarkError",
    # Analyzer
    "analyze_metrics",
    "compare_metrics",
    "MetricsAnalyzer",
    "MetricValue",
    "AnalysisError",
    # Recommendations
    "generate_recommendation",
    "generate_all_recommendations",
    "determine_overall_health",
    "check_health_thresholds",
    "calculate_gap",
    "is_higher_better",
    "determine_priority",
    "determine_effort",
    # Formatters
    "format_report_json",
    "format_report_text",
    "format_health_check",
    "format_comparison_json",
    "format_comparison_text",
    # Config
    "load_config",
    "find_config_file",
    "ProjectConfig",
    "ThresholdsConfig",
    "NotificationsConfig",
    "CustomTarget",
    "ConfigError",
    # Storage
    "MetricsStorage",
    "AnalysisRecord",
    "MetricHistory",
    "StorageError",
    # Logging
    "setup_logging",
    "get_logger",
    "set_context_id",
    "clear_context_id",
    "timed",
    "JSONFormatter",
    "HumanFormatter",
    "ContextLogger",
]
