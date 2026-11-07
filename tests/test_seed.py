"""Regression tests for the seed script and the migrations (SQLite, no PostgreSQL needed)."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")  # app.bxb.database insists on a URL at import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, select

from app.api.deps import DEV_USER_ID
from app.bxb import listing_screen as LS, models as m, seed as seed_mod


@pytest.fixture()
def engine(monkeypatch):
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(seed_mod, "engine", eng)
    return eng


def test_seed_runs_and_is_idempotent(engine):
    seed_mod.main()
    with Session(engine) as s:
        users = {u.email for u in s.exec(select(m.User))}
        n_listings = len(s.exec(select(m.Listing)).all())
        n_drafts = len(s.exec(select(m.Listing).where(m.Listing.status == m.ListingStatus.draft)).all())
    assert {"seller@bxb.demo", "investor@bxb.demo", "admin@bxb.demo", "dev@bxb.local"} <= users
    assert n_drafts == len(seed_mod.DEMO_DRAFTS) and n_listings > 1000
    seed_mod.main()  # second run must add nothing
    with Session(engine) as s:
        assert len(s.exec(select(m.Listing)).all()) == n_listings
        assert len(s.exec(select(m.User)).all()) == len(users)


def test_dev_user_row_exists(engine):
    """deps.py serves every request as DEV_USER_ID; investorprofile.user_id is a foreign key to this row."""
    seed_mod.main()
    with Session(engine) as s:
        assert s.get(m.User, DEV_USER_ID).is_superuser
        assert s.get(m.Profile, DEV_USER_ID).role == m.Role.admin


def test_every_demo_draft_is_flagged_and_listing_data_is_clean():
    flagged = [LS.screen_listing(d)["status"] for d in seed_mod.DEMO_DRAFTS]
    assert all(s != "clear" for s in flagged) and "hold" in flagged


def test_hashed_password_is_not_plaintext():
    h = seed_mod._hash_password("demopass123")
    assert h.startswith("scrypt$") and "demopass123" not in h and h != seed_mod._hash_password("demopass123")


def test_seed_refuses_outside_local(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SystemExit):
        seed_mod._guard_environment()


def test_migrations_build_the_same_tables_and_columns_as_the_models():
    """Drift guard for table and column NAMES. SQLite cannot show enum-versus-VARCHAR differences
    (the migration once created VARCHAR where the models expect PostgreSQL enums), so that part
    needs a PostgreSQL run: alembic upgrade head, then python -m app.bxb.seed."""
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with eng.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            for name in ("2026_11_06_0001_bxb_foundation", "2026_11_06_0002_bxb_financial_fact"):
                importlib.import_module(f"app.alembic.versions.{name}").upgrade()
    insp = inspect(eng)
    assert set(insp.get_table_names()) == set(SQLModel.metadata.tables)
    for table in SQLModel.metadata.tables.values():
        assert {c["name"] for c in insp.get_columns(table.name)} == {c.name for c in table.columns}, table.name
