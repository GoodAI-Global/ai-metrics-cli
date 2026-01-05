"""Tests for the storage module."""

import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from goodai_metrics.storage import (
    MetricsStorage,
    AnalysisRecord,
    MetricHistory,
    StorageError,
)


class TestMetricsStorage:
    """Tests for MetricsStorage class."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create a storage instance with temp database."""
        return MetricsStorage(db_path=temp_db)

    @pytest.fixture
    def sample_results(self):
        """Sample analysis results for testing."""
        return {
            "industry": "manufacturing",
            "metrics_analyzed": 3,
            "metrics_with_benchmarks": 3,
            "analysis": [
                {
                    "metric": "prediction_accuracy",
                    "current_value": 0.82,
                    "benchmark_p50": 0.78,
                    "gap_percent": 0,
                    "percentile_bracket": "p75-p90",
                },
                {
                    "metric": "defect_detection_rate",
                    "current_value": 0.88,
                    "benchmark_p50": 0.85,
                    "gap_percent": 0,
                    "percentile_bracket": "p50-p75",
                },
            ],
            "recommendations": [
                {"metric": "prediction_accuracy", "priority": "LOW"},
                {"metric": "defect_detection_rate", "priority": "LOW"},
            ],
            "overall_health": "HEALTHY",
        }

    def test_storage_creates_database(self, temp_db):
        """Storage creates database file on initialization."""
        storage = MetricsStorage(db_path=temp_db)
        assert temp_db.exists()

    def test_storage_creates_parent_directory(self, temp_db):
        """Storage creates parent directory if needed."""
        nested_path = temp_db.parent / "subdir" / "test.db"
        storage = MetricsStorage(db_path=nested_path)
        assert nested_path.parent.exists()

    def test_store_analysis_returns_run_id(self, storage, sample_results):
        """store_analysis returns a run ID."""
        run_id = storage.store_analysis(sample_results, project="test-project")
        assert run_id is not None
        assert len(run_id) == 16  # SHA256 truncated to 16 chars

    def test_store_and_retrieve_analysis(self, storage, sample_results):
        """Can store and retrieve analysis by run_id."""
        run_id = storage.store_analysis(sample_results, project="test-project")

        record = storage.get_analysis(run_id)

        assert record is not None
        assert record.run_id == run_id
        assert record.project == "test-project"
        assert record.industry == "manufacturing"
        assert record.overall_health == "HEALTHY"
        assert record.metrics_count == 3

    def test_retrieve_nonexistent_returns_none(self, storage):
        """get_analysis returns None for nonexistent run_id."""
        record = storage.get_analysis("nonexistent123")
        assert record is None

    def test_list_analyses_empty(self, storage):
        """list_analyses returns empty list when no records."""
        records = storage.list_analyses()
        assert records == []

    def test_list_analyses_returns_records(self, storage, sample_results):
        """list_analyses returns stored records."""
        storage.store_analysis(sample_results, project="project1")
        storage.store_analysis(sample_results, project="project2")

        records = storage.list_analyses()

        assert len(records) == 2

    def test_list_analyses_filter_by_project(self, storage, sample_results):
        """list_analyses filters by project name."""
        storage.store_analysis(sample_results, project="project1")
        storage.store_analysis(sample_results, project="project2")

        records = storage.list_analyses(project="project1")

        assert len(records) == 1
        assert records[0].project == "project1"

    def test_list_analyses_filter_by_industry(self, storage, sample_results):
        """list_analyses filters by industry."""
        storage.store_analysis(sample_results, project="project1")

        # Modify industry for second record
        results2 = {**sample_results, "industry": "insurance"}
        storage.store_analysis(results2, project="project2")

        records = storage.list_analyses(industry="manufacturing")

        assert len(records) == 1
        assert records[0].industry == "manufacturing"

    def test_list_analyses_respects_limit(self, storage, sample_results):
        """list_analyses respects limit parameter."""
        for i in range(5):
            storage.store_analysis(sample_results, project=f"project{i}")

        records = storage.list_analyses(limit=3)

        assert len(records) == 3

    def test_list_analyses_ordered_by_timestamp_desc(self, storage, sample_results):
        """list_analyses returns records ordered by timestamp descending."""
        # Store with explicit timestamps
        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
        ts3 = datetime(2025, 1, 3, tzinfo=timezone.utc)

        storage.store_analysis(sample_results, project="old", timestamp=ts1)
        storage.store_analysis(sample_results, project="middle", timestamp=ts2)
        storage.store_analysis(sample_results, project="new", timestamp=ts3)

        records = storage.list_analyses()

        assert records[0].project == "new"
        assert records[1].project == "middle"
        assert records[2].project == "old"


