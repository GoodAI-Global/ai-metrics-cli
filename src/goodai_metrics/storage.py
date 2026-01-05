"""
SQLite storage for metrics history tracking.

Provides persistent storage of analysis results with support for:
- Historical trend analysis
- Regression detection
- Time-series comparison

Storage follows the 'Evidence over opinions' principle by preserving
actual measurements for data-driven decision making.

Thread Safety:
- Each database operation creates a new connection
- SQLite handles concurrent access with locking
- Not suitable for high-concurrency write scenarios
"""

import sqlite3
import json
import hashlib
import uuid
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator
from dataclasses import dataclass


logger = logging.getLogger(__name__)

# Validation constants
MAX_STRING_FIELD_SIZE = 1000
MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB
MAX_LIMIT = 10000
MAX_OFFSET = 1000000
MAX_DAYS = 3650  # 10 years


class StorageError(Exception):
    """Raised when storage operations fail."""
    pass


@dataclass
class AnalysisRecord:
    """A stored analysis result."""
    id: Optional[int]
    run_id: str
    project: Optional[str]
    industry: str
    timestamp: datetime
    metrics_count: int
    overall_health: str
    summary: Dict[str, Any]
    full_results: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "project": self.project,
            "industry": self.industry,
            "timestamp": self.timestamp.isoformat(),
            "metrics_count": self.metrics_count,
            "overall_health": self.overall_health,
            "summary": self.summary,
            "full_results": self.full_results,
        }


@dataclass
class MetricHistory:
    """Historical values for a single metric."""
    metric_name: str
    values: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "metric_name": self.metric_name,
            "values": self.values,
        }


# Database schema version for migrations
SCHEMA_VERSION = 1

# SQL for creating tables
CREATE_TABLES_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Analysis runs
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    project TEXT,
    industry TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metrics_count INTEGER NOT NULL,
    overall_health TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    full_results_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Individual metric values (normalized for efficient querying)
CREATE TABLE IF NOT EXISTS metric_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    current_value REAL NOT NULL,
    benchmark_p50 REAL,
    gap_percent REAL,
    percentile_bracket TEXT,
    priority TEXT,
    timestamp TEXT,
    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_runs_project ON analysis_runs(project);
