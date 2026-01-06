# Good AI Metrics CLI

**Enterprise AI Implementation Analytics**

A CLI tool for analyzing AI implementation metrics and producing actionable recommendations.

> *Evidence over opinions. Leverage, not lore. No fantasy metrics.*

[![CI](https://github.com/GoodAI-Global/ai-metrics-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/GoodAI-Global/ai-metrics-cli/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## What This Is

- A **CLI tool** for analyzing AI metrics against industry benchmarks
- Provides **actionable recommendations** with priority levels
- Supports **CI/CD integration** with JUnit XML, GitHub Actions, and GitLab CI
- Includes **optional REST API** for integration with dashboards
- Stores **historical data** for trend analysis
- Generates **PDF reports** for stakeholders

## What This Is NOT

- Not a metrics collection agent (you provide the CSV data)
- Not a monitoring/alerting system (use Prometheus/Grafana for that)
- Not a machine learning framework
- Not validated for regulated industries without your own compliance review
- Benchmarks are illustrative, not guarantees of industry standards

---

## Quickstart (< 5 minutes)

```bash
# Install
pip install goodai-metrics

# Analyze built-in sample data
goodai-metrics analyze --sample manufacturing

# Analyze your own CSV
goodai-metrics analyze your-metrics.csv --industry manufacturing

# Quick health check for CI/CD
goodai-metrics health your-metrics.csv
```

Your CSV needs these columns:

```csv
metric,value,timestamp
accuracy,0.87,2025-01-01
latency_ms,350,2025-01-01
error_rate,0.11,2025-01-01
```

---

## Installation

```bash
pip install goodai-metrics
```

With optional features:

```bash
pip install "goodai-metrics[server]"   # REST API
pip install "goodai-metrics[reports]"  # PDF reports
pip install "goodai-metrics[all]"      # Everything
```

For development:

```bash
git clone https://github.com/GoodAI-Global/ai-metrics-cli.git
cd ai-metrics-cli
make setup
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `analyze` | Analyze metrics against benchmarks |
| `health` | CI/CD health check (exit 0/1) |
| `compare` | Compare two CSV files |
| `report` | Generate PDF report |
| `trends` | View historical trends |
| `config` | Manage configuration |
| `serve` | Start REST API server |
| `ci check` | CI/CD with JUnit/GitHub/GitLab output |

### Examples

```bash
# Analyze with text output
goodai-metrics analyze metrics.csv -f text

# Health check with custom thresholds
goodai-metrics health metrics.csv --max-high-priority 1 --max-gap 50

# Compare before/after
goodai-metrics compare before.csv after.csv

# Generate PDF report
goodai-metrics report metrics.csv -o report.pdf

# CI/CD with JUnit output
goodai-metrics ci check metrics.csv --format junit -o results.xml
```

---

## Configuration

Create `.goodai-metrics.yaml`:

```yaml
project: my-ai-project

defaults:
  industry: manufacturing
  format: json

thresholds:
  fail_on_priority: HIGH
  max_gap_percent: 30.0
  max_high_priority: 0

# Optional: webhook notifications
notifications:
  on_regression: true
  webhook_url: ${WEBHOOK_URL}

store_results: true
storage_path: .goodai-metrics/history.db
```

---

## Supported Industries

- **manufacturing** - accuracy, latency_ms, error_rate, adoption_percent, cost_per_inference
- **insurance** - accuracy, processing_time_hours, straight_through_rate, error_rate
- **aquaculture** - prediction_accuracy, early_warning_hours, feed_efficiency_improvement
- **general** - accuracy, latency_ms, error_rate

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

## About Good AI

Good AI is an enterprise AI consultancy. We believe in:

- **Evidence over opinions** - Recommendations tied to measurable gaps
- **Leverage, not lore** - Practical tools, not frameworks
- **No fantasy metrics** - Conservative benchmarks from real implementations
