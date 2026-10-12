"""One durable, coalesced extraction intent per owner; never a memory record."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session


class CaptureIntentStore:
    def __init__(self, session_factory: Callable[[], Session]):
        self._factory = session_factory

    def _open(self) -> Session:
        db = self._factory()
        try:
            db.execute(
                text("""CREATE TABLE IF NOT EXISTS memory_capture_intents (
                owner TEXT PRIMARY KEY, snippet TEXT NOT NULL, version TEXT NOT NULL
            )""")
            )
            db.commit()
            return db
        except BaseException:
            db.close()
            raise

    def put(self, owner: str, snippet: str) -> str:
        if not owner or len(owner) > 200 or len(snippet) > 65536:
            raise ValueError("Invalid extraction intent")
        version = uuid.uuid4().hex
        with self._open() as db:
            db.execute(
                text("""INSERT INTO memory_capture_intents(owner,snippet,version)
                VALUES (:owner,:snippet,:version) ON CONFLICT(owner) DO UPDATE
                SET snippet=excluded.snippet, version=excluded.version"""),
                {"owner": owner, "snippet": snippet, "version": version},
            )
            db.commit()
        return version

    def list_pending(self) -> list[tuple[str, str, str]]:
        with self._open() as db:
            return [
                tuple(row)
                for row in db.execute(
                    text(
                        "SELECT owner,snippet,version FROM memory_capture_intents ORDER BY owner"
                    )
                )
            ]

    def get(self, owner: str) -> tuple[str, str, str] | None:
        with self._open() as db:
            row = db.execute(
                text(
                    "SELECT owner,snippet,version FROM memory_capture_intents WHERE owner=:owner"
                ),
                {"owner": owner},
            ).first()
            return tuple(row) if row else None

    def complete(self, owner: str, version: str) -> None:
        with self._open() as db:
            # A slow older request must not erase a newer coalesced transcript.
            db.execute(
                text(
                    "DELETE FROM memory_capture_intents WHERE owner=:owner AND version=:version"
                ),
                {"owner": owner, "version": version},
            )
            db.commit()


def get_capture_intent_store() -> CaptureIntentStore:
    from core.database import get_db_session

    return CaptureIntentStore(get_db_session)
