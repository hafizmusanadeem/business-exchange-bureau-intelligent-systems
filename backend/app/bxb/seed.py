"""Load synthetic data + a few demo users so authenticated routes work.

Usage (from backend/ after `alembic upgrade head`):

    python -m app.bxb.seed

ALL DATA IS SYNTHETIC and clearly labelled.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlmodel import Session, func, select

from app.bxb.models import (
    EventKind,
    InvestorEvent,
    InvestorProfile,
    Listing,
    ListingStatus,
    Profile,
    Role,
)
from app.bxb.synthetic import generate
from app.core.config import settings
from app.core.db import engine
from app.core.security import get_password_hash
from app.models import User


# Fixed demo users so the interactive API can be exercised immediately.
DEMO_USERS = [
    {
        "email": "seller@bxb.demo",
        "password": "demopass123",
        "full_name": "Demo Seller",
        "is_superuser": False,
        "role": Role.seller,
    },
    {
        "email": "investor@bxb.demo",
        "password": "demopass123",
        "full_name": "Demo Investor",
        "is_superuser": False,
        "role": Role.investor,
    },
    {
        "email": "admin@bxb.demo",
        "password": "demopass123",
        "full_name": "BXB Admin",
        "is_superuser": True,
        "role": Role.admin,
    },
]


def _ensure_demo_users(session: Session) -> dict[str, uuid.UUID]:
    """Create the three demo users if they do not already exist. Returns email → id."""
    id_map: dict[str, uuid.UUID] = {}
    for u in DEMO_USERS:
        existing = session.exec(select(User).where(User.email == u["email"])).first()
        if existing:
            id_map[u["email"]] = existing.id
            if not session.get(Profile, existing.id):
                session.add(Profile(user_id=existing.id, role=u["role"]))
            continue
        user = User(
            id=uuid.uuid4(),
            email=u["email"],
            hashed_password=get_password_hash(u["password"]),
            full_name=u["full_name"],
            is_superuser=u["is_superuser"],
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.add(Profile(user_id=user.id, role=u["role"]))
        id_map[u["email"]] = user.id
    session.commit()
    return id_map


# Tables whose ids are inserted explicitly above, so their SERIAL sequences lag behind.
SEQUENCED_TABLES = ("listing", "investorprofile", "investorevent")


def _guard_environment() -> None:
    """The demo users have known passwords (one is a superuser): local only."""
    if settings.ENVIRONMENT != "local":
        raise SystemExit(
            f"Refusing to seed: ENVIRONMENT={settings.ENVIRONMENT!r}. "
            "This script creates accounts with published passwords and is local-only."
        )


def _already_seeded(session: Session) -> bool:
    return session.exec(select(func.count()).select_from(Listing)).one() > 0


def _sync_sequences(session: Session) -> None:
    """Inserting explicit ids bypasses the sequences, so the next API insert would
    reuse id 1 and fail with a duplicate key. Move each sequence past MAX(id).
    Empty table -> setval(seq, 1, false), so the next id is 1. No commit here.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    for table in SEQUENCED_TABLES:  # constant names, never user input
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
            )
        )


def main() -> None:
    _guard_environment()
    with Session(engine) as s:
        user_ids = _ensure_demo_users(s)
        if _already_seeded(s):
            # Re-running is safe, and also repairs a DB seeded by the older script.
            _sync_sequences(s)
            s.commit()
            print("Listings already present: seeding skipped, id sequences re-synced.")
            return
        d = generate()  # 36 months, planted trends
        seller_id = user_ids["seller@bxb.demo"]
        investor_uid = user_ids["investor@bxb.demo"]

        # --- Listings (keep original synthetic ids by setting them explicitly)
        # SQLModel / Postgres will accept explicit primary keys.
        listings = []
        for raw in d["listings"]:
            owner = seller_id if raw["id"] % 7 == 0 else None
            listings.append(
                Listing(
                    id=raw["id"],
                    sector=raw["sector"],
                    emirate=raw["emirate"],
                    years_operating=raw["years_operating"],
                    annual_revenue=raw["annual_revenue"],
                    ebitda=raw["ebitda"],
                    asking_price=raw["asking_price"],
                    ownership_pct=raw["ownership_pct"],
                    status=ListingStatus(raw["status"]),
                    listed_on=raw["listed_on"],
                    closed_on=raw["closed_on"],
                    owner_id=owner,
                )
            )
        s.add_all(listings)
        s.flush()  # one transaction for the whole seed: all-or-nothing

        # --- Investor profiles (explicit ids)
        inv_id_map: dict[int, int] = {}
        for raw in d["investors"]:
            uid = investor_uid if raw["id"] == 1 else None
            prof = InvestorProfile(
                id=raw["id"],
                name=raw["name"],
                country=raw["country"],
                budget_min=raw["budget_min"],
                budget_max=raw["budget_max"],
                min_ebitda=raw["min_ebitda"],
                risk_appetite=raw["risk_appetite"],
                sectors=raw["sectors"],
                emirates=raw["emirates"],
                joined_on=raw["joined_on"],
                user_id=uid,
            )
            s.add(prof)
            inv_id_map[raw["id"]] = raw["id"]
        s.flush()

        # --- Events (now ids line up)
        events = [
            InvestorEvent(
                id=raw["id"],
                investor_id=raw["investor_id"],
                listing_id=raw["listing_id"],
                sector=raw["sector"],
                kind=EventKind(raw["kind"]),
                qualified=raw["qualified"],
                occurred_on=raw["occurred_on"],
            )
            for raw in d["events"]
        ]
        s.add_all(events)
        s.flush()
        _sync_sequences(s)
        s.commit()

    print(
        {
            "listings": len(d["listings"]),
            "investors": len(d["investors"]),
            "events": len(d["events"]),
            "demo_users": list(user_ids.keys()),
        },
        "- all synthetic + demo users ready",
    )


if __name__ == "__main__":
    main()