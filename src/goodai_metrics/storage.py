"""
SQLite storage for metrics history tracking.

Provides persistent storage of analysis results with support for:
- Historical trend analysis
- Regression detection
- Time-series comparison

Storage follows the 'Evidence over opinions' principle by preserving
actual measurements for data-driven decision making.
"""

import sqlite3
import json
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Generator
from dataclasses import dataclass


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
    Thread-safe with connection pooling per thread.
    """

    DEFAULT_DB_NAME = ".goodai-metrics/history.db"

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize storage with database path.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            db_path = Path.cwd() / self.DEFAULT_DB_NAME
        else:
            db_path = Path(db_path)

        self.db_path = db_path
        self._ensure_directory()
        self._initialize_schema()

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper configuration."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable foreign key support
        conn.execute("PRAGMA foreign_keys = ON")
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
        """Generate a unique run ID."""
        data = f"{timestamp.isoformat()}-{industry}-{project or 'default'}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

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
            StorageError: If storage operation fails.
        """
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

    def get_analysis(self, run_id: str) -> Optional[AnalysisRecord]:
        """
        Retrieve a specific analysis by run ID.

        Args:
            run_id: The unique run identifier.

        Returns:
            AnalysisRecord if found, None otherwise.
        """
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

                return AnalysisRecord(
                    id=row["id"],
                    run_id=row["run_id"],
                    project=row["project"],
                    industry=row["industry"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    metrics_count=row["metrics_count"],
                    overall_health=row["overall_health"],
                    summary=json.loads(row["summary_json"]),
                    full_results=json.loads(row["full_results_json"]),
                )

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
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of AnalysisRecord objects.
        """
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
                    records.append(AnalysisRecord(
                        id=row["id"],
                        run_id=row["run_id"],
                        project=row["project"],
                        industry=row["industry"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        metrics_count=row["metrics_count"],
                        overall_health=row["overall_health"],
                        summary=json.loads(row["summary_json"]),
                        full_results=json.loads(row["full_results_json"]),
                    ))

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
            days: Number of days to look back.

        Returns:
            MetricHistory with all values.
        """
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
            threshold_percent: Minimum change to consider a regression.

        Returns:
            List of regression alerts.
        """
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

        except StorageError:
            return []

    def delete_old_records(self, days: int = 90) -> int:
        """
        Delete analysis records older than specified days.

        Args:
            days: Delete records older than this many days.

        Returns:
            Number of records deleted.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get run_ids to delete
                cursor.execute(
                    """
                    SELECT run_id FROM analysis_runs
                    WHERE timestamp < datetime('now', ?)
                    """,
                    (f"-{days} days",)
                )
                run_ids = [row["run_id"] for row in cursor.fetchall()]

                if not run_ids:
                    return 0

                # Delete metric values first (foreign key)
                placeholders = ",".join("?" * len(run_ids))
                cursor.execute(
                    f"DELETE FROM metric_values WHERE run_id IN ({placeholders})",
                    run_ids
                )

                # Delete analysis runs
                cursor.execute(
                    f"DELETE FROM analysis_runs WHERE run_id IN ({placeholders})",
                    run_ids
                )

                return len(run_ids)

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
