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
    ("teams", "max_players"): "INTEGER NOT NULL DEFAULT 7",
    ("tournament_matches", "stage"): "VARCHAR(20) NOT NULL DEFAULT 'grupos'",
    ("tournament_matches", "walkover"): "BOOLEAN NOT NULL DEFAULT 0",
}

# Run once, right after the column is added, to fill it from older data.
BACKFILL = {
    ("tournament_matches", "stage"): "UPDATE tournament_matches SET stage = 'final' WHERE is_final = 1",
}


def add_missing_columns():
    with engine.begin() as conn:
        for (table, column), sql_type in MISSING_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
                if (table, column) in BACKFILL:
                    conn.exec_driver_sql(BACKFILL[(table, column)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
