"""Tests for webhook notifications."""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from goodai_metrics.notifications import (
    NotificationError,
    _sanitize_text,
    _send_http_request,
    _validate_webhook_url,
    is_slack_webhook,
    notify_analysis_complete,
    notify_regression_detected,
    notify_threshold_breach,
    send_slack_notification,
    send_webhook_notification,
)


class TestValidateWebhookUrl:
    """Tests for webhook URL validation."""

    def test_valid_https_url(self):
        """Valid HTTPS URL passes."""
        _validate_webhook_url("https://example.com/webhook")  # Should not raise

    def test_valid_http_url(self):
        """Valid HTTP URL passes."""
        _validate_webhook_url("http://example.com/webhook")  # Should not raise

    def test_localhost_blocked(self):
        """Localhost is blocked."""
        with pytest.raises(NotificationError, match="cannot target internal"):
            _validate_webhook_url("https://localhost/webhook")

    def test_127_0_0_1_blocked(self):
        """127.0.0.1 is blocked."""
        with pytest.raises(NotificationError, match="cannot target internal"):
            _validate_webhook_url("https://127.0.0.1/webhook")

    def test_private_10_blocked(self):
        """10.x.x.x networks blocked."""
        with pytest.raises(NotificationError, match="cannot target private"):
            _validate_webhook_url("https://10.0.0.1/webhook")

    def test_private_192_168_blocked(self):
        """192.168.x.x networks blocked."""
        with pytest.raises(NotificationError, match="cannot target private"):
            _validate_webhook_url("https://192.168.1.1/webhook")

    def test_private_172_16_blocked(self):
        """172.16-31.x.x networks blocked."""
        with pytest.raises(NotificationError, match="cannot target private"):
            _validate_webhook_url("https://172.16.0.1/webhook")

    def test_172_32_allowed(self):
        """172.32.x.x is not private and allowed."""
        _validate_webhook_url("https://172.32.0.1/webhook")  # Should not raise

    def test_aws_metadata_blocked(self):
        """AWS metadata IP blocked."""
        with pytest.raises(NotificationError, match="cannot target internal"):
            _validate_webhook_url("https://169.254.169.254/latest")

    def test_gcp_metadata_blocked(self):
        """GCP metadata hostname blocked."""
        with pytest.raises(NotificationError, match="cannot target internal"):
            _validate_webhook_url("https://metadata.google.internal/")

    def test_invalid_scheme(self):
        """Non-HTTP scheme raises error."""
        with pytest.raises(NotificationError, match="must use http or https"):
            _validate_webhook_url("ftp://example.com/webhook")

    def test_missing_hostname(self):
        """Missing hostname raises error."""
        with pytest.raises(NotificationError, match="must have a valid hostname"):
            _validate_webhook_url("https:///webhook")


