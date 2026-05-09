from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    """Check DB + Redis connectivity."""
    from cache.redis_client import get_redis_client
    from db.connection import get_engine

    checks: dict[str, str] = {}

    # Redis
    try:
        redis = get_redis_client()
        if redis is None:
            checks["redis"] = "disabled"
        else:
            await redis.ping()
            checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # Postgres
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    all_ok = all(v in {"ok", "disabled"} for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
