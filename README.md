# AI Metrics CLI

[![CI](https://github.com/GoodAI-Global/ai-metrics-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/GoodAI-Global/ai-metrics-cli/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> Analyze your AI implementation metrics against industry benchmarks. Know where you stand.

---

## What This Is

- A **CLI tool** for analyzing AI metrics against industry benchmarks
- Provides **actionable recommendations** with priority levels (HIGH/MEDIUM/LOW)
- Supports **CI/CD integration** with JUnit XML, GitHub Actions, and GitLab CI
- Includes **optional REST API** for dashboard integration
- Generates **PDF reports** for stakeholders
- Stores **historical data** for trend analysis

## What This Is NOT

- Not a metrics collection agent (you provide the CSV data)
- Not a monitoring/alerting system (use Prometheus/Grafana for that)
- Not a machine learning framework
- Benchmarks are illustrative, not guarantees of industry standards

---

## Installation

```bash
pip install goodai-metrics

# With PDF report generation
pip install goodai-metrics[reports]

# With REST API server
pip install goodai-metrics[server]

# Everything
pip install goodai-metrics[all]
```

---

## Quick Start

```bash
# Check version
goodai-metrics --version

# Run analysis with sample data
goodai-metrics analyze --sample manufacturing

# Run health check on your metrics
goodai-metrics health metrics.csv --industry manufacturing

# Compare two time periods
goodai-metrics compare before.csv after.csv --industry manufacturing

# Generate PDF report
goodai-metrics report metrics.csv --output report.pdf
```

---

## Commands

### `analyze` - Full Analysis

Analyze your metrics file against industry benchmarks:

```bash
# Analyze a CSV file
goodai-metrics analyze metrics.csv --industry manufacturing

# Use built-in sample data
goodai-metrics analyze --sample manufacturing

# Output as formatted text
goodai-metrics analyze --sample manufacturing -f text
```

**Output:**
```json
{
  "summary": {
    "industry": "manufacturing",
    "metrics_analyzed": 5,
    "high_priority_gaps": 2,
    "overall_health": "NEEDS_ATTENTION"
  },
  "recommendations": [
    {
      "metric": "latency_ms",
      "current_value": 350,
      "benchmark_p50": 200,
      "gap_percent": 75.0,
      "priority": "HIGH",
      "recommendation": "Review batch size and model quantization..."
    }
  ]
}
```

### `health` - Quick Health Check

Fast pass/fail check for CI/CD pipelines:

```bash
# Basic health check
goodai-metrics health metrics.csv --industry manufacturing

# With custom thresholds
goodai-metrics health metrics.csv --max-high-priority 1 --max-gap 50

# In CI/CD (exits 0 on pass, 1 on fail)
goodai-metrics health metrics.csv || exit 1
```

**Output:**
```
HEALTH CHECK: PASSED
Metrics checked: 5
High priority gaps: 0
```

### `compare` - Period Comparison

Compare metrics between two time periods:

```bash
goodai-metrics compare q1.csv q2.csv --industry manufacturing
```

**Output:**
```json
{
  "metrics_compared": 5,
  "summary": {
    "improved": 3,
    "declined": 1,
    "unchanged": 1
  },
  "comparisons": [
    {
      "metric": "accuracy",
      "before": 0.85,
      "after": 0.92,
      "change_percent": 8.2,
      "status": "improved"
    }
  ]
}
```

### `report` - PDF Report

Generate a professional PDF report:

```bash
goodai-metrics report metrics.csv \
  --output report.pdf \
  --title "Q1 2025 AI Metrics Review" \
  --industry manufacturing
```

### `ci check` - CI/CD Integration

Output in CI/CD formats:

```bash
# JUnit XML for test frameworks
goodai-metrics ci check metrics.csv --format junit -o results.xml

# GitHub Actions annotations
goodai-metrics ci check metrics.csv --format github

# GitLab CI Code Quality
goodai-metrics ci check metrics.csv --format gitlab -o codequality.json
```

### `trends` - Historical Trends

View trends over time (requires stored history):

```bash
goodai-metrics trends --days 30 --project my-project
```

### `list-industries` - Available Industries

```bash
goodai-metrics list-industries
```

**Output:**
```
Available industries:
  • manufacturing - OEE, latency, error rate, adoption, cost
  • insurance - accuracy, processing time, straight-through rate
  • aquaculture - prediction accuracy, early warning, feed efficiency
  • general - accuracy, latency, error rate
```

---

## Input Format

### CSV Format (Required Columns)

```csv
metric,value,timestamp
accuracy,0.87,2025-01-01
latency_ms,350,2025-01-01
error_rate,0.11,2025-01-01
```

### Supported Metrics by Industry

| Industry | Metrics |
|----------|---------|
| **manufacturing** | accuracy, latency_ms, error_rate, adoption_percent, cost_per_inference |
| **insurance** | accuracy, processing_time_hours, straight_through_rate, error_rate |
| **aquaculture** | prediction_accuracy, early_warning_hours, feed_efficiency_improvement |
| **general** | accuracy, latency_ms, error_rate |

---

## Configuration

Create `.goodai-metrics.yaml` in your project:

```yaml
project: my-ai-project

defaults:
  industry: manufacturing
  format: json

thresholds:
  fail_on_priority: HIGH
  max_gap_percent: 30.0
  max_high_priority: 0

# Webhook notifications
notifications:
  on_regression: true
  on_threshold_breach: true
  webhook_url: ${WEBHOOK_URL}

# Store results for trending
store_results: true
storage_path: .goodai-metrics/history.db
```

---

## Python API

```python
from goodai_metrics import (
    MetricsAnalyzer,
    load_benchmarks,
    generate_all_recommendations,
    determine_overall_health
)

# Create analyzer
analyzer = MetricsAnalyzer(industry="manufacturing")

# Load and analyze metrics
metrics = analyzer.load_csv("metrics.csv")
results = analyzer.analyze(metrics)

# Get recommendations
benchmarks = load_benchmarks()
recommendations = generate_all_recommendations(
    results,
    benchmarks["manufacturing"]
)

# Check overall health
health = determine_overall_health(recommendations)
print(f"Health: {health}")

for rec in recommendations:
    print(f"[{rec['priority']}] {rec['metric']}: {rec['recommendation']}")
```

---

## CI/CD Integration Examples

### GitHub Actions

```yaml
- name: Check AI Metrics
  run: |
    pip install goodai-metrics
    goodai-metrics health metrics.csv --industry manufacturing
```

### GitLab CI

```yaml
metrics-check:
  script:
    - pip install goodai-metrics
    - goodai-metrics ci check metrics.csv --format gitlab -o codequality.json
  artifacts:
    reports:
      codequality: codequality.json
```

---

## Priority Levels

| Gap from Benchmark | Priority | Action |
|-------------------|----------|--------|
| > 20% | **HIGH** | Address immediately |
| 10-20% | **MEDIUM** | Plan for next quarter |
| < 10% | **LOW** | Monitor and maintain |

---

## Development

```bash
git clone https://github.com/GoodAI-Global/ai-metrics-cli.git
cd ai-metrics-cli
make setup   # Install dependencies
make lint    # Run linter
make test    # Run tests
make clean   # Clean artifacts
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

**Good AI** — We solve what slows you down.

</div>
