"""
Webhook Notifications for Good AI Metrics.

Sends notifications to webhooks and Slack when analysis events occur.
Supports generic HTTP webhooks and Slack webhooks.
"""

import json
import re
import urllib.request
import urllib.error
import ssl
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


class NotificationError(Exception):
    """Raised when notification sending fails."""
    pass


# Security limits
MAX_PAYLOAD_SIZE = 100 * 1024  # 100 KB
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 2

# Blocked hosts (prevent SSRF attacks)
BLOCKED_HOSTS = {
    'localhost', '127.0.0.1', '0.0.0.0', '::1',
    '169.254.169.254',  # AWS metadata
    'metadata.google.internal',  # GCP metadata
}


def _validate_webhook_url(url: str) -> None:
    """
    Validate webhook URL is safe.

    Raises:
        NotificationError: If URL is invalid or targets blocked host.
    """
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ('http', 'https'):
            raise NotificationError(
                f"Webhook URL must use http or https, got: {parsed.scheme or 'none'}"
            )

        if not parsed.netloc:
            raise NotificationError("Webhook URL must have a valid hostname")

        hostname = (parsed.hostname or '').lower()

        if hostname in BLOCKED_HOSTS:
            raise NotificationError(
                f"Webhook URL cannot target internal host: {hostname}"
            )

        # Block private IP ranges
        if hostname.startswith('10.') or hostname.startswith('192.168.'):
            raise NotificationError(
                f"Webhook URL cannot target private network: {hostname}"
            )

        if hostname.startswith('172.'):
            parts = hostname.split('.')
            if len(parts) >= 2:
                try:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        raise NotificationError(
                            f"Webhook URL cannot target private network: {hostname}"
                        )
                except ValueError:
                    pass

    except ValueError as e:
        raise NotificationError(f"Invalid webhook URL: {e}")


def _sanitize_text(text: str, max_length: int = 500) -> str:
    """Sanitize text for notification payloads."""
    if not text:
        return ""

    # Remove control characters except newlines
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # Limit length
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."

    return text


def _send_http_request(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """
    Send HTTP POST request with JSON payload.

    Args:
        url: Target URL.
        payload: JSON payload to send.
        headers: Optional additional headers.
        timeout: Request timeout in seconds.

    Returns:
        Response info dict with status_code and body.

    Raises:
        NotificationError: If request fails.
    """
    _validate_webhook_url(url)

    # Serialize payload
    try:
        body = json.dumps(payload).encode('utf-8')
    except (TypeError, ValueError) as e:
        raise NotificationError(f"Failed to serialize payload: {e}")

    # Check payload size
    if len(body) > MAX_PAYLOAD_SIZE:
        raise NotificationError(
            f"Payload too large: {len(body)} bytes (max {MAX_PAYLOAD_SIZE})"
        )

    # Build headers
    request_headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'GoodAI-Metrics/1.0',
    }
    if headers:
        request_headers.update(headers)

    # Create request
    req = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method='POST',
    )

    # Create SSL context
    ssl_context = ssl.create_default_context()

    # Send request with retries
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(
                req,
                timeout=timeout,
                context=ssl_context,
            ) as response:
                return {
                    "status_code": response.status,
                    "body": response.read().decode('utf-8', errors='replace')[:1000],
                    "success": 200 <= response.status < 300,
                }
        except urllib.error.HTTPError as e:
            return {
                "status_code": e.code,
                "body": e.read().decode('utf-8', errors='replace')[:1000] if e.fp else "",
                "success": False,
                "error": str(e),
            }
        except urllib.error.URLError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                continue
        except Exception as e:
            last_error = e
            break

    raise NotificationError(f"Failed to send notification after {MAX_RETRIES + 1} attempts: {last_error}")


