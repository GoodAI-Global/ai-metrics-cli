"""
Configuration management for Good AI Metrics CLI.

Supports YAML config files with environment variable interpolation.
Provides type-safe configuration with sensible defaults.

Example config file (.goodai-metrics.yaml):

    project: my-ai-project

    defaults:
      industry: manufacturing
      format: json

    thresholds:
      fail_on_priority: HIGH  # HIGH, MEDIUM, or LOW
      max_gap_percent: 30.0   # 0-100
      max_high_priority: 0    # >= 0

Configuration search order:
  1. Current directory and parent directories
  2. Home directory (~/.goodai-metrics.yaml)
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# Constants for config file discovery
CONFIG_FILENAMES = [
    ".goodai-metrics.yaml",
    ".goodai-metrics.yml",
    "goodai-metrics.yaml",
]
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Valid output formats
VALID_FORMATS = {"json", "text"}

# Slack channel pattern: #channel, @user, or channel ID (CXXXXXXXX)
SLACK_CHANNEL_PATTERN = re.compile(r"^([#@][\w\-]+|C[A-Z0-9]{8,})$")

# Blocked hosts for webhook URLs (security)
BLOCKED_WEBHOOK_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP metadata
}


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


def _validate_webhook_url(url: Optional[str]) -> None:
    """
    Validate webhook URL is safe and properly formatted.

    Prevents SSRF attacks by blocking internal/metadata URLs.

    Raises:
        ConfigError: If URL is invalid or targets blocked host.
    """
    if not url:
        return

    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise ConfigError(
                f"Webhook URL must use http or https, got: {parsed.scheme or 'none'}"
            )

        if not parsed.netloc:
            raise ConfigError("Webhook URL must have a valid hostname")

        hostname = parsed.hostname or ""
        if hostname.lower() in BLOCKED_WEBHOOK_HOSTS:
            raise ConfigError(f"Webhook URL cannot target internal host: {hostname}")

        # Block private IP ranges
        if hostname.startswith("10.") or hostname.startswith("192.168."):
            raise ConfigError(f"Webhook URL cannot target private network: {hostname}")

        if hostname.startswith("172."):
            parts = hostname.split(".")
            if len(parts) >= 2:
                try:
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        raise ConfigError(
                            f"Webhook URL cannot target private network: {hostname}"
                        )
                except ValueError:
                    pass

    except ValueError as e:
        raise ConfigError(f"Invalid webhook URL: {e}") from e


def _validate_slack_channel(channel: Optional[str]) -> None:
    """
    Validate Slack channel format.

    Raises:
        ConfigError: If channel format is invalid.
    """
    if not channel:
        return

    if not SLACK_CHANNEL_PATTERN.match(channel):
        raise ConfigError(
            f"Invalid Slack channel format: {channel}. "
            "Use #channel, @user, or channel ID (CXXXXXXXX)"
        )


def _validate_storage_path(
    path: Optional[str], config_dir: Optional[Path] = None
) -> None:
    """
    Validate storage path is safe (no path traversal).

    Raises:
        ConfigError: If path attempts traversal outside project.
    """
    if not path:
        return

    try:
        # Resolve the path
        storage = Path(path)

        # Check for obvious path traversal
        if ".." in str(storage):
            raise ConfigError(f"Storage path cannot contain '..': {path}")

        # If absolute path, must be within reasonable locations
        if storage.is_absolute():
            # Allow /tmp and home directory
            home = Path.home()
            allowed_roots = [Path("/tmp"), home, Path("/var/tmp")]

            is_allowed = any(
                str(storage).startswith(str(root)) for root in allowed_roots
            )

            if not is_allowed:
                raise ConfigError(
                    f"Absolute storage path must be within home or tmp directory: {path}"
                )

    except (ValueError, RuntimeError) as e:
        raise ConfigError(f"Invalid storage path: {e}") from e


def _validate_format(fmt: str) -> None:
    """Validate output format."""
    if fmt not in VALID_FORMATS:
        raise ConfigError(f"Invalid format: {fmt}. Must be one of: {VALID_FORMATS}")


def _validate_numeric_bounds(
    value: float,
    name: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> None:
    """Validate numeric value is within bounds."""
    import math

    if math.isnan(value) or math.isinf(value):
        raise ConfigError(f"{name} must be a finite number, got: {value}")

    if min_val is not None and value < min_val:
        raise ConfigError(f"{name} must be >= {min_val}, got: {value}")

    if max_val is not None and value > max_val:
        raise ConfigError(f"{name} must be <= {max_val}, got: {value}")


@dataclass
class ThresholdsConfig:
    """CI/CD threshold configuration."""

    fail_on_priority: str = "HIGH"  # HIGH, MEDIUM, or LOW
    max_gap_percent: float = 30.0
    max_high_priority: int = 0

    def __post_init__(self) -> None:
        valid_priorities = {"HIGH", "MEDIUM", "LOW"}
        if self.fail_on_priority.upper() not in valid_priorities:
            raise ConfigError(
                f"Invalid fail_on_priority: {self.fail_on_priority}. "
                f"Must be one of: {valid_priorities}"
            )
        self.fail_on_priority = self.fail_on_priority.upper()

        _validate_numeric_bounds(self.max_gap_percent, "max_gap_percent", 0, 100)
        _validate_numeric_bounds(
            float(self.max_high_priority), "max_high_priority", 0, 100
        )


@dataclass
class NotificationsConfig:
    """Notification configuration."""

    on_regression: bool = False
    on_threshold_breach: bool = False
    webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_webhook_url(self.webhook_url)
        _validate_slack_channel(self.slack_channel)


@dataclass
class CustomTarget:
    """Custom target for a metric."""

    target: float  # Goal value
    minimum: Optional[float] = None  # Acceptable floor
    maximum: Optional[float] = None  # Acceptable ceiling

    def __post_init__(self) -> None:
        _validate_numeric_bounds(self.target, "target")

        if self.minimum is not None:
            _validate_numeric_bounds(self.minimum, "minimum")
        if self.maximum is not None:
            _validate_numeric_bounds(self.maximum, "maximum")

        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ConfigError("minimum cannot be greater than maximum")


@dataclass
class CustomBenchmark:
    """
    Custom benchmark definition with full percentile data.

    Allows defining organization-specific benchmarks for metrics
    that override or extend industry defaults.

    Example in config:
        custom_benchmarks:
          my_industry:
            custom_metric:
              p25: 0.70
              p50: 0.80
              p75: 0.90
              p90: 0.95
              description: "Our custom accuracy metric"
    """

    p25: float  # 25th percentile
    p50: float  # 50th percentile (median)
    p75: float  # 75th percentile
    p90: float  # 90th percentile
    description: Optional[str] = None  # Human-readable description
    higher_is_better: Optional[bool] = None  # Override default detection

    def __post_init__(self) -> None:
        _validate_numeric_bounds(self.p25, "p25")
        _validate_numeric_bounds(self.p50, "p50")
        _validate_numeric_bounds(self.p75, "p75")
        _validate_numeric_bounds(self.p90, "p90")

    def to_dict(self) -> dict[str, Any]:
        """Convert to benchmark dictionary format."""
        result = {
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
        }
        if self.description:
            result["description"] = self.description
        if self.higher_is_better is not None:
            result["higher_is_better"] = self.higher_is_better
        return result


@dataclass
class ProjectConfig:
    """Complete project configuration."""

    # Project metadata
    project_name: Optional[str] = None
    version: str = "1.0"

    # Analysis defaults
    default_industry: str = "general"
    default_format: str = "json"

    # Custom targets override benchmarks (simple target/min/max)
    custom_targets: dict[str, CustomTarget] = field(default_factory=dict)

    # Custom benchmarks with full percentile data (industry -> metric -> benchmark)
    custom_benchmarks: dict[str, dict[str, CustomBenchmark]] = field(
        default_factory=dict
    )

    # Additional benchmark files to load
    benchmark_files: list = field(default_factory=list)

    # CI/CD thresholds
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)

    # Notifications
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)

    # Storage settings
    store_results: bool = False
    storage_path: Optional[str] = None

    # Source file path (for reference)
    _config_path: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _validate_format(self.default_format)
        _validate_storage_path(self.storage_path)

    def get_merged_benchmarks(self) -> dict[str, dict[str, Any]]:
        """
        Get custom benchmarks merged into a dictionary format.

        Returns dict of industry -> metric -> {p25, p50, p75, p90}.
        """
        result: dict[str, dict[str, Any]] = {}
        for industry, metrics in self.custom_benchmarks.items():
            result[industry] = {}
            for metric_name, benchmark in metrics.items():
                result[industry][metric_name] = benchmark.to_dict()
        return result


def _interpolate_env_vars(value: Any, strict: bool = False) -> Any:
    """
    Recursively interpolate environment variables in config values.

    Supports ${VAR_NAME} syntax with optional default: ${VAR_NAME:-default}

    Args:
        value: Value to interpolate.
        strict: If True, raise error for missing env vars without defaults.

    Returns:
        Interpolated value.

    Raises:
        ConfigError: If strict=True and env var is missing without default.
    """
    if isinstance(value, str):

        def replace_env_var(match: re.Match) -> str:
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
            else:
                var_name = var_expr
                default = None

            env_value = os.environ.get(var_name)

            if env_value is None:
                if default is not None:
                    return default
                if strict:
                    raise ConfigError(
                        f"Required environment variable not set: {var_name}"
                    )
                return ""  # Return empty string for non-strict mode

            return env_value

        return ENV_VAR_PATTERN.sub(replace_env_var, value)

    elif isinstance(value, dict):
        return {k: _interpolate_env_vars(v, strict) for k, v in value.items()}

    elif isinstance(value, list):
        return [_interpolate_env_vars(item, strict) for item in value]

    return value


def _parse_yaml_safe(content: str) -> dict[str, Any]:
    """
    Parse YAML content safely.

    Uses PyYAML if available, otherwise falls back to minimal parser.
    The fallback parser only supports simple key: value configs.
    """
    try:
        import yaml

        return yaml.safe_load(content) or {}
    except ImportError:
        # Fallback: minimal parsing for simple key: value files
        result: dict[str, Any] = {}
        current_section: Optional[str] = None
        current_indent = 0

        for line in content.split("\n"):
            # Skip empty lines and comments
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Calculate indent level
            indent = len(line) - len(line.lstrip())

            # Check for key: value pattern
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                # Remove quotes from values
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Handle boolean values
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif _is_float(value):
                    value = float(value)

                if indent == 0:
                    if value == "" or value is None:
                        # Start of a new section
                        current_section = key
                        result[key] = {}
                        current_indent = indent
                    else:
                        result[key] = value
                        current_section = None
                elif current_section and indent > current_indent:
                    if isinstance(result.get(current_section), dict):
                        result[current_section][key] = value if value != "" else {}

        return result


def _is_float(value: str) -> bool:
    """Check if string represents a float."""
    try:
        float(value)
        return "." in value
    except (ValueError, TypeError):
        return False


def find_config_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find config file by searching upward from start_path.

    Search order:
      1. start_path and its parents
      2. Home directory

    Args:
        start_path: Starting directory. Defaults to current working directory.

    Returns:
        Path to config file if found, None otherwise.
    """
    if start_path is None:
        start_path = Path.cwd()

    start_path = Path(start_path).resolve()

    # Search upward through directory tree
    current = start_path
    while current != current.parent:
        for filename in CONFIG_FILENAMES:
            config_path = current / filename
            if config_path.is_file():
                return config_path
        current = current.parent

    # Also check home directory
    home = Path.home()
    for filename in CONFIG_FILENAMES:
        config_path = home / filename
        if config_path.is_file():
            return config_path

    return None


