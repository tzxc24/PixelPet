"""Idempotent additive migration preserving all five original tables and rows."""
from sqlalchemy import inspect, text


def migrate(engine):
    additions = {
        "conversations": {"title": "VARCHAR(100) NOT NULL DEFAULT '新对话'"},
        "messages": {"emotion": "VARCHAR(20) NOT NULL DEFAULT 'normal'", "action": "VARCHAR(20) NOT NULL DEFAULT 'idle'", "status": "VARCHAR(20) NOT NULL DEFAULT 'complete'", "mode": "VARCHAR(20) NOT NULL DEFAULT 'legacy'"},
        "memories": {"importance": "FLOAT NOT NULL DEFAULT 0.8", "source": "TEXT NOT NULL DEFAULT 'legacy'", "created_at":"DATETIME", "confirmed":"BOOLEAN NOT NULL DEFAULT 0", "confidence":"FLOAT NOT NULL DEFAULT 0.9"},
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            present = {col["name"] for col in inspect(conn).get_columns(table)}
            for name, declaration in columns.items():
                if name not in present:
                    # Identifiers and declarations are fixed code, never request input.
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {declaration}'))
        conn.execute(text("UPDATE memories SET created_at=updated_at WHERE created_at IS NULL"))
        conn.execute(text("PRAGMA user_version=3"))
        # An interrupted previous process cannot resume its model request.
        conn.execute(text("UPDATE messages SET status='failed' WHERE status='pending'"))
