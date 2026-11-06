import uuid
from types import SimpleNamespace
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.bxb.database import engine

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_session():
    with Session(engine) as session:
        yield session


def get_current_user():
    # Local development only. Replace with real auth before production.
    return SimpleNamespace(id=DEV_USER_ID, is_superuser=True)


SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[SimpleNamespace, Depends(get_current_user)]