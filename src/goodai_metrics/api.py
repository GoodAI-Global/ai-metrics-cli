"""
REST API Server for Good AI Metrics CLI.

Provides HTTP endpoints for metrics analysis, allowing integration
with web applications, dashboards, and automated pipelines.

Security features:
- Request validation with Pydantic
- Rate limiting (optional)
- CORS configuration
- Request ID tracking
- Input size limits
- No file system access from API payloads

Usage:
    goodai-metrics serve --host 0.0.0.0 --port 8000
    goodai-metrics serve --reload  # Development mode
"""

import io
import csv
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Annotated

from fastapi import FastAPI, HTTPException, Depends, Query, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict

from . import __version__
from .analyzer import MetricsAnalyzer, AnalysisError
from .benchmarks import load_benchmarks, get_benchmark_for_industry, BenchmarkError
from .config import load_config, ProjectConfig, ConfigError
from .storage import MetricsStorage, StorageError
from .logging_config import setup_logging, get_logger, set_context_id, clear_context_id
from .recommendations import (
    generate_all_recommendations,
    determine_overall_health,
    check_health_thresholds,
)


# ============================================================================
# Configuration and Constants
# ============================================================================

# Maximum request sizes to prevent DoS
MAX_METRICS_COUNT = 1000
MAX_METRIC_NAME_LENGTH = 100
MAX_CSV_ROWS = 10000
MAX_PROJECT_NAME_LENGTH = 100
MAX_INDUSTRY_LENGTH = 50

# Rate limiting defaults
DEFAULT_RATE_LIMIT = 100  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds

# Valid metric value range
MIN_METRIC_VALUE = -1e12
MAX_METRIC_VALUE = 1e12


# ============================================================================
# Pydantic Models for Request/Response Validation
# ============================================================================

