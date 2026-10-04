"""End-to-end detection pipeline: bytes -> validated image -> detections -> history.

Kept separate from the HTTP layer so it can be reused (routes, evaluation
script, future WebSocket stream) and tested directly.
"""

import logging
import time
from dataclasses import asdict

from backend.config import Settings
from backend.db import DetectionRepository
from backend.models.detection import DetectResponse, PersonDetection, Timings
from backend.models.record import DetectionRecordCreate, PersonBox
from backend.services.detector import PersonDetector
from backend.utils.preprocessing import decode_image, preprocess, validate_bytes
from backend.utils.visualization import draw_detections, encode_jpeg_base64

logger = logging.getLogger("detecto.pipeline")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


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
) -> DetectResponse:
    """Validate, detect, save and build the API response.

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
    result = detector.detect(pre, conf=conf)

    annotated, overlay_ms = None, 0.0
    if return_image:
        t = time.perf_counter()
        annotated = encode_jpeg_base64(draw_detections(img, result.detections))
        overlay_ms = _ms(t)

    width, height = result.image_size
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

    total_ms = _ms(t_start)
    logger.info(
        "detect source=%s size=%dx%d people=%d avg_conf=%s inference=%.1fms total=%.1fms",
        source, width, height, result.count, result.avg_confidence, result.inference_ms, total_ms,
    )

    return DetectResponse(
        record_id=record.id,
        timestamp=record.timestamp,
        count=result.count,
        avg_confidence=result.avg_confidence,
        detections=[PersonDetection(**asdict(d)) for d in result.detections],
        image_width=width,
        image_height=height,
        conf_threshold=conf,
        contrast_enhanced=pre.contrast_enhanced,
        timings=Timings(
            decode_ms=decode_ms,
            preprocess_ms=preprocess_ms,
            inference_ms=result.inference_ms,
            detect_ms=result.total_ms,
            overlay_ms=overlay_ms,
            total_ms=total_ms,
        ),
        annotated_image=annotated,
    )