CREATE INDEX IF NOT EXISTS idx_runs_industry ON analysis_runs(industry);
CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON analysis_runs(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metric_values(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_run ON metric_values(run_id);
"""


class MetricsStorage:
    """
    SQLite-based storage for metrics analysis history.

    Supports storing, retrieving, and analyzing historical metrics data.

    Thread Safety:
    - Each database operation creates a new connection
    - SQLite handles concurrent access with locking
    - For high-concurrency scenarios, consider WAL mode
    """

    DEFAULT_DB_NAME = ".goodai-metrics/history.db"
    DEFAULT_DB_TIMEOUT = 30.0  # seconds

    def __init__(self, db_path: Optional[Path] = None, timeout: float = DEFAULT_DB_TIMEOUT):
        """
        Initialize storage with database path.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
            timeout: Database connection timeout in seconds.

        Raises:
            StorageError: If path validation fails.
        """
        if db_path is None:
            db_path = Path.cwd() / self.DEFAULT_DB_NAME
        else:
            db_path = Path(db_path)

        # Validate path (prevent path traversal)
        self._validate_db_path(db_path)

        self.db_path = db_path.resolve()
        self.timeout = timeout
        self._ensure_directory()
        self._initialize_schema()

    def _validate_db_path(self, db_path: Path) -> None:
        """Validate database path is safe."""
        path_str = str(db_path)

        # Check for path traversal
        if '..' in path_str:
            raise StorageError(f"Database path cannot contain '..': {path_str}")

        # If absolute path, must be within allowed directories
        if db_path.is_absolute():
            home = Path.home()
            allowed_roots = [Path('/tmp'), home, Path('/var/tmp'), Path.cwd()]

            is_allowed = any(
                path_str.startswith(str(root.resolve()))
                for root in allowed_roots
            )

            if not is_allowed:
                raise StorageError(
                    f"Absolute database path must be within home, tmp, or project directory: {path_str}"
                )

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper configuration."""
        conn = sqlite3.connect(str(self.db_path), timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        # Enable foreign key support and WAL mode for better concurrency
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        """Initialize database schema if needed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check current schema version
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if cursor.fetchone() is None:
                # Fresh database - create all tables
                cursor.executescript(CREATE_TABLES_SQL)
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
                )

    def _generate_run_id(self, timestamp: datetime, industry: str, project: Optional[str]) -> str:
        """Generate a unique run ID with entropy for collision resistance."""
        # Include UUID4 for uniqueness even with identical timestamps
        data = f"{timestamp.isoformat()}-{industry}-{project or 'default'}-{uuid.uuid4()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _validate_results(self, results: Dict[str, Any]) -> None:
        """Validate analysis results structure and content."""
        if not isinstance(results, dict):
            raise StorageError("Results must be a dictionary")

        # Validate industry
        industry = results.get("industry", "general")
        if not isinstance(industry, str) or not industry.strip():
            raise StorageError("Industry must be non-empty string")
        if len(industry) > MAX_STRING_FIELD_SIZE:
            raise StorageError(f"Industry exceeds {MAX_STRING_FIELD_SIZE} characters")

        # Validate analysis list
        analysis_list = results.get("analysis", [])
        if not isinstance(analysis_list, list):
            raise StorageError("Analysis must be a list")

        for i, analysis in enumerate(analysis_list):
            if not isinstance(analysis, dict):
                raise StorageError(f"Analysis item {i} must be a dictionary")
            if "metric" not in analysis:
                raise StorageError(f"Analysis item {i} missing required 'metric' field")
            if not isinstance(analysis.get("metric"), str):
                raise StorageError(f"Metric name in item {i} must be a string")

        # Validate recommendations list
        recommendations = results.get("recommendations", [])
        if not isinstance(recommendations, list):
            raise StorageError("Recommendations must be a list")

        # Validate JSON size
        results_json = json.dumps(results)
        if len(results_json) > MAX_JSON_SIZE:
            raise StorageError(f"Results exceed maximum size of {MAX_JSON_SIZE} bytes")

    def store_analysis(
        self,
        results: Dict[str, Any],
        project: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Store analysis results in the database.

        Args:
            results: Full analysis results dictionary.
            project: Project name (optional).
            timestamp: Analysis timestamp. If None, uses current time.

        Returns:
            The run_id of the stored analysis.

        Raises:
            StorageError: If storage operation fails or validation fails.
        """
        # Validate input
        self._validate_results(results)

        # Validate project name
        if project is not None:
            if not isinstance(project, str):
                raise StorageError("Project must be a string")
            if len(project) > MAX_STRING_FIELD_SIZE:
                raise StorageError(f"Project name exceeds {MAX_STRING_FIELD_SIZE} characters")

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        industry = results.get("industry", "general")
        run_id = self._generate_run_id(timestamp, industry, project)

        # Extract summary information
        analysis_list = results.get("analysis", [])
        recommendations = results.get("recommendations", [])

        summary = {
            "metrics_analyzed": results.get("metrics_analyzed", 0),
            "metrics_with_benchmarks": results.get("metrics_with_benchmarks", 0),
            "overall_health": results.get("overall_health", "unknown"),
            "high_priority_count": sum(
                1 for r in recommendations if r.get("priority") == "HIGH"
            ),
            "medium_priority_count": sum(
                1 for r in recommendations if r.get("priority") == "MEDIUM"
            ),
            "low_priority_count": sum(
                1 for r in recommendations if r.get("priority") == "LOW"
            ),
        }

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Insert main analysis record
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO analysis_runs
                    (run_id, project, industry, timestamp, metrics_count,
                     overall_health, summary_json, full_results_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        project,
                        industry,
                        timestamp.isoformat(),
                        results.get("metrics_analyzed", 0),
                        results.get("overall_health", "unknown"),
                        json.dumps(summary),
                        json.dumps(results),
                    )
                )

                # Delete any existing metric values for this run
                cursor.execute(
                    "DELETE FROM metric_values WHERE run_id = ?", (run_id,)
                )

                # Insert individual metric values
                for analysis in analysis_list:
                    # Find matching recommendation for priority
                    priority = None
                    for rec in recommendations:
                        if rec.get("metric") == analysis.get("metric"):
                            priority = rec.get("priority")
                            break

                    cursor.execute(
                        """
                        INSERT INTO metric_values
                        (run_id, metric_name, current_value, benchmark_p50,
                         gap_percent, percentile_bracket, priority, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            analysis.get("metric"),
                            analysis.get("current_value"),
                            analysis.get("benchmark_p50"),
                            analysis.get("gap_percent"),
                            analysis.get("percentile_bracket"),
                            priority,
                            analysis.get("timestamp"),
                        )
                    )

            return run_id

        except sqlite3.Error as e:
            raise StorageError(f"Failed to store analysis: {e}")

    def _parse_analysis_row(self, row: sqlite3.Row) -> AnalysisRecord:
        """Parse a database row into an AnalysisRecord with proper error handling."""
        run_id = row["run_id"]

        # Parse timestamp with error handling
        try:
            timestamp = datetime.fromisoformat(row["timestamp"])
        except (ValueError, TypeError) as e:
            raise StorageError(
                f"Invalid timestamp format for run {run_id}: {row['timestamp']}"
            )

        # Parse JSON with error handling
        try:
            summary = json.loads(row["summary_json"])
        except json.JSONDecodeError as e:
            raise StorageError(
                f"Corrupted summary JSON for run {run_id}: {e}"
            )

        try:
            full_results = json.loads(row["full_results_json"])
        except json.JSONDecodeError as e:
            raise StorageError(
                f"Corrupted results JSON for run {run_id}: {e}"
            )

        return AnalysisRecord(
            id=row["id"],
            run_id=run_id,
            project=row["project"],
            industry=row["industry"],
            timestamp=timestamp,
            metrics_count=row["metrics_count"],
            overall_health=row["overall_health"],
            summary=summary,
            full_results=full_results,
        )

    def get_analysis(self, run_id: str) -> Optional[AnalysisRecord]:
        """
        Retrieve a specific analysis by run ID.

        Args:
            run_id: The unique run identifier.

        Returns:
            AnalysisRecord if found, None otherwise.

        Raises:
            StorageError: If retrieval fails or data is corrupted.
        """
        if not run_id or not isinstance(run_id, str):
            raise StorageError("run_id must be a non-empty string")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, run_id, project, industry, timestamp,
                           metrics_count, overall_health, summary_json, full_results_json
                    FROM analysis_runs WHERE run_id = ?
                    """,
                    (run_id,)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                return self._parse_analysis_row(row)

        except sqlite3.Error as e:
            raise StorageError(f"Failed to retrieve analysis: {e}")

    def list_analyses(
        self,
        project: Optional[str] = None,
        industry: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AnalysisRecord]:
        """
        List analysis records with optional filtering.

        Args:
            project: Filter by project name.
            industry: Filter by industry.
            limit: Maximum records to return (1-10000).
            offset: Number of records to skip (0-1000000).

        Returns:
            List of AnalysisRecord objects.

        Raises:
            StorageError: If parameters are invalid or query fails.
        """
        # Validate parameters
        if not isinstance(limit, int) or limit <= 0:
            raise StorageError("limit must be a positive integer")
        if limit > MAX_LIMIT:
            raise StorageError(f"limit cannot exceed {MAX_LIMIT}")
        if not isinstance(offset, int) or offset < 0:
            raise StorageError("offset must be a non-negative integer")
        if offset > MAX_OFFSET:
            raise StorageError(f"offset cannot exceed {MAX_OFFSET}")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT id, run_id, project, industry, timestamp,
                           metrics_count, overall_health, summary_json, full_results_json
                    FROM analysis_runs
                    WHERE 1=1
                """
                params: List[Any] = []

                if project is not None:
                    query += " AND project = ?"
                    params.append(project)

                if industry is not None:
                    query += " AND industry = ?"
                    params.append(industry)

                query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query, params)

                records = []
                for row in cursor.fetchall():
                    records.append(self._parse_analysis_row(row))

                return records

        except sqlite3.Error as e:
            raise StorageError(f"Failed to list analyses: {e}")

    def get_metric_history(
        self,
        metric_name: str,
        project: Optional[str] = None,
        days: int = 30,
    ) -> MetricHistory:
        """
        Get historical values for a specific metric.

        Args:
            metric_name: Name of the metric to track.
            project: Filter by project name.
            days: Number of days to look back (1-3650).

        Returns:
            MetricHistory with all values.

        Raises:
            StorageError: If parameters are invalid or query fails.
        """
        # Validate parameters
        if not metric_name or not isinstance(metric_name, str):
            raise StorageError("metric_name must be a non-empty string")
        if not isinstance(days, int) or days <= 0:
            raise StorageError("days must be a positive integer")
        if days > MAX_DAYS:
            raise StorageError(f"days cannot exceed {MAX_DAYS}")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT mv.current_value, mv.benchmark_p50, mv.gap_percent,
                           mv.percentile_bracket, mv.priority, ar.timestamp
                    FROM metric_values mv
                    JOIN analysis_runs ar ON mv.run_id = ar.run_id
                    WHERE mv.metric_name = ?
                    AND ar.timestamp >= datetime('now', ?)
                """
                params: List[Any] = [metric_name, f"-{days} days"]

                if project is not None:
                    query += " AND ar.project = ?"
                    params.append(project)

                query += " ORDER BY ar.timestamp ASC"

                cursor.execute(query, params)

                values = []
                for row in cursor.fetchall():
                    values.append({
                        "value": row["current_value"],
                        "benchmark_p50": row["benchmark_p50"],
                        "gap_percent": row["gap_percent"],
                        "percentile_bracket": row["percentile_bracket"],
                        "priority": row["priority"],
                        "timestamp": row["timestamp"],
                    })

                return MetricHistory(metric_name=metric_name, values=values)

        except sqlite3.Error as e:
            raise StorageError(f"Failed to get metric history: {e}")

    def get_trend_summary(
        self,
        project: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get trend summary across all metrics.

        Args:
            project: Filter by project name.
            days: Number of days to analyze.

        Returns:
            Dictionary with trend analysis.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get all unique metrics in time range
                metric_query = """
                    SELECT DISTINCT mv.metric_name
                    FROM metric_values mv
                    JOIN analysis_runs ar ON mv.run_id = ar.run_id
                    WHERE ar.timestamp >= datetime('now', ?)
                """
                params: List[Any] = [f"-{days} days"]

                if project is not None:
                    metric_query += " AND ar.project = ?"
                    params.append(project)

                cursor.execute(metric_query, params)
                metric_names = [row["metric_name"] for row in cursor.fetchall()]

                # Analyze trends for each metric
                trends = []
                for metric_name in metric_names:
                    history = self.get_metric_history(metric_name, project, days)
                    if len(history.values) >= 2:
                        first_value = history.values[0]["value"]
                        last_value = history.values[-1]["value"]

                        if first_value != 0:
                            change_percent = ((last_value - first_value) / abs(first_value)) * 100
                        else:
                            change_percent = 100.0 if last_value != 0 else 0.0

                        trends.append({
                            "metric": metric_name,
                            "first_value": first_value,
                            "last_value": last_value,
                            "change_percent": round(change_percent, 2),
                            "direction": "improving" if change_percent > 0 else "declining" if change_percent < 0 else "stable",
                            "data_points": len(history.values),
                        })

                # Count analyses in period
                count_query = """
                    SELECT COUNT(*) as count FROM analysis_runs
                    WHERE timestamp >= datetime('now', ?)
                """
                count_params: List[Any] = [f"-{days} days"]
                if project is not None:
                    count_query += " AND project = ?"
                    count_params.append(project)

                cursor.execute(count_query, count_params)
                analysis_count = cursor.fetchone()["count"]

                return {
                    "period_days": days,
                    "project": project,
                    "total_analyses": analysis_count,
                    "metrics_tracked": len(trends),
                    "trends": trends,
                    "improving": sum(1 for t in trends if t["direction"] == "improving"),
                    "declining": sum(1 for t in trends if t["direction"] == "declining"),
                    "stable": sum(1 for t in trends if t["direction"] == "stable"),
                }

        except sqlite3.Error as e:
            raise StorageError(f"Failed to get trend summary: {e}")

    def detect_regressions(
        self,
        current_results: Dict[str, Any],
        project: Optional[str] = None,
        threshold_percent: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """
        Detect regressions compared to previous analysis.

        Args:
            current_results: Current analysis results.
            project: Project to compare against.
            threshold_percent: Minimum change to consider a regression (0-100).

        Returns:
            List of regression alerts.

        Raises:
            StorageError: If parameters are invalid or retrieval fails.
        """
        # Validate parameters
        if not isinstance(current_results, dict):
            raise StorageError("current_results must be a dictionary")
        if not isinstance(threshold_percent, (int, float)):
            raise StorageError("threshold_percent must be numeric")
        if threshold_percent < 0 or threshold_percent > 100:
            raise StorageError("threshold_percent must be between 0 and 100")

        try:
            # Get most recent previous analysis
            previous = self.list_analyses(project=project, limit=1)
            if not previous:
                return []

            prev_results = previous[0].full_results
            prev_analysis = {a["metric"]: a for a in prev_results.get("analysis", [])}
            curr_analysis = {a["metric"]: a for a in current_results.get("analysis", [])}

            regressions = []
            for metric, curr in curr_analysis.items():
                if metric not in prev_analysis:
                    continue

                prev = prev_analysis[metric]
                prev_gap = prev.get("gap_percent", 0)
                curr_gap = curr.get("gap_percent", 0)

                # Regression = gap increased significantly
                gap_increase = curr_gap - prev_gap
                if gap_increase >= threshold_percent:
                    regressions.append({
                        "metric": metric,
                        "previous_gap_percent": round(prev_gap, 2),
                        "current_gap_percent": round(curr_gap, 2),
                        "gap_increase": round(gap_increase, 2),
                        "severity": "HIGH" if gap_increase >= 20 else "MEDIUM",
                    })

            return regressions

        except StorageError as e:
            logger.error(f"Failed to detect regressions: {e}", exc_info=True)
            raise

    def delete_old_records(self, days: int = 90) -> int:
        """
        Delete analysis records older than specified days.

        Args:
            days: Delete records older than this many days (1-3650).

        Returns:
            Number of records deleted.

        Raises:
            StorageError: If parameters are invalid or deletion fails.
        """
        # Validate parameters
        if not isinstance(days, int) or days <= 0:
            raise StorageError("days must be a positive integer")
        if days > MAX_DAYS:
            raise StorageError(f"days cannot exceed {MAX_DAYS}")

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Count records to be deleted first
                cursor.execute(
                    """
                    SELECT COUNT(*) as count FROM analysis_runs
                    WHERE timestamp < datetime('now', ?)
                    """,
                    (f"-{days} days",)
                )
                count = cursor.fetchone()["count"]

                if count == 0:
                    return 0

                # Delete metric values first (using subquery to avoid dynamic SQL)
                cursor.execute(
                    """
                    DELETE FROM metric_values
                    WHERE run_id IN (
                        SELECT run_id FROM analysis_runs
                        WHERE timestamp < datetime('now', ?)
                    )
                    """,
                    (f"-{days} days",)
                )

                # Delete analysis runs
                cursor.execute(
                    """
                    DELETE FROM analysis_runs
                    WHERE timestamp < datetime('now', ?)
                    """,
                    (f"-{days} days",)
                )

                return count

        except sqlite3.Error as e:
            raise StorageError(f"Failed to delete old records: {e}")

    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) as count FROM analysis_runs")
                total_runs = cursor.fetchone()["count"]

                cursor.execute("SELECT COUNT(*) as count FROM metric_values")
                total_metrics = cursor.fetchone()["count"]

                cursor.execute(
                    "SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest FROM analysis_runs"
                )
                row = cursor.fetchone()

                return {
                    "total_analyses": total_runs,
                    "total_metric_values": total_metrics,
                    "oldest_record": row["oldest"],
                    "newest_record": row["newest"],
                    "database_path": str(self.db_path),
                    "database_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
                }

        except sqlite3.Error as e:
            raise StorageError(f"Failed to get database stats: {e}")