class MetricInput(BaseModel):
    """Single metric input for analysis."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(
        ...,
        min_length=1,
        max_length=MAX_METRIC_NAME_LENGTH,
        description="Metric name"
    )
    value: float = Field(
        ...,
        ge=MIN_METRIC_VALUE,
        le=MAX_METRIC_VALUE,
        description="Metric value"
    )

    @field_validator("metric")
    @classmethod
    def validate_metric_name(cls, v: str) -> str:
        """Validate metric name format."""
        # Only allow alphanumeric, underscore, hyphen
        import re
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "Metric name must start with letter and contain only "
                "alphanumeric, underscore, or hyphen characters"
            )
        return v

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float) -> float:
        """Ensure value is not NaN or infinite."""
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Value must be a finite number")
        return v


class AnalyzeRequest(BaseModel):
    """Request body for analyze endpoint."""

    model_config = ConfigDict(extra="forbid")

    metrics: List[MetricInput] = Field(
        ...,
        min_length=1,
        max_length=MAX_METRICS_COUNT,
        description="List of metrics to analyze"
    )
    industry: str = Field(
        default="general",
        max_length=MAX_INDUSTRY_LENGTH,
        description="Industry for benchmark comparison"
    )
    store_results: bool = Field(
        default=False,
        description="Store results in history database"
    )
    project: Optional[str] = Field(
        default=None,
        max_length=MAX_PROJECT_NAME_LENGTH,
        description="Project name for result tracking"
    )

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, v: str) -> str:
        """Validate industry name format."""
        import re
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError("Invalid industry name format")
        return v.lower()

    @field_validator("project")
    @classmethod
    def validate_project(cls, v: Optional[str]) -> Optional[str]:
        """Validate project name format."""
        if v is None:
            return v
        import re
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError("Invalid project name format")
        return v


class HealthCheckRequest(BaseModel):
    """Request body for health check endpoint."""

    model_config = ConfigDict(extra="forbid")

    metrics: List[MetricInput] = Field(
        ...,
        min_length=1,
        max_length=MAX_METRICS_COUNT,
        description="List of metrics to check"
    )
    industry: str = Field(
        default="general",
        max_length=MAX_INDUSTRY_LENGTH,
        description="Industry for benchmark comparison"
    )
    max_high_priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Maximum allowed HIGH priority items"
    )
    max_gap_percent: float = Field(
        default=30.0,
        ge=0,
        le=1000,
        description="Maximum allowed gap percentage"
    )


class CompareRequest(BaseModel):
    """Request body for compare endpoint."""

    model_config = ConfigDict(extra="forbid")

    before: List[MetricInput] = Field(
        ...,
        min_length=1,
        max_length=MAX_METRICS_COUNT,
        description="Metrics from before period"
    )
    after: List[MetricInput] = Field(
        ...,
        min_length=1,
        max_length=MAX_METRICS_COUNT,
        description="Metrics from after period"
    )
    industry: str = Field(
        default="general",
        max_length=MAX_INDUSTRY_LENGTH,
        description="Industry context"
    )


class MetricAnalysis(BaseModel):
    """Single metric analysis result."""
    metric: str
    current_value: float
    benchmark_p50: Optional[float] = None
    gap_percent: float
    percentile_bracket: Optional[str] = None


class Recommendation(BaseModel):
    """Single recommendation."""
    metric: str
    priority: str
    effort: str
    recommendation_text: str
    gap_percent: float


class AnalyzeResponse(BaseModel):
    """Response for analyze endpoint."""
    run_id: Optional[str] = None
    industry: str
    metrics_analyzed: int
    metrics_with_benchmarks: int
    overall_health: str
    analysis: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    timestamp: str


class HealthCheckResponse(BaseModel):
    """Response for health check endpoint."""
    passed: bool
    overall_health: str
    high_priority_count: int
    max_gap_found: float
    violations: List[str]
    timestamp: str


class CompareResponse(BaseModel):
    """Response for compare endpoint."""
    industry: str
    metrics_compared: int
    improvements: List[Dict[str, Any]]
    regressions: List[Dict[str, Any]]
    unchanged: List[Dict[str, Any]]
    summary: Dict[str, Any]


class IndustryInfo(BaseModel):
    """Industry information."""
    name: str
    metrics: List[str]
    metric_count: int


class ServerInfo(BaseModel):
    """Server information response."""
    version: str
    status: str
    uptime_seconds: float
    timestamp: str


class HistoryListItem(BaseModel):
    """Single history list item."""
    run_id: str
    project: Optional[str]
    industry: str
    timestamp: str
    metrics_count: int
    overall_health: str


class TrendSummaryResponse(BaseModel):
    """Trend summary response."""
    total_analyses: int
    metrics_tracked: int
    improving: int
    declining: int
    stable: int
    trends: List[Dict[str, Any]]


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None


# ============================================================================
# Rate Limiting (Simple In-Memory)
# ============================================================================

class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = DEFAULT_RATE_LIMIT, window: int = RATE_LIMIT_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self.requests: Dict[str, List[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed for client."""
        now = time.time()

        # Clean old entries
        if client_id in self.requests:
            self.requests[client_id] = [
                ts for ts in self.requests[client_id]
                if now - ts < self.window
            ]
        else:
            self.requests[client_id] = []

        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        # Record request
        self.requests[client_id].append(now)
        return True

    def get_remaining(self, client_id: str) -> int:
        """Get remaining requests for client."""
        if client_id not in self.requests:
            return self.max_requests
        now = time.time()
        active = [ts for ts in self.requests[client_id] if now - ts < self.window]
        return max(0, self.max_requests - len(active))


# ============================================================================
# Application State
# ============================================================================

class AppState:
    """Application state container."""

    def __init__(self):
        self.start_time: float = time.time()
        self.config: ProjectConfig = ProjectConfig()
        self.rate_limiter: RateLimiter = RateLimiter()
        self.benchmarks: Dict[str, Any] = {}
        self._storage: Optional[MetricsStorage] = None

    def get_storage(self) -> MetricsStorage:
        """Get or create storage instance."""
        if self._storage is None:
            storage_path = Path(self.config.storage_path) if self.config.storage_path else None
            self._storage = MetricsStorage(db_path=storage_path)
        return self._storage

    def reload_config(self) -> None:
        """Reload configuration."""
        try:
            self.config = load_config()
        except ConfigError:
            self.config = ProjectConfig()

    def reload_benchmarks(self) -> None:
        """Reload benchmarks."""
        try:
            self.benchmarks = load_benchmarks()
        except BenchmarkError:
            self.benchmarks = {}


app_state = AppState()


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger = get_logger(__name__)

    # Startup
    logger.info("Starting Good AI Metrics API server")
    app_state.start_time = time.time()

    try:
        app_state.reload_config()
        app_state.reload_benchmarks()
        logger.info(f"Loaded {len(app_state.benchmarks)} industry benchmarks")
    except Exception as e:
        logger.error(f"Error during startup: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Good AI Metrics API server")
    clear_context_id()


