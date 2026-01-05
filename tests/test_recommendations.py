"""Tests for the recommendations module."""

import pytest

from goodai_metrics.recommendations import (
    generate_recommendation,
    generate_all_recommendations,
    determine_overall_health,
    check_health_thresholds,
    calculate_gap,
    determine_priority,
    is_higher_better
)


class TestRecommendationLogic:
    """Tests for recommendation generation logic."""

    def test_high_gap_gives_high_priority(self):
        """High gap (>20%) results in HIGH priority."""
        benchmark = {"p25": 0.85, "p50": 0.92, "p75": 0.96, "p90": 0.99}

        # Value of 0.70 is significantly below p50 of 0.92
        # Gap = (0.92 - 0.70) / 0.92 = 0.239 = 23.9%
        rec = generate_recommendation("accuracy", 0.70, benchmark)

        assert rec["priority"] == "HIGH"
        assert rec["gap_percent"] > 20

    def test_medium_gap_gives_medium_priority(self):
        """Medium gap (10-20%) results in MEDIUM priority."""
        benchmark = {"p25": 0.85, "p50": 0.92, "p75": 0.96, "p90": 0.99}

        # Value of 0.80 vs p50 of 0.92
        # Gap = (0.92 - 0.80) / 0.92 = 0.13 = 13%
        rec = generate_recommendation("accuracy", 0.80, benchmark)

        assert rec["priority"] == "MEDIUM"
        assert 10 < rec["gap_percent"] <= 20

    def test_low_gap_gives_low_priority(self):
        """Low gap (<10%) results in LOW priority."""
        benchmark = {"p25": 0.85, "p50": 0.92, "p75": 0.96, "p90": 0.99}

        # Value of 0.90 vs p50 of 0.92
        # Gap = (0.92 - 0.90) / 0.92 = 0.022 = 2.2%
        rec = generate_recommendation("accuracy", 0.90, benchmark)

        assert rec["priority"] == "LOW"
        assert rec["gap_percent"] <= 10

    def test_infrastructure_metric_medium_effort(self):
        """Infrastructure metrics have Medium effort."""
        benchmark = {"p25": 500, "p50": 200, "p75": 100, "p90": 50}

        rec = generate_recommendation("latency_ms", 400, benchmark)

        assert rec["effort"] == "Medium"

    def test_process_metric_high_effort(self):
        """Process metrics have High effort."""
        benchmark = {"p25": 0.85, "p50": 0.92, "p75": 0.96, "p90": 0.99}

        rec = generate_recommendation("accuracy", 0.80, benchmark)

        assert rec["effort"] == "High"

    def test_lower_is_better_for_error_rate(self):
        """Error rate treats lower values as better."""
        assert is_higher_better("accuracy") is True
        assert is_higher_better("error_rate") is False
        assert is_higher_better("latency_ms") is False

    def test_recommendation_includes_text(self):
        """Recommendations include actionable text."""
        benchmark = {"p25": 500, "p50": 200, "p75": 100, "p90": 50}

        rec = generate_recommendation("latency_ms", 400, benchmark)

        assert "recommendation" in rec
        assert len(rec["recommendation"]) > 10  # Has meaningful text


class TestCalculateGap:
    """Tests for gap calculation."""

    def test_gap_for_higher_is_better(self):
        """Gap calculation for metrics where higher is better."""
        # Current value 0.80, benchmark 1.00
        # Gap = (1.00 - 0.80) / 1.00 = 0.20
        gap = calculate_gap(0.80, 1.00, higher_is_better=True)
        assert gap == pytest.approx(0.20)

    def test_gap_for_lower_is_better(self):
        """Gap calculation for metrics where lower is better."""
        # Current value 300, benchmark 200
        # Gap = (300 - 200) / 200 = 0.50
        gap = calculate_gap(300, 200, higher_is_better=False)
        assert gap == pytest.approx(0.50)

    def test_no_gap_when_at_benchmark(self):
        """No gap when at or above benchmark."""
        gap = calculate_gap(0.92, 0.92, higher_is_better=True)
        assert gap == 0.0

    def test_no_negative_gap(self):
        """Gap is never negative (better than benchmark = 0 gap)."""
        gap = calculate_gap(0.95, 0.92, higher_is_better=True)
        assert gap == 0.0


class TestDeterminePriority:
    """Tests for priority determination."""

    def test_priority_thresholds(self):
        """Priority levels follow specified thresholds."""
        assert determine_priority(0.25) == "HIGH"  # > 20%
        assert determine_priority(0.21) == "HIGH"
        assert determine_priority(0.20) == "MEDIUM"  # 10-20%
        assert determine_priority(0.15) == "MEDIUM"
        assert determine_priority(0.10) == "LOW"  # <= 10%
        assert determine_priority(0.05) == "LOW"


