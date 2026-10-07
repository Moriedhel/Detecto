"""SQLite storage for detection history.

Uses the standard-library sqlite3 module with one short-lived connection per
operation, which is safe across FastAPI's worker threads.
Timestamps are stored as UTC ISO-8601 strings so they sort and compare correctly.
"""

# Lazy annotations: the `list` method below would otherwise shadow the builtin
# inside the class body (e.g. in `-> list[HourlyBucket]`).
from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.config import get_settings
from backend.models.record import (
    DetectionRecord,
    DetectionRecordCreate,
    HistoryFilter,
    HistoryPage,
    HistoryQuery,
    TimeRange,
)
from backend.models.stats import HourlyBucket, HourlyQuery, SummaryStats

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

    def iter_records(self, f: HistoryFilter, batch_size: int = 500) -> Iterator[DetectionRecord]:
        """Yield every record matching the filters, fetched in batches.

        Each batch uses its own short-lived connection, so the generator can be
        consumed across threads (as StreamingResponse does) without holding a
        connection open for the whole export.
        """
        q = HistoryQuery(**f.model_dump(include=set(HistoryFilter.model_fields)),
                         limit=batch_size, offset=0)
        while True:
            items = self.list(q).items
            yield from items
            if len(items) < batch_size:
                return
            q.offset += batch_size

    def get(self, record_id: int) -> DetectionRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (record_id,)).fetchone()
        return self._row_to_record(row) if row else None

    # --- statistics ---------------------------------------------------------

    def summary(self, q: TimeRange | None = None) -> SummaryStats:
        """Aggregate counts, confidence and timing over the (filtered) history."""
        where, params = self._build_where(q or TimeRange())
        with self._connect() as conn:
            row = conn.execute(
                f"""SELECT
                        COUNT(*)                                   AS total_detections,
                        COALESCE(SUM(count > 0), 0)                AS frames_with_people,
                        COALESCE(SUM(count), 0)                    AS total_people,
                        AVG(count)                                 AS avg_people,
                        MAX(count)                                 AS max_people,
                        -- per-person mean: weight each frame's average by its count
                        SUM(avg_confidence * count)
                          / NULLIF(SUM(CASE WHEN avg_confidence IS NOT NULL THEN count END), 0)
                                                                   AS avg_confidence,
                        AVG(inference_ms)                          AS avg_inference_ms,
                        MAX(inference_ms)                          AS max_inference_ms,
                        AVG(total_ms)                              AS avg_total_ms,
                        MIN(timestamp)                             AS first_timestamp,
                        MAX(timestamp)                             AS last_timestamp
                    FROM detections {where}""",
                params,
            ).fetchone()
            data = dict(row)
            n = data["total_detections"]
            data["p50_inference_ms"] = self._percentile(conn, "inference_ms", 0.50, n, where, params)
            data["p95_inference_ms"] = self._percentile(conn, "inference_ms", 0.95, n, where, params)

        for key in ("avg_people", "avg_confidence", "avg_inference_ms", "max_inference_ms",
                    "avg_total_ms", "p50_inference_ms", "p95_inference_ms"):
            if data[key] is not None:
                data[key] = round(data[key], 4 if key == "avg_confidence" else 2)
        return SummaryStats(**data)

    def hourly(self, q: HourlyQuery) -> list[HourlyBucket]:
        """Group detections into hourly buckets (calendar hours or hour-of-day)."""
        where, params = self._build_where(q)
        fmt = "%Y-%m-%dT%H:00" if q.mode == "timeline" else "%H"
        shift = f"{q.tz_offset_minutes:+d} minutes"  # SQLite date modifier
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT strftime(?, timestamp, ?)  AS hour,
                           COUNT(*)                   AS detections,
                           ROUND(AVG(count), 2)       AS avg_people,
                           MAX(count)                 AS max_people,
                           ROUND(SUM(avg_confidence * count)
                             / NULLIF(SUM(CASE WHEN avg_confidence IS NOT NULL THEN count END), 0), 4)
                                                      AS avg_confidence
                    FROM detections {where}
                    GROUP BY hour ORDER BY hour""",
                [fmt, shift, *params],
            ).fetchall()
        return [HourlyBucket(**dict(r)) for r in rows]

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _percentile(conn, column: str, p: float, n: int, where: str, params: list) -> float | None:
        """Nearest-rank percentile computed in SQL (no need to load all rows)."""
        if n == 0:
            return None
        offset = max(math.ceil(p * n) - 1, 0)
        row = conn.execute(
            f"SELECT {column} FROM detections {where} ORDER BY {column} LIMIT 1 OFFSET ?",
            [*params, offset],
        ).fetchone()
        return row[0]

    @staticmethod
    def _build_where(q: TimeRange) -> tuple[str, list]:
        """WHERE clause from a TimeRange (and HistoryQuery's extra filters, if present)."""
        clauses, params = [], []
        if q.start is not None:
            clauses.append("timestamp >= ?")
            params.append(_to_utc_iso(q.start))
        if q.end is not None:
            clauses.append("timestamp <= ?")
            params.append(_to_utc_iso(q.end))
        min_confidence = getattr(q, "min_confidence", None)
        if min_confidence is not None:
            # Records with no people (NULL avg) are excluded by a confidence filter
            clauses.append("avg_confidence >= ?")
            params.append(min_confidence)
        min_count = getattr(q, "min_count", None)
        if min_count is not None:
            clauses.append("count >= ?")
            params.append(min_count)
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
