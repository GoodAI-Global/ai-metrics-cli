# Good AI Metrics CLI

**Enterprise AI Implementation Analytics**

A production CLI tool for analyzing AI implementation metrics and producing actionable recommendations.

> *Evidence over opinions. Leverage, not lore. No fantasy metrics.*

[![PyPI version](https://badge.fury.io/py/goodai-metrics.svg)](https://pypi.org/project/goodai-metrics/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Quickstart in 60 Seconds

```bash
# Install
pip install goodai-metrics

# Run with sample data
goodai-metrics analyze --sample manufacturing

# That's it! You'll see a JSON report with recommendations.
```

---

## Installation

```bash
pip install goodai-metrics
```

For development:

```bash
git clone https://github.com/goodai/goodai-metrics.git
cd goodai-metrics
pip install -e ".[dev]"
```

---

## CLI Commands

### 1. Analyze Metrics

Analyze your AI metrics against industry benchmarks.

```bash
# Analyze a CSV file
goodai-metrics analyze metrics.csv --industry manufacturing

# Use built-in sample data
goodai-metrics analyze --sample manufacturing
goodai-metrics analyze --sample insurance
goodai-metrics analyze --sample aquaculture
goodai-metrics analyze --sample general

# Output as text instead of JSON
goodai-metrics analyze --sample manufacturing -f text
```

### 2. Health Check (CI/CD)

Quick pass/fail check for your CI/CD pipelines.

```bash
# Basic health check (exits 0 on pass, 1 on fail)
goodai-metrics health metrics.csv

# With custom thresholds
goodai-metrics health metrics.csv --max-high-priority 1 --max-gap 50

# Example in CI/CD
goodai-metrics health ./metrics.csv --industry manufacturing || exit 1
```

### 3. Compare Metrics

Compare metrics between two time periods.

```bash
# Compare before and after
goodai-metrics compare before.csv after.csv

# With industry context
goodai-metrics compare q1.csv q2.csv --industry manufacturing

# Output as text
goodai-metrics compare before.csv after.csv -f text
```

### 4. List Industries

Show available industries and their metrics.

```bash
goodai-metrics list-industries
```

---

## Input Format

Your metrics CSV should have these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `metric` | Yes | Metric name (e.g., `accuracy`, `latency_ms`) |
| `value` | Yes | Numeric value |
| `timestamp` | No | ISO date (e.g., `2025-01-01`) |

**Example `metrics.csv`:**

```csv
metric,value,timestamp
accuracy,0.87,2025-01-01
latency_ms,350,2025-01-01
error_rate,0.11,2025-01-01
adoption_percent,45,2025-01-01
```

---

## Output Format

### JSON Output (default)

```json
{
  "summary": {
    "industry": "manufacturing",
    "metrics_analyzed": 4,
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
      "effort": "Medium",
      "recommendation": "Review batch size and model quantization options..."
    }
  ],
  "detailed_analysis": [...],
  "metrics_without_benchmarks": []
}
```

### Text Output

```
============================================================
GOOD AI METRICS ANALYSIS REPORT
============================================================

SUMMARY
----------------------------------------
Industry:              manufacturing
Metrics Analyzed:      4
With Benchmarks:       4
High Priority Gaps:    2
Overall Health:        NEEDS_ATTENTION

RECOMMENDATIONS
----------------------------------------

1. [!!] latency_ms
   Current: 350 | Benchmark: 200
   Gap: 75.0% | Effort: Medium
   > Review batch size and model quantization options...
```

---

## Supported Metrics by Industry

### Manufacturing
- `accuracy` - Model prediction accuracy
- `latency_ms` - Inference latency in milliseconds
- `error_rate` - Prediction error rate
- `adoption_percent` - User adoption percentage
- `cost_per_inference` - Cost per model inference

### Insurance
- `accuracy` - Model prediction accuracy
- `processing_time_hours` - End-to-end processing time
- `straight_through_rate` - Automated processing rate
- `error_rate` - Processing error rate

### Aquaculture
- `prediction_accuracy` - Prediction model accuracy
- `early_warning_hours` - Early warning lead time
- `feed_efficiency_improvement` - Feed optimization improvement

### General
- `accuracy` - General model accuracy
- `latency_ms` - Inference latency
- `error_rate` - Error rate

---

## Priority Levels

Recommendations are prioritized based on gap from industry median (p50):

| Gap | Priority | Action |
|-----|----------|--------|
| > 20% | **HIGH** | Address immediately |
| 10-20% | **MEDIUM** | Plan for next quarter |
| < 10% | **LOW** | Monitor and maintain |

---

## Health Status

Overall health is determined by:

| Condition | Status |
|-----------|--------|
| 2+ HIGH priority items | `CRITICAL` |
| 1 HIGH or 2+ MEDIUM | `NEEDS_ATTENTION` |
| All LOW priority | `HEALTHY` |

---

## Python API

You can also use Good AI Metrics programmatically:

```python
from goodai_metrics import (
    MetricsAnalyzer,
    load_benchmarks,
    get_benchmark_for_industry,
    generate_all_recommendations,
    determine_overall_health
)

# Load benchmarks
benchmarks = load_benchmarks()
industry_benchmarks = get_benchmark_for_industry("manufacturing", benchmarks)

# Analyze metrics
analyzer = MetricsAnalyzer(industry="manufacturing")
metrics = analyzer.load_csv("metrics.csv")
results = analyzer.analyze(metrics)

# Generate recommendations
recommendations = generate_all_recommendations(results, industry_benchmarks)
health = determine_overall_health(recommendations)

print(f"Health: {health}")
for rec in recommendations:
    print(f"[{rec['priority']}] {rec['metric']}: {rec['recommendation']}")
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run demo
python demo_run.py
```

---

## About Good AI

Good AI is a premium enterprise AI consultancy. We believe in:

- **Evidence over opinions** - Recommendations tied to measurable gaps
- **Leverage, not lore** - Practical tools, not frameworks
- **No fantasy metrics** - Conservative benchmarks from real implementations

---

## License

MIT License - see [LICENSE](LICENSE) for details.
