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

from .analyzer import (
    AnalysisError,
    MetricsAnalyzer,
    MetricValue,
    analyze_metrics,
    compare_metrics,
)
from .benchmarks import (
    BenchmarkError,
    create_custom_industry,
    get_available_industries,
    get_benchmark_for_industry,
    get_percentile_rank,
    load_benchmark_file,
    load_benchmarks,
    load_benchmarks_with_custom,
    merge_benchmarks,
    validate_benchmark_data,
)
from .config import (
    ConfigError,
    CustomBenchmark,
    CustomTarget,
    NotificationsConfig,
    ProjectConfig,
    ThresholdsConfig,
    find_config_file,
    load_config,
)
from .formatters import (
    format_comparison_json,
    format_comparison_text,
    format_health_check,
    format_report_json,
    format_report_text,
)
from .logging_config import (
    ContextLogger,
    HumanFormatter,
    JSONFormatter,
    clear_context_id,
    get_logger,
    set_context_id,
    setup_logging,
    timed,
)
from .recommendations import (
    calculate_gap,
    check_health_thresholds,
    determine_effort,
    determine_overall_health,
    determine_priority,
    generate_all_recommendations,
    generate_recommendation,
    is_higher_better,
)
from .storage import (
    AnalysisRecord,
    MetricHistory,
    MetricsStorage,
    StorageError,
)

# API is optional (requires server extras)
try:
    from .api import app as api_app
    from .api import create_app

    _HAS_API = True
except ImportError:
    _HAS_API = False
    create_app = None
    api_app = None

# Reports are optional (requires reports extras)
try:
    from .reports import (
        ReportError,
        generate_comparison_pdf_report,
        generate_pdf_report,
    )

    _HAS_REPORTS = True
except ImportError:
    _HAS_REPORTS = False
    generate_pdf_report = None
    generate_comparison_pdf_report = None
    ReportError = None

# Notifications
# CI/CD Integration
from .cicd import (
    EXIT_ANALYSIS_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_SUCCESS,
    EXIT_THRESHOLD_FAILURE,
    CICDError,
    batch_check_files,
    format_summary_table,
    generate_github_annotations,
    generate_gitlab_ci_report,
    generate_junit_xml,
    get_exit_code,
)
from .notifications import (
    NotificationError,
    is_slack_webhook,
    notify_analysis_complete,
    notify_regression_detected,
    notify_threshold_breach,
    send_slack_notification,
    send_webhook_notification,
)

__all__ = [
    # Package metadata
    "__version__",
    "__author__",
    # Benchmarks
    "load_benchmarks",
    "load_benchmarks_with_custom",
    "load_benchmark_file",
    "merge_benchmarks",
    "validate_benchmark_data",
    "create_custom_industry",
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
    "CustomBenchmark",
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
    # API (optional)
    "create_app",
    "api_app",
    # Reports (optional)
    "generate_pdf_report",
    "generate_comparison_pdf_report",
    "ReportError",
    # Notifications
    "send_webhook_notification",
    "send_slack_notification",
    "notify_analysis_complete",
    "notify_threshold_breach",
    "notify_regression_detected",
    "is_slack_webhook",
    "NotificationError",
    # CI/CD Integration
    "generate_junit_xml",
    "generate_github_annotations",
    "generate_gitlab_ci_report",
    "get_exit_code",
    "format_summary_table",
    "batch_check_files",
    "CICDError",
    "EXIT_SUCCESS",
    "EXIT_THRESHOLD_FAILURE",
    "EXIT_ANALYSIS_ERROR",
    "EXIT_CONFIG_ERROR",
]