class TestMetricHistory:
    """Tests for metric history tracking."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create a storage instance with temp database."""
        return MetricsStorage(db_path=temp_db)

    def test_get_metric_history_empty(self, storage):
        """get_metric_history returns empty values for unknown metric."""
        history = storage.get_metric_history("unknown_metric")
        assert history.metric_name == "unknown_metric"
        assert history.values == []

    def test_get_metric_history_with_data(self, storage):
        """get_metric_history returns values for stored metric."""
        results = {
            "industry": "manufacturing",
            "metrics_analyzed": 1,
            "analysis": [
                {
                    "metric": "prediction_accuracy",
                    "current_value": 0.82,
                    "benchmark_p50": 0.78,
                    "gap_percent": 0,
                    "percentile_bracket": "p75-p90",
                }
            ],
            "recommendations": [],
            "overall_health": "HEALTHY",
        }

        storage.store_analysis(results, project="test")

        history = storage.get_metric_history("prediction_accuracy")

        assert history.metric_name == "prediction_accuracy"
        assert len(history.values) == 1
        assert history.values[0]["value"] == 0.82

    def test_metric_history_multiple_values(self, storage):
        """get_metric_history returns multiple values over time."""
        for value in [0.75, 0.78, 0.82]:
            results = {
                "industry": "manufacturing",
                "metrics_analyzed": 1,
                "analysis": [
                    {
                        "metric": "prediction_accuracy",
                        "current_value": value,
                        "benchmark_p50": 0.78,
                        "gap_percent": 0,
                    }
                ],
                "recommendations": [],
                "overall_health": "HEALTHY",
            }
            storage.store_analysis(results, project="test")

        history = storage.get_metric_history("prediction_accuracy")

        assert len(history.values) == 3


class TestTrendSummary:
    """Tests for trend summary functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create a storage instance with temp database."""
        return MetricsStorage(db_path=temp_db)

    def test_get_trend_summary_empty(self, storage):
        """get_trend_summary returns empty data when no records."""
        summary = storage.get_trend_summary()

        assert summary["total_analyses"] == 0
        assert summary["metrics_tracked"] == 0
        assert summary["trends"] == []

    def test_get_trend_summary_with_data(self, storage):
        """get_trend_summary calculates trends correctly."""
        # Store two analyses with improving accuracy
        for value in [0.75, 0.82]:
            results = {
                "industry": "manufacturing",
                "metrics_analyzed": 1,
                "analysis": [
                    {
                        "metric": "prediction_accuracy",
                        "current_value": value,
                        "benchmark_p50": 0.78,
                        "gap_percent": 0,
                    }
                ],
                "recommendations": [],
                "overall_health": "HEALTHY",
            }
            storage.store_analysis(results, project="test")

        summary = storage.get_trend_summary()

        assert summary["total_analyses"] == 2
        assert summary["metrics_tracked"] == 1
        assert len(summary["trends"]) == 1
        assert summary["trends"][0]["metric"] == "prediction_accuracy"
        assert summary["trends"][0]["direction"] == "improving"
        assert summary["improving"] == 1


