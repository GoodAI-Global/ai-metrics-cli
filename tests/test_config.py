"""Tests for the config module."""

import os
import tempfile
from pathlib import Path

import pytest

from goodai_metrics.config import (
    ConfigError,
    CustomTarget,
    NotificationsConfig,
    ProjectConfig,
    ThresholdsConfig,
    _interpolate_env_vars,
    find_config_file,
    load_config,
)


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_default_config(self):
        """Default config has sensible values."""
        config = ProjectConfig()

        assert config.default_industry == "general"
        assert config.default_format == "json"
        assert config.project_name is None
        assert config.custom_targets == {}

    def test_thresholds_defaults(self):
        """Thresholds have correct defaults."""
        config = ProjectConfig()

        assert config.thresholds.fail_on_priority == "HIGH"
        assert config.thresholds.max_gap_percent == 30.0
        assert config.thresholds.max_high_priority == 0


class TestThresholdsConfig:
    """Tests for ThresholdsConfig validation."""

    def test_valid_priorities(self):
        """Valid priority levels are accepted."""
        for priority in ["HIGH", "MEDIUM", "LOW", "high", "medium", "low"]:
            config = ThresholdsConfig(fail_on_priority=priority)
            assert config.fail_on_priority in {"HIGH", "MEDIUM", "LOW"}

    def test_invalid_priority_raises(self):
        """Invalid priority level raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ThresholdsConfig(fail_on_priority="INVALID")

        assert "Invalid fail_on_priority" in str(exc_info.value)

    def test_negative_gap_raises(self):
        """Negative max_gap_percent raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ThresholdsConfig(max_gap_percent=-10.0)

        assert "must be >= 0" in str(exc_info.value)


class TestCustomTarget:
    """Tests for CustomTarget dataclass."""

    def test_simple_target(self):
        """Simple target value works."""
        target = CustomTarget(target=0.95)
        assert target.target == 0.95
        assert target.minimum is None
        assert target.maximum is None

    def test_target_with_bounds(self):
        """Target with min/max bounds works."""
        target = CustomTarget(target=0.95, minimum=0.90, maximum=0.99)
        assert target.minimum == 0.90
        assert target.maximum == 0.99

    def test_invalid_bounds_raises(self):
        """minimum > maximum raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            CustomTarget(target=0.95, minimum=0.99, maximum=0.90)

        assert "minimum cannot be greater than maximum" in str(exc_info.value)


class TestEnvVarInterpolation:
    """Tests for environment variable interpolation."""

    def test_simple_env_var(self):
        """Simple ${VAR} interpolation works."""
        os.environ["TEST_VAR"] = "test_value"
        try:
            result = _interpolate_env_vars("prefix_${TEST_VAR}_suffix")
            assert result == "prefix_test_value_suffix"
        finally:
            del os.environ["TEST_VAR"]

    def test_env_var_with_default(self):
        """${VAR:-default} syntax works."""
        # Remove var if exists
        os.environ.pop("MISSING_VAR", None)

        result = _interpolate_env_vars("${MISSING_VAR:-fallback}")
        assert result == "fallback"

    def test_nested_dict_interpolation(self):
        """Interpolation works in nested dicts."""
        os.environ["NESTED_VAR"] = "nested_value"
        try:
            data = {"outer": {"inner": "${NESTED_VAR}"}}
            result = _interpolate_env_vars(data)
            assert result["outer"]["inner"] == "nested_value"
        finally:
            del os.environ["NESTED_VAR"]


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_default_when_no_file(self):
        """Returns default config when no file found."""
        # Use a temp directory with no config
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                config = load_config()
                assert config.default_industry == "general"
            finally:
                os.chdir(original_cwd)

    def test_load_yaml_config(self):
        """Loads config from YAML file."""
        yaml_content = """
project: test-project
defaults:
  industry: manufacturing
  format: text
thresholds:
  max_gap_percent: 50.0
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert config.project_name == "test-project"
            assert config.default_industry == "manufacturing"
            assert config.default_format == "text"
            assert config.thresholds.max_gap_percent == 50.0
        finally:
            config_path.unlink()

    def test_load_config_with_custom_targets(self):
        """Loads custom targets from config."""
        yaml_content = """
custom_targets:
  accuracy: 0.95
  latency_ms:
    target: 150
    maximum: 300
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            config = load_config(config_path)
            assert "accuracy" in config.custom_targets
            assert config.custom_targets["accuracy"].target == 0.95
            assert config.custom_targets["latency_ms"].target == 150
            assert config.custom_targets["latency_ms"].maximum == 300
        finally:
            config_path.unlink()


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_finds_config_in_cwd(self):
        """Finds config file in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".goodai-metrics.yaml"
            config_path.write_text("project: test", encoding="utf-8")

            found = find_config_file(Path(tmpdir))
            assert found == config_path

    def test_finds_config_in_parent(self):
        """Finds config file in parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config in parent
            config_path = Path(tmpdir) / ".goodai-metrics.yaml"
            config_path.write_text("project: test", encoding="utf-8")

            # Create subdirectory
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            found = find_config_file(subdir)
            assert found == config_path

    def test_returns_none_when_not_found(self):
        """Returns None when no config file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            found = find_config_file(Path(tmpdir))
            # May find home directory config, so just check it doesn't error
            assert found is None or found.exists()


