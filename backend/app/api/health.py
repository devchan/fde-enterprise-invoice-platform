from fastapi import APIRouter, Depends, Response, status
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe: the process is running. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(response: Response, db: Session = Depends(get_db)) -> dict:
    """Readiness probe: the process can serve traffic because its backing
    dependencies (database, Redis) are reachable. Returns 503 otherwise so
    orchestrators stop routing to an instance that cannot do real work."""
    checks: dict[str, str] = {}
    ready = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        ready = False

    client = None
    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
        ready = False
    finally:
        if client is not None:
            client.close()

    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "not_ready", "checks": checks}