def send_webhook_notification(
    webhook_url: str,
    event_type: str,
    data: Dict[str, Any],
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send notification to a generic webhook endpoint.

    Args:
        webhook_url: Target webhook URL.
        event_type: Type of event (e.g., "analysis_complete", "threshold_breach").
        data: Event data to send.
        project: Optional project name.

    Returns:
        Response info dict.

    Raises:
        NotificationError: If notification fails.
    """
    payload = {
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "goodai-metrics",
        "data": data,
    }

    if project:
        payload["project"] = _sanitize_text(project, 100)

    return _send_http_request(webhook_url, payload)


def send_slack_notification(
    webhook_url: str,
    title: str,
    message: str,
    color: str = "good",
    fields: Optional[List[Dict[str, str]]] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send notification to Slack via webhook.

    Args:
        webhook_url: Slack webhook URL.
        title: Notification title.
        message: Main message text.
        color: Attachment color ("good", "warning", "danger", or hex).
        fields: Optional list of field dicts with title/value.
        project: Optional project name.

    Returns:
        Response info dict.

    Raises:
        NotificationError: If notification fails.
    """
    # Build Slack message format
    attachment = {
        "fallback": _sanitize_text(f"{title}: {message}", 500),
        "color": color,
        "title": _sanitize_text(title, 200),
        "text": _sanitize_text(message, 1000),
        "ts": int(datetime.utcnow().timestamp()),
    }

    if fields:
        attachment["fields"] = [
            {
                "title": _sanitize_text(f.get("title", ""), 100),
                "value": _sanitize_text(f.get("value", ""), 200),
                "short": f.get("short", True),
            }
            for f in fields[:10]  # Limit fields
        ]

    if project:
        attachment["footer"] = f"Project: {_sanitize_text(project, 100)}"

    payload = {
        "attachments": [attachment],
    }

    return _send_http_request(webhook_url, payload)


def notify_analysis_complete(
    webhook_url: str,
    analysis_results: Dict[str, Any],
    recommendations: List[Dict[str, Any]],
    overall_health: str,
    project: Optional[str] = None,
    is_slack: bool = False,
) -> Dict[str, Any]:
    """
    Send notification when analysis is complete.

    Args:
        webhook_url: Webhook URL (generic or Slack).
        analysis_results: Analysis results from analyzer.
        recommendations: List of recommendations.
        overall_health: Overall health status.
        project: Optional project name.
        is_slack: If True, format for Slack.

    Returns:
        Response info dict.
    """
    high_priority = sum(1 for r in recommendations if r.get("priority") == "HIGH")
    metrics_analyzed = analysis_results.get("metrics_analyzed", 0)
    industry = analysis_results.get("industry", "unknown")

    if is_slack:
        color = {
            "HEALTHY": "good",
            "NEEDS_ATTENTION": "warning",
            "CRITICAL": "danger",
        }.get(overall_health, "#808080")

        fields = [
            {"title": "Industry", "value": industry, "short": True},
            {"title": "Metrics Analyzed", "value": str(metrics_analyzed), "short": True},
            {"title": "Health Status", "value": overall_health, "short": True},
            {"title": "High Priority", "value": str(high_priority), "short": True},
        ]

        return send_slack_notification(
            webhook_url=webhook_url,
            title="AI Metrics Analysis Complete",
            message=f"Analysis completed with status: {overall_health}",
            color=color,
            fields=fields,
            project=project,
        )
    else:
        data = {
            "industry": industry,
            "metrics_analyzed": metrics_analyzed,
            "overall_health": overall_health,
            "high_priority_count": high_priority,
            "recommendations_count": len(recommendations),
        }

        return send_webhook_notification(
            webhook_url=webhook_url,
            event_type="analysis_complete",
            data=data,
            project=project,
        )


def notify_threshold_breach(
    webhook_url: str,
    metric_name: str,
    current_value: float,
    threshold_value: float,
    breach_type: str,
    project: Optional[str] = None,
    is_slack: bool = False,
) -> Dict[str, Any]:
    """
    Send notification when a threshold is breached.

    Args:
        webhook_url: Webhook URL.
        metric_name: Name of the metric.
        current_value: Current metric value.
        threshold_value: Threshold that was breached.
        breach_type: Type of breach (e.g., "above_max", "below_min").
        project: Optional project name.
        is_slack: If True, format for Slack.

    Returns:
        Response info dict.
    """
    if is_slack:
        fields = [
            {"title": "Metric", "value": metric_name, "short": True},
            {"title": "Current Value", "value": f"{current_value:.4f}", "short": True},
            {"title": "Threshold", "value": f"{threshold_value:.4f}", "short": True},
            {"title": "Breach Type", "value": breach_type, "short": True},
        ]

        return send_slack_notification(
            webhook_url=webhook_url,
            title="Threshold Breach Detected",
            message=f"Metric '{metric_name}' has breached its threshold",
            color="danger",
            fields=fields,
            project=project,
        )
    else:
        data = {
            "metric_name": metric_name,
            "current_value": current_value,
            "threshold_value": threshold_value,
            "breach_type": breach_type,
        }

        return send_webhook_notification(
            webhook_url=webhook_url,
            event_type="threshold_breach",
            data=data,
            project=project,
        )


def notify_regression_detected(
    webhook_url: str,
    regressions: List[Dict[str, Any]],
    project: Optional[str] = None,
    is_slack: bool = False,
) -> Dict[str, Any]:
    """
    Send notification when metric regressions are detected.

    Args:
        webhook_url: Webhook URL.
        regressions: List of regression details.
        project: Optional project name.
        is_slack: If True, format for Slack.

    Returns:
        Response info dict.
    """
    if is_slack:
        regression_text = "\n".join([
            f"- {r.get('metric', 'unknown')}: {r.get('previous_value', 0):.3f} -> {r.get('current_value', 0):.3f} ({r.get('change_percent', 0):+.1f}%)"
            for r in regressions[:5]  # Limit to 5
        ])

        if len(regressions) > 5:
            regression_text += f"\n... and {len(regressions) - 5} more"

        return send_slack_notification(
            webhook_url=webhook_url,
            title=f"Regression Detected: {len(regressions)} metric(s)",
            message=regression_text,
            color="warning",
            project=project,
        )
    else:
        data = {
            "regression_count": len(regressions),
            "regressions": [
                {
                    "metric": r.get("metric", "unknown"),
                    "previous_value": r.get("previous_value"),
                    "current_value": r.get("current_value"),
                    "change_percent": r.get("change_percent"),
                }
                for r in regressions[:20]  # Limit payload size
            ],
        }

        return send_webhook_notification(
            webhook_url=webhook_url,
            event_type="regression_detected",
            data=data,
            project=project,
        )


def is_slack_webhook(url: str) -> bool:
    """
    Detect if a webhook URL is a Slack webhook.

    Args:
        url: Webhook URL to check.

    Returns:
        True if URL appears to be a Slack webhook.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or '').lower()
        return 'slack.com' in hostname or 'hooks.slack.com' in hostname
    except Exception:
        return False
