"""CSV export of detection history.

Output is UTF-8 with a BOM so Excel detects the encoding, and text cells that
start with formula characters are escaped to prevent CSV/formula injection
(e.g. an uploaded file named "=HYPERLINK(...).jpg").
"""

import csv
import io
import json
from collections.abc import Iterable, Iterator

from backend.models.record import DetectionRecord

BOM = "﻿"
COLUMNS = [
    "id", "timestamp_utc", "people_count", "avg_confidence", "inference_ms", "total_ms",
    "source", "image_width", "image_height", "conf_threshold", "contrast_enhanced",
]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str | None) -> str:
    """Neutralise spreadsheet formulas in user-controlled text."""
    if value is None:
        return ""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


def _row(rec: DetectionRecord, include_detections: bool) -> list:
    row = [
        rec.id,
        rec.timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        rec.count,
        "" if rec.avg_confidence is None else rec.avg_confidence,
        rec.inference_ms,
        rec.total_ms,
        safe_cell(rec.source),
        rec.image_width,
        rec.image_height,
        rec.conf_threshold,
        str(rec.contrast_enhanced).lower(),
    ]
    if include_detections:
        row.append(json.dumps([d.model_dump() for d in rec.detections], separators=(",", ":")))
    return row


def iter_csv(records: Iterable[DetectionRecord], include_detections: bool = False,
             chunk_rows: int = 200) -> Iterator[str]:
    """Yield the CSV in text chunks (header first) for streaming responses."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")  # RFC 4180 line endings

    writer.writerow(COLUMNS + (["detections_json"] if include_detections else []))
    pending = 1
    first = True

    for rec in records:
        writer.writerow(_row(rec, include_detections))
        pending += 1
        if pending >= chunk_rows:
            yield (BOM if first else "") + buf.getvalue()
            first = False
            buf.seek(0)
            buf.truncate()
            pending = 0

    yield (BOM if first else "") + buf.getvalue()
