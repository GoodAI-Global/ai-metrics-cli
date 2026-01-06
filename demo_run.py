#!/usr/bin/env python3
"""
Good AI Metrics CLI - Demo Script

Generates sample data and runs analysis.
Must work standalone with: python demo_run.py
"""

import csv
import sys
import tempfile
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from goodai_metrics.analyzer import MetricsAnalyzer
from goodai_metrics.benchmarks import get_benchmark_for_industry, load_benchmarks
from goodai_metrics.formatters import format_report_json, format_report_text
from goodai_metrics.recommendations import (
    determine_overall_health,
    generate_all_recommendations,
)


def generate_sample_csv(output_path: Path) -> None:
    """Generate a sample metrics CSV file."""
    metrics = [
        {"metric": "accuracy", "value": "0.87", "timestamp": "2025-01-01"},
        {"metric": "latency_ms", "value": "350", "timestamp": "2025-01-01"},
        {"metric": "error_rate", "value": "0.11", "timestamp": "2025-01-01"},
        {"metric": "adoption_percent", "value": "45", "timestamp": "2025-01-01"},
        {"metric": "cost_per_inference", "value": "0.08", "timestamp": "2025-01-01"},
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value", "timestamp"])
        writer.writeheader()
        writer.writerows(metrics)


def main():
    """Run the demo analysis."""
    print("=" * 60)
    print("GOOD AI METRICS CLI - DEMO")
    print("Evidence over opinions. Leverage, not lore.")
    print("=" * 60)
    print()

    # Create temporary CSV
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        temp_path = Path(f.name)

    try:
        # Generate sample data
        print(f"Generating sample data: {temp_path}")
        generate_sample_csv(temp_path)
        print("Sample CSV contents:")
        print("-" * 40)
        with open(temp_path) as f:
            print(f.read())
        print("-" * 40)
        print()

        # Load benchmarks
        print("Loading industry benchmarks...")
        benchmarks = load_benchmarks()
        industry = "manufacturing"
        industry_benchmarks = get_benchmark_for_industry(industry, benchmarks)
        print(f"Using industry: {industry}")
        print()

        # Analyze metrics
        print("Analyzing metrics...")
        analyzer = MetricsAnalyzer(industry=industry)
        metrics = analyzer.load_csv(temp_path)
        analysis_results = analyzer.analyze(metrics)

        # Generate recommendations
        print("Generating recommendations...")
        recommendations = generate_all_recommendations(
            analysis_results, industry_benchmarks
        )
        overall_health = determine_overall_health(recommendations)
        print()

        # Output JSON report
        print("JSON REPORT:")
        print("=" * 60)
        json_output = format_report_json(
            analysis_results, recommendations, overall_health
        )
        print(json_output)
        print()

        # Output text report
        print()
        print("TEXT REPORT:")
        text_output = format_report_text(
            analysis_results, recommendations, overall_health
        )
        print(text_output)

        print()
        print("Demo completed successfully!")
        print("Run 'goodai-metrics analyze --sample manufacturing' for CLI usage.")

    finally:
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    main()