# ============================================================================
# FastAPI Application
# ============================================================================

def create_app(
    enable_cors: bool = True,
    cors_origins: List[str] = None,
    rate_limit: Optional[int] = DEFAULT_RATE_LIMIT,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        enable_cors: Enable CORS middleware.
        cors_origins: Allowed CORS origins (default: all).
        rate_limit: Requests per minute limit (None to disable).

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Good AI Metrics API",
        description=(
            "REST API for analyzing AI implementation metrics against "
            "industry benchmarks. Evidence over opinions."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS middleware
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins or ["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    # Request tracking middleware
    @app.middleware("http")
    async def add_request_tracking(request: Request, call_next):
        """Add request ID and timing to all requests."""
        # Generate request ID
        request_id = secrets.token_hex(8)
        set_context_id(request_id)

        # Rate limiting
        if rate_limit:
            client_ip = request.client.host if request.client else "unknown"
            if not app_state.rate_limiter.is_allowed(client_ip):
                clear_context_id()
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": f"Maximum {rate_limit} requests per minute",
                        "request_id": request_id,
                    },
                )

        # Process request
        start_time = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        # Add response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        clear_context_id()
        return response

    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger = get_logger(__name__)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    # Register routes
    app.include_router(api_router, prefix="/api/v1")

    return app


# ============================================================================
# API Routes
# ============================================================================

from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/info", response_model=ServerInfo, tags=["Server"])
async def get_server_info():
    """
    Get server information and status.

    Returns server version, status, and uptime.
    """
    return ServerInfo(
        version=__version__,
        status="healthy",
        uptime_seconds=time.time() - app_state.start_time,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@api_router.get("/industries", response_model=List[IndustryInfo], tags=["Benchmarks"])
async def list_industries():
    """
    List available industries with benchmarks.

    Returns all industries that have benchmark data available
    along with the metrics tracked for each industry.
    """
    if not app_state.benchmarks:
        app_state.reload_benchmarks()

    industries = []
    for name, metrics in sorted(app_state.benchmarks.items()):
        metric_names = list(metrics.keys())
        industries.append(IndustryInfo(
            name=name,
            metrics=metric_names,
            metric_count=len(metric_names),
        ))

    return industries


@api_router.get("/industries/{industry}", tags=["Benchmarks"])
async def get_industry_benchmarks(industry: str):
    """
    Get benchmark data for a specific industry.

    Returns all benchmark values (p25, p50, p75, p90) for
    metrics in the specified industry.
    """
    if not app_state.benchmarks:
        app_state.reload_benchmarks()

    try:
        benchmarks = get_benchmark_for_industry(industry, app_state.benchmarks)
        return {
            "industry": industry,
            "benchmarks": benchmarks,
        }
    except BenchmarkError as e:
        raise HTTPException(status_code=404, detail=str(e))


@api_router.post("/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze_metrics(request: AnalyzeRequest):
    """
    Analyze metrics against industry benchmarks.

    Accepts a list of metrics and returns analysis with
    benchmark comparisons, gap analysis, and recommendations.

    Optionally stores results in the history database for
    trend tracking.
    """
    logger = get_logger(__name__)

    try:
        # Convert request metrics to analyzer format
        metrics_dict = {m.metric: m.value for m in request.metrics}

        # Load benchmarks
        if not app_state.benchmarks:
            app_state.reload_benchmarks()

        industry_benchmarks = get_benchmark_for_industry(
            request.industry, app_state.benchmarks
        )

        # Create analyzer and analyze
        analyzer = MetricsAnalyzer(industry=request.industry)

        # Build metrics list for analyzer
        metrics_list = [
            {"metric": m.metric, "value": m.value}
            for m in request.metrics
        ]

        # Analyze
        analysis_results = analyzer.analyze_dict(metrics_dict)

        # Generate recommendations
        recommendations = generate_all_recommendations(
            analysis_results, industry_benchmarks
        )
        overall_health = determine_overall_health(recommendations)

        # Build full results
        full_results = {
            **analysis_results,
            "recommendations": recommendations,
            "overall_health": overall_health,
        }

        # Store if requested
        run_id = None
        if request.store_results:
            try:
                storage = app_state.get_storage()
                run_id = storage.store_analysis(
                    full_results,
                    project=request.project or app_state.config.project_name
                )
                logger.info(f"Stored analysis with run_id={run_id}")
            except StorageError as e:
                logger.warning(f"Failed to store results: {e}")

        return AnalyzeResponse(
            run_id=run_id,
            industry=request.industry,
            metrics_analyzed=analysis_results.get("metrics_analyzed", 0),
            metrics_with_benchmarks=analysis_results.get("metrics_with_benchmarks", 0),
            overall_health=overall_health,
            analysis=analysis_results.get("analysis", []),
            recommendations=recommendations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except BenchmarkError as e:
        raise HTTPException(status_code=400, detail=f"Benchmark error: {e}")
    except AnalysisError as e:
        raise HTTPException(status_code=400, detail=f"Analysis error: {e}")


@api_router.post("/health-check", response_model=HealthCheckResponse, tags=["Analysis"])
async def health_check(request: HealthCheckRequest):
    """
    Quick health check for CI/CD pipelines.

    Analyzes metrics and returns pass/fail status based on
    configurable thresholds. Use this endpoint for automated
    quality gates.
    """
    try:
        # Convert request metrics
        metrics_dict = {m.metric: m.value for m in request.metrics}

        # Load benchmarks
        if not app_state.benchmarks:
            app_state.reload_benchmarks()

        industry_benchmarks = get_benchmark_for_industry(
            request.industry, app_state.benchmarks
        )

        # Analyze
        analyzer = MetricsAnalyzer(industry=request.industry)
        analysis_results = analyzer.analyze_dict(metrics_dict)

        # Generate recommendations
        recommendations = generate_all_recommendations(
            analysis_results, industry_benchmarks
        )
        overall_health = determine_overall_health(recommendations)

        # Check thresholds
        health_result = check_health_thresholds(
            recommendations,
            max_high_priority=request.max_high_priority,
            max_gap_percent=request.max_gap_percent,
        )

        return HealthCheckResponse(
            passed=health_result["passed"],
            overall_health=overall_health,
            high_priority_count=health_result.get("high_priority_count", 0),
            max_gap_found=health_result.get("max_gap", 0),
            violations=health_result.get("violations", []),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except BenchmarkError as e:
        raise HTTPException(status_code=400, detail=f"Benchmark error: {e}")
    except AnalysisError as e:
        raise HTTPException(status_code=400, detail=f"Analysis error: {e}")


@api_router.post("/compare", response_model=CompareResponse, tags=["Analysis"])
async def compare_metrics(request: CompareRequest):
    """
    Compare metrics between two time periods.

    Accepts before and after metrics and returns improvement
    analysis with percentage changes and direction indicators.
    """
    try:
        # Convert to dicts
        before_dict = {m.metric: m.value for m in request.before}
        after_dict = {m.metric: m.value for m in request.after}

        # Find common metrics
        common_metrics = set(before_dict.keys()) & set(after_dict.keys())

        improvements = []
        regressions = []
        unchanged = []

        for metric in common_metrics:
            before_val = before_dict[metric]
            after_val = after_dict[metric]

            if before_val == 0:
                change_percent = 100.0 if after_val > 0 else 0.0
            else:
                change_percent = ((after_val - before_val) / abs(before_val)) * 100

            result = {
                "metric": metric,
                "before": before_val,
                "after": after_val,
                "change_percent": round(change_percent, 2),
            }

            # Determine if higher is better (simple heuristic)
            lower_is_better = any(
                word in metric.lower()
                for word in ["error", "latency", "failure", "cost", "time"]
            )

            if lower_is_better:
                if change_percent < -1:
                    result["direction"] = "improved"
                    improvements.append(result)
                elif change_percent > 1:
                    result["direction"] = "regressed"
                    regressions.append(result)
                else:
                    result["direction"] = "unchanged"
                    unchanged.append(result)
            else:
                if change_percent > 1:
                    result["direction"] = "improved"
                    improvements.append(result)
                elif change_percent < -1:
                    result["direction"] = "regressed"
                    regressions.append(result)
                else:
                    result["direction"] = "unchanged"
                    unchanged.append(result)

        return CompareResponse(
            industry=request.industry,
            metrics_compared=len(common_metrics),
            improvements=improvements,
            regressions=regressions,
            unchanged=unchanged,
            summary={
                "improved_count": len(improvements),
                "regressed_count": len(regressions),
                "unchanged_count": len(unchanged),
                "before_metrics_only": list(set(before_dict.keys()) - common_metrics),
                "after_metrics_only": list(set(after_dict.keys()) - common_metrics),
            },
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Comparison error: {e}")


@api_router.get("/history", response_model=List[HistoryListItem], tags=["History"])
async def list_history(
    project: Optional[str] = Query(None, max_length=MAX_PROJECT_NAME_LENGTH),
    industry: Optional[str] = Query(None, max_length=MAX_INDUSTRY_LENGTH),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List analysis history.

    Returns recent analysis records with optional filtering
    by project and industry.
    """
    try:
        storage = app_state.get_storage()
        records = storage.list_analyses(
            project=project,
            industry=industry,
            limit=limit,
        )

        return [
            HistoryListItem(
                run_id=r.run_id,
                project=r.project,
                industry=r.industry,
                timestamp=r.timestamp.isoformat(),
                metrics_count=r.metrics_count,
                overall_health=r.overall_health,
            )
            for r in records
        ]

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


@api_router.get("/history/{run_id}", tags=["History"])
async def get_history_record(run_id: str):
    """
    Get detailed analysis record by run ID.

    Returns the full analysis results including all metrics,
    recommendations, and timestamps.
    """
    # Validate run_id format
    if not run_id or len(run_id) > 64 or not run_id.isalnum():
        raise HTTPException(status_code=400, detail="Invalid run_id format")

    try:
        storage = app_state.get_storage()
        record = storage.get_analysis(run_id)

        if not record:
            raise HTTPException(status_code=404, detail=f"Record not found: {run_id}")

        return {
            "run_id": record.run_id,
            "project": record.project,
            "industry": record.industry,
            "timestamp": record.timestamp.isoformat(),
            "metrics_count": record.metrics_count,
            "overall_health": record.overall_health,
            "results": record.full_results,
        }

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


@api_router.delete("/history/cleanup", tags=["History"])
async def cleanup_history(
    days: int = Query(90, ge=1, le=3650),
):
    """
    Delete old analysis records.

    Removes records older than the specified number of days.
    Returns the count of deleted records.
    """
    try:
        storage = app_state.get_storage()
        deleted = storage.delete_old_records(days=days)

        return {
            "deleted_count": deleted,
            "days_threshold": days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


@api_router.get("/trends", response_model=TrendSummaryResponse, tags=["Trends"])
async def get_trends(
    project: Optional[str] = Query(None, max_length=MAX_PROJECT_NAME_LENGTH),
    days: int = Query(30, ge=1, le=365),
):
    """
    Get historical metric trends.

    Analyzes stored metrics over time to identify improving,
    declining, and stable trends.
    """
    try:
        storage = app_state.get_storage()
        summary = storage.get_trend_summary(project=project, days=days)

        return TrendSummaryResponse(
            total_analyses=summary.get("total_analyses", 0),
            metrics_tracked=summary.get("metrics_tracked", 0),
            improving=summary.get("improving", 0),
            declining=summary.get("declining", 0),
            stable=summary.get("stable", 0),
            trends=summary.get("trends", []),
        )

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


@api_router.get("/metrics/{metric_name}/history", tags=["Trends"])
async def get_metric_history(
    metric_name: str,
    project: Optional[str] = Query(None, max_length=MAX_PROJECT_NAME_LENGTH),
    days: int = Query(30, ge=1, le=365),
):
    """
    Get history for a specific metric.

    Returns all recorded values for a metric over time,
    useful for detailed trend analysis.
    """
    # Validate metric name
    import re
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", metric_name):
        raise HTTPException(status_code=400, detail="Invalid metric name format")

    if len(metric_name) > MAX_METRIC_NAME_LENGTH:
        raise HTTPException(status_code=400, detail="Metric name too long")

    try:
        storage = app_state.get_storage()
        history = storage.get_metric_history(
            metric_name,
            project=project,
            days=days,
        )

        return history.to_dict()

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


@api_router.get("/stats", tags=["Server"])
async def get_storage_stats():
    """
    Get storage statistics.

    Returns database size, record counts, and date ranges
    for stored analysis data.
    """
    try:
        storage = app_state.get_storage()
        stats = storage.get_database_stats()
        return stats

    except StorageError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")


# ============================================================================
# Default Application Instance
# ============================================================================

# Create default app for use with uvicorn directly
app = create_app()
