"""Re-identification: recognise a person who leaves the view and comes back.

ByteTrack links boxes by position/motion only, so someone who walks out and back
in gets a new tracker ID. This layer sits on top of the tracker and maps tracker
IDs to *person* IDs:

1. While a person is visible, build an appearance description from clean views
   (not overlapping anyone): clothing colours of torso and legs, plus a face
   embedding when a face is visible and the face model is available.
2. When a new track has been seen for a few frames, compare it with people who
   left recently. A confident match gives the old person ID back (counted once).

Decision rules are deliberately conservative (wrongly merging two people is
worse than counting one person twice):
- both faces known  -> face similarity decides alone
- otherwise colours -> must reach `reid_color_threshold` AND beat the runner-up
                       by `reid_color_margin`

Privacy: descriptors live in memory for one session only and are never stored.
"""

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from backend.config import Settings

logger = logging.getLogger("detecto.reid")

COUNT_AFTER = 3  # frames before a track counts as a person (shorter = flicker, never numbered)
DECIDE_AFTER = 4  # frames of a new track before trying to match it
DECIDE_UNTIL = 40  # after this many frames without a match the person counts as new
CLEARLY_DIFFERENT = 0.15  # colour similarity this far below the threshold -> decide "new" at once
FACE_WAIT = 12  # frames to wait for a face before deciding "new" on colours alone
RETURN_MIN_GAP_S = 1.5  # shorter gaps are tracker hiccups (repaired, not counted as a return)
FACE_EVERY = 3  # try to get a face embedding every N frames while missing
MIN_BOX_H = 60  # boxes smaller than this give unreliable colours
MIN_FACE_PX = 36


# --- appearance descriptors ---------------------------------------------------------

def _part_hist(patch: np.ndarray) -> np.ndarray:
    """Hue/saturation histogram of coloured pixels + 3 brightness bins for neutral pixels."""
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1], hsv[..., 2]
    chroma = (s >= 40) & (v >= 40)
    hs = cv2.calcHist([hsv], [0, 1], chroma.astype(np.uint8), [16, 4], [0, 180, 40, 256]).ravel()
    neutral = np.histogram(v[~chroma], bins=3, range=(0, 256))[0].astype(np.float32)
    d = np.concatenate([hs, neutral])
    return d / (d.sum() + 1e-9)


def color_descriptor(img: np.ndarray, box) -> np.ndarray | None:
    """Torso + legs colour histograms (central 60% width, to skip background), or None if too small."""
    h_img, w_img = img.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w_img, x2), min(h_img, y2)
    w, h = x2 - x1, y2 - y1
    if h < MIN_BOX_H or w < 16:
        return None
    cx1, cx2 = x1 + int(0.2 * w), x2 - int(0.2 * w)
    torso = img[y1 + int(0.2 * h):y1 + int(0.55 * h), cx1:cx2]
    legs = img[y1 + int(0.55 * h):y1 + int(0.9 * h), cx1:cx2]
    if torso.size == 0 or legs.size == 0:
        return None
    return np.stack([_part_hist(torso), _part_hist(legs)])


