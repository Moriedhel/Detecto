"""API tests for /history and /reset (no model inference; records inserted directly)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.db import DetectionRepository, get_repository
from backend.main import app
from backend.models.record import DetectionRecordCreate

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo(tmp_path):
    repo = DetectionRepository(tmp_path / "history.db")
    # 6 records, one per hour: counts 0..5, avg confidence rising 0.5 -> 0.9
    for i in range(6):
        repo.add(DetectionRecordCreate(
            count=i, avg_confidence=round(0.5 + i * 0.08, 2) if i else None,
            inference_ms=50, total_ms=60, source=f"frame{i}.jpg",
            image_width=640, image_height=480, conf_threshold=0.4,
        ), timestamp=T0 + timedelta(hours=i))
    return repo


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_all_newest_first(client):
    body = client.get("/history").json()
    assert body["total"] == 6
    assert [r["count"] for r in body["items"]] == [5, 4, 3, 2, 1, 0]
    assert body["items"][0]["timestamp"].startswith("2026-10-01T14:00")


def test_pagination(client):
    body = client.get("/history", params={"limit": 2, "offset": 2}).json()
    assert body["total"] == 6
    assert [r["count"] for r in body["items"]] == [3, 2]


def test_oldest_first(client):
    body = client.get("/history", params={"newest_first": False, "limit": 1}).json()
    assert body["items"][0]["count"] == 0


def test_time_range_filter(client):
    params = {"start": "2026-10-01T10:00:00Z", "end": "2026-10-01T12:00:00Z"}
    body = client.get("/history", params=params).json()
    assert sorted(r["count"] for r in body["items"]) == [1, 2, 3]


def test_time_range_with_offset_timezone(client):
    # 15:00 Athens (+03:00) == 12:00 UTC
    body = client.get("/history", params={"start": "2026-10-01T15:00:00+03:00"}).json()
    assert sorted(r["count"] for r in body["items"]) == [3, 4, 5]


def test_confidence_and_count_filters(client):
    assert client.get("/history", params={"min_confidence": 0.7}).json()["total"] == 3
    assert client.get("/history", params={"min_count": 4}).json()["total"] == 2


def test_start_after_end_is_400(client):
    res = client.get("/history", params={"start": "2026-10-02T00:00:00Z", "end": "2026-10-01T00:00:00Z"})
    assert res.status_code == 400


@pytest.mark.parametrize("params", [{"min_confidence": 2}, {"limit": 0}, {"start": "yesterday"}])
def test_invalid_params_are_422(client, params):
    assert client.get("/history", params=params).status_code == 422


def test_get_one_and_404(client):
    rec = client.get("/history/3").json()
    assert rec["id"] == 3 and rec["source"] == "frame2.jpg"
    assert client.get("/history/999").status_code == 404


@pytest.mark.parametrize("method", ["DELETE", "POST"])
def test_reset_clears_history(client, method):
    res = client.request(method, "/reset")
    assert res.status_code == 200
    assert res.json() == {"deleted": 6}
    assert client.get("/history").json()["total"] == 0
    assert client.request(method, "/reset").json() == {"deleted": 0}