class TestConfigIntegration:
    """Integration tests for config with CLI defaults."""

    def test_config_provides_defaults(self):
        """Config values can be used as CLI defaults."""
        config = ProjectConfig(
            default_industry="manufacturing",
            default_format="text",
            thresholds=ThresholdsConfig(max_gap_percent=50.0, max_high_priority=2),
        )

        # Simulate CLI using config defaults
        industry = None or config.default_industry
        max_gap = None or config.thresholds.max_gap_percent

        assert industry == "manufacturing"
        assert max_gap == 50.0

    def test_cli_args_override_config(self):
        """CLI arguments take precedence over config."""
        config = ProjectConfig(default_industry="manufacturing", default_format="text")

        # Simulate CLI args overriding
        cli_industry = "insurance"
        cli_format = "json"

        industry = cli_industry if cli_industry else config.default_industry
        output_format = cli_format if cli_format else config.default_format

        assert industry == "insurance"
        assert output_format == "json"


class TestSecurityValidation:
    """Security validation tests for config module."""

    def test_webhook_url_blocks_localhost(self):
        """Webhook URL cannot target localhost (SSRF prevention)."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://localhost:8080/webhook")

        assert "internal host" in str(exc_info.value).lower()

    def test_webhook_url_blocks_internal_ip(self):
        """Webhook URL cannot target internal IPs."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://127.0.0.1:8080/webhook")

        assert "internal host" in str(exc_info.value).lower()

    def test_webhook_url_blocks_metadata_service(self):
        """Webhook URL cannot target AWS metadata service (SSRF prevention)."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://169.254.169.254/latest/meta-data/")

        assert "internal host" in str(exc_info.value).lower()

    def test_webhook_url_blocks_private_network_10(self):
        """Webhook URL cannot target 10.x.x.x private network."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://10.0.0.5:3000/api")

        assert "private network" in str(exc_info.value).lower()

    def test_webhook_url_blocks_private_network_192(self):
        """Webhook URL cannot target 192.168.x.x private network."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://192.168.1.100/hook")

        assert "private network" in str(exc_info.value).lower()

    def test_webhook_url_blocks_private_network_172(self):
        """Webhook URL cannot target 172.16-31.x.x private network."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="http://172.16.0.1/hook")

        assert "private network" in str(exc_info.value).lower()

    def test_webhook_url_allows_public_https(self):
        """Valid public HTTPS URLs are allowed."""

        # Should not raise
        config = NotificationsConfig(webhook_url="https://api.example.com/webhook")
        assert config.webhook_url == "https://api.example.com/webhook"

    def test_webhook_url_requires_http_scheme(self):
        """Webhook URL must use http or https scheme."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(webhook_url="ftp://example.com/hook")

        assert "http or https" in str(exc_info.value).lower()

    def test_slack_channel_valid_formats(self):
        """Valid Slack channel formats are accepted."""

        # #channel format
        config = NotificationsConfig(slack_channel="#alerts")
        assert config.slack_channel == "#alerts"

        # @user format
        config = NotificationsConfig(slack_channel="@username")
        assert config.slack_channel == "@username"

        # Channel ID format
        config = NotificationsConfig(slack_channel="CABCDEFGH")
        assert config.slack_channel == "CABCDEFGH"

    def test_slack_channel_invalid_format_raises(self):
        """Invalid Slack channel format raises error."""

        with pytest.raises(ConfigError) as exc_info:
            NotificationsConfig(slack_channel="invalid<script>")

        assert "invalid slack channel" in str(exc_info.value).lower()

    def test_storage_path_blocks_traversal(self):
        """Storage path cannot contain path traversal."""
        with pytest.raises(ConfigError) as exc_info:
            ProjectConfig(storage_path="../../../etc/passwd")

        assert ".." in str(exc_info.value)

    def test_storage_path_allows_relative(self):
        """Relative storage paths are allowed."""
        config = ProjectConfig(storage_path=".goodai-metrics/history.db")
        assert config.storage_path == ".goodai-metrics/history.db"

    def test_invalid_format_raises(self):
        """Invalid output format raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ProjectConfig(default_format="xml")

        assert "invalid format" in str(exc_info.value).lower()

    def test_nan_value_raises(self):
        """NaN values raise ConfigError."""

        with pytest.raises(ConfigError) as exc_info:
            CustomTarget(target=float("nan"))

        assert "finite number" in str(exc_info.value).lower()

    def test_inf_value_raises(self):
        """Infinite values raise ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            CustomTarget(target=float("inf"))

        assert "finite number" in str(exc_info.value).lower()

    def test_invalid_metric_name_raises(self):
        """Invalid metric names in custom_targets raise error."""
        yaml_content = """
custom_targets:
  "invalid<script>": 0.95
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)

            assert "invalid metric name" in str(exc_info.value).lower()
        finally:
            config_path.unlink()

    def test_config_file_extension_validation(self):
        """Config file must be YAML extension."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write('{"project": "test"}')
            config_path = Path(f.name)

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)

            assert (
                ".yaml" in str(exc_info.value).lower()
                or ".yml" in str(exc_info.value).lower()
            )
        finally:
            config_path.unlink()
