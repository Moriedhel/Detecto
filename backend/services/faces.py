"""Face detection, embedding and matching with OpenCV's YuNet + SFace models.

- YuNet finds faces (box, 5 landmarks, score).
- SFace turns an aligned face crop into a 128-number embedding.
- Two faces belong to the same person when the cosine similarity of their
  embeddings is >= settings.face_match_threshold (OpenCV recommends 0.363).
"""

import logging
import threading
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from backend.config import Settings, get_settings
from backend.face_store import Gallery
from backend.utils.preprocessing import resize_max_side

logger = logging.getLogger("detecto.faces")

ENROLL_MAX_SIDE = 1280  # big phone photos are downscaled before face detection
MIN_ENROLL_FACE_PX = 60  # enrolment faces smaller than this give poor embeddings


class FaceModelsMissing(RuntimeError):
    """Raised when the ONNX model files are not in the weights folder."""


class EnrollError(ValueError):
    """A photo can't be used for enrolment (reason in the message)."""


@dataclass
class Face:
    box: tuple[float, float, float, float]  # x, y, w, h
    score: float
    raw: np.ndarray  # YuNet row (box + landmarks + score), needed for alignment


class FaceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        det_path = settings.weights_dir / settings.face_detector_model
        rec_path = settings.weights_dir / settings.face_recognizer_model
        missing = [p.name for p in (det_path, rec_path) if not p.exists()]
        if missing:
            raise FaceModelsMissing(
                f"Face model file(s) missing in {settings.weights_dir}: {', '.join(missing)}"
            )
        # Silence OpenCV 5's harmless "targets are not supported" warnings
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        self._detector = cv2.FaceDetectorYN.create(
            str(det_path), "", (320, 320), settings.face_det_score, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")
        self._lock = threading.Lock()  # OpenCV nets are not thread-safe
        logger.info("Loaded face models %s, %s", det_path.name, rec_path.name)

    # --- primitives -------------------------------------------------------------

    def detect(self, img: np.ndarray) -> list[Face]:
        h, w = img.shape[:2]
        with self._lock:
            self._detector.setInputSize((w, h))
            _, rows = self._detector.detect(img)
        if rows is None:
            return []
        return [Face(tuple(float(v) for v in r[:4]), float(r[-1]), r) for r in rows]

    def embed(self, img: np.ndarray, face: Face) -> np.ndarray:
        """L2-normalised 128-d embedding, so cosine similarity is a dot product."""
        with self._lock:
            crop = self._recognizer.alignCrop(img, face.raw)
            feat = self._recognizer.feature(crop).reshape(-1).astype(np.float32)
        return feat / (np.linalg.norm(feat) + 1e-12)

    # --- enrolment --------------------------------------------------------------

    def enrollment_embedding(self, img: np.ndarray) -> np.ndarray:
        """Embedding for an enrolment photo, which must show exactly one clear face."""
        img, _ = resize_max_side(img, ENROLL_MAX_SIDE)
        faces = self.detect(img)
        if not faces:
            raise EnrollError("No face found. Use a clear, front-facing photo.")
        if len(faces) > 1:
            raise EnrollError(f"{len(faces)} faces found. Use a photo with only this person.")
        face = faces[0]
        if min(face.box[2], face.box[3]) < MIN_ENROLL_FACE_PX:
            raise EnrollError("Face is too small. Use a closer photo.")
        return self.embed(img, face)

    # --- recognition ------------------------------------------------------------

    def identify(self, img: np.ndarray, gallery: Gallery) -> list[dict]:
        """Detect faces and match each against the enrolled gallery.

        Returns dicts with bbox [x1, y1, x2, y2], score, person_id, name, similarity.
        Unknown faces have person_id/name None (similarity = best score found, or 0).
        """
        results = []
        for face in self.detect(img):
            person_id, name, similarity = None, None, 0.0
            if len(gallery):
                sims = gallery.matrix @ self.embed(img, face)
                best = int(np.argmax(sims))
                similarity = float(sims[best])
                if similarity >= self.settings.face_match_threshold:
                    person_id, name = int(gallery.person_ids[best]), gallery.names[best]
            x, y, w, h = face.box
            results.append({
                "bbox": [round(x, 1), round(y, 1), round(x + w, 1), round(y + h, 1)],
                "score": round(face.score, 3),
                "person_id": person_id,
                "name": name,
                "similarity": round(similarity, 3),
            })
        return results


@lru_cache
def get_face_service() -> FaceService:
    """Shared face service, loaded on first use (raises FaceModelsMissing)."""
    return FaceService(get_settings())


def attach_identities(detections: list[dict], faces: list[dict]) -> None:
    """Give each person box the identity of the recognised face inside it.

    A face belongs to the smallest person box that contains its centre. If two
    faces fall in one box, the more similar known face wins.
    """
    for face in faces:
        cx = (face["bbox"][0] + face["bbox"][2]) / 2
        cy = (face["bbox"][1] + face["bbox"][3]) / 2
        inside = [d for d in detections
                  if d["bbox"][0] <= cx <= d["bbox"][2] and d["bbox"][1] <= cy <= d["bbox"][3]]
        if not inside:
            continue
        owner = min(inside, key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]))
        current = owner.get("identity")
        if current is None or (face["name"] and face["similarity"] > current["similarity"]):
            owner["identity"] = {k: face[k] for k in ("person_id", "name", "similarity")}
