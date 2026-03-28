from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


def normalize_database_url(database_url: str) -> str:
    value = str(database_url or "").strip()
    if not value:
        return value
    if value.lower().startswith("sqlite"):
        return value
    url = make_url(value)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


class Base(DeclarativeBase):
    pass


settings = get_settings()
resolved_database_url = normalize_database_url(settings.database_url)

engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
connect_args: dict[str, object] = {}
if resolved_database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {"connect_timeout": 10}
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(resolved_database_url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
