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
from typing import Optional, Dict

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
from .storage import MetricsStorage, StorageError
from .logging_config import setup_logging, get_logger, set_context_id, timed
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

# Storage settings
store_results: false
storage_path: .goodai-metrics/history.db
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
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output (debug logging)"
)
@click.option(
    "--json-logs",
    is_flag=True,
    help="Output logs in JSON format"
)
@click.option(
    "--log-file",
    type=click.Path(),
    help="Write logs to file"
)
@click.pass_context
def main(
    ctx: click.Context,
    config_path: Optional[str],
    verbose: bool,
    json_logs: bool,
    log_file: Optional[str]
):
    """
    Good AI Metrics CLI - Enterprise AI Implementation Analytics.

    Evidence over opinions. Leverage, not lore.
    """
    ctx.ensure_object(dict)

    # Set up logging (WARNING by default, DEBUG if verbose)
    log_level = "DEBUG" if verbose else "WARNING"
    setup_logging(level=log_level, json_output=json_logs, log_file=log_file)

    # Set context ID for this CLI invocation
    context_id = set_context_id()
    ctx.obj["context_id"] = context_id

    logger = get_logger(__name__)
    logger.debug(f"CLI invoked with context_id={context_id}")

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
@click.option(
    "--store/--no-store",
    default=None,
    help="Store results in history database (default: from config)"
)
@click.pass_context
def analyze(
    ctx: click.Context,
    file: Optional[str],
    sample: Optional[str],
    industry: Optional[str],
    output_format: Optional[str],
    store: Optional[bool]
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
    logger = get_logger(__name__)

    # Determine file path
    if sample:
        filepath = get_sample_data_path(sample)
        if industry is None:
            industry = sample
        logger.debug(f"Using sample data for industry: {sample}")
    elif file:
        filepath = Path(file).resolve()
        if not filepath.exists():
            raise click.ClickException(f"File not found: {filepath}")
        logger.debug(f"Analyzing file: {filepath}")
    else:
        raise click.ClickException(
            "Please provide a CSV file path or use --sample <industry>"
        )

    # Apply config defaults (CLI args take precedence)
    if industry is None:
        industry = config.default_industry
    if output_format is None:
        output_format = config.default_format

    logger.event("analysis_started", f"Analyzing {filepath.name} for {industry}")

    try:
        # Load benchmarks
        with timed(logger, "load_benchmarks"):
            benchmarks = load_benchmarks()
            industry_benchmarks = get_benchmark_for_industry(industry, benchmarks)

        # Analyze metrics
        with timed(logger, "analyze_metrics"):
            analyzer = MetricsAnalyzer(industry=industry)
            metrics = analyzer.load_csv(filepath)
            analysis_results = analyzer.analyze(metrics)

        # Generate recommendations
        with timed(logger, "generate_recommendations"):
            recommendations = generate_all_recommendations(analysis_results, industry_benchmarks)
            overall_health = determine_overall_health(recommendations)

        logger.metric("metrics_analyzed", analysis_results.get("metrics_analyzed", 0))
        logger.metric("high_priority_count", sum(1 for r in recommendations if r.get("priority") == "HIGH"))

        # Build full results
        full_results = {
            **analysis_results,
            "recommendations": recommendations,
            "overall_health": overall_health,
        }

        # Store results if enabled
        should_store = store if store is not None else config.store_results
        if should_store:
            try:
                storage_path = Path(config.storage_path) if config.storage_path else None
                storage = MetricsStorage(db_path=storage_path)
                run_id = storage.store_analysis(
                    full_results,
                    project=config.project_name
                )
                click.echo(f"Results stored (run_id: {run_id})", err=True)
            except StorageError as e:
                click.echo(f"Warning: Failed to store results: {e}", err=True)

        # Format output
        if output_format == "json":
            output = format_report_json(analysis_results, recommendations, overall_health)
        else:
            output = format_report_text(analysis_results, recommendations, overall_health)

        click.echo(output)
        logger.event("analysis_completed", f"Health: {overall_health}", industry=industry)

    except BenchmarkError as e:
        logger.error(f"Benchmark error: {e}")
        raise click.ClickException(f"Benchmark error: {e}")
    except AnalysisError as e:
        logger.error(f"Analysis error: {e}")
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


@main.command()
@click.option(
    "--project", "-p",
    default=None,
    help="Filter by project name"
)
@click.option(
    "--industry", "-i",
    default=None,
    help="Filter by industry"
)
@click.option(
    "--limit", "-n",
    default=20,
    type=int,
    help="Number of records to show (default: 20)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format (default: text)"
)
@click.pass_context
def history(
    ctx: click.Context,
    project: Optional[str],
    industry: Optional[str],
    limit: int,
    output_format: str
):
    """
    View analysis history from storage.

    Examples:

        goodai-metrics history

        goodai-metrics history --project my-project --limit 10

        goodai-metrics history -f json
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        records = storage.list_analyses(
            project=project,
            industry=industry,
            limit=limit
        )

        if not records:
            click.echo("No analysis records found.")
            return

        if output_format == "json":
            import json
            output = json.dumps([r.to_dict() for r in records], indent=2)
            click.echo(output)
        else:
            click.echo(f"Analysis History ({len(records)} records)")
            click.echo("=" * 60)
            for record in records:
                click.echo(f"\n  Run ID:    {record.run_id}")
                click.echo(f"  Timestamp: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                click.echo(f"  Project:   {record.project or '(default)'}")
                click.echo(f"  Industry:  {record.industry}")
                click.echo(f"  Health:    {record.overall_health}")
                click.echo(f"  Metrics:   {record.metrics_count}")

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


@main.command(name="history-show")
@click.argument("run_id")
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (default: json)"
)
@click.pass_context
def history_show(ctx: click.Context, run_id: str, output_format: str):
    """
    Show details of a specific analysis run.

    Examples:

        goodai-metrics history-show abc123def456

        goodai-metrics history-show abc123 -f text
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        record = storage.get_analysis(run_id)

        if not record:
            raise click.ClickException(f"No record found with run_id: {run_id}")

        if output_format == "json":
            import json
            output = json.dumps(record.full_results, indent=2)
            click.echo(output)
        else:
            results = record.full_results
            recommendations = results.get("recommendations", [])
            overall_health = results.get("overall_health", "unknown")

            output = format_report_text(
                results,
                recommendations,
                overall_health
            )
            click.echo(output)

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


@main.command(name="history-stats")
@click.pass_context
def history_stats(ctx: click.Context):
    """
    Show storage statistics.

    Examples:

        goodai-metrics history-stats
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        stats = storage.get_database_stats()

        click.echo("Storage Statistics")
        click.echo("=" * 40)
        click.echo(f"Database path:    {stats['database_path']}")
        click.echo(f"Database size:    {stats['database_size_bytes']:,} bytes")
        click.echo(f"Total analyses:   {stats['total_analyses']}")
        click.echo(f"Total metrics:    {stats['total_metric_values']}")
        click.echo(f"Oldest record:    {stats['oldest_record'] or 'N/A'}")
        click.echo(f"Newest record:    {stats['newest_record'] or 'N/A'}")

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


@main.command(name="history-cleanup")
@click.option(
    "--days",
    default=90,
    type=int,
    help="Delete records older than this many days (default: 90)"
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    help="Skip confirmation prompt"
)
@click.pass_context
def history_cleanup(ctx: click.Context, days: int, yes: bool):
    """
    Delete old analysis records.

    Examples:

        goodai-metrics history-cleanup --days 30

        goodai-metrics history-cleanup --days 60 --yes
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    if not yes:
        click.confirm(
            f"Delete all analysis records older than {days} days?",
            abort=True
        )

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        deleted = storage.delete_old_records(days=days)
        click.echo(f"Deleted {deleted} old record(s).")

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


@main.command()
@click.option(
    "--project", "-p",
    default=None,
    help="Filter by project name"
)
@click.option(
    "--days", "-d",
    default=30,
    type=int,
    help="Number of days to analyze (default: 30)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format (default: text)"
)
@click.pass_context
def trends(ctx: click.Context, project: Optional[str], days: int, output_format: str):
    """
    Show historical metric trends.

    Analyzes stored metrics over time to identify improving,
    declining, and stable metrics.

    Examples:

        goodai-metrics trends

        goodai-metrics trends --days 60 --project my-project

        goodai-metrics trends -f json
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        summary = storage.get_trend_summary(project=project, days=days)

        if output_format == "json":
            import json
            output = json.dumps(summary, indent=2)
            click.echo(output)
        else:
            _format_trends_text(summary, days, project)

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


def _format_trends_text(summary: Dict, days: int, project: Optional[str]) -> None:
    """Format trend summary as text output."""
    click.echo(f"Metric Trends (last {days} days)")
    if project:
        click.echo(f"Project: {project}")
    click.echo("=" * 60)

    if summary["total_analyses"] == 0:
        click.echo("\nNo analysis records found in this period.")
        click.echo("Run 'goodai-metrics analyze --store' to start tracking.")
        return

    click.echo(f"\nTotal analyses: {summary['total_analyses']}")
    click.echo(f"Metrics tracked: {summary['metrics_tracked']}")

    if not summary["trends"]:
        click.echo("\nInsufficient data for trend analysis.")
        click.echo("At least 2 analyses are needed per metric.")
        return

    # Summary counts
    improving = summary.get("improving", 0)
    declining = summary.get("declining", 0)
    stable = summary.get("stable", 0)

    click.echo(f"\nSummary: {improving} improving, {declining} declining, {stable} stable")

    # Show declining metrics first (most actionable)
    declining_trends = [t for t in summary["trends"] if t["direction"] == "declining"]
    if declining_trends:
        click.echo("\n[DECLINING]")
        for trend in declining_trends:
            click.echo(f"  {trend['metric']}: {trend['first_value']:.2f} -> {trend['last_value']:.2f} ({trend['change_percent']:+.1f}%)")

    # Then improving
    improving_trends = [t for t in summary["trends"] if t["direction"] == "improving"]
    if improving_trends:
        click.echo("\n[IMPROVING]")
        for trend in improving_trends:
            click.echo(f"  {trend['metric']}: {trend['first_value']:.2f} -> {trend['last_value']:.2f} ({trend['change_percent']:+.1f}%)")

    # Then stable
    stable_trends = [t for t in summary["trends"] if t["direction"] == "stable"]
    if stable_trends:
        click.echo("\n[STABLE]")
        for trend in stable_trends:
            click.echo(f"  {trend['metric']}: {trend['first_value']:.2f} (no change)")


@main.command(name="metric-history")
@click.argument("metric_name")
@click.option(
    "--project", "-p",
    default=None,
    help="Filter by project name"
)
@click.option(
    "--days", "-d",
    default=30,
    type=int,
    help="Number of days to look back (default: 30)"
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["json", "text"]),
    default="text",
    help="Output format (default: text)"
)
@click.pass_context
def metric_history(
    ctx: click.Context,
    metric_name: str,
    project: Optional[str],
    days: int,
    output_format: str
):
    """
    Show history for a specific metric.

    Displays all recorded values for a metric over time.

    Examples:

        goodai-metrics metric-history accuracy

        goodai-metrics metric-history latency_ms --days 60

        goodai-metrics metric-history error_rate -f json
    """
    config: ProjectConfig = ctx.obj.get("config", ProjectConfig())

    try:
        storage_path = Path(config.storage_path) if config.storage_path else None
        storage = MetricsStorage(db_path=storage_path)

        history = storage.get_metric_history(metric_name, project=project, days=days)

        if output_format == "json":
            import json
            output = json.dumps(history.to_dict(), indent=2)
            click.echo(output)
        else:
            _format_metric_history_text(history, days, project)

    except StorageError as e:
        raise click.ClickException(f"Storage error: {e}")


def _format_metric_history_text(history, days: int, project: Optional[str]) -> None:
    """Format metric history as text output."""
    click.echo(f"Metric History: {history.metric_name} (last {days} days)")
    if project:
        click.echo(f"Project: {project}")
    click.echo("=" * 60)

    if not history.values:
        click.echo("\nNo data found for this metric.")
        return

    click.echo(f"\nRecorded values: {len(history.values)}")
    click.echo("")
    click.echo("  Timestamp              Value       Gap%   Priority")
    click.echo("  " + "-" * 50)

    for entry in history.values:
        ts = entry.get("timestamp", "N/A")[:19]  # Truncate to datetime
        value = entry.get("value", 0)
        gap = entry.get("gap_percent", 0)
        priority = entry.get("priority", "-")
        click.echo(f"  {ts}  {value:10.3f}  {gap:6.1f}%  {priority or '-'}")

    # Show trend if enough data
    if len(history.values) >= 2:
        first = history.values[0]["value"]
        last = history.values[-1]["value"]
        if first != 0:
            change = ((last - first) / abs(first)) * 100
            direction = "improved" if change > 0 else "declined" if change < 0 else "unchanged"
            click.echo(f"\nTrend: {first:.3f} -> {last:.3f} ({change:+.1f}%, {direction})")


if __name__ == "__main__":
    main()
