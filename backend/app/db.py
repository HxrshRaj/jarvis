from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def init_engine(url: str | None = None):
    """(Re)initialise the global engine. Tests call this with an isolated URL."""
    global _engine, _SessionLocal
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    _SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    from app import models  # noqa: F401  (register tables)

    if url.startswith("sqlite"):  # dev/tests; Postgres schemas are managed by Alembic (`alembic upgrade head`)
        Base.metadata.create_all(_engine)
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal


def get_db() -> Iterator[Session]:
    with session_factory()() as s:
        yield s
