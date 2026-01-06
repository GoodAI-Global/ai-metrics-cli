# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-06

### Added

- **Core Analysis Engine**
  - `MetricsAnalyzer` class for CSV-based metrics analysis
  - Industry benchmarks for manufacturing, insurance, aquaculture, and general
  - Percentile-based gap analysis (p25, p50, p75, p90)
  - Priority recommendations (HIGH, MEDIUM, LOW)
  - Health status determination (CRITICAL, NEEDS_ATTENTION, HEALTHY)

- **CLI Commands**
  - `analyze` - Analyze metrics against industry benchmarks
  - `health` - Quick CI/CD health check with exit codes
  - `compare` - Compare metrics between two time periods
  - `report` - Generate PDF analysis reports
  - `report-compare` - Generate PDF comparison reports
  - `trends` - View historical metric trends
  - `metric-history` - View history for specific metrics
  - `history` - List stored analysis runs
  - `config` - Manage configuration
  - `serve` - Start REST API server
  - `ci check` - CI/CD integration with JUnit/GitHub/GitLab output

- **Configuration System**
  - YAML-based configuration (`.goodai-metrics.yaml`)
  - Environment variable interpolation (`${VAR_NAME}`)
  - Custom targets for metrics
  - Custom benchmarks with full percentile data
  - External benchmark file loading

- **Storage & History**
  - SQLite-based metrics storage
  - Trend analysis over time
  - Regression detection

- **Notifications**
  - Webhook notifications (generic HTTP)
  - Slack webhook support
  - Regression notifications
  - Threshold breach notifications

- **CI/CD Integration**
  - JUnit XML output
  - GitHub Actions annotations
  - GitLab CI Code Quality reports
  - Configurable thresholds

- **REST API** (optional)
  - FastAPI-based REST server
  - OpenAPI documentation
  - Rate limiting
  - CORS support

- **PDF Reports** (optional)
  - Professional PDF report generation
  - Comparison reports

- **Enterprise Features**
  - Structured logging (JSON output)
  - Request tracing
  - Input validation and sanitization
  - SSRF protection for webhooks

### Security

- SSRF protection for webhook URLs
- Input sanitization for all user-provided data
- Path traversal protection for file operations
- Private IP range blocking

[Unreleased]: https://github.com/goodai/goodai-metrics/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/goodai/goodai-metrics/releases/tag/v0.1.0
