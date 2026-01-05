"""
Good AI Metrics CLI - Command Line Interface.

Production CLI tool for analyzing AI implementation metrics.

Usage:
    goodai-metrics analyze <file.csv> [--industry <name>] [--format json|text]
    goodai-metrics analyze --sample <industry>
    goodai-metrics health <file.csv> [--industry <name>]
    goodai-metrics compare <before.csv> <after.csv> [--industry <name>]
    goodai-metrics config [--show | --init]
"""

import sys
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .analyzer import MetricsAnalyzer, AnalysisError, compare_metrics
from .benchmarks import load_benchmarks, get_benchmark_for_industry, BenchmarkError
from .config import (
    load_config,
    find_config_file,
    ProjectConfig,
    ConfigError,
)
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
    "aquaculture": "aquaculture_metrics.csv",
    "general": "general_metrics.csv",
}

# Default config template
CONFIG_TEMPLATE = '''# Good AI Metrics Configuration
# https://github.com/goodai/goodai-metrics

version: "1.0"

# Project name (optional)
project: my-ai-project

# Default settings
defaults:
  industry: general
  format: json

# Custom targets (override industry benchmarks)
# custom_targets:
#   accuracy:
#     target: 0.95
#     minimum: 0.90
#   latency_ms:
#     target: 150
#     maximum: 300

# CI/CD thresholds
thresholds:
  fail_on_priority: HIGH
  max_gap_percent: 30.0
  max_high_priority: 0

# Notifications (coming soon)
# notifications:
#   on_regression: true
#   webhook_url: ${NOTIFICATION_WEBHOOK}

# Storage settings (coming soon)
# store_results: true
# storage_path: .goodai-metrics/history.db
'''


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


def _load_project_config() -> ProjectConfig:
    """Load project config, returning defaults if not found."""
    try:
        return load_config()
    except ConfigError as e:
        # Log warning but continue with defaults
        click.echo(f"Warning: {e}", err=True)
        return ProjectConfig()


@click.group()
@click.version_option(version=__version__, prog_name="goodai-metrics")
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True),
    help="Path to config file (default: auto-discover)"
)
@click.pass_context
def main(ctx: click.Context, config_path: Optional[str]):
    """
    Good AI Metrics CLI - Enterprise AI Implementation Analytics.

    Evidence over opinions. Leverage, not lore.
    """
    ctx.ensure_object(dict)

    # Load config and store in context
    try:
        if config_path:
            ctx.obj["config"] = load_config(Path(config_path))
        else:
            ctx.obj["config"] = load_config()
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        ctx.obj["config"] = ProjectConfig()


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
    default=None,
    help="Output format (default: from config or json)"
)
@click.pass_context
def analyze(
    ctx: click.Context,
    file: Optional[str],
    sample: Optional[str],
    industry: Optional[str],
    output_format: Optional[str]
):
    """
    Analyze AI metrics against industry benchmarks.

    Provide a CSV file path OR use --sample to use built-in data.

    Examples:

        goodai-metrics analyze metrics.csv --industry manufacturing

        goodai-metrics analyze --sample manufacturing

        goodai-metrics analyze data.csv -f text
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    # Determine file path
    if sample:
        filepath = get_sample_data_path(sample)
        if industry is None:
            industry = sample
    elif file:
        filepath = Path(file).resolve()
        if not filepath.exists():
            raise click.ClickException(f"File not found: {filepath}")
    else:
        raise click.ClickException(
            "Please provide a CSV file path or use --sample <industry>"
        )

    # Apply config defaults (CLI args take precedence)
    if industry is None:
        industry = config.default_industry
    if output_format is None:
        output_format = config.default_format

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
    default=None,
    help="Industry for benchmark comparison (default: from config or general)"
)
@click.option(
    "--max-high-priority",
    default=None,
    type=int,
    help="Maximum allowed HIGH priority items (default: from config or 0)"
)
@click.option(
    "--max-gap",
    default=None,
    type=float,
    help="Maximum allowed gap percentage (default: from config or 30.0)"
)
@click.pass_context
def health(
    ctx: click.Context,
    file: str,
    industry: Optional[str],
    max_high_priority: Optional[int],
    max_gap: Optional[float]
):
    """
    Quick health check for CI/CD pipelines.

    Exits with code 0 if all metrics pass thresholds.
    Exits with code 1 if any metric fails.

    Examples:

        goodai-metrics health metrics.csv

        goodai-metrics health metrics.csv --max-high-priority 1 --max-gap 50
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())
    filepath = Path(file)

    # Apply config defaults (CLI args take precedence)
    if industry is None:
        industry = config.default_industry
    if max_high_priority is None:
        max_high_priority = config.thresholds.max_high_priority
    if max_gap is None:
        max_gap = config.thresholds.max_gap_percent

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
        raise click.ClickException(f"Benchmark error: {e}")
    except AnalysisError as e:
        raise click.ClickException(f"Analysis error: {e}")