class TestSanitizeText:
    """Tests for text sanitization."""

    def test_normal_text_unchanged(self):
        """Normal text unchanged."""
        assert _sanitize_text("Hello World") == "Hello World"

    def test_control_chars_removed(self):
        """Control characters removed."""
        assert _sanitize_text("Hello\x00\x01World") == "HelloWorld"

    def test_newlines_preserved(self):
        """Newlines preserved."""
        assert _sanitize_text("Hello\nWorld") == "Hello\nWorld"

    def test_length_limited(self):
        """Long text truncated."""
        long_text = "a" * 1000
        result = _sanitize_text(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")


class TestSendHttpRequest:
    """Tests for HTTP request sending."""

    @patch("urllib.request.urlopen")
    def test_successful_request(self, mock_urlopen):
        """Successful request returns response."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = _send_http_request("https://example.com/webhook", {"message": "test"})

        assert result["status_code"] == 200
        assert result["success"] is True

    @patch("urllib.request.urlopen")
    def test_http_error_returned(self, mock_urlopen):
        """HTTP error returns error info."""
        mock_error = urllib.error.HTTPError(
            "https://example.com", 400, "Bad Request", {}, None
        )
        mock_urlopen.side_effect = mock_error

        result = _send_http_request("https://example.com/webhook", {"message": "test"})

        assert result["status_code"] == 400
        assert result["success"] is False

    def test_payload_size_limit(self):
        """Large payload raises error."""
        large_payload = {"data": "x" * 200000}

        with pytest.raises(NotificationError, match="Payload too large"):
            _send_http_request("https://example.com/webhook", large_payload)


class TestSendWebhookNotification:
    """Tests for generic webhook notifications."""

    @patch("goodai_metrics.notifications._send_http_request")
    def test_sends_correct_payload(self, mock_send):
        """Sends correct payload structure."""
        mock_send.return_value = {"status_code": 200, "success": True}

        send_webhook_notification(
            webhook_url="https://example.com/webhook",
            event_type="test_event",
            data={"key": "value"},
            project="test-project",
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]

        assert payload["event"] == "test_event"
        assert payload["source"] == "goodai-metrics"
        assert payload["data"] == {"key": "value"}
        assert payload["project"] == "test-project"
        assert "timestamp" in payload

    @patch("goodai_metrics.notifications._send_http_request")
    def test_without_project(self, mock_send):
        """Works without project name."""
        mock_send.return_value = {"status_code": 200, "success": True}

        result = send_webhook_notification(
            webhook_url="https://example.com/webhook",
            event_type="test_event",
            data={"key": "value"},
        )

        assert result["success"] is True


class TestSendSlackNotification:
    """Tests for Slack webhook notifications."""

    @patch("goodai_metrics.notifications._send_http_request")
    def test_sends_slack_format(self, mock_send):
        """Sends Slack-formatted payload."""
        mock_send.return_value = {"status_code": 200, "success": True}

        send_slack_notification(
            webhook_url="https://hooks.slack.com/services/xxx",
            title="Test Title",
            message="Test message",
            color="good",
            project="test-project",
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]

        assert "attachments" in payload
        attachment = payload["attachments"][0]
        assert attachment["title"] == "Test Title"
        assert attachment["text"] == "Test message"
        assert attachment["color"] == "good"
        assert "Project: test-project" in attachment["footer"]

    @patch("goodai_metrics.notifications._send_http_request")
    def test_with_fields(self, mock_send):
        """Includes fields in payload."""
        mock_send.return_value = {"status_code": 200, "success": True}

        fields = [
            {"title": "Field1", "value": "Value1"},
            {"title": "Field2", "value": "Value2"},
        ]

        send_slack_notification(
            webhook_url="https://hooks.slack.com/services/xxx",
            title="Test",
            message="Test",
            fields=fields,
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]
        attachment = payload["attachments"][0]

        assert len(attachment["fields"]) == 2


class TestNotifyAnalysisComplete:
    """Tests for analysis complete notifications."""

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_generic_webhook(self, mock_send):
        """Sends generic webhook notification."""
        mock_send.return_value = {"status_code": 200, "success": True}

        analysis_results = {
            "industry": "manufacturing",
            "metrics_analyzed": 5,
        }
        recommendations = [
            {"priority": "HIGH"},
            {"priority": "MEDIUM"},
        ]

        notify_analysis_complete(
            webhook_url="https://example.com/webhook",
            analysis_results=analysis_results,
            recommendations=recommendations,
            overall_health="NEEDS_ATTENTION",
            is_slack=False,
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["event_type"] == "analysis_complete"
        assert call_args[1]["data"]["high_priority_count"] == 1

    @patch("goodai_metrics.notifications.send_slack_notification")
    def test_slack_webhook(self, mock_send):
        """Sends Slack notification."""
        mock_send.return_value = {"status_code": 200, "success": True}

        analysis_results = {
            "industry": "manufacturing",
            "metrics_analyzed": 5,
        }
        recommendations = [{"priority": "HIGH"}]

        notify_analysis_complete(
            webhook_url="https://hooks.slack.com/services/xxx",
            analysis_results=analysis_results,
            recommendations=recommendations,
            overall_health="CRITICAL",
            is_slack=True,
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["color"] == "danger"


class TestNotifyThresholdBreach:
    """Tests for threshold breach notifications."""

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_generic_webhook(self, mock_send):
        """Sends breach notification."""
        mock_send.return_value = {"status_code": 200, "success": True}

        notify_threshold_breach(
            webhook_url="https://example.com/webhook",
            metric_name="accuracy",
            current_value=0.65,
            threshold_value=0.80,
            breach_type="below_min",
            is_slack=False,
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["event_type"] == "threshold_breach"
        assert call_args[1]["data"]["metric_name"] == "accuracy"


class TestNotifyRegressionDetected:
    """Tests for regression notifications."""

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_generic_webhook(self, mock_send):
        """Sends regression notification."""
        mock_send.return_value = {"status_code": 200, "success": True}

        regressions = [
            {
                "metric": "accuracy",
                "previous_value": 0.90,
                "current_value": 0.80,
                "change_percent": -11.1,
            }
        ]

        notify_regression_detected(
            webhook_url="https://example.com/webhook",
            regressions=regressions,
            is_slack=False,
        )

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[1]["event_type"] == "regression_detected"
        assert call_args[1]["data"]["regression_count"] == 1


class TestIsSlackWebhook:
    """Tests for Slack webhook detection."""

    def test_detects_slack_webhook(self):
        """Detects Slack webhook URLs."""
        assert is_slack_webhook("https://hooks.slack.com/services/xxx") is True
        assert is_slack_webhook("https://slack.com/api/webhook") is True

    def test_rejects_non_slack(self):
        """Rejects non-Slack URLs."""
        assert is_slack_webhook("https://example.com/webhook") is False
        assert is_slack_webhook("https://discord.com/webhook") is False

    def test_handles_invalid_urls(self):
        """Handles invalid URLs gracefully."""
        assert is_slack_webhook("not-a-url") is False
        assert is_slack_webhook("") is False


class TestSecurityLimits:
    """Tests for security limits."""

    @patch("goodai_metrics.notifications._send_http_request")
    def test_sanitizes_project_name(self, mock_send):
        """Project name is sanitized."""
        mock_send.return_value = {"status_code": 200, "success": True}

        send_webhook_notification(
            webhook_url="https://example.com/webhook",
            event_type="test",
            data={},
            project="test\x00project\x01name",
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]
        assert "\x00" not in payload["project"]
        assert "\x01" not in payload["project"]

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_limits_regression_count(self, mock_send):
        """Limits regression count in payload."""
        mock_send.return_value = {"status_code": 200, "success": True}

        regressions = [{"metric": f"metric_{i}"} for i in range(100)]

        notify_regression_detected(
            webhook_url="https://example.com/webhook",
            regressions=regressions,
            is_slack=False,
        )

        call_args = mock_send.call_args
        # The data should be limited to 20 regressions
        assert len(call_args[1]["data"]["regressions"]) <= 20

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_sanitizes_metric_name_in_threshold_breach(self, mock_send):
        """Metric name is sanitized in threshold breach."""
        mock_send.return_value = {"status_code": 200, "success": True}

        notify_threshold_breach(
            webhook_url="https://example.com/webhook",
            metric_name="metric\x00with\x01control\x02chars",
            current_value=0.65,
            threshold_value=0.80,
            breach_type="below_min",
            is_slack=False,
        )

        call_args = mock_send.call_args
        assert "\x00" not in call_args[1]["data"]["metric_name"]
        assert "\x01" not in call_args[1]["data"]["metric_name"]

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_sanitizes_breach_type(self, mock_send):
        """Breach type is sanitized."""
        mock_send.return_value = {"status_code": 200, "success": True}

        notify_threshold_breach(
            webhook_url="https://example.com/webhook",
            metric_name="accuracy",
            current_value=0.65,
            threshold_value=0.80,
            breach_type="below\x00min",
            is_slack=False,
        )

        call_args = mock_send.call_args
        assert "\x00" not in call_args[1]["data"]["breach_type"]

    @patch("goodai_metrics.notifications.send_webhook_notification")
    def test_sanitizes_regression_metric_names(self, mock_send):
        """Regression metric names are sanitized."""
        mock_send.return_value = {"status_code": 200, "success": True}

        regressions = [
            {
                "metric": "metric\x00name",
                "previous_value": 0.90,
                "current_value": 0.80,
                "change_percent": -11.1,
            }
        ]

        notify_regression_detected(
            webhook_url="https://example.com/webhook",
            regressions=regressions,
            is_slack=False,
        )

        call_args = mock_send.call_args
        assert "\x00" not in call_args[1]["data"]["regressions"][0]["metric"]

    @patch("goodai_metrics.notifications._send_http_request")
    def test_invalid_slack_color_defaults_to_gray(self, mock_send):
        """Invalid Slack color defaults to gray."""
        mock_send.return_value = {"status_code": 200, "success": True}

        send_slack_notification(
            webhook_url="https://hooks.slack.com/services/xxx",
            title="Test",
            message="Test",
            color="invalid_color",
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]
        assert payload["attachments"][0]["color"] == "#808080"

    @patch("goodai_metrics.notifications._send_http_request")
    def test_valid_hex_color_accepted(self, mock_send):
        """Valid hex color is accepted."""
        mock_send.return_value = {"status_code": 200, "success": True}

        send_slack_notification(
            webhook_url="https://hooks.slack.com/services/xxx",
            title="Test",
            message="Test",
            color="#FF5733",
        )

        call_args = mock_send.call_args
        payload = call_args[0][1]
        assert payload["attachments"][0]["color"] == "#FF5733"
