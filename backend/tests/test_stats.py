"""Tests for summary/hourly statistics (repository + /stats API)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.db import DetectionRepository, get_repository
from backend.main import app
from backend.models.record import DetectionRecordCreate, TimeRange
from backend.models.stats import HourlyQuery

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _add(repo, count, ts, inference_ms=50.0):
    repo.add(DetectionRecordCreate(
        count=count, avg_confidence=round(0.5 + count * 0.08, 2) if count else None,
        inference_ms=inference_ms, total_ms=inference_ms + 10, source="x.jpg",
        image_width=640, image_height=480, conf_threshold=0.4,
    ), timestamp=ts)


@pytest.fixture
def repo(tmp_path):
    """6 hourly records 09:00-14:00 UTC: count = 0..5, inference = 10..60 ms."""
    repo = DetectionRepository(tmp_path / "stats.db")
    for i in range(6):
        _add(repo, i, T0 + timedelta(hours=i), inference_ms=10.0 * (i + 1))
    return repo


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- repository -------------------------------------------------------------

def test_summary_values(repo):
    s = repo.summary()
    assert s.total_detections == 6
    assert s.frames_with_people == 5
    assert s.total_people == 15
    assert s.avg_people == 2.5
    assert s.max_people == 5
    # per-person mean: (0.58*1 + 0.66*2 + 0.74*3 + 0.82*4 + 0.90*5) / 15
    assert s.avg_confidence == pytest.approx(0.7933, abs=1e-4)
    assert s.avg_inference_ms == 35.0
    assert s.p50_inference_ms == 30.0
    assert s.p95_inference_ms == 60.0
    assert s.max_inference_ms == 60.0
    assert s.first_timestamp == T0
    assert s.last_timestamp == T0 + timedelta(hours=5)


def test_summary_time_range(repo):
    s = repo.summary(TimeRange(start=T0 + timedelta(hours=4)))
    assert s.total_detections == 2 and s.total_people == 9


def test_summary_empty_db(tmp_path):
    s = DetectionRepository(tmp_path / "empty.db").summary()
    assert s.total_detections == 0 and s.total_people == 0
    assert s.avg_people is None and s.avg_confidence is None and s.p95_inference_ms is None


def test_hourly_timeline_utc_and_local(repo):
    utc = repo.hourly(HourlyQuery())
    assert [b.hour for b in utc] == [f"2026-10-01T{h:02d}:00" for h in range(9, 15)]
    assert [b.max_people for b in utc] == [0, 1, 2, 3, 4, 5]
    assert utc[0].avg_confidence is None  # no people in that hour

    local = repo.hourly(HourlyQuery(tz_offset_minutes=180))  # UTC+3
    assert local[0].hour == "2026-10-01T12:00"


def test_hourly_hour_of_day_merges_days(repo):
    _add(repo, 3, T0 + timedelta(days=1, minutes=30))  # next day 09:30
    buckets = {b.hour: b for b in repo.hourly(HourlyQuery(mode="hour_of_day"))}
    assert set(buckets) == {"09", "10", "11", "12", "13", "14"}
    assert buckets["09"].detections == 2
    assert buckets["09"].avg_people == 1.5


# --- API --------------------------------------------------------------------

def test_stats_endpoint(client):
    body = client.get("/stats").json()
    assert body["summary"]["total_people"] == 15
    assert body["summary"]["p95_inference_ms"] == 60.0
    rt = body["runtime"]
    assert rt["model"] == "yolov8n.pt" and rt["device"] == "cpu" and rt["uptime_s"] >= 0


def test_stats_endpoint_with_range(client):
    body = client.get("/stats", params={"end": "2026-10-01T10:00:00Z"}).json()
    assert body["summary"]["total_detections"] == 2


def test_hourly_endpoint(client):
    body = client.get("/stats/hourly", params={"mode": "hour_of_day", "tz_offset_minutes": 180}).json()
    assert body["mode"] == "hour_of_day"
    assert [b["hour"] for b in body["buckets"]] == ["12", "13", "14", "15", "16", "17"]


def test_stats_and_hourly_accept_record_filters(client):
    # records: counts 0..5, avg confidence 0.58..0.90 for counts 1..5
    body = client.get("/stats", params={"min_count": 3}).json()["summary"]
    assert body["total_detections"] == 3 and body["total_people"] == 12

    body = client.get("/stats", params={"min_confidence": 0.8}).json()["summary"]
    assert body["total_detections"] == 2  # counts 4 (0.82) and 5 (0.90)

    hourly = client.get("/stats/hourly", params={"min_count": 4}).json()["buckets"]
    assert [b["max_people"] for b in hourly] == [4, 5]


@pytest.mark.parametrize("path,params,code", [
    ("/stats", {"start": "2026-10-02T00:00:00Z", "end": "2026-10-01T00:00:00Z"}, 400),
    ("/stats/hourly", {"mode": "daily"}, 422),
    ("/stats/hourly", {"tz_offset_minutes": 5000}, 422),
])
def test_stats_validation(client, path, params, code):
    assert client.get(path, params=params).status_code == code
