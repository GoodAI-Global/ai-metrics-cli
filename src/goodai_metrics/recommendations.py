"""
Recommendation engine.

Generates actionable recommendations based on metric gaps.
Implements the 'Evidence over opinions' principle with data-driven priorities.
"""

from typing import Dict, Any, List, Optional


# Metric categorization for effort estimation
INFRASTRUCTURE_METRICS = {
    "latency_ms",
    "cost_per_inference",
    "processing_time_hours"
}

PROCESS_METRICS = {
    "accuracy",
    "error_rate",
    "adoption_percent",
    "straight_through_rate",
    "prediction_accuracy"
}

# Specific recommendations based on metric and gap
RECOMMENDATION_TEMPLATES = {
    "latency_ms": {
        "high": "Review batch size and model quantization options. Consider edge deployment for latency-critical paths.",
        "medium": "Profile inference pipeline to identify bottlenecks. Evaluate caching strategies for repeated inputs.",
        "low": "Monitor latency trends. Minor optimizations available through request batching."
    },
    "accuracy": {
        "high": "Inspect failure cases for hard negatives and edge cases. Consider ensemble methods or model retraining.",
        "medium": "Analyze confusion matrix for systematic errors. Augment training data for underperforming classes.",
        "low": "Current accuracy acceptable. Focus on maintaining data quality for continued performance."
    },
    "error_rate": {
        "high": "Implement human-in-the-loop for high-uncertainty predictions. Add confidence thresholds for automated decisions.",
        "medium": "Review error patterns for common failure modes. Consider adding validation rules for edge cases.",
        "low": "Error rate within acceptable range. Continue monitoring for regression."
    },
    "adoption_percent": {
        "high": "Conduct user research to identify adoption barriers. Improve onboarding and training materials.",
        "medium": "Address common user pain points. Consider UX improvements and workflow integration.",
        "low": "Adoption on track. Focus on power user features and advanced capabilities."
    },
    "cost_per_inference": {
        "high": "Evaluate model distillation or quantization. Consider spot instances or reserved capacity.",
        "medium": "Implement request batching. Review caching for frequently requested predictions.",
        "low": "Cost efficiency good. Monitor for usage spikes."
    },
    "processing_time_hours": {
        "high": "Implement parallel processing. Review for blocking operations and batch optimization.",
        "medium": "Streamline workflow steps. Consider async processing for non-critical paths.",
        "low": "Processing time acceptable. Minor gains available through queue optimization."
    },
    "straight_through_rate": {
        "high": "Review exception handling rules for over-rejection. Train model on rejected cases.",
        "medium": "Analyze manual intervention patterns. Automate common exception resolutions.",
        "low": "STP rate on track. Focus on maintaining quality while increasing automation."
    },
    "prediction_accuracy": {
        "high": "Collect more labeled data for problem areas. Consider feature engineering improvements.",
        "medium": "Retrain with recent data. Review feature drift and data quality.",
        "low": "Accuracy acceptable. Monitor for model drift over time."
    },
    "early_warning_hours": {
        "high": "Improve sensor data quality and sampling frequency. Review detection thresholds.",
        "medium": "Add leading indicators to detection model. Consider ensemble approaches.",
        "low": "Warning time adequate. Focus on response process optimization."
    },
    "feed_efficiency_improvement": {
        "high": "Review feeding algorithm calibration. Collect more environmental data for model inputs.",
        "medium": "Fine-tune prediction parameters. A/B test feeding strategies.",
        "low": "Efficiency gains on track. Monitor for seasonal variations."
    }
}


def calculate_gap(value: float, benchmark_p50: float, higher_is_better: bool = True) -> float:
    """
    Calculate the gap between current value and benchmark.

    Args:
        value: Current metric value.
        benchmark_p50: Benchmark median (p50) value.
        higher_is_better: If True, gap is negative when value < benchmark.

    Returns:
        Gap as a proportion (e.g., 0.15 = 15% gap).
    """
    if benchmark_p50 == 0:
        return 0.0

    if higher_is_better:
        # For accuracy, adoption, etc. - higher is better
        gap = (benchmark_p50 - value) / benchmark_p50
    else:
        # For latency, error_rate, etc. - lower is better
        gap = (value - benchmark_p50) / benchmark_p50

    return max(0, gap)  # Only return positive gaps (areas needing improvement)


def is_higher_better(metric: str) -> bool:
    """Determine if higher values are better for this metric."""
    lower_is_better = {
        "latency_ms",
        "error_rate",
        "cost_per_inference",
        "processing_time_hours"
    }
    return metric not in lower_is_better


def determine_priority(gap: float) -> str:
    """
    Determine priority based on gap size.

    Args:
        gap: Gap as a proportion.

    Returns:
        Priority level: 'HIGH', 'MEDIUM', or 'LOW'.
    """
    if gap > 0.20:
        return "HIGH"
    elif gap > 0.10:
        return "MEDIUM"
    else:
        return "LOW"


