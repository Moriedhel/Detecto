"""Tests for CSV export (helper, repository batching and /history/export.csv)."""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.db import DetectionRepository, get_repository
from backend.main import app
from backend.models.record import DetectionRecordCreate, HistoryFilter, PersonBox
from backend.utils.export import BOM, COLUMNS, iter_csv, safe_cell

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _add(repo, count, ts, source="frame.jpg", avg=None):
    boxes = [PersonBox(bbox=[1, 2, 3, 4], confidence=0.9, center=[2, 3])] * count
    return repo.add(DetectionRecordCreate(
        count=count, avg_confidence=avg if avg is not None else (0.8 if count else None),
        inference_ms=50, total_ms=60, source=source, image_width=640, image_height=480,
        conf_threshold=0.4, detections=boxes,
    ), timestamp=ts)


def _parse(text: str) -> list[list[str]]:
    assert text.startswith(BOM)
    return list(csv.reader(io.StringIO(text[len(BOM):])))


@pytest.fixture
def repo(tmp_path):
    repo = DetectionRepository(tmp_path / "export.db")
    for i in range(4):  # counts 0..3, one per hour
        _add(repo, i, T0 + timedelta(hours=i))
    return repo


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- helper -----------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("photo.jpg", "photo.jpg"),
    ("=HYPERLINK(\"http://x\").jpg", "'=HYPERLINK(\"http://x\").jpg"),
    ("+1.jpg", "'+1.jpg"), ("-a.png", "'-a.png"), ("@x.png", "'@x.png"),
    (None, ""),
])
def test_safe_cell(value, expected):
    assert safe_cell(value) == expected


def test_iter_csv_chunks_and_single_bom(repo):
    records = list(repo.iter_records(HistoryFilter(newest_first=False)))
    chunks = list(iter_csv(records, chunk_rows=2))
    assert len(chunks) > 1
    text = "".join(chunks)
    assert text.count(BOM) == 1
    rows = _parse(text)
    assert rows[0] == COLUMNS
    assert [r[2] for r in rows[1:]] == ["0", "1", "2", "3"]
    assert rows[1][3] == ""  # no people -> empty avg_confidence
    assert rows[1][1] == "2026-10-01T09:00:00.000Z"


def test_iter_records_spans_batches(repo):
    got = list(repo.iter_records(HistoryFilter(), batch_size=3))
    assert [r.count for r in got] == [3, 2, 1, 0]


# --- API --------------------------------------------------------------------

def test_export_all(client):
    res = client.get("/history/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert 'filename="detecto_history_' in res.headers["content-disposition"]
    rows = _parse(res.text)
    assert rows[0] == COLUMNS
    assert len(rows) == 5
    assert rows[1][2] == "3"  # newest first by default


def test_export_filters(client):
    rows = _parse(client.get("/history/export.csv", params={
        "start": "2026-10-01T10:00:00Z", "min_count": 2, "newest_first": False,
    }).text)
    assert [r[2] for r in rows[1:]] == ["2", "3"]


def test_export_with_detections(client):
    rows = _parse(client.get("/history/export.csv", params={"include_detections": True}).text)
    assert rows[0][-1] == "detections_json"
    boxes = json.loads(rows[1][-1])
    assert len(boxes) == 3 and boxes[0]["bbox"] == [1, 2, 3, 4]


def test_export_escapes_formula_filenames(client, repo):
    _add(repo, 1, T0 + timedelta(days=1), source="=cmd|'/c calc'!A1.jpg")
    rows = _parse(client.get("/history/export.csv").text)
    assert rows[1][6] == "'=cmd|'/c calc'!A1.jpg"


def test_export_empty_history_has_header_only(client):
    client.delete("/reset")
    rows = _parse(client.get("/history/export.csv").text)
    assert rows == [COLUMNS]


def test_export_bad_range_is_400(client):
    res = client.get("/history/export.csv", params={
        "start": "2026-10-02T00:00:00Z", "end": "2026-10-01T00:00:00Z",
    })
    assert res.status_code == 400


def test_record_route_still_works(client):
    assert client.get("/history/1").status_code == 200
