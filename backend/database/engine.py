"""SQLite engine lifecycle and connection integrity."""
from pathlib import Path

from sqlalchemy import URL, create_engine, event

from backend.database.models import Base
from backend.database.migrations import migrate


def initialize_database(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)), connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(engine)
        migrate(engine)
    except Exception:
        engine.dispose()
        raise
    return engine