class TestRegressionDetection:
    """Tests for regression detection."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create a storage instance with temp database."""
        return MetricsStorage(db_path=temp_db)

    def test_detect_regressions_no_previous(self, storage):
        """detect_regressions returns empty when no previous analysis."""
        current = {
            "analysis": [
                {"metric": "accuracy", "gap_percent": 15}
            ]
        }

        regressions = storage.detect_regressions(current)
        assert regressions == []

    def test_detect_regressions_with_regression(self, storage):
        """detect_regressions detects gap increases."""
        # Store previous analysis with low gap
        previous = {
            "industry": "manufacturing",
            "metrics_analyzed": 1,
            "analysis": [
                {"metric": "accuracy", "current_value": 0.8, "gap_percent": 5}
            ],
            "recommendations": [],
            "overall_health": "HEALTHY",
        }
        storage.store_analysis(previous, project="test")

        # Current analysis with high gap
        current = {
            "analysis": [
                {"metric": "accuracy", "current_value": 0.7, "gap_percent": 25}
            ]
        }

        regressions = storage.detect_regressions(current, project="test")

        assert len(regressions) == 1
        assert regressions[0]["metric"] == "accuracy"
        assert regressions[0]["gap_increase"] == 20.0

    def test_detect_regressions_respects_threshold(self, storage):
        """detect_regressions respects threshold parameter."""
        previous = {
            "industry": "manufacturing",
            "metrics_analyzed": 1,
            "analysis": [
                {"metric": "accuracy", "current_value": 0.8, "gap_percent": 10}
            ],
            "recommendations": [],
            "overall_health": "HEALTHY",
        }
        storage.store_analysis(previous, project="test")

        # Current with small gap increase (5%)
        current = {
            "analysis": [
                {"metric": "accuracy", "current_value": 0.75, "gap_percent": 15}
            ]
        }

        # With default threshold (10%), should not detect
        regressions = storage.detect_regressions(current, project="test", threshold_percent=10.0)
        assert len(regressions) == 0

        # With lower threshold (3%), should detect
        regressions = storage.detect_regressions(current, project="test", threshold_percent=3.0)
        assert len(regressions) == 1


class TestStorageCleanup:
    """Tests for storage cleanup functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield db_path

    @pytest.fixture
    def storage(self, temp_db):
        """Create a storage instance with temp database."""
        return MetricsStorage(db_path=temp_db)

    def test_delete_old_records_none_old(self, storage):
        """delete_old_records returns 0 when no old records."""
        results = {
            "industry": "manufacturing",
            "metrics_analyzed": 1,
            "analysis": [],
            "recommendations": [],
            "overall_health": "HEALTHY",
        }
        storage.store_analysis(results, project="test")

        deleted = storage.delete_old_records(days=1)
        assert deleted == 0

    def test_get_database_stats(self, storage):
        """get_database_stats returns correct statistics."""
        results = {
            "industry": "manufacturing",
            "metrics_analyzed": 1,
            "analysis": [
                {"metric": "accuracy", "current_value": 0.8}
            ],
            "recommendations": [],
            "overall_health": "HEALTHY",
        }
        storage.store_analysis(results, project="test")

        stats = storage.get_database_stats()

        assert stats["total_analyses"] == 1
        assert stats["total_metric_values"] == 1
        assert stats["database_size_bytes"] > 0


class TestAnalysisRecordDataclass:
    """Tests for AnalysisRecord dataclass."""

    def test_to_dict(self):
        """to_dict returns correct dictionary representation."""
        record = AnalysisRecord(
            id=1,
            run_id="abc123",
            project="test",
            industry="manufacturing",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            metrics_count=3,
            overall_health="HEALTHY",
            summary={"high_priority_count": 0},
            full_results={"analysis": []},
        )

        result = record.to_dict()

        assert result["id"] == 1
        assert result["run_id"] == "abc123"
        assert result["project"] == "test"
        assert result["timestamp"] == "2025-01-01T00:00:00+00:00"


class TestMetricHistoryDataclass:
    """Tests for MetricHistory dataclass."""

    def test_to_dict(self):
        """to_dict returns correct dictionary representation."""
        history = MetricHistory(
            metric_name="accuracy",
            values=[{"value": 0.8}, {"value": 0.85}],
        )

        result = history.to_dict()

        assert result["metric_name"] == "accuracy"
        assert len(result["values"]) == 2
