"""Re-identification: same person returning keeps their ID; others don't (colour path, no faces)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.config import Settings, get_settings
from backend.models.video import VideoOptions
from backend.services.detector import get_detector
from backend.services.reid import ReIdentifier, color_descriptor, color_similarity
from backend.services.video import analyse_video

BG = (120, 120, 120)


def person_image(boxes_colours, size=(480, 640)):
    """Grey frame with 'people': boxes with a coloured torso (upper half) and legs (lower half)."""
    img = np.full((*size, 3), BG, np.uint8)
    for (x1, y1, x2, y2), (top, bottom) in boxes_colours:
        mid = (y1 + y2) // 2
        img[y1:mid, x1:x2] = top
        img[mid:y2, x1:x2] = bottom
    return img


RED_BLUE = ((40, 40, 220), (200, 60, 30))  # BGR: red top, blue trousers
GREEN_YELLOW = ((60, 200, 60), (40, 220, 230))


def run(reid, frames):
    """frames: list of (t, [(raw_id, box, colours), ...]); returns raw->pid of the last frame."""
    out = {}
    for t, people in frames:
        img = person_image([(b, c) for _, b, c in people])
        out = reid.process([(raw, np.array(b, float)) for raw, b, _ in people], img, t)
    return out


def visible(raw, x, colours, t0, n=8):
    return [(t0 + i * 0.1, [(raw, (x + 5 * i, 100, x + 5 * i + 80, 340), colours)]) for i in range(n)]


def empty(t0, seconds):
    return [(t0 + i * 0.1, []) for i in range(int(seconds * 10))]


@pytest.fixture
def settings():
    return Settings(reid_enabled=True)


def test_descriptor_similarity():
    img = person_image([((100, 100, 180, 340), RED_BLUE), ((300, 100, 380, 340), GREEN_YELLOW)])
    a = color_descriptor(img, (100, 100, 180, 340))
    b = color_descriptor(img, (300, 100, 380, 340))
    assert color_similarity(a, a) == pytest.approx(1.0, abs=1e-6)
    assert color_similarity(a, b) < 0.3
    assert color_descriptor(img, (0, 0, 20, 20)) is None  # too small


def test_same_clothes_returning_gets_old_id(settings):
    reid = ReIdentifier(settings)
    frames = visible(1, 50, RED_BLUE, 0) + empty(0.8, 5) + visible(2, 400, RED_BLUE, 6.0)
    assert run(reid, frames) == {2: 1}  # tracker ID 2 mapped back to person 1
    assert reid.returns == 1
    assert 2 in reid.reidentified_raw
    assert len(reid.people) == 1


def test_new_track_is_pending_while_someone_could_be_returning(settings):
    reid = ReIdentifier(settings)
    run(reid, visible(1, 50, RED_BLUE, 0) + empty(0.8, 5))
    run(reid, visible(2, 400, GREEN_YELLOW, 6.0, n=2))  # 2 frames: not decided yet
    assert reid.pending == {2}
    run(reid, visible(2, 410, GREEN_YELLOW, 6.2, n=3))  # decided as new person
    assert reid.pending == set()


def test_first_person_is_never_pending(settings):
    reid = ReIdentifier(settings)
    run(reid, visible(1, 50, RED_BLUE, 0, n=2))
    assert reid.pending == set()  # nobody has left yet, so nothing to compare with


def test_flicker_never_uses_up_a_number(settings):
    """A 2-frame flicker gets no number, so the first real person is #1 (not #2)."""
    reid = ReIdentifier(settings)
    run(reid, visible(1, 50, GREEN_YELLOW, 0, n=2) + empty(0.2, 1))  # flicker
    keys = run(reid, visible(2, 300, RED_BLUE, 1.5, n=5))
    assert reid.number_of(keys[2]) == 1
    assert len(reid.numbers) == 1


def test_short_tracker_gap_is_repaired_but_not_a_return(settings):
    """The tracker losing someone for a moment gives a new tracker ID; re-ID repairs it
    without reporting a 'return' (the person never left)."""
    reid = ReIdentifier(settings)
    run(reid, visible(1, 50, RED_BLUE, 0) + empty(0.8, 0.5))
    keys = run(reid, visible(2, 120, RED_BLUE, 1.3))
    assert reid.number_of(keys[2]) == 1  # repaired: same person
    assert reid.returns == 0
    assert 2 not in reid.reidentified_raw


