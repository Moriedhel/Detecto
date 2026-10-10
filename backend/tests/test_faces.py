"""Face enrolment and recognition (real YuNet + SFace models, temporary database)."""

import base64
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.db import DetectionRepository, get_repository
from backend.face_store import FaceStore, get_face_store
from backend.main import app
from backend.routes import detect as detect_routes
from backend.services.faces import FaceModelsMissing, attach_identities, get_face_service

COUPLE = Path(__file__).resolve().parents[1] / "samples" / "05_prom_couple.jpg"

pytestmark = pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "weights" / "face_recognition_sface_2021dec.onnx").exists(),
    reason="face models not downloaded (scripts/download_face_models.py)",
)


def _jpeg(img) -> bytes:
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture(scope="module")
def portraits():
    """Single-face crops of the left and right person in the couple photo."""
    img = cv2.imread(str(COUPLE))
    faces = sorted(get_face_service().detect(img), key=lambda f: f.box[0])
    assert len(faces) == 2
    crops = {}
    for label, f in zip(("left", "right"), faces):
        x, y, w, h = f.box
        cx, cy = x + w / 2, y + h / 2
        half = max(w, h) * 1.3  # generous margin, still only one face
        x1, y1 = int(max(0, cx - half)), int(max(0, cy - half))
        x2, y2 = int(min(img.shape[1], cx + half)), int(min(img.shape[0], cy + half))
        crops[label] = _jpeg(img[y1:y2, x1:x2])
    return crops


@pytest.fixture
def store(tmp_path):
    return FaceStore(tmp_path / "faces.db")


@pytest.fixture
def client(store, tmp_path):
    repo = DetectionRepository(tmp_path / "hist.db")
    app.dependency_overrides[get_face_store] = lambda: store
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _enroll(client, name, photos, consent=True):
    files = [("files", (f"photo{i}.jpg", data, "image/jpeg")) for i, data in enumerate(photos)]
    return client.post("/faces/people", data={"name": name, "consent": str(consent).lower()}, files=files)


def _detect_couple(client, **params):
    b64 = base64.b64encode(COUPLE.read_bytes()).decode()
    res = client.post("/detect/base64", json={"image": b64},
                      params={"save": False, "return_image": False, **params})
    assert res.status_code == 200, res.text
    return res.json()


# --- store ----------------------------------------------------------------------

def test_store_people_and_gallery(store):
    alice, created = store.get_or_create_person("Alice")
    assert created
    again, created = store.get_or_create_person("alice")  # names are case-insensitive
    assert not created and again.id == alice.id

    store.add_embeddings(alice.id, [np.ones(128, np.float32), np.zeros(128, np.float32)])
    assert store.list_people()[0].photos == 2
    assert len(store.gallery()) == 2

    assert store.delete_person(alice.id)
    assert store.list_people() == [] and len(store.gallery()) == 0  # cascade + cache cleared
    assert not store.delete_person(alice.id)


def test_attach_identities_picks_smallest_containing_box():
    dets = [{"bbox": [0, 0, 100, 100]}, {"bbox": [40, 0, 90, 60]}]
    faces = [{"bbox": [50, 10, 70, 30], "person_id": 1, "name": "Ana", "similarity": 0.8}]
    attach_identities(dets, faces)
    assert "identity" not in dets[0]
    assert dets[1]["identity"]["name"] == "Ana"


# --- enrolment API --------------------------------------------------------------

def test_enroll_list_and_delete(client, portraits):
    res = _enroll(client, "  Right   Person ", [portraits["right"]])
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["person"]["name"] == "Right Person" and body["person"]["photos"] == 1
    assert body["results"] == [{"file": "photo0.jpg", "ok": True, "reason": None}]

    listing = client.get("/faces/people").json()
    assert listing["available"] is True
    assert listing["threshold"] == pytest.approx(0.363)
    assert [p["name"] for p in listing["people"]] == ["Right Person"]

    pid = body["person"]["id"]
    assert client.delete(f"/faces/people/{pid}").status_code == 204
    assert client.delete(f"/faces/people/{pid}").status_code == 404
    assert client.get("/faces/people").json()["people"] == []


def test_enroll_rejects_bad_photos_but_keeps_good_ones(client, portraits):
    res = _enroll(client, "Left", [portraits["left"], COUPLE.read_bytes(), b"not an image"])
    assert res.status_code == 201
    results = res.json()["results"]
    assert results[0]["ok"] is True
    assert "2 faces found" in results[1]["reason"]
    assert results[2]["ok"] is False
    assert res.json()["person"]["photos"] == 1


def test_enroll_requires_usable_photo_consent_and_name(client, portraits):
    res = _enroll(client, "Nobody", [COUPLE.read_bytes()])
    assert res.status_code == 422 and "No usable photos" in res.json()["detail"]
    assert client.get("/faces/people").json()["people"] == []  # nothing half-created

    assert _enroll(client, "X", [portraits["left"]], consent=False).status_code == 400
    assert _enroll(client, "   ", [portraits["left"]]).status_code == 400


# --- recognition during detection ---------------------------------------------

def test_detect_with_faces_names_the_right_person(client, portraits):
    _enroll(client, "Right Person", [portraits["right"]])
    body = _detect_couple(client, faces=True)

    assert len(body["faces"]) == 2
    named = [f for f in body["faces"] if f["name"]]
    assert [f["name"] for f in named] == ["Right Person"]
    assert named[0]["similarity"] > 0.9

    # the name is attached to the right-hand person box, the other stays unknown
    by_x = sorted(body["detections"], key=lambda d: d["center"][0])
    assert by_x[-1]["identity"]["name"] == "Right Person"
    assert by_x[0]["identity"] is None or by_x[0]["identity"]["name"] is None
    assert body["timings"]["faces_ms"] > 0


def test_detect_without_faces_option_is_unchanged(client, portraits):
    _enroll(client, "Right Person", [portraits["right"]])
    body = _detect_couple(client)
    assert body["faces"] is None
    assert all(d["identity"] is None for d in body["detections"])


def test_unknown_when_nobody_enrolled(client):
    body = _detect_couple(client, faces=True)
    assert len(body["faces"]) == 2
    assert all(f["name"] is None for f in body["faces"])


def test_missing_models_give_503(client, monkeypatch):
    def boom():
        raise FaceModelsMissing("face_recognition_sface_2021dec.onnx")
    monkeypatch.setattr(detect_routes, "get_face_service", boom)
    b64 = base64.b64encode(COUPLE.read_bytes()).decode()
    res = client.post("/detect/base64", json={"image": b64}, params={"faces": True, "save": False})
    assert res.status_code == 503
    assert "unavailable" in res.json()["detail"]
