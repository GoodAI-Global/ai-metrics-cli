# Acceptance Tests

Manual verification steps to confirm the Good AI Metrics CLI is working correctly.

## Prerequisites

- Python 3.9+
- pip

---

## Commands

Run these commands in order from the project root directory:

### 1. Install the package

```bash
pip install -e .
```

**Expected:** Install completes without errors.

### 2. Run the demo script

```bash
python demo_run.py
```

**Expected:**
- Prints "GOOD AI METRICS CLI - DEMO"
- Generates sample CSV contents
- Prints JSON report with summary and recommendations
- Prints text report with formatted output
- Completes with "Demo completed successfully!"

### 3. Run CLI with sample data

```bash
goodai-metrics analyze --sample manufacturing
```

**Expected:**
- Prints valid JSON output
- Contains `"summary"` with `"industry": "manufacturing"`
- Contains `"recommendations"` array
- Contains `"detailed_analysis"` array

### 4. Run all tests

```bash
pytest
```

**Expected:**
- All tests pass (green)
- At least 4 tests run
- No failures or errors

---

## Expected Results Summary

| Step | Command | Expected Outcome |
|------|---------|------------------|
| 1 | `pip install -e .` | Install succeeds |
| 2 | `python demo_run.py` | Prints JSON report |
| 3 | `goodai-metrics analyze --sample manufacturing` | CLI with --sample works without file |
| 4 | `pytest` | All tests pass |

---

## Additional Verification

### Health Check (CI/CD Integration)

```bash
goodai-metrics health sample_data/manufacturing_metrics.csv --industry manufacturing
```

**Expected:** Prints health check result (PASSED or FAILED with details).

### Compare Command

```bash
# Create a second metrics file for comparison
echo "metric,value,timestamp
accuracy,0.90,2025-02-01
latency_ms,250,2025-02-01
error_rate,0.08,2025-02-01
adoption_percent,55,2025-02-01" > /tmp/after_metrics.csv

goodai-metrics compare sample_data/manufacturing_metrics.csv /tmp/after_metrics.csv
```

**Expected:** Prints JSON with improvement percentages.

### Text Format

```bash
goodai-metrics analyze --sample manufacturing -f text
```

**Expected:** Prints human-readable report with borders and formatting.

### List Industries

```bash
goodai-metrics list-industries
```

**Expected:** Lists manufacturing, insurance, aquaculture, general with their metrics.

---

## Definition of Done

- [x] `pip install -e .` works
- [x] `goodai-metrics analyze --sample manufacturing` prints report
- [x] `pytest` passes (minimum 4 tests)
- [x] `demo_run.py` works standalone
- [x] `ACCEPTANCE_TESTS.md` exists

---

## Troubleshooting

### "Command not found: goodai-metrics"

Ensure you've installed the package and your Python scripts directory is in PATH:

```bash
pip install -e .
which goodai-metrics
```

### "Benchmark file not found"

Run commands from the project root directory where `benchmarks/` exists:

```bash
cd /path/to/ai-metrics-cli
goodai-metrics analyze --sample manufacturing
```

### Import errors

Ensure you're using Python 3.9+ and have installed dependencies:

```bash
python --version
pip install -e ".[dev]"
```
