"""API tests for /detect using the real model and a temporary database."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.db import DetectionRepository, get_repository
from backend.main import app

SAMPLES = Path(__file__).resolve().parent / "fixtures"
BUS = (SAMPLES / "bus.jpg").read_bytes()


@pytest.fixture
def repo(tmp_path):
    return DetectionRepository(tmp_path / "api.db")


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _upload(client, data=BUS, name="bus.jpg", ctype="image/jpeg", **params):
    return client.post("/detect", files={"file": (name, data, ctype)}, params=params)


# --- success paths ----------------------------------------------------------

def test_detect_upload_returns_people_and_saves_record(client, repo):
    res = _upload(client)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["count"] >= 3
    assert len(body["detections"]) == body["count"]
    assert body["annotated_image"].startswith("data:image/jpeg;base64,")
    assert body["timings"]["inference_ms"] > 0
    assert body["image_width"] == 810 and body["image_height"] == 1080

    saved = repo.get(body["record_id"])
    assert saved.count == body["count"]
    assert saved.source == "bus.jpg"


def test_detect_options(client):
    body = _upload(client, conf=0.9, enhance=True, return_image=False).json()
    assert body["annotated_image"] is None
    assert body["conf_threshold"] == 0.9
    assert body["contrast_enhanced"] is True
    assert all(d["confidence"] >= 0.9 for d in body["detections"])


def test_detect_base64_form_field(client):
    b64 = base64.b64encode(BUS).decode()
    res = client.post("/detect", data={"image_base64": b64})
    assert res.status_code == 200
    assert res.json()["count"] >= 3


def test_detect_base64_json(client, repo):
    data_url = "data:image/jpeg;base64," + base64.b64encode(BUS).decode()
    res = client.post("/detect/base64", json={"image": data_url, "source": "webcam"})
    assert res.status_code == 200
    assert repo.get(res.json()["record_id"]).source == "webcam"


def test_default_saves_and_reports_img_size(client, repo):
    body = _upload(client, return_image=False).json()
    assert body["saved"] is True and body["record_id"] is not None
    assert body["img_size"] == 1280


def test_save_false_skips_history(client, repo):
    res = client.post(
        "/detect/base64",
        json={"image": base64.b64encode(BUS).decode(), "source": "webcam"},
        params={"save": False, "return_image": False},
    )
    body = res.json()
    assert res.status_code == 200
    assert body["saved"] is False and body["record_id"] is None
    assert body["count"] >= 3  # detection still runs
    assert body["timestamp"]
    assert repo.list().total == 0


def test_img_size_override(client):
    small = _upload(client, img_size=640, return_image=False, save=False).json()
    assert small["img_size"] == 640
    assert small["count"] >= 3


@pytest.mark.parametrize("size", [100, 650, 4096])
def test_invalid_img_size_is_422(client, size):
    assert _upload(client, img_size=size).status_code == 422


# --- error paths ------------------------------------------------------------

def test_no_image_is_400(client):
    res = client.post("/detect")
    assert res.status_code == 400
    assert "No image provided" in res.json()["detail"]


def test_empty_upload_is_400(client):
    res = _upload(client, data=b"")
    assert res.status_code == 400
    assert res.json()["error"] == "EmptyFileError"


def test_unsupported_type_is_415(client):
    res = _upload(client, data=b"GIF89a....", name="x.gif", ctype="image/gif")
    assert res.status_code == 415


def test_text_file_disguised_as_png_is_415(client):
    res = _upload(client, data=b"just text", name="x.png", ctype="image/png")
    assert res.status_code == 415


def test_corrupt_image_is_400(client):
    res = _upload(client, data=BUS[:200], name="broken.jpg")
    assert res.status_code == 400
    assert res.json()["error"] == "InvalidImageError"


def test_bad_base64_is_400(client):
    res = client.post("/detect/base64", json={"image": "%%%not base64%%%"})
    assert res.status_code == 400


def test_invalid_conf_is_422(client):
    assert _upload(client, conf=1.5).status_code == 422


def test_failed_requests_are_not_saved(client, repo):
    _upload(client, data=b"")
    assert repo.list().total == 0
