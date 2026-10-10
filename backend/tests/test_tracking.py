"""Tracking sessions: stable IDs, per-session counters, memory, expiry, API."""

import base64
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from ultralytics.engine.results import Boxes

from backend.config import Settings
from backend.db import DetectionRepository, get_repository
from backend.main import app
from backend.services.pipeline import carry_track_identities
from backend.services.tracking import TrackingSessions, TrackSession

FRISBEE = Path(__file__).resolve().parents[1] / "samples" / "12_frisbee_team.jpg"


def boxes(*rows):
    """Ultralytics Boxes from (x1, y1, x2, y2, conf) rows, class person."""
    data = np.array([[*r, 0] for r in rows], dtype=np.float32).reshape(-1, 6)
    return Boxes(data, orig_shape=(480, 640))


@pytest.fixture
def settings():
    return Settings(track_memory_s=1.0, conf_threshold=0.4)


# --- TrackSession -----------------------------------------------------------------

def test_ids_stay_stable_while_a_person_moves(settings):
    s = TrackSession("unit-session", settings, fps=10)
    ids = []
    for i in range(6):
        out = s.update(boxes((100 + 5 * i, 100, 150 + 5 * i, 250, 0.9)), conf=0.4, t=i / 10)
        ids.append([tb.track_id for tb in out])
    assert ids[:2] == [[None], [None]]  # no number until seen for 3 frames (flicker guard)
    assert all(frame == [1] for frame in ids[2:])
    assert s.unique_people == 1
    assert s.people()[0]["duration_s"] == pytest.approx(0.5)


def test_short_gap_keeps_id_long_gap_gives_new_id(settings):
    s = TrackSession("gap-session", settings, fps=10)  # memory 1 s = 10 frames
    box = (100, 100, 150, 250, 0.9)
    for i in range(3):
        s.update(boxes(box), 0.4, i / 10)
    for i in range(3, 8):  # 0.5 s without the person
        s.update(boxes(), 0.4, i / 10)
    assert [tb.track_id for tb in s.update(boxes(box), 0.4, 0.8)] == [1]  # same ID back

    for i in range(9, 30):  # 2 s gap > 1 s memory
        s.update(boxes(), 0.4, i / 10)
    new = [tb.track_id for tb in s.update(boxes(box), 0.4, 3.0)]
    assert new != [1]


def test_flicker_does_not_count_as_a_person(settings):
    s = TrackSession("flicker-sess", settings, fps=10)
    s.update(boxes((100, 100, 150, 250, 0.9)), 0.4, 0.0)
    s.update(boxes((100, 100, 150, 250, 0.9)), 0.4, 0.1)
    s.update(boxes(), 0.4, 0.2)
    assert s.unique_people == 0  # seen in only 2 frames


def test_sessions_have_independent_id_counters(settings):
    a = TrackSession("session-a1", settings, fps=10)
    for i in range(3):
        a.update(boxes((10, 10, 60, 200, 0.9), (300, 10, 350, 200, 0.9)), 0.4, i / 10)
    TrackSession("session-b1", settings, fps=10)  # resets Ultralytics' global counter
    out = a.update(boxes((10, 10, 60, 200, 0.9), (300, 10, 350, 200, 0.9), (500, 10, 550, 200, 0.9)), 0.4, 0.3)
    ids = [tb.track_id for tb in out]
    assert len(set(ids)) == len(ids)  # no duplicates after another session started
    assert {1, 2} <= set(ids)


def test_identity_is_carried_by_the_track(settings):
    s = TrackSession("faces-sess", settings, fps=10)
    dets = [{"track_id": 4, "identity": {"person_id": 1, "name": "Ana", "similarity": 0.8}}]
    carry_track_identities(s, dets)
    later = [{"track_id": 4, "identity": None}]  # face turned away
    carry_track_identities(s, later)
    assert later[0]["identity"]["name"] == "Ana"
    assert later[0]["identity"]["from_track"] is True


# --- session manager --------------------------------------------------------------

def test_session_manager_validates_expires_and_limits():
    mgr = TrackingSessions(Settings(track_session_ttl_s=0.05, track_max_sessions=2))
    with pytest.raises(ValueError):
        mgr.get("bad id!")
    a = mgr.get("session-one")
    assert mgr.get("session-one") is a
    mgr.get("session-two")
    mgr.get("session-three")  # over the limit: least recently used is dropped
    assert len(mgr) == 2
    time.sleep(0.1)
    mgr.get("session-four")  # expiry runs on access
    assert len(mgr) == 1
    assert mgr.end("session-four") and not mgr.end("session-four")


# --- API ----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_repository] = lambda: DetectionRepository(tmp_path / "h.db")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _frame(shift=0):
    img = np.roll(cv2.imread(str(FRISBEE)), shift, axis=1)
    return base64.b64encode(cv2.imencode(".jpg", img)[1]).decode()


def test_detect_with_session_returns_stable_track_ids(client):
    params = {"session": "api-test-session", "save": False, "return_image": False, "img_size": 640}
    frames = [client.post("/detect/base64", json={"image": _frame(3 * i)}, params=params).json()
              for i in range(5)]

    first = frames[0]["detections"]
    assert first and all(d["track_id"] is None and d["pending"] for d in first)  # numbers from frame 3

    ids3 = [d["track_id"] for d in frames[3]["detections"]]
    ids4 = [d["track_id"] for d in frames[4]["detections"]]
    assert ids3 and None not in ids3
    assert set(ids4) <= set(ids3) and len(ids4) >= len(ids3) - 1  # same people keep their numbers
    assert frames[4]["tracking"]["session_id"] == "api-test-session"
    assert frames[4]["tracking"]["unique_people"] == len(set(ids3))

    assert client.delete("/detect/sessions/api-test-session").status_code == 204
    assert client.delete("/detect/sessions/api-test-session").status_code == 404


def test_detect_without_session_has_no_tracking(client):
    body = client.post("/detect/base64", json={"image": _frame()},
                       params={"save": False, "return_image": False}).json()
    assert body["tracking"] is None
    assert all(d["track_id"] is None for d in body["detections"])


def test_invalid_session_id_is_422(client):
    res = client.post("/detect/base64", json={"image": _frame()}, params={"session": "x y"})
    assert res.status_code == 422
