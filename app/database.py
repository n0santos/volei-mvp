import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.environ.get("DB_PATH", "./volei.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def add_missing_columns():
    # create_all() never alters existing tables, so columns added after a
    # database was created have to be added by hand.
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(matches)")}
        if cols and "winner" not in cols:
            conn.exec_driver_sql("ALTER TABLE matches ADD COLUMN winner VARCHAR(1)")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
