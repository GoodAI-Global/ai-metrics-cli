"""
Structured logging configuration for Good AI Metrics CLI.

Provides enterprise-grade logging with:
- JSON-structured output for production/SIEM integration
- Human-readable output for development
- Configurable log levels
- Context-aware logging with request IDs
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Context variable for request/operation tracking
_context_id: ContextVar[str] = ContextVar("context_id", default="")


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs logs as JSON objects for easy parsing by log aggregators
    and SIEM systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context ID if present
        context_id = _context_id.get()
        if context_id:
            log_obj["context_id"] = context_id

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime"
            }:
                try:
                    # Try to serialize, skip if not possible
                    json.dumps(value)
                    log_obj[key] = value
                except (TypeError, ValueError):
                    log_obj[key] = str(value)

        return json.dumps(log_obj)


class HumanFormatter(logging.Formatter):
    """
    Human-readable log formatter for development.

    Provides colored, easy-to-read log output for terminal use.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        """Initialize formatter with optional color support."""
        super().__init__()
        self.use_color = use_color and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for human reading."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname

        if self.use_color:
            color = self.COLORS.get(level, "")
            level_str = f"{color}{level:8}{self.RESET}"
        else:
            level_str = f"{level:8}"

        context_id = _context_id.get()
        context_str = f"[{context_id[:8]}] " if context_id else ""

        message = f"{timestamp} {level_str} {context_str}{record.getMessage()}"

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context information.

    Provides convenience methods for structured logging with metrics.
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
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
        **extra_fields: Any
    ) -> None:
        """Log a metric value for monitoring/alerting."""
        extra = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_type": "gauge",
            **extra_fields,
        }
        if unit:
            extra["metric_unit"] = unit
        self.info(f"METRIC {metric_name}={value}{unit or ''}", extra=extra)

    def timing(
        self,
        operation: str,
        duration_ms: float,
        **extra_fields: Any
    ) -> None:
        """Log an operation timing for performance monitoring."""
        extra = {
            "metric_name": f"{operation}_duration_ms",
            "metric_value": duration_ms,
            "metric_type": "timing",
            "operation": operation,
            **extra_fields,
        }
        self.info(f"TIMING {operation}: {duration_ms:.2f}ms", extra=extra)

    def event(
        self,
        event_type: str,
        description: str,
        **extra_fields: Any
    ) -> None:
        """Log a business event for audit trail."""
        extra = {
            "event_type": event_type,
            "event_description": description,
            **extra_fields,
        }
        self.info(f"EVENT [{event_type}] {description}", extra=extra)


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
        log_file: Optional path to log file.
    """
    # Get root logger for the package
    root_logger = logging.getLogger("goodai_metrics")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatter based on output type
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = HumanFormatter()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        # Always use JSON for file logs
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Don't propagate to root logger
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
    """
    if context_id is None:
        context_id = str(uuid.uuid4())
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
        self.operation = operation
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
