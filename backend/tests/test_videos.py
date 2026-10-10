"""Video analysis: job lifecycle, tracking results, validation (real model, generated clips)."""

import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from backend.models.video import VideoOptions
from backend.services.detector import get_detector
from backend.services.video import JobCancelled, analyse_video

FRISBEE = Path(__file__).resolve().parents[1] / "samples" / "12_frisbee_team.jpg"


def make_clip(path: Path, seconds=2.0, fps=10, shift_px=3) -> Path:
    """A short MP4 of the frisbee photo panning slowly, so 4-5 people move a little."""
    img = cv2.resize(cv2.imread(str(FRISBEE)), (640, 428))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 428))
    for i in range(int(seconds * fps)):
        writer.write(np.roll(img, shift_px * i, axis=1))
    writer.release()
    return path


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return make_clip(tmp_path_factory.mktemp("vid") / "clip.mp4")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def wait_for(client, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/videos/{job_id}").json()
        if job["status"] in ("done", "error", "cancelled"):
            return job
        time.sleep(0.2)
    raise AssertionError("video job did not finish in time")


def _upload(client, path: Path, name="clip.mp4", ctype="video/mp4", **params):
    with open(path, "rb") as f:
        return client.post("/videos", files={"file": (name, f, ctype)}, params=params)


# --- full job through the API ---------------------------------------------------

def test_video_job_tracks_people(client, clip):
    res = _upload(client, clip, sample_fps=10)
    assert res.status_code == 202, res.text
    job = res.json()
    assert job["status"] in ("queued", "processing") and job["result"] is None

    done = wait_for(client, job["id"])
    assert done["status"] == "done", done["error"]
    r = done["result"]
    assert r["video"]["fps"] == pytest.approx(10, abs=0.1)
    assert r["video"]["duration_s"] == pytest.approx(2.0, abs=0.15)
    assert r["summary"]["frames_analysed"] == 20
    assert 3 <= r["summary"]["unique_people"] <= 6
    assert r["summary"]["peak_people"] >= 3

    # tracks are stable: the same IDs recur through the clip
    ids_first = {b[0] for b in r["frames"][2]["boxes"]}
    ids_last = {b[0] for b in r["frames"][-1]["boxes"]}
    assert len(ids_first & ids_last) >= 3
    assert all(p["duration_s"] >= 0 for p in r["people"])
    assert r["frames"][1]["t"] == pytest.approx(0.1, abs=1e-3)

    assert not list(get_settings().db_path.parent.joinpath("videos").glob("*.mp4"))  # upload deleted
    assert client.delete(f"/videos/{job['id']}").status_code == 204  # forget finished job
    assert client.get(f"/videos/{job['id']}").status_code == 404


def test_sample_fps_subsamples_frames(client, clip):
    done = wait_for(client, _upload(client, clip, sample_fps=5).json()["id"])
    assert done["result"]["summary"]["frames_analysed"] == 10
    assert done["result"]["video"]["analysed_fps"] == pytest.approx(5)


def test_corrupt_video_reports_error(client, tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"garbage" * 200)
    done = wait_for(client, _upload(client, bad).json()["id"])
    assert done["status"] == "error"
    assert done["error"]


# --- validation -------------------------------------------------------------------

def test_rejects_non_video_files(client, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    assert _upload(client, txt, name="notes.txt", ctype="text/plain").status_code == 415


def test_rejects_empty_and_oversized(client, tmp_path, clip):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert _upload(client, empty).status_code == 400

    big = tmp_path / "big.mp4"
    big.write_bytes(b"\x00" * (2 * 1024 * 1024))
    app.dependency_overrides[get_settings] = lambda: Settings(max_video_mb=1)
    assert _upload(client, big).status_code == 413
    assert not list(get_settings().db_path.parent.joinpath("videos").glob("*.mp4"))  # partial file removed


def test_invalid_options_are_422(client, clip):
    assert _upload(client, clip, sample_fps=100).status_code == 422
    assert _upload(client, clip, img_size=650).status_code == 422


def test_unknown_job_is_404(client):
    assert client.get("/videos/does-not-exist").status_code == 404


# --- analyse_video directly ---------------------------------------------------------

def test_too_long_and_cancel(clip):
    opts = VideoOptions(conf=0.4, img_size=640, sample_fps=10, enhance=False)
    with pytest.raises(ValueError, match="limit"):
        analyse_video(clip, opts, Settings(max_video_seconds=1), get_detector())
    with pytest.raises(JobCancelled):
        analyse_video(clip, opts, get_settings(), get_detector(), should_stop=lambda: True)
