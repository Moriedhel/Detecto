"""End-to-end detection pipeline: bytes -> validated image -> detections -> history.

Kept separate from the HTTP layer so it can be reused (routes, evaluation
script, future WebSocket stream) and tested directly.
"""

import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone

from backend.config import Settings
from backend.db import DetectionRepository
from backend.face_store import FaceStore
from backend.models.detection import DetectResponse, PersonDetection, Timings, TrackingInfo
from backend.models.record import DetectionRecordCreate, PersonBox
from backend.services.detector import PersonDetector
from backend.services.faces import FaceService, attach_identities
from backend.services.tracking import TrackSession
from backend.utils.preprocessing import decode_image, preprocess, validate_bytes
from backend.utils.visualization import draw_detections, encode_jpeg_base64

logger = logging.getLogger("detecto.pipeline")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def carry_track_identities(session: TrackSession, detections: list[dict]) -> None:
    """Remember who each track is, and keep the name while their face is turned away."""
    for d in detections:
        tid = d.get("track_id")
        if tid is None:
            continue
        identity = d.get("identity")
        if identity and identity.get("name"):
            session.remember_identity(tid, identity)
        elif tid in session.identities:
            d["identity"] = {**session.identities[tid], "from_track": True}


def run_detection(
    data: bytes,
    *,
    content_type: str | None,
    source: str | None,
    settings: Settings,
    detector: PersonDetector,
    repo: DetectionRepository,
    conf: float | None = None,
    enhance: bool | None = None,
    return_image: bool = True,
    img_size: int | None = None,
    save: bool = True,
    face_service: FaceService | None = None,
    face_store: FaceStore | None = None,
    session: TrackSession | None = None,
) -> DetectResponse:
    """Validate, detect, optionally save, and build the API response.

    `save=False` skips the history write (e.g. live webcam frames, which the
    client saves selectively). Passing `face_service` + `face_store` also
    recognises enrolled faces; identities are returned but never stored.
    A tracking `session` gives every person a stable track_id across frames.
    Raises ImageError subclasses for invalid input (mapped to 4xx by main.py).
    """
    t_start = time.perf_counter()

    t = time.perf_counter()
    validate_bytes(data, content_type, settings)
    img = decode_image(data)
    decode_ms = _ms(t)

    t = time.perf_counter()
    pre = preprocess(img, settings, enhance=enhance)
    preprocess_ms = _ms(t)

    conf = settings.conf_threshold if conf is None else conf
    img_size = img_size or settings.img_size
    result = detector.detect(pre, conf=conf, img_size=img_size, tracker=session)
    detections = [asdict(d) for d in result.detections]

    faces, faces_ms = None, 0.0
    if face_service is not None and face_store is not None:
        t = time.perf_counter()
        faces = face_service.identify(img, face_store.gallery())  # original-resolution image
        attach_identities(detections, faces)
        if session is not None:
            carry_track_identities(session, detections)
        faces_ms = _ms(t)

    tracking = None
    if session is not None:
        tracking = TrackingInfo(session_id=session.id, unique_people=session.unique_people,
                                returns=session.returns, active=len(detections), fps=round(session.fps, 1))

    annotated, overlay_ms = None, 0.0
    if return_image:
        t = time.perf_counter()
        annotated = encode_jpeg_base64(draw_detections(img, result.detections))
        overlay_ms = _ms(t)

    width, height = result.image_size
    record_id, timestamp = None, datetime.now(timezone.utc)
    if save:
        record = repo.add(DetectionRecordCreate(
            count=result.count,
            avg_confidence=result.avg_confidence,
            inference_ms=result.inference_ms,
            total_ms=result.total_ms,
            source=source,
            image_width=width,
            image_height=height,
            conf_threshold=conf,
            contrast_enhanced=pre.contrast_enhanced,
            detections=[PersonBox(bbox=d.bbox, confidence=d.confidence, center=d.center)
                        for d in result.detections],
        ))
        record_id, timestamp = record.id, record.timestamp

    total_ms = _ms(t_start)
    logger.info(
        "detect source=%s size=%dx%d imgsz=%d people=%d avg_conf=%s inference=%.1fms "
        "total=%.1fms saved=%s",
        source, width, height, img_size, result.count, result.avg_confidence,
        result.inference_ms, total_ms, save,
    )

    return DetectResponse(
        record_id=record_id,
        saved=save,
        timestamp=timestamp,
        img_size=img_size,
        count=result.count,
        avg_confidence=result.avg_confidence,
        detections=[PersonDetection(**d) for d in detections],
        image_width=width,
        image_height=height,
        conf_threshold=conf,
        contrast_enhanced=pre.contrast_enhanced,
        timings=Timings(
            decode_ms=decode_ms,
            preprocess_ms=preprocess_ms,
            inference_ms=result.inference_ms,
            detect_ms=result.total_ms,
            faces_ms=faces_ms,
            overlay_ms=overlay_ms,
            total_ms=total_ms,
        ),
        faces=faces,
        tracking=tracking,
        annotated_image=annotated,
    )