class TestOverallHealth:
    """Tests for overall health determination."""

    def test_critical_with_multiple_high_priority(self):
        """Two or more HIGH priority items = CRITICAL."""
        recommendations = [
            {"priority": "HIGH", "gap_percent": 25},
            {"priority": "HIGH", "gap_percent": 22},
        ]
        assert determine_overall_health(recommendations) == "CRITICAL"

    def test_needs_attention_with_one_high(self):
        """One HIGH priority item = NEEDS_ATTENTION."""
        recommendations = [
            {"priority": "HIGH", "gap_percent": 25},
            {"priority": "LOW", "gap_percent": 5},
        ]
        assert determine_overall_health(recommendations) == "NEEDS_ATTENTION"

    def test_healthy_with_only_low(self):
        """Only LOW priority items = HEALTHY."""
        recommendations = [
            {"priority": "LOW", "gap_percent": 5},
            {"priority": "LOW", "gap_percent": 3},
        ]
        assert determine_overall_health(recommendations) == "HEALTHY"

    def test_empty_is_healthy(self):
        """No recommendations = HEALTHY."""
        assert determine_overall_health([]) == "HEALTHY"


class TestHealthCheck:
    """Tests for CI/CD health check."""

    def test_passes_with_no_high_priority(self):
        """Health check passes with no HIGH priority items."""
        recommendations = [
            {"priority": "MEDIUM", "gap_percent": 15, "metric": "accuracy"},
            {"priority": "LOW", "gap_percent": 5, "metric": "latency_ms"},
        ]
        result = check_health_thresholds(recommendations)
        assert result["passed"] is True

    def test_fails_with_high_priority(self):
        """Health check fails with HIGH priority items (default max=0)."""
        recommendations = [
            {"priority": "HIGH", "gap_percent": 25, "metric": "accuracy"},
        ]
        result = check_health_thresholds(recommendations)
        assert result["passed"] is False
        assert len(result["failures"]) > 0

    def test_fails_with_large_gap(self):
        """Health check fails with gap > 30%."""
        recommendations = [
            {"priority": "MEDIUM", "gap_percent": 35, "metric": "accuracy"},
        ]
        result = check_health_thresholds(recommendations)
        assert result["passed"] is False


class TestCustomTargets:
    """Tests for custom targets integration."""

    def test_custom_target_overrides_benchmark(self):
        """Custom target takes precedence over industry benchmark."""
        analysis_results = {
            "analysis": [
                {"metric": "accuracy", "current_value": 0.85},
            ]
        }
        industry_benchmarks = {
            "accuracy": {"p25": 0.80, "p50": 0.90, "p75": 0.95, "p90": 0.98}
        }
        # Custom target is lower than industry benchmark
        custom_targets = {
            "accuracy": {"target": 0.80}  # Lower target
        }

        recommendations = generate_all_recommendations(
            analysis_results,
            industry_benchmarks,
            custom_targets=custom_targets,
        )

        assert len(recommendations) == 1
        rec = recommendations[0]
        # With target of 0.80 and value of 0.85, we're above target (no gap)
        assert rec["has_custom_target"] is True
        assert rec["benchmark_p50"] == 0.80

    def test_custom_target_with_object(self):
        """Custom target works with CustomTarget-like object."""
        from types import SimpleNamespace

        analysis_results = {
            "analysis": [
                {"metric": "latency_ms", "current_value": 150},
            ]
        }
        industry_benchmarks = {
            "latency_ms": {"p25": 100, "p50": 200, "p75": 300, "p90": 500}
        }
        # Custom target using object with .target attribute
        custom_targets = {
            "latency_ms": SimpleNamespace(target=100, minimum=50, maximum=200)
        }

        recommendations = generate_all_recommendations(
            analysis_results,
            industry_benchmarks,
            custom_targets=custom_targets,
        )

        assert len(recommendations) == 1
        rec = recommendations[0]
        assert rec["has_custom_target"] is True
        assert rec["benchmark_p50"] == 100

    def test_no_custom_target_uses_benchmark(self):
        """Metrics without custom targets use industry benchmark."""
        analysis_results = {
            "analysis": [
                {"metric": "accuracy", "current_value": 0.80},
                {"metric": "latency_ms", "current_value": 200},
            ]
        }
        industry_benchmarks = {
            "accuracy": {"p25": 0.85, "p50": 0.90, "p75": 0.95, "p90": 0.98},
            "latency_ms": {"p25": 100, "p50": 150, "p75": 200, "p90": 300},
        }
        # Only custom target for accuracy
        custom_targets = {
            "accuracy": {"target": 0.85}
        }

        recommendations = generate_all_recommendations(
            analysis_results,
            industry_benchmarks,
            custom_targets=custom_targets,
        )

        assert len(recommendations) == 2

        # Find each recommendation
        accuracy_rec = next(r for r in recommendations if r["metric"] == "accuracy")
        latency_rec = next(r for r in recommendations if r["metric"] == "latency_ms")

        # accuracy uses custom target
        assert accuracy_rec.get("has_custom_target") is True
        assert accuracy_rec["benchmark_p50"] == 0.85

        # latency_ms uses industry benchmark
        assert latency_rec.get("has_custom_target") is None or latency_rec.get("has_custom_target") is False
        assert latency_rec["benchmark_p50"] == 150