def color_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Mean Bhattacharyya coefficient of the parts (1 = identical colour distribution)."""
    return float(np.mean(np.sum(np.sqrt(a * b), axis=1)))


def face_descriptor(face_service, img: np.ndarray, box) -> tuple[np.ndarray, float] | None:
    """Face embedding from the head region of a person box: (embedding, face size) or None."""
    h_img, w_img = img.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    head = img[max(0, y1):min(h_img, y1 + int(0.45 * (y2 - y1))), max(0, x1):min(w_img, x2)]
    if head.shape[0] < MIN_FACE_PX or head.shape[1] < MIN_FACE_PX:
        return None
    faces = [f for f in face_service.detect(head) if min(f.box[2], f.box[3]) >= MIN_FACE_PX]
    if not faces:
        return None
    face = max(faces, key=lambda f: f.box[2] * f.box[3])
    return face_service.embed(head, face), min(face.box[2], face.box[3])


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


# --- per-person state -----------------------------------------------------------------

@dataclass
class Person:
    pid: int
    first_t: float
    last_t: float
    frames: int = 0
    color: np.ndarray | None = None  # running average of clean views
    color_n: int = 0
    face: np.ndarray | None = None
    face_size: float = 0.0
    returns: int = 0  # times this person came back (re-identified)
    decided: bool = False  # True once confirmed as new or matched
    raw_ids: set = field(default_factory=set)

    def add_color(self, desc: np.ndarray) -> None:
        self.color_n += 1
        self.color = desc if self.color is None else self.color + (desc - self.color) / min(self.color_n, 20)

    def absorb(self, other: "Person") -> None:
        """Merge a provisional person (the returning track) into this one."""
        self.frames += other.frames
        self.last_t = max(self.last_t, other.last_t)
        self.raw_ids |= other.raw_ids
        if other.color is not None:
            for _ in range(min(other.color_n, 5)):
                self.add_color(other.color)
        if other.face is not None and other.face_size > self.face_size:
            self.face, self.face_size = other.face, other.face_size


class ReIdentifier:
    """Maps tracker IDs to person IDs for one session."""

    def __init__(self, settings: Settings, face_service=None):
        self.settings = settings
        self.face_service = face_service
        self.people: dict[int, Person] = {}
        self.raw_to_pid: dict[int, int] = {}
        self.reidentified_raw: set[int] = set()  # tracker IDs that were matched back
        self.pending: set[int] = set()  # person keys still being compared with people who left
        self.numbers: dict[int, int] = {}  # person key -> visible number (#1, #2, ...)
        self.alias: dict[int, int] = {}  # merged person key -> the key it was merged into
        self._next_pid = 1  # internal keys (never reused)
        self._next_number = 1
        self.returns = 0

    def process(self, rows: list[tuple[int, np.ndarray]], img: np.ndarray | None, t: float) -> dict[int, int]:
        """Update with this frame's (tracker_id, xyxy) rows; returns tracker_id -> person key."""
        active = self._observe_frame(rows, img, t)
        self._decide(rows, active, t)
        self._assign_numbers(rows)
        return {raw: self.raw_to_pid[raw] for raw, _ in rows}

    def _observe_frame(self, rows, img, t) -> set[int]:
        """Create/update people for this frame's tracks; returns the active person keys."""
        active = set()
        for raw, box in rows:
            pid = self.raw_to_pid.get(raw)
            if pid is None:
                pid = self._new_person(raw, t)
            person = self.people[pid]
            person.frames += 1
            person.last_t = t
            active.add(pid)
            if img is not None:
                self._observe(person, img, box, [b for r, b in rows if r != raw])
        return active

    def _decide(self, rows, active: set[int], t: float) -> None:
        """Match new tracks against people who left; mark the ones still undecided as pending."""
        self.pending.clear()
        for raw, _ in rows:
            person = self.people[self.raw_to_pid[raw]]
            if person.decided:
                continue
            if not self.settings.reid_enabled:
                person.decided = True
            elif person.frames >= DECIDE_AFTER:
                self._try_match(person, active, t)
            # Still undecided while someone who left could be returning: its ID may change,
            # so the UI shows it as pending ("#?") instead of a number that then jumps
            person = self.people[self.raw_to_pid[raw]]
            if not person.decided and self._candidates(person, active, t):
                self.pending.add(person.pid)

    def _assign_numbers(self, rows) -> None:
        """Visible numbers only for real people (COUNT_AFTER frames, not pending), so flicker
        never uses up a number and the first real person is #1."""
        for raw, _ in rows:
            pid = self.raw_to_pid[raw]
            if pid not in self.numbers and pid not in self.pending and self.people[pid].frames >= COUNT_AFTER:
                self.numbers[pid] = self._next_number
                self._next_number += 1

    def number_of(self, pid: int) -> int | None:
        """Visible number for a person key (following merges), or None if not (yet) a person."""
        while pid in self.alias:
            pid = self.alias[pid]
        return self.numbers.get(pid)

    def _candidates(self, person: Person, active: set[int], t: float) -> list[Person]:
        """People who left recently and could be this person coming back."""
        return [
            p for p in self.people.values()
            if p.pid not in active and p.decided and p.pid != person.pid
            and t - p.last_t <= self.settings.reid_window_s
        ]

    # --- internals -----------------------------------------------------------------------

    def _new_person(self, raw: int, t: float) -> int:
        pid = self._next_pid
        self._next_pid += 1
        self.people[pid] = Person(pid=pid, first_t=t, last_t=t, raw_ids={raw})
        self.raw_to_pid[raw] = pid
        return pid

    def _observe(self, person: Person, img: np.ndarray, box, others) -> None:
        if any(_iou(box, o) > 0.05 for o in others):
            return  # overlapping someone: colours would mix
        desc = color_descriptor(img, box)
        if desc is not None:
            person.add_color(desc)
        if self.face_service is not None and person.face is None and person.frames % FACE_EVERY == 1:
            found = face_descriptor(self.face_service, img, box)
            if found:
                person.face, person.face_size = found

    def _try_match(self, person: Person, active: set[int], t: float) -> None:
        candidates = self._candidates(person, active, t)
        verdict, match = self._judge(person, candidates)
        if verdict == "match":
            self._merge(person, match)
        elif verdict == "new" or person.frames >= DECIDE_UNTIL:
            person.decided = True  # a genuinely new person
        # "unsure": keep comparing on the next frames

    def _judge(self, person: Person, candidates: list[Person]) -> tuple[str, Person | None]:
        """Compare a new track with people who left: ("match", p) | ("new", None) | ("unsure", None)."""
        if not candidates:
            return "new", None
        face_match = self._face_match(person, candidates)  # faces decide on their own
        if face_match is not None:
            return "match", face_match
        return self._judge_colours(person, candidates)

    def _face_match(self, person: Person, candidates: list[Person]) -> Person | None:
        if person.face is None:
            return None
        with_face = [(float(person.face @ c.face), c) for c in candidates if c.face is not None]
        if not with_face:
            return None
        score, best = max(with_face, key=lambda x: x[0])
        if score < self.settings.reid_face_threshold:
            return None
        logger.info("Re-identified person %d by face (%.2f)", best.pid, score)
        return best

    def _judge_colours(self, person: Person, candidates: list[Person]) -> tuple[str, Person | None]:
        """Clothing colours, only against people whose faces don't contradict."""
        s = self.settings
        if person.color is None:
            return "unsure", None
        scored = sorted(
            ((color_similarity(person.color, c.color), c) for c in candidates
             if c.color is not None and not self._faces_differ(person, c)),
            key=lambda x: x[0], reverse=True,
        )
        if scored and scored[0][0] >= s.reid_color_threshold:
            if len(scored) > 1 and scored[0][0] - scored[1][0] < s.reid_color_margin:
                return "unsure", None  # ambiguous: two people who left look alike
            logger.info("Re-identified person %d by clothing colours (%.2f)", scored[0][1].pid, scored[0][0])
            return "match", scored[0][1]

        clearly_different = not scored or scored[0][0] < s.reid_color_threshold - CLEARLY_DIFFERENT
        if clearly_different:
            # A face could still reveal the same person in different clothes: wait briefly for one
            waiting_for_face = (self.face_service is not None and person.face is None
                                and person.frames < FACE_WAIT
                                and any(c.face is not None for c in candidates))
            return ("unsure", None) if waiting_for_face else ("new", None)
        return "unsure", None

    def _faces_differ(self, a: Person, b: Person) -> bool:
        return (a.face is not None and b.face is not None
                and float(a.face @ b.face) < self.settings.reid_face_threshold)

    def _merge(self, provisional: Person, target: Person) -> None:
        # A short gap is the tracker briefly losing someone (repaired silently);
        # only a real absence counts as "came back"
        is_return = provisional.first_t - target.last_t >= RETURN_MIN_GAP_S
        target.absorb(provisional)
        if is_return:
            target.returns += 1
            self.returns += 1
        for r in provisional.raw_ids:
            self.raw_to_pid[r] = target.pid
            if is_return:
                self.reidentified_raw.add(r)
        del self.people[provisional.pid]
        self.alias[provisional.pid] = target.pid  # keys are never reused, so aliases stay valid
        number = self.numbers.pop(provisional.pid, None)
        if number is not None and number == self._next_number - 1:
            self._next_number -= 1  # keep visible numbering contiguous
