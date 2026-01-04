"""
Good AI Metrics CLI - Command Line Interface.

Production CLI tool for analyzing AI implementation metrics.

Usage:
    goodai-metrics analyze <file.csv> [--industry <name>] [--format json|text]
    goodai-metrics analyze --sample <industry>
    goodai-metrics health <file.csv> [--industry <name>]
    goodai-metrics compare <before.csv> <after.csv> [--industry <name>]
"""

import sys
from pathlib import Path
from typing import Optional

import click

from .analyzer import MetricsAnalyzer, AnalysisError, compare_metrics
from .benchmarks import load_benchmarks, get_benchmark_for_industry, BenchmarkError
from .recommendations import (
    generate_all_recommendations,
    determine_overall_health,
    check_health_thresholds
)
from .formatters import (
    format_report_json,
    format_report_text,
    format_health_check,
    format_comparison_json,
    format_comparison_text
)


# Sample data mapping
SAMPLE_DATA_MAP = {
    "manufacturing": "manufacturing_metrics.csv",
    "insurance": "insurance_metrics.csv",
    "aquaculture": "manufacturing_metrics.csv",  # Use manufacturing as fallback
    "general": "manufacturing_metrics.csv"  # Use manufacturing as fallback
}


def get_sample_data_path(industry: str) -> Path:
    """Get the path to sample data for an industry."""
    filename = SAMPLE_DATA_MAP.get(industry, "manufacturing_metrics.csv")

    # Check relative to package
    package_dir = Path(__file__).parent
    sample_path = package_dir.parent.parent / "sample_data" / filename

    if sample_path.exists():
        return sample_path

    # Check relative to cwd
    cwd_path = Path.cwd() / "sample_data" / filename
    if cwd_path.exists():
        return cwd_path

    raise click.ClickException(
        f"Sample data not found for industry '{industry}'. "
        f"Searched: {sample_path}, {cwd_path}"
    )


@click.group()
@click.version_option(version="1.0.0", prog_name="goodai-metrics")
def main():
    """
    Good AI Metrics CLI - Enterprise AI Implementation Analytics.

    Evidence over opinions. Leverage, not lore.
    """
    pass


@main.command()
@click.argument("file", required=False, type=click.Path(exists=False))
@click.option(
    "--sample",
    type=click.Choice(["manufacturing", "insurance", "aquaculture", "general"]),
    help="Use built-in sample data for the specified industry"
)
@click.option(
    "--industry", "-i",
    default=None,
    help="Industry for benchmark comparison (auto-detected from --sample if used)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (default: json)"
)
def analyze(file: Optional[str], sample: Optional[str], industry: Optional[str], output_format: str):
    """
    Analyze AI metrics against industry benchmarks.

    Provide a CSV file path OR use --sample to use built-in data.

    Examples:

        goodai-metrics analyze metrics.csv --industry manufacturing

        goodai-metrics analyze --sample manufacturing

        goodai-metrics analyze data.csv -f text
    """
    # Determine file path
    if sample:
        filepath = get_sample_data_path(sample)
        if industry is None:
            industry = sample
    elif file:
        filepath = Path(file)
        if not filepath.exists():
            raise click.ClickException(f"File not found: {filepath}")
    else:
        raise click.ClickException(
            "Please provide a CSV file path or use --sample <industry>"
        )

    # Default industry
    if industry is None:
        industry = "general"

    try:
        # Load benchmarks
        benchmarks = load_benchmarks()
        industry_benchmarks = get_benchmark_for_industry(industry, benchmarks)

        # Analyze metrics
        analyzer = MetricsAnalyzer(industry=industry)
        metrics = analyzer.load_csv(filepath)
        analysis_results = analyzer.analyze(metrics)

        # Generate recommendations
        recommendations = generate_all_recommendations(analysis_results, industry_benchmarks)
        overall_health = determine_overall_health(recommendations)

        # Format output
        if output_format == "json":
            output = format_report_json(analysis_results, recommendations, overall_health)
        else:
            output = format_report_text(analysis_results, recommendations, overall_health)

        click.echo(output)

    except BenchmarkError as e:
        raise click.ClickException(f"Benchmark error: {e}")
    except AnalysisError as e:
        raise click.ClickException(f"Analysis error: {e}")


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--industry", "-i",
    default="general",
    help="Industry for benchmark comparison (default: general)"
)
@click.option(
    "--max-high-priority",
    default=0,
    type=int,
    help="Maximum allowed HIGH priority items (default: 0)"
)
@click.option(
    "--max-gap",
    default=30.0,
    type=float,
    help="Maximum allowed gap percentage (default: 30.0)"
)
def health(file: str, industry: str, max_high_priority: int, max_gap: float):
    """
    Quick health check for CI/CD pipelines.

    Exits with code 0 if all metrics pass thresholds.
    Exits with code 1 if any metric fails.

    Examples:

        goodai-metrics health metrics.csv

        goodai-metrics health metrics.csv --max-high-priority 1 --max-gap 50
    """
    filepath = Path(file)

    try:
        # Load benchmarks
        benchmarks = load_benchmarks()
        industry_benchmarks = get_benchmark_for_industry(industry, benchmarks)

        # Analyze metrics
        analyzer = MetricsAnalyzer(industry=industry)
        metrics = analyzer.load_csv(filepath)
        analysis_results = analyzer.analyze(metrics)

        # Generate recommendations
        recommendations = generate_all_recommendations(analysis_results, industry_benchmarks)

        # Check health thresholds
        health_result = check_health_thresholds(
            recommendations,
            max_high_priority=max_high_priority,
            max_gap_percent=max_gap
        )

        # Output result
        output = format_health_check(health_result)
        click.echo(output)

        # Exit with appropriate code
        if health_result["passed"]:
            sys.exit(0)
        else:
            sys.exit(1)

    except BenchmarkError as e:
        click.echo(f"Benchmark error: {e}", err=True)
        sys.exit(1)
    except AnalysisError as e:
        click.echo(f"Analysis error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("before_file", type=click.Path(exists=True))
@click.argument("after_file", type=click.Path(exists=True))
@click.option(
    "--industry", "-i",
    default="general",
    help="Industry context (default: general)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (default: json)"
)
def compare(before_file: str, after_file: str, industry: str, output_format: str):
    """
    Compare metrics between two time periods.

    Shows improvement percentages and direction.

    Examples:

        goodai-metrics compare before.csv after.csv

        goodai-metrics compare q1.csv q2.csv --industry manufacturing -f text
    """
    try:
        comparison_results = compare_metrics(
            Path(before_file),
            Path(after_file),
            industry=industry
        )

        if output_format == "json":
            output = format_comparison_json(comparison_results)
        else:
            output = format_comparison_text(comparison_results)

        click.echo(output)

    except AnalysisError as e:
        raise click.ClickException(f"Analysis error: {e}")


@main.command(name="list-industries")
def list_industries():
    """
    List available industries with benchmarks.
    """
    try:
        benchmarks = load_benchmarks()
        click.echo("Available industries:")
        for industry in sorted(benchmarks.keys()):
            metrics = list(benchmarks[industry].keys())
            click.echo(f"  - {industry}: {', '.join(metrics)}")
    except BenchmarkError as e:
        raise click.ClickException(f"Benchmark error: {e}")


if __name__ == "__main__":
    main()
