"""
Structured logging configuration for Good AI Metrics CLI.

Provides enterprise-grade logging with:
- JSON-structured output for production/SIEM integration
- Human-readable output for development
- Configurable log levels
- Context-aware logging with request IDs
- Sensitive data filtering
- Log rotation support

Thread Safety:
- Uses contextvars for async-safe context tracking
- Handler operations are thread-safe via logging module
- Clear context at end of operations to prevent leakage
"""

import json
import logging
import logging.handlers
import os
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Context variable for request/operation tracking
_context_id: ContextVar[str] = ContextVar("context_id", default="")

# Sensitive fields to redact in logs
SENSITIVE_FIELDS: set[str] = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "privatekey",
    "ssn",
    "social_security",
    "credit_card",
    "creditcard",
    "card_number",
    "cvv",
    "pin",
    "access_token",
    "refresh_token",
    "session_id",
}

# Maximum sizes for security
MAX_CONTEXT_ID_LENGTH = 100
MAX_EXCEPTION_LENGTH = 2000
MAX_MESSAGE_LENGTH = 10000
MAX_LOG_FILE_BYTES = 100 * 1024 * 1024  # 100MB
MAX_LOG_BACKUP_COUNT = 10

# Valid log levels
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Pattern for sanitizing log injection attempts
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_log_input(value: str) -> str:
    """Remove control characters to prevent log injection."""
    if not isinstance(value, str):
        value = str(value)
    # Replace control characters (newlines, carriage returns, etc.) with space
    return CONTROL_CHAR_PATTERN.sub(" ", value)


def _redact_sensitive(key: str, value: Any) -> Any:
    """Redact sensitive field values."""
    key_lower = key.lower()
    if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
        return "[REDACTED]"
    return value


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs logs as JSON objects for easy parsing by log aggregators
    and SIEM systems. Includes sensitive data filtering.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Sanitize message to prevent log injection
        message = record.getMessage()
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[:MAX_MESSAGE_LENGTH] + "...[truncated]"
        message = _sanitize_log_input(message)

        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context ID if present
        context_id = _context_id.get()
        if context_id:
            log_obj["context_id"] = _sanitize_log_input(
                context_id[:MAX_CONTEXT_ID_LENGTH]
            )

        # Add exception info if present (with size limit)
        if record.exc_info:
            exc_str = self.formatException(record.exc_info)
            if len(exc_str) > MAX_EXCEPTION_LENGTH:
                exc_str = exc_str[:MAX_EXCEPTION_LENGTH] + "\n[... truncated ...]"
            log_obj["exception"] = exc_str

        # Add extra fields with sensitive data filtering
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
                "asctime",
            }:
                # Redact sensitive fields
                value = _redact_sensitive(key, value)

                try:
                    # Try to serialize, skip if not possible
                    json.dumps(value)
                    log_obj[key] = value
                except (TypeError, ValueError):
                    try:
                        log_obj[key] = str(value)
                    except Exception:
                        log_obj[key] = f"[Unserializable: {type(value).__name__}]"

        return json.dumps(log_obj)


class HumanFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Provides colored, easy-to-read log output for terminal use.
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        """Initialize formatter with optional color support."""
        super().__init__()
        self.use_color = use_color and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for human reading."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        level = record.levelname

        if self.use_color:
            color = self.COLORS.get(level, "")
            level_str = f"{color}{level:8}{self.RESET}"
        else:
            level_str = f"{level:8}"

        context_id = _context_id.get()
        # Safely truncate context ID
        context_str = f"[{context_id[:8]}] " if context_id else ""

        # Sanitize message
        msg = _sanitize_log_input(record.getMessage())
        if len(msg) > MAX_MESSAGE_LENGTH:
            msg = msg[:MAX_MESSAGE_LENGTH] + "...[truncated]"

        message = f"{timestamp} {level_str} {context_str}{msg}"

        if record.exc_info:
            exc_str = self.formatException(record.exc_info)
            if len(exc_str) > MAX_EXCEPTION_LENGTH:
                exc_str = exc_str[:MAX_EXCEPTION_LENGTH] + "\n[... truncated ...]"
            message += "\n" + exc_str

        return message


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context information.

    Provides convenience methods for structured logging with metrics.
    """

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Add context to log message."""
        extra = kwargs.get("extra", {})

        # Add context ID
        context_id = _context_id.get()
        if context_id:
            extra["context_id"] = context_id

        kwargs["extra"] = extra
        return msg, kwargs

    def metric(
        self,
        metric_name: str,
        value: float,
        unit: Optional[str] = None,
        **extra_fields: Any,
    ) -> None:
        """Log a metric value for monitoring/alerting."""
        # Sanitize inputs
        metric_name = _sanitize_log_input(str(metric_name))
        unit_str = _sanitize_log_input(str(unit)) if unit else ""

        extra = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_type": "gauge",
            **extra_fields,
        }
        if unit:
            extra["metric_unit"] = unit_str
        self.info(f"METRIC {metric_name}={value}{unit_str}", extra=extra)

    def timing(self, operation: str, duration_ms: float, **extra_fields: Any) -> None:
        """Log an operation timing for performance monitoring."""
        # Sanitize inputs
        operation = _sanitize_log_input(str(operation))

        extra = {
            "metric_name": f"{operation}_duration_ms",
            "metric_value": duration_ms,
            "metric_type": "timing",
            "operation": operation,
            **extra_fields,
        }
        self.info(f"TIMING {operation}: {duration_ms:.2f}ms", extra=extra)

    def event(self, event_type: str, description: str, **extra_fields: Any) -> None:
        """Log a business event for audit trail."""
        # Sanitize inputs
        event_type = _sanitize_log_input(str(event_type))
        description = _sanitize_log_input(str(description))

        extra = {
            "event_type": event_type,
            "event_description": description,
            **extra_fields,
        }
        self.info(f"EVENT [{event_type}] {description}", extra=extra)