def determine_effort(metric: str) -> str:
    """
    Determine effort level based on metric type.

    Args:
        metric: Metric name.

    Returns:
        Effort level: 'Low', 'Medium', or 'High'.
    """
    if metric in INFRASTRUCTURE_METRICS:
        return "Medium"
    elif metric in PROCESS_METRICS:
        return "High"
    else:
        return "Medium"  # Default for unknown metrics


def get_recommendation_text(metric: str, priority: str) -> str:
    """
    Get specific recommendation text for a metric and priority level.

    Args:
        metric: Metric name.
        priority: Priority level ('HIGH', 'MEDIUM', 'LOW').

    Returns:
        Recommendation text.
    """
    priority_key = priority.lower()

    if metric in RECOMMENDATION_TEMPLATES:
        return RECOMMENDATION_TEMPLATES[metric].get(
            priority_key,
            f"Review {metric} performance and identify improvement opportunities."
        )
    else:
        # Generic recommendation for unknown metrics
        if priority == "HIGH":
            return f"Significant gap in {metric}. Conduct root cause analysis and prioritize improvement."
        elif priority == "MEDIUM":
            return f"Moderate gap in {metric}. Plan improvement initiatives for next quarter."
        else:
            return f"{metric} within acceptable range. Continue monitoring."


def generate_recommendation(metric: str, value: float, benchmark: Dict) -> Dict[str, Any]:
    """
    Generate a recommendation for a single metric.

    Implements the exact logic specified in the requirements.

    Args:
        metric: Metric name.
        value: Current metric value.
        benchmark: Benchmark dictionary with p25, p50, p75, p90.

    Returns:
        Recommendation dictionary.
    """
    higher_better = is_higher_better(metric)
    gap = calculate_gap(value, benchmark["p50"], higher_better)
    priority = determine_priority(gap)
    effort = determine_effort(metric)
    recommendation = get_recommendation_text(metric, priority)

    return {
        "metric": metric,
        "current_value": value,
        "benchmark_p50": benchmark["p50"],
        "gap_percent": round(gap * 100, 1),
        "priority": priority,
        "effort": effort,
        "recommendation": recommendation
    }


def generate_all_recommendations(
    analysis_results: Dict[str, Any],
    industry_benchmarks: Dict[str, Dict]
) -> List[Dict[str, Any]]:
    """
    Generate recommendations for all analyzed metrics.

    Args:
        analysis_results: Results from MetricsAnalyzer.analyze().
        industry_benchmarks: Benchmark data for the industry.

    Returns:
        List of recommendation dictionaries, sorted by priority.
    """
    recommendations = []

    for metric_analysis in analysis_results.get("analysis", []):
        metric_name = metric_analysis["metric"]

        if metric_name in industry_benchmarks:
            benchmark = industry_benchmarks[metric_name]
            rec = generate_recommendation(
                metric_name,
                metric_analysis["current_value"],
                benchmark
            )
            recommendations.append(rec)

    # Sort by priority (HIGH first, then MEDIUM, then LOW)
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recommendations.sort(key=lambda x: (priority_order.get(x["priority"], 3), -x["gap_percent"]))

    return recommendations


def determine_overall_health(recommendations: List[Dict]) -> str:
    """
    Determine overall health status based on recommendations.

    Args:
        recommendations: List of recommendation dictionaries.

    Returns:
        Health status: 'HEALTHY', 'NEEDS_ATTENTION', or 'CRITICAL'.
    """
    if not recommendations:
        return "HEALTHY"

    high_priority_count = sum(1 for r in recommendations if r["priority"] == "HIGH")
    medium_priority_count = sum(1 for r in recommendations if r["priority"] == "MEDIUM")

    if high_priority_count >= 2:
        return "CRITICAL"
    elif high_priority_count >= 1 or medium_priority_count >= 2:
        return "NEEDS_ATTENTION"
    else:
        return "HEALTHY"


def check_health_thresholds(
    recommendations: List[Dict],
    max_high_priority: int = 0,
    max_gap_percent: float = 30.0
) -> Dict[str, Any]:
    """
    Check if metrics pass health thresholds for CI/CD.

    Args:
        recommendations: List of recommendation dictionaries.
        max_high_priority: Maximum allowed HIGH priority items (default 0).
        max_gap_percent: Maximum allowed gap percentage (default 30%).

    Returns:
        Health check result dictionary.
    """
    failures = []

    high_priority_items = [r for r in recommendations if r["priority"] == "HIGH"]
    if len(high_priority_items) > max_high_priority:
        failures.append({
            "check": "high_priority_count",
            "expected": f"<= {max_high_priority}",
            "actual": len(high_priority_items),
            "metrics": [r["metric"] for r in high_priority_items]
        })

    large_gap_items = [r for r in recommendations if r["gap_percent"] > max_gap_percent]
    if large_gap_items:
        failures.append({
            "check": "gap_percent",
            "expected": f"<= {max_gap_percent}%",
            "actual": [f"{r['metric']}: {r['gap_percent']}%" for r in large_gap_items]
        })

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "metrics_checked": len(recommendations)
    }
