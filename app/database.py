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


# create_all() never alters a table that already exists, so a column added
# after launch has to be ALTERed into existing DBs here: (table, column) -> type.
MISSING_COLUMNS = {
    ("teams", "group_name"): "VARCHAR(1)",
}


def add_missing_columns():
    with engine.begin() as conn:
        for (table, column), sql_type in MISSING_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