def _validate_log_file_path(log_file: str) -> Path:
    """
    Validate log file path for security.

    Prevents path traversal and ensures path is within allowed directories.

    Raises:
        ValueError: If path is invalid or outside allowed directories.
    """
    log_path = Path(log_file).resolve()

    # Check for path traversal attempt
    if ".." in str(log_file):
        raise ValueError(f"Log file path cannot contain '..': {log_file}")

    # Allowed directories: current working dir, home, /tmp, /var/tmp
    allowed_roots = [
        Path.cwd().resolve(),
        Path.home().resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
    ]

    is_allowed = any(str(log_path).startswith(str(root)) for root in allowed_roots)

    if not is_allowed:
        raise ValueError(
            f"Log file path must be within project, home, or tmp directory: {log_file}"
        )

    return log_path


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: If True, output JSON formatted logs.
        log_file: Optional path to log file (with rotation).

    Raises:
        ValueError: If log level is invalid or log file path is unsafe.
    """
    # Validate log level
    level_upper = level.upper()
    if level_upper not in VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {level}. Must be one of {VALID_LOG_LEVELS}"
        )

    # Get root logger for the package
    root_logger = logging.getLogger("goodai_metrics")
    root_logger.setLevel(getattr(logging, level_upper))

    # Safely clear existing handlers (close them first)
    for handler in root_logger.handlers[
        :
    ]:  # Copy list to avoid modification during iteration
        try:
            handler.close()
        except Exception:
            pass
        root_logger.removeHandler(handler)

    # Create formatter based on output type
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = HumanFormatter()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified (with rotation and validation)
    if log_file:
        log_path = _validate_log_file_path(log_file)

        # Ensure parent directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Use rotating file handler to prevent disk exhaustion
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=MAX_LOG_FILE_BYTES,
                backupCount=MAX_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            # Always use JSON for file logs
            file_handler.setFormatter(JSONFormatter())
            root_logger.addHandler(file_handler)

            # Set restrictive file permissions (Unix only)
            try:
                os.chmod(log_path, 0o600)  # Owner read/write only
            except (OSError, AttributeError):
                pass  # Windows or permission error, skip

        except OSError as e:
            raise ValueError(f"Failed to create log file: {e}") from e

    # Don't propagate to root logger to prevent duplicate logs
    root_logger.propagate = False


def get_logger(name: str = "goodai_metrics") -> ContextLogger:
    """
    Get a context-aware logger for the specified module.

    Args:
        name: Logger name (typically module name).

    Returns:
        ContextLogger instance.
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})


def set_context_id(context_id: Optional[str] = None) -> str:
    """
    Set the context ID for the current operation.

    Args:
        context_id: Optional specific ID. If None, generates UUID.

    Returns:
        The context ID that was set.

    Raises:
        ValueError: If context_id exceeds maximum length.
    """
    # Clear any existing context first (prevents leakage in thread pools)
    _context_id.set("")

    if context_id is None:
        context_id = str(uuid.uuid4())
    else:
        # Validate length
        if len(context_id) > MAX_CONTEXT_ID_LENGTH:
            raise ValueError(
                f"context_id exceeds maximum length of {MAX_CONTEXT_ID_LENGTH}"
            )
        # Sanitize
        context_id = _sanitize_log_input(context_id)

    _context_id.set(context_id)
    return context_id


def clear_context_id() -> None:
    """Clear the current context ID."""
    _context_id.set("")


class TimingContext:
    """Context manager for timing operations."""

    def __init__(self, logger: ContextLogger, operation: str, **extra: Any):
        """Initialize timing context."""
        self.logger = logger
        self.operation = _sanitize_log_input(str(operation))
        self.extra = extra
        self.start_time: float = 0

    def __enter__(self) -> "TimingContext":
        """Start timing."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """End timing and log result."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        self.logger.timing(self.operation, duration_ms, **self.extra)


def timed(logger: ContextLogger, operation: str, **extra: Any) -> TimingContext:
    """
    Create a timing context for an operation.

    Usage:
        with timed(logger, "analyze_metrics"):
            # do work
            pass

    Args:
        logger: Logger to use for timing output.
        operation: Name of the operation being timed.
        **extra: Additional fields to include in log.

    Returns:
        TimingContext instance.
    """
    return TimingContext(logger, operation, **extra)
