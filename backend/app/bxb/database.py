
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

# Load environment variables from backend/.env
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from backend/.env")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


def get_session():
    with Session(engine) as session:
        yield session
