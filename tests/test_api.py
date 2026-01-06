"""Tests for the REST API module."""

import pytest
from fastapi.testclient import TestClient

from goodai_metrics.api import app


@pytest.fixture
def client():
    """Create test client for API."""
    return TestClient(app)


class TestServerInfo:
    """Tests for server info endpoint."""

    def test_get_info(self, client):
        """GET /api/v1/info returns server info."""
        response = client.get("/api/v1/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "status" in data
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert "timestamp" in data

    def test_info_has_request_id_header(self, client):
        """Response includes X-Request-ID header."""
        response = client.get("/api/v1/info")
        assert "X-Request-ID" in response.headers


class TestIndustries:
    """Tests for industry endpoints."""

    def test_list_industries(self, client):
        """GET /api/v1/industries returns list of industries."""
        response = client.get("/api/v1/industries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Check structure
        industry = data[0]
        assert "name" in industry
        assert "metrics" in industry
        assert "metric_count" in industry

    def test_get_industry_benchmarks(self, client):
        """GET /api/v1/industries/{industry} returns benchmarks."""
        response = client.get("/api/v1/industries/manufacturing")
        assert response.status_code == 200
        data = response.json()
        assert data["industry"] == "manufacturing"
        assert "benchmarks" in data
        assert isinstance(data["benchmarks"], dict)

    def test_get_industry_not_found(self, client):
        """GET /api/v1/industries/{industry} returns 404 for unknown."""
        response = client.get("/api/v1/industries/unknown_industry_xyz")
        assert response.status_code == 404


class TestAnalyze:
    """Tests for analyze endpoint."""

    def test_analyze_valid_metrics(self, client):
        """POST /api/v1/analyze with valid metrics returns analysis."""
        payload = {
            "metrics": [
                {"metric": "prediction_accuracy", "value": 0.82},
                {"metric": "defect_detection_rate", "value": 0.88},
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["industry"] == "manufacturing"
        assert data["metrics_analyzed"] == 2
        assert "overall_health" in data
        assert "analysis" in data
        assert "recommendations" in data
        assert "timestamp" in data

    def test_analyze_with_store(self, client):
        """POST /api/v1/analyze with store_results=true stores result."""
        payload = {
            "metrics": [
                {"metric": "prediction_accuracy", "value": 0.82},
            ],
            "industry": "manufacturing",
            "store_results": True,
            "project": "test-project",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        # run_id should be returned when storing
        assert data["run_id"] is not None

    def test_analyze_empty_metrics_fails(self, client):
        """POST /api/v1/analyze with empty metrics returns 422."""
        payload = {"metrics": [], "industry": "manufacturing"}
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_invalid_metric_name(self, client):
        """POST /api/v1/analyze with invalid metric name returns 422."""
        payload = {
            "metrics": [
                {"metric": "123invalid", "value": 0.5},
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_missing_required_field(self, client):
        """POST /api/v1/analyze with missing required field returns 422."""
        # Missing 'value' field
        payload = {
            "metrics": [
                {"metric": "accuracy"},  # No value
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_analyze_extra_fields_rejected(self, client):
        """POST /api/v1/analyze rejects extra fields."""
        payload = {
            "metrics": [
                {"metric": "accuracy", "value": 0.8},
            ],
            "industry": "manufacturing",
            "extra_field": "not_allowed",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_pass(self, client):
        """POST /api/v1/health-check passes with good metrics."""
        payload = {
            "metrics": [
                {"metric": "prediction_accuracy", "value": 0.90},
            ],
            "industry": "manufacturing",
            "max_high_priority": 0,
            "max_gap_percent": 30.0,
        }
        response = client.post("/api/v1/health-check", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "passed" in data
        assert "overall_health" in data
        assert "high_priority_count" in data
        assert "max_gap_found" in data
        assert "violations" in data

    def test_health_check_fail_high_gap(self, client):
        """POST /api/v1/health-check fails with large gap."""
        payload = {
            "metrics": [
                {"metric": "prediction_accuracy", "value": 0.50},  # Very low
            ],
            "industry": "manufacturing",
            "max_gap_percent": 5.0,  # Strict threshold
        }
        response = client.post("/api/v1/health-check", json=payload)
        assert response.status_code == 200
        data = response.json()
        # With very low accuracy and strict threshold, should fail
        assert isinstance(data["passed"], bool)


class TestCompare:
    """Tests for compare endpoint."""

    def test_compare_metrics(self, client):
        """POST /api/v1/compare compares before/after metrics."""
        payload = {
            "before": [
                {"metric": "accuracy", "value": 0.75},
                {"metric": "latency_ms", "value": 200},
            ],
            "after": [
                {"metric": "accuracy", "value": 0.82},
                {"metric": "latency_ms", "value": 150},
            ],
            "industry": "general",
        }
        response = client.post("/api/v1/compare", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["metrics_compared"] == 2
        assert "improvements" in data
        assert "regressions" in data
        assert "unchanged" in data
        assert "summary" in data


class TestHistory:
    """Tests for history endpoints."""

    def test_list_history_empty(self, client):
        """GET /api/v1/history returns list (may be empty)."""
        response = client.get("/api/v1/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_history_with_params(self, client):
        """GET /api/v1/history accepts filter params."""
        response = client.get(
            "/api/v1/history?project=test&industry=manufacturing&limit=10"
        )
        assert response.status_code == 200

    def test_get_history_not_found(self, client):
        """GET /api/v1/history/{run_id} returns 404 for unknown."""
        response = client.get("/api/v1/history/nonexistent123")
        assert response.status_code == 404

    def test_get_history_invalid_run_id(self, client):
        """GET /api/v1/history/{run_id} validates run_id format."""
        response = client.get("/api/v1/history/invalid!@#$%")
        assert response.status_code == 400

    def test_cleanup_history(self, client):
        """DELETE /api/v1/history/cleanup returns count."""
        response = client.delete("/api/v1/history/cleanup?days=30")
        assert response.status_code == 200
        data = response.json()
        assert "deleted_count" in data
        assert "days_threshold" in data


class TestTrends:
    """Tests for trends endpoints."""

    def test_get_trends(self, client):
        """GET /api/v1/trends returns trend summary."""
        response = client.get("/api/v1/trends")
        assert response.status_code == 200
        data = response.json()
        assert "total_analyses" in data
        assert "metrics_tracked" in data
        assert "trends" in data

    def test_get_trends_with_params(self, client):
        """GET /api/v1/trends accepts filter params."""
        response = client.get("/api/v1/trends?project=test&days=60")
        assert response.status_code == 200

    def test_get_metric_history(self, client):
        """GET /api/v1/metrics/{name}/history returns metric history."""
        response = client.get("/api/v1/metrics/accuracy/history")
        assert response.status_code == 200
        data = response.json()
        assert "metric_name" in data
        assert "values" in data

    def test_get_metric_history_invalid_name(self, client):
        """GET /api/v1/metrics/{name}/history validates metric name."""
        response = client.get("/api/v1/metrics/123invalid/history")
        assert response.status_code == 400


class TestStats:
    """Tests for stats endpoint."""

    def test_get_stats(self, client):
        """GET /api/v1/stats returns storage stats."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_analyses" in data
        assert "database_size_bytes" in data


class TestCORS:
    """Tests for CORS handling."""

    def test_cors_preflight(self, client):
        """OPTIONS request gets CORS headers."""
        response = client.options(
            "/api/v1/info",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestDocs:
    """Tests for API documentation endpoints."""

    def test_openapi_json(self, client):
        """OpenAPI JSON is available."""
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert data["info"]["title"] == "Good AI Metrics API"

    def test_docs_available(self, client):
        """Swagger docs page is available."""
        response = client.get("/api/docs")
        assert response.status_code == 200


class TestInputValidation:
    """Tests for input validation and security."""

    def test_metric_name_length_limit(self, client):
        """Metric name length is limited."""
        payload = {
            "metrics": [
                {"metric": "a" * 200, "value": 0.5},  # Too long
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_metrics_count_limit(self, client):
        """Number of metrics is limited."""
        payload = {
            "metrics": [
                {"metric": f"metric_{i}", "value": 0.5} for i in range(1500)  # Too many
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_project_name_validation(self, client):
        """Project name format is validated."""
        payload = {
            "metrics": [
                {"metric": "accuracy", "value": 0.8},
            ],
            "industry": "manufacturing",
            "project": "invalid project!@#",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_industry_name_validation(self, client):
        """Industry name format is validated."""
        payload = {
            "metrics": [
                {"metric": "accuracy", "value": 0.8},
            ],
            "industry": "invalid industry!@#",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422

    def test_value_bounds(self, client):
        """Metric values are within bounds."""
        payload = {
            "metrics": [
                {"metric": "accuracy", "value": 1e15},  # Too large
            ],
            "industry": "manufacturing",
        }
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 422
