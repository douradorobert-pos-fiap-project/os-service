import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://os_service:os_service@localhost:5432/os_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def session_scope() -> Iterator[Session]:
    with SessionFactory() as session:
        yield session