@main.command()
@click.argument("before_file", type=click.Path(exists=True))
@click.argument("after_file", type=click.Path(exists=True))
@click.option(
    "--industry", "-i",
    default=None,
    help="Industry context (default: from config or general)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default=None,
    help="Output format (default: from config or json)"
)
@click.pass_context
def compare(
    ctx: click.Context,
    before_file: str,
    after_file: str,
    industry: Optional[str],
    output_format: Optional[str]
):
    """
    Compare metrics between two time periods.

    Shows improvement percentages and direction.

    Examples:

        goodai-metrics compare before.csv after.csv

        goodai-metrics compare q1.csv q2.csv --industry manufacturing -f text
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    # Apply config defaults
    if industry is None:
        industry = config.default_industry
    if output_format is None:
        output_format = config.default_format

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


@main.command()
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--init", "init_config", is_flag=True, help="Create a new config file")
@click.option("--path", is_flag=True, help="Show path to active config file")
@click.pass_context
def config(ctx: click.Context, show: bool, init_config: bool, path: bool):
    """
    Manage configuration.

    Examples:

        goodai-metrics config --show

        goodai-metrics config --init

        goodai-metrics config --path
    """
    if init_config:
        config_path = Path.cwd() / ".goodai-metrics.yaml"
        if config_path.exists():
            raise click.ClickException(
                f"Config file already exists: {config_path}\n"
                "Use --show to view current configuration."
            )
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        click.echo(f"Created config file: {config_path}")
        return

    if path:
        found_path = find_config_file()
        if found_path:
            click.echo(found_path)
        else:
            click.echo("No config file found. Use 'goodai-metrics config --init' to create one.")
        return

    # Default: show config
    project_config: ProjectConfig = ctx.obj.get("config", ProjectConfig())
    found_path = find_config_file()

    click.echo("Good AI Metrics Configuration")
    click.echo("=" * 40)

    if found_path:
        click.echo(f"Config file: {found_path}")
    else:
        click.echo("Config file: (none - using defaults)")

    click.echo("")
    click.echo("Current Settings:")
    click.echo(f"  Project:          {project_config.project_name or '(not set)'}")
    click.echo(f"  Default Industry: {project_config.default_industry}")
    click.echo(f"  Default Format:   {project_config.default_format}")
    click.echo("")
    click.echo("Thresholds:")
    click.echo(f"  Fail on Priority:   {project_config.thresholds.fail_on_priority}")
    click.echo(f"  Max Gap Percent:    {project_config.thresholds.max_gap_percent}%")
    click.echo(f"  Max High Priority:  {project_config.thresholds.max_high_priority}")

    if project_config.custom_targets:
        click.echo("")
        click.echo("Custom Targets:")
        for metric, target in project_config.custom_targets.items():
            click.echo(f"  {metric}: target={target.target}", nl=False)
            if target.minimum is not None:
                click.echo(f", min={target.minimum}", nl=False)
            if target.maximum is not None:
                click.echo(f", max={target.maximum}", nl=False)
            click.echo("")


if __name__ == "__main__":
    main()
