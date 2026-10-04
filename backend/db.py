"""SQLite storage for detection history.

Uses the standard-library sqlite3 module with one short-lived connection per
operation, which is safe across FastAPI's worker threads.
Timestamps are stored as UTC ISO-8601 strings so they sort and compare correctly.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.config import get_settings
from backend.models.record import (
    DetectionRecord,
    DetectionRecordCreate,
    HistoryPage,
    HistoryQuery,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    count             INTEGER NOT NULL,
    avg_confidence    REAL,
    inference_ms      REAL    NOT NULL,
    total_ms          REAL    NOT NULL,
    source            TEXT,
    image_width       INTEGER NOT NULL,
    image_height      INTEGER NOT NULL,
    conf_threshold    REAL    NOT NULL,
    contrast_enhanced INTEGER NOT NULL DEFAULT 0,
    detections_json   TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections (timestamp);
"""


def _to_utc_iso(dt: datetime) -> str:
    """Normalize a datetime to a UTC ISO string (naive values are treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


class DetectionRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits on success, rolls back on error
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
            conn.executescript(_SCHEMA)

    # --- writes -------------------------------------------------------------

    def add(self, rec: DetectionRecordCreate, timestamp: datetime | None = None) -> DetectionRecord:
        ts = _to_utc_iso(timestamp or datetime.now(timezone.utc))
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO detections (timestamp, count, avg_confidence, inference_ms,
                       total_ms, source, image_width, image_height, conf_threshold,
                       contrast_enhanced, detections_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts, rec.count, rec.avg_confidence, rec.inference_ms, rec.total_ms,
                    rec.source, rec.image_width, rec.image_height, rec.conf_threshold,
                    int(rec.contrast_enhanced),
                    json.dumps([d.model_dump() for d in rec.detections]),
                ),
            )
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._row_to_record(row)

    def clear(self) -> int:
        """Delete all history. Returns the number of rows removed."""
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM detections").rowcount
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'detections'")  # restart ids
        return deleted

    # --- reads --------------------------------------------------------------

    def list(self, q: HistoryQuery | None = None) -> HistoryPage:
        q = q or HistoryQuery()
        where, params = self._build_where(q)
        order = "DESC" if q.newest_first else "ASC"

        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM detections {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM detections {where} ORDER BY timestamp {order}, id {order} "
                "LIMIT ? OFFSET ?",
                [*params, q.limit, q.offset],
            ).fetchall()
        return HistoryPage(total=total, items=[self._row_to_record(r) for r in rows])

    def get(self, record_id: int) -> DetectionRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (record_id,)).fetchone()
        return self._row_to_record(row) if row else None

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _build_where(q: HistoryQuery) -> tuple[str, list]:
        clauses, params = [], []
        if q.start is not None:
            clauses.append("timestamp >= ?")
            params.append(_to_utc_iso(q.start))
        if q.end is not None:
            clauses.append("timestamp <= ?")
            params.append(_to_utc_iso(q.end))
        if q.min_confidence is not None:
            # Records with no people (NULL avg) are excluded by a confidence filter
            clauses.append("avg_confidence >= ?")
            params.append(q.min_confidence)
        if q.min_count is not None:
            clauses.append("count >= ?")
            params.append(q.min_count)
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DetectionRecord:
        data = dict(row)
        data["detections"] = json.loads(data.pop("detections_json"))
        data["contrast_enhanced"] = bool(data["contrast_enhanced"])
        return DetectionRecord(**data)


@lru_cache
def get_repository() -> DetectionRepository:
    """Shared repository bound to the configured database path."""
    return DetectionRepository(get_settings().db_path)
