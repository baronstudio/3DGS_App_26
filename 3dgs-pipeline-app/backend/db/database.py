from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

sqlite_url = f"sqlite:///{Path(__file__).parents[2] / 'pipeline.db'}"

engine = create_engine(sqlite_url, echo=True)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
