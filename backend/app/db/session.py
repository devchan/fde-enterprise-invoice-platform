from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# pool_pre_ping checks connections before use so stale/dropped DB connections
# (e.g. after an idle timeout) are transparently replaced instead of erroring.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    # FastAPI dependency: yields a session and guarantees it is closed once the
    # request finishes, whether it succeeds or raises.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