def load_config(config_path: Optional[Path] = None) -> ProjectConfig:
    """
    Load configuration from YAML file.

    Args:
        config_path: Explicit path to config file. If None, searches for config.

    Returns:
        ProjectConfig with loaded or default values.

    Raises:
        ConfigError: If config file is invalid.
    """
    if config_path is None:
        config_path = find_config_file()

    if config_path is None:
        # Return default config
        return ProjectConfig()

    config_path = Path(config_path).resolve()

    # Validate file extension
    if config_path.suffix.lower() not in (".yaml", ".yml"):
        raise ConfigError(
            f"Config file must be YAML (.yaml or .yml), got: {config_path.suffix}"
        )

    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        content = config_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ConfigError(
            f"Config file must be UTF-8 encoded. Error at position {e.start}: {e.reason}"
        ) from e
    except OSError as e:
        raise ConfigError(f"Failed to read config file: {e}") from e

    # Parse YAML
    try:
        raw_config = _parse_yaml_safe(content)
    except Exception as e:
        raise ConfigError(f"Failed to parse config file: {e}") from e

    # Interpolate environment variables
    raw_config = _interpolate_env_vars(raw_config)

    # Build ProjectConfig
    return _build_config(raw_config, config_path)


def _build_config(raw: dict[str, Any], config_path: Path) -> ProjectConfig:
    """Build ProjectConfig from raw parsed data."""
    # Extract nested configs
    thresholds_raw = raw.get("thresholds", raw.get("ci", {}))
    notifications_raw = raw.get("notifications", {})
    custom_targets_raw = raw.get("custom_targets", {})
    defaults_raw = raw.get("defaults", {})

    # Build thresholds with validation
    try:
        max_gap = float(thresholds_raw.get("max_gap_percent", 30.0))
        max_high = int(thresholds_raw.get("max_high_priority", 0))
    except (ValueError, TypeError) as e:
        raise ConfigError(f"Invalid threshold value: {e}") from e

    thresholds = ThresholdsConfig(
        fail_on_priority=str(thresholds_raw.get("fail_on_priority", "HIGH")),
        max_gap_percent=max_gap,
        max_high_priority=max_high,
    )

    # Build notifications with validation
    webhook_url = notifications_raw.get("webhook_url") or notifications_raw.get(
        "webhook"
    )
    slack_channel = notifications_raw.get("slack_channel")

    notifications = NotificationsConfig(
        on_regression=bool(notifications_raw.get("on_regression", False)),
        on_threshold_breach=bool(notifications_raw.get("on_threshold_breach", False)),
        webhook_url=webhook_url if webhook_url else None,
        slack_channel=slack_channel if slack_channel else None,
    )

    # Build custom targets
    custom_targets = {}
    for metric, target_raw in custom_targets_raw.items():
        # Validate metric name (basic sanitization)
        if not re.match(r"^[\w_]+$", str(metric)):
            raise ConfigError(
                f"Invalid metric name in custom_targets: {metric}. "
                "Use only letters, numbers, and underscores."
            )

        try:
            if isinstance(target_raw, dict):
                custom_targets[metric] = CustomTarget(
                    target=float(target_raw.get("target", 0)),
                    minimum=(
                        float(target_raw["minimum"])
                        if "minimum" in target_raw
                        else None
                    ),
                    maximum=(
                        float(target_raw["maximum"])
                        if "maximum" in target_raw
                        else None
                    ),
                )
            else:
                # Simple value = target only
                custom_targets[metric] = CustomTarget(target=float(target_raw))
        except (ValueError, TypeError) as e:
            raise ConfigError(f"Invalid custom target for {metric}: {e}") from e

    # Build custom benchmarks
    custom_benchmarks_raw = raw.get("custom_benchmarks", {})
    custom_benchmarks: dict[str, dict[str, CustomBenchmark]] = {}

    for industry, metrics_raw in custom_benchmarks_raw.items():
        # Validate industry name
        if not re.match(r"^[\w_-]+$", str(industry)):
            raise ConfigError(
                f"Invalid industry name in custom_benchmarks: {industry}. "
                "Use only letters, numbers, underscores, and hyphens."
            )

        if not isinstance(metrics_raw, dict):
            raise ConfigError(
                f"custom_benchmarks.{industry} must contain metric definitions"
            )

        custom_benchmarks[industry] = {}
        for metric, benchmark_raw in metrics_raw.items():
            # Validate metric name
            if not re.match(r"^[\w_-]+$", str(metric)):
                raise ConfigError(
                    f"Invalid metric name in custom_benchmarks.{industry}: {metric}. "
                    "Use only letters, numbers, underscores, and hyphens."
                )

            if not isinstance(benchmark_raw, dict):
                raise ConfigError(
                    f"custom_benchmarks.{industry}.{metric} must be a benchmark object"
                )

            # Validate required percentile keys
            required_keys = {"p25", "p50", "p75", "p90"}
            missing = required_keys - set(benchmark_raw.keys())
            if missing:
                raise ConfigError(
                    f"custom_benchmarks.{industry}.{metric} missing required keys: {missing}"
                )

            try:
                custom_benchmarks[industry][metric] = CustomBenchmark(
                    p25=float(benchmark_raw["p25"]),
                    p50=float(benchmark_raw["p50"]),
                    p75=float(benchmark_raw["p75"]),
                    p90=float(benchmark_raw["p90"]),
                    description=benchmark_raw.get("description"),
                    higher_is_better=benchmark_raw.get("higher_is_better"),
                )
            except (ValueError, TypeError) as e:
                raise ConfigError(
                    f"Invalid benchmark value in custom_benchmarks.{industry}.{metric}: {e}"
                ) from e

    # Parse benchmark files list
    benchmark_files_raw = raw.get("benchmark_files", [])
    if isinstance(benchmark_files_raw, str):
        benchmark_files_raw = [benchmark_files_raw]
    benchmark_files = []
    for bf in benchmark_files_raw:
        if not isinstance(bf, str):
            raise ConfigError(
                f"benchmark_files entries must be strings, got: {type(bf)}"
            )
        # Validate path doesn't contain traversal
        if ".." in bf:
            raise ConfigError(f"benchmark_files path cannot contain '..': {bf}")
        benchmark_files.append(bf)

    # Get format with validation
    fmt = defaults_raw.get("format", raw.get("format", "json"))
    if fmt not in VALID_FORMATS:
        raise ConfigError(f"Invalid format: {fmt}. Must be one of: {VALID_FORMATS}")

    return ProjectConfig(
        project_name=raw.get("project") or raw.get("project_name"),
        version=str(raw.get("version", "1.0")),
        default_industry=str(
            defaults_raw.get("industry", raw.get("industry", "general"))
        ),
        default_format=fmt,
        custom_targets=custom_targets,
        custom_benchmarks=custom_benchmarks,
        benchmark_files=benchmark_files,
        thresholds=thresholds,
        notifications=notifications,
        store_results=bool(raw.get("store_results", False)),
        storage_path=raw.get("storage_path"),
        _config_path=config_path,
    )


def get_effective_config(
    cli_industry: Optional[str] = None,
    cli_format: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> ProjectConfig:
    """
    Get effective configuration merging CLI args with config file.

    CLI arguments take precedence over config file values.

    Args:
        cli_industry: Industry from CLI argument.
        cli_format: Format from CLI argument.
        config_path: Explicit config file path.

    Returns:
        Merged ProjectConfig.
    """
    config = load_config(config_path)

    # CLI args override config
    if cli_industry is not None:
        config.default_industry = cli_industry
    if cli_format is not None:
        _validate_format(cli_format)
        config.default_format = cli_format

    return config
