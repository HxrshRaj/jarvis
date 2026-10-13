import argparse
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app import models  # noqa: F401
from app.db import Base

BACKEND = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return cfg


def test_migrations_match_models_and_are_reversible(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_cfg(url), "head")
    eng = create_engine(url)
    assert set(inspect(eng).get_table_names()) >= set(Base.metadata.tables) | {"alembic_version"}
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models drifted from migrations: {diff}"  # fails when a model changes without a new revision
    command.downgrade(_cfg(url), "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
