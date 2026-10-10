"""SQLite storage for enrolled people and their face embeddings.

Privacy by design: only SFace embeddings (128 floats per photo) are stored,
never the photos themselves. Deleting a person deletes their embeddings.
Lives in the same database file as the detection history, in separate tables,
and is NOT affected by /reset (which clears detection history only).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.config import get_settings
from backend.models.faces import Person

EMBEDDING_DIM = 128

_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS face_embeddings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    embedding  BLOB    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_face_embeddings_person ON face_embeddings (person_id);
"""


class Gallery:
    """In-memory copy of all embeddings for fast matching (one row per photo)."""

    def __init__(self, person_ids: np.ndarray, names: list[str], matrix: np.ndarray):
        self.person_ids = person_ids  # (N,)
        self.names = names  # (N,)
        self.matrix = matrix  # (N, 128), rows L2-normalised

    def __len__(self) -> int:
        return len(self.names)


class FaceStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._gallery: Gallery | None = None
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- people ---------------------------------------------------------------

    def list_people(self) -> list[Person]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.id, p.name, p.created_at, COUNT(e.id) AS photos
                   FROM people p LEFT JOIN face_embeddings e ON e.person_id = p.id
                   GROUP BY p.id ORDER BY p.name COLLATE NOCASE"""
            ).fetchall()
        return [Person(**dict(r)) for r in rows]

    def get_person(self, person_id: int) -> Person | None:
        return next((p for p in self.list_people() if p.id == person_id), None)

    def get_or_create_person(self, name: str) -> tuple[Person, bool]:
        """Return (person, created). Names are unique, case-insensitive."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()
            created = row is None
            if created:
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                person_id = conn.execute(
                    "INSERT INTO people (name, created_at) VALUES (?, ?)", (name, now)
                ).lastrowid
            else:
                person_id = row["id"]
        return self.get_person(person_id), created

    def delete_person(self, person_id: int) -> bool:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM people WHERE id = ?", (person_id,)).rowcount
        self._invalidate()
        return deleted > 0

    # --- embeddings -----------------------------------------------------------

    def add_embeddings(self, person_id: int, embeddings: list[np.ndarray]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [(person_id, _to_blob(e), now) for e in embeddings]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO face_embeddings (person_id, embedding, created_at) VALUES (?, ?, ?)", rows
            )
        self._invalidate()

    def gallery(self) -> Gallery:
        """All embeddings, cached in memory until people/embeddings change."""
        with self._lock:
            if self._gallery is None:
                with self._connect() as conn:
                    rows = conn.execute(
                        """SELECT e.person_id, p.name, e.embedding
                           FROM face_embeddings e JOIN people p ON p.id = e.person_id"""
                    ).fetchall()
                matrix = (np.stack([_from_blob(r["embedding"]) for r in rows])
                          if rows else np.zeros((0, EMBEDDING_DIM), np.float32))
                self._gallery = Gallery(
                    np.array([r["person_id"] for r in rows], dtype=np.int64),
                    [r["name"] for r in rows],
                    matrix,
                )
            return self._gallery

    def _invalidate(self) -> None:
        with self._lock:
            self._gallery = None


def _to_blob(e: np.ndarray) -> bytes:
    return np.asarray(e, dtype=np.float32).reshape(EMBEDDING_DIM).tobytes()


def _from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32).copy()


@lru_cache
def get_face_store() -> FaceStore:
    return FaceStore(get_settings().db_path)
