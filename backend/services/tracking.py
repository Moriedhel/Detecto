"""Multi-person tracking with ByteTrack (Ultralytics), one tracker per session.

A *session* is one continuous stream: a live webcam run (session id sent by the
browser) or one uploaded video. Each session has its own tracker so IDs never
mix between streams.

Two details matter:
- Ultralytics' track IDs come from ONE class-level counter shared by every
  tracker, and creating a tracker resets it. With several sessions that would
  hand out duplicate IDs, so each session gets its own track class with its own
  counter.
- How long a lost person keeps their ID is configured in seconds
  (`track_memory_s`) and converted to frames from the session's frame rate.

Privacy: sessions live in memory only; nothing about a track is persisted.
"""

import logging
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from ultralytics.trackers.byte_tracker import BYTETracker, STrack
from ultralytics.utils import IterableSimpleNamespace

from backend.config import Settings, get_settings
from backend.services.reid import ReIdentifier

logger = logging.getLogger("detecto.tracking")

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEFAULT_FPS = 10.0


def _session_track_class() -> type[STrack]:
    """A track class with a private ID counter (Ultralytics' counter is global)."""

    class SessionTrack(STrack):
        _session_count = 0

        @classmethod
        def next_id(cls) -> int:  # called as self.next_id() when a track starts
            cls._session_count += 1
            return cls._session_count

    return SessionTrack


@dataclass
class TrackedBox:
    xyxy: np.ndarray  # in the coordinates of the frame given to update()
    score: float
    track_id: int | None  # visible person number (#1, #2...); None until it counts as a person
    tracked_s: float  # seconds since this person was first seen
    reidentified: bool = False  # this person left earlier and was recognised on return
    pending: bool = False  # no number yet (just appeared, or being compared with people who left)
    person_key: int = 0  # internal re-ID key; videos remap it to the final number afterwards


def optional_face_service():
    """Face model for re-identification if available (colours are used otherwise)."""
    try:
        from backend.services.faces import FaceModelsMissing, get_face_service
        try:
            return get_face_service()
        except FaceModelsMissing:
            return None
    except Exception:  # never let an optional helper break tracking
        logger.exception("Face service unavailable for re-identification")
        return None


class TrackSession:
    def __init__(self, session_id: str, settings: Settings, fps: float | None = None, face_service=None):
        self.id = session_id
        self.settings = settings
        self.fixed_fps = fps  # known for videos; estimated from timestamps for live streams
        self.reid = ReIdentifier(settings, face_service)
        self.args = IterableSimpleNamespace(
            tracker_type="bytetrack",
            track_high_thresh=settings.conf_threshold,
            track_low_thresh=settings.track_low_conf,
            new_track_thresh=settings.conf_threshold,
            track_buffer=30,
            match_thresh=0.8,
            fuse_score=True,
        )
        self.tracker = BYTETracker(self.args)
        self.tracker.track_class = _session_track_class()
        self.lock = threading.Lock()
        self.best_score: dict[int, float] = {}  # person ID -> best detection confidence
        self.identities: dict[int, dict] = {}  # person ID -> best face identity seen
        self.frames = 0
        self.last_used = time.monotonic()
        self._last_t: float | None = None
        self._interval: float | None = None

    @property
    def fps(self) -> float:
        if self.fixed_fps:
            return self.fixed_fps
        return 1.0 / self._interval if self._interval else DEFAULT_FPS

    @property
    def unique_people(self) -> int:
        """Different people seen (returns counted once; flicker never gets a number)."""
        return len(self.reid.numbers)

    @property
    def returns(self) -> int:
        """How many times someone came back and was recognised."""
        return self.reid.returns

    def people(self) -> list[dict]:
        """Per-person summary (only those that count as people), ordered by first appearance."""
        return [
            {"track_id": self.reid.numbers[p.pid], "first_t": round(p.first_t, 2), "last_t": round(p.last_t, 2),
             "duration_s": round(p.last_t - p.first_t, 2), "frames": p.frames,
             "best_confidence": round(self.best_score.get(p.pid, 0.0), 3), "returns": p.returns}
            for p in sorted(self.reid.people.values(), key=lambda p: self.reid.numbers.get(p.pid, 0))
            if p.pid in self.reid.numbers
        ]

    def update(self, boxes, conf: float, t: float, image: np.ndarray | None = None) -> list[TrackedBox]:
        """Feed one frame's detections (Ultralytics Boxes, numpy) taken at time `t` (seconds).

        `image` is the frame the boxes refer to; it enables appearance-based
        re-identification (without it, people who leave and return get new IDs).
        """
        with self.lock:
            # Thresholds follow the user's confidence setting; weaker boxes may still
            # continue an existing track (ByteTrack's second association stage).
            self.args.track_high_thresh = conf
            self.args.new_track_thresh = conf
            if self._last_t is not None and t > self._last_t:
                dt = t - self._last_t
                self._interval = dt if self._interval is None else 0.8 * self._interval + 0.2 * dt
            self._last_t = t
            self.tracker.max_frames_lost = max(3, round(self.settings.track_memory_s * self.fps))

            rows = self.tracker.update(boxes)  # [x1, y1, x2, y2, track_id, score, cls, idx]
            self.frames += 1
            self.last_used = time.monotonic()

            pids = self.reid.process([(int(r[4]), r[:4]) for r in rows], image, t)
            out = []
            for r in rows:
                raw = int(r[4])
                pid = pids[raw]
                number = self.reid.number_of(pid)
                self.best_score[pid] = max(self.best_score.get(pid, 0.0), float(r[5]))
                out.append(TrackedBox(
                    xyxy=r[:4].copy(), score=float(r[5]), track_id=number,
                    tracked_s=round(t - self.reid.people[pid].first_t, 1),
                    reidentified=raw in self.reid.reidentified_raw,
                    pending=number is None,
                    person_key=pid,
                ))
            return out

    def remember_identity(self, track_id: int, identity: dict) -> None:
        """Keep the best face match per track, so the name stays while the face is turned away."""
        best = self.identities.get(track_id)
        if best is None or identity["similarity"] > best["similarity"]:
            self.identities[track_id] = dict(identity)


class TrackingSessions:
    """Live tracking sessions, created on first use and dropped when idle."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._sessions: OrderedDict[str, TrackSession] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, session_id: str) -> TrackSession:
        if not SESSION_ID_RE.match(session_id):
            raise ValueError("Invalid session id (8-64 letters, digits, '-' or '_').")
        with self._lock:
            self._expire()
            session = self._sessions.get(session_id)
            if session is None:
                while len(self._sessions) >= self.settings.track_max_sessions:
                    old_id, _ = self._sessions.popitem(last=False)  # least recently used
                    logger.info("Dropped tracking session %s (limit reached)", old_id)
                session = TrackSession(session_id, self.settings, face_service=optional_face_service())
                self._sessions[session_id] = session
                logger.info("Started tracking session %s", session_id)
            self._sessions.move_to_end(session_id)
            return session

    def end(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:
        return len(self._sessions)

    def _expire(self) -> None:
        now = time.monotonic()
        for sid in [s for s, sess in self._sessions.items()
                    if now - sess.last_used > self.settings.track_session_ttl_s]:
            del self._sessions[sid]
            logger.info("Expired tracking session %s", sid)


@lru_cache
def get_tracking_sessions() -> TrackingSessions:
    return TrackingSessions(get_settings())
