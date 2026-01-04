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

from .benchmarks import load_benchmarks, get_benchmark_for_industry
from .analyzer import analyze_metrics, MetricsAnalyzer
from .recommendations import generate_recommendation, generate_all_recommendations
from .formatters import format_report_json, format_report_text

__all__ = [
    "__version__",
    "load_benchmarks",
    "get_benchmark_for_industry",
    "analyze_metrics",
    "MetricsAnalyzer",
    "generate_recommendation",
    "generate_all_recommendations",
    "format_report_json",
    "format_report_text",
]
