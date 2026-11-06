# BXB Pulse – Module 1 (foundation layer)

Drop-in layer for `fastapi/full-stack-fastapi-template` (MIT). The template supplies auth, users,
Docker, CI, migrations and the React frontend; this layer adds the BXB domain.

## Install
    git clone https://github.com/fastapi/full-stack-fastapi-template bxb-pulse && cd bxb-pulse
    cp -r <this>/backend/app/bxb backend/app/bxb
    cp backend/app/bxb/routes.py backend/app/api/routes/bxb.py
    # backend/app/api/main.py: add `from app.api.routes import bxb` and `api_router.include_router(bxb.router)`
    # backend/app/models.py: add `from app.bxb.models import *  # noqa` so Alembic sees the tables
    cd backend && alembic revision --autogenerate -m "bxb tables" && alembic upgrade head
    python -m app.bxb.seed

## Notes
- Check that `app.api.deps` exports `SessionDep` and `CurrentUser` and that `app.core.db.engine` exists; the
  template has changed over time, so adjust import names if needed.
- Roles: BXB admin = template superuser; sellers and investors are normal users with a `Profile.role`.
- Only enquiry, meeting and offer events count as qualified demand. Views and saves are stored but excluded.
- All generated data is synthetic with planted trends (Healthcare demand up, Retail down, IT oversupplied).