def test_returning_person_keeps_number_through_alias(settings):
    reid = ReIdentifier(settings)
    first = run(reid, visible(1, 50, RED_BLUE, 0))
    run(reid, empty(0.8, 5))
    back = run(reid, visible(2, 400, RED_BLUE, 6.0))
    assert reid.number_of(first[1]) == reid.number_of(back[2]) == 1


def test_different_clothes_is_a_new_person(settings):
    reid = ReIdentifier(settings)
    frames = visible(1, 50, RED_BLUE, 0) + empty(0.8, 5) + visible(2, 400, GREEN_YELLOW, 6.0)
    assert run(reid, frames) == {2: 2}
    assert reid.returns == 0


def test_lookalikes_are_not_merged(settings):
    """Two people dressed alike were seen together, then left: a returning look-alike is
    ambiguous (could be either), so it becomes a new person rather than a guess."""
    reid = ReIdentifier(settings)
    together = [(i * 0.1, [(1, (50, 100, 130, 340), RED_BLUE), (2, (400, 100, 480, 340), RED_BLUE)])
                for i in range(8)]
    frames = together + empty(0.8, 5) + visible(3, 250, RED_BLUE, 6.0)
    assert run(reid, frames)[3] == 3
    assert reid.returns == 0


def test_known_limitation_lookalikes_one_after_another(settings):
    """Documented limit: with colours only (no face), someone dressed exactly like a person
    who just left is indistinguishable from that person returning, so they are merged."""
    reid = ReIdentifier(settings)
    frames = visible(1, 50, RED_BLUE, 0) + empty(0.8, 5) + visible(2, 400, RED_BLUE, 6.0)
    assert run(reid, frames)[2] == 1


def test_people_visible_at_the_same_time_are_never_merged(settings):
    reid = ReIdentifier(settings)
    frames = [(i * 0.1, [(1, (50, 100, 130, 340), RED_BLUE), (2, (400, 100, 480, 340), RED_BLUE)]) for i in range(10)]
    assert run(reid, frames) == {1: 1, 2: 2}


def test_outside_window_or_disabled_is_a_new_person():
    frames = visible(1, 50, RED_BLUE, 0) + visible(2, 400, RED_BLUE, 400.0)  # returns after 400 s
    assert run(ReIdentifier(Settings(reid_window_s=300)), frames)[2] == 2

    frames = visible(1, 50, RED_BLUE, 0) + empty(0.8, 5) + visible(2, 400, RED_BLUE, 6.0)
    assert run(ReIdentifier(Settings(reid_enabled=False)), frames)[2] == 2


# --- end to end on video (real detector + face model if available) --------------------

S = Path(__file__).resolve().parents[1] / "samples"


def _leave_and_return_clip(path: Path, returning_crop: np.ndarray) -> Path:
    W, H = 640, 480
    room = cv2.resize(cv2.imread(str(S / "01_bedroom_empty.jpg")), (W, H))
    couple = cv2.imread(str(S / "05_prom_couple.jpg"))
    walker = cv2.resize(couple[40:640, 120:330], (130, 370))

    def walk(sprite, reverse=False):
        frames = []
        for i in range(30):
            f = room.copy()
            k = 29 - i if reverse else i
            x = int(-130 + k * (W + 130) / 29)
            x1, x2 = max(0, x), min(W, x + 130)
            if x2 > x1:
                f[H - 380:H - 10, x1:x2] = sprite[:, x1 - x:x2 - x]
            frames.append(f)
        return frames

    sprite = walker if returning_crop is None else returning_crop
    frames = walk(walker) + [room.copy()] * 40 + walk(cv2.flip(sprite, 1), reverse=True)
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (W, H))
    for f in frames:
        w.write(f)
    w.release()
    return path


@pytest.mark.parametrize("same,unique,returns", [(True, 1, 1), (False, 2, 0)])
def test_video_leave_and_return(tmp_path, same, unique, returns):
    couple = cv2.imread(str(S / "05_prom_couple.jpg"))
    other = cv2.resize(couple[20:640, 430:640], (130, 370))
    clip = _leave_and_return_clip(tmp_path / "walk.mp4", None if same else other)
    r = analyse_video(clip, VideoOptions(conf=0.4, img_size=640, sample_fps=10, enhance=False),
                      get_settings(), get_detector())
    assert r.summary.unique_people == unique  # gone 4 s: longer than the tracker's 3 s memory
    assert r.summary.returns == returns
