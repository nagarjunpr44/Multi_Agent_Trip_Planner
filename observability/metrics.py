"""
Prometheus metrics for AgenticTripPlanner.

Exposes /metrics endpoint when prometheus_client is installed.
Metrics:
  - atp_graph_runs_total          (counter, labels: status)
  - atp_agent_duration_seconds    (histogram, labels: agent)
  - atp_active_sessions           (gauge)
  - atp_validation_score          (histogram)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Lazily imported to avoid hard dependency ───────────────────────────────
try:
    from prometheus_client import Counter, Gauge, Histogram

    _ENABLED = True
except ImportError:
    _ENABLED = False
    logger.debug("prometheus_client not installed — metrics disabled")


def _noop(*args, **kwargs):  # noqa: ANN001
    """No-op fallback for all metric operations."""


class _NoopMetric:
    def labels(self, **kwargs):  # noqa: ANN001
        return self

    def inc(self, amount=1):  # noqa: ANN001
        pass

    def dec(self, amount=1):  # noqa: ANN001
        pass

    def observe(self, amount):  # noqa: ANN001
        pass

    def set(self, value):  # noqa: ANN001
        pass


if _ENABLED:
    GRAPH_RUNS = Counter(
        "atp_graph_runs_total",
        "Total graph invocations",
        ["status"],
    )
    AGENT_DURATION = Histogram(
        "atp_agent_duration_seconds",
        "Time spent in each agent node",
        ["agent"],
        buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    )
    ACTIVE_SESSIONS = Gauge("atp_active_sessions", "Currently active planning sessions")
    VALIDATION_SCORE = Histogram(
        "atp_validation_score",
        "Itinerary validation scores",
        buckets=[0.1, 0.25, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0],
    )
else:
    GRAPH_RUNS = _NoopMetric()  # type: ignore[assignment]
    AGENT_DURATION = _NoopMetric()  # type: ignore[assignment]
    ACTIVE_SESSIONS = _NoopMetric()  # type: ignore[assignment]
    VALIDATION_SCORE = _NoopMetric()  # type: ignore[assignment]


def record_agent_timing(agent: str, duration_ms: float) -> None:
    AGENT_DURATION.labels(agent=agent).observe(duration_ms / 1000)


def record_graph_run(status: str) -> None:
    GRAPH_RUNS.labels(status=status).inc()


def record_validation_score(score: float) -> None:
    VALIDATION_SCORE.observe(score)


def mount_metrics_endpoint(app) -> None:  # noqa: ANN001
    """Mount /metrics endpoint on the FastAPI app if prometheus_client is installed."""
    if not _ENABLED:
        logger.debug("Skipping /metrics endpoint (prometheus_client not installed)")
        return

    from prometheus_client import make_asgi_app

    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    logger.info("Prometheus /metrics endpoint mounted")
