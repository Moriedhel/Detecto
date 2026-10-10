"""Person detector built on a pretrained COCO YOLO model (Ultralytics).

The model is loaded once (see get_detector) and shared across requests.
Only COCO class 0 ("person") is kept.
"""

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import numpy as np
import torch
from ultralytics import YOLO

from backend.config import Settings, get_settings
from backend.services.tracking import TrackSession
from backend.utils.preprocessing import PreprocessResult

logger = logging.getLogger("detecto.detector")

PERSON_CLASS_ID = 0  # "person" in COCO


@dataclass
class Detection:
    """One detected person, in ORIGINAL image pixel coordinates."""
    bbox: list[float]  # [x1, y1, x2, y2]
    confidence: float
    center: list[float]  # [cx, cy]
    width: float
    height: float
    track_id: int | None = None  # set when tracking (stable across frames of a session)
    tracked_s: float | None = None  # seconds this track has been seen

    @classmethod
    def from_xyxy(cls, x1, y1, x2, y2, confidence, **extra) -> "Detection":
        return cls(
            bbox=[round(float(v), 1) for v in (x1, y1, x2, y2)],
            confidence=round(float(confidence), 4),
            center=[round(float((x1 + x2) / 2), 1), round(float((y1 + y2) / 2), 1)],
            width=round(float(x2 - x1), 1),
            height=round(float(y2 - y1), 1),
            **extra,
        )


@dataclass
class DetectionResult:
    count: int
    detections: list[Detection]
    avg_confidence: float | None  # None when nobody is detected
    inference_ms: float  # model forward pass only
    total_ms: float  # preprocess + inference + postprocess inside predict()
    image_size: tuple[int, int]  # original (width, height)
    speed: dict = field(default_factory=dict)  # Ultralytics per-stage timings (ms)

    def to_dict(self) -> dict:
        return asdict(self)


class PersonDetector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device = self._resolve_device(settings.device)
        self.model_path = settings.model_path

        t0 = time.perf_counter()
        self.model = YOLO(str(self.model_path))  # downloads weights if missing
        self._lock = threading.Lock()  # predict() is not thread-safe
        self._warmup()
        logger.info(
            "Loaded %s on %s in %.0f ms",
            self.model_path.name, self.device, (time.perf_counter() - t0) * 1000,
        )

    @staticmethod
    def _resolve_device(requested: str) -> str:
        if requested != "cpu" and not torch.cuda.is_available():
            logger.warning("Device '%s' requested but CUDA is unavailable; using CPU.", requested)
            return "cpu"
        return requested

    def _warmup(self) -> None:
        """Run one dummy inference so the first real request isn't slow."""
        dummy = np.zeros((self.settings.img_size, self.settings.img_size, 3), dtype=np.uint8)
        self._predict(dummy, self.settings.conf_threshold)

    def _predict(self, image: np.ndarray, conf: float, img_size: int | None = None):
        with self._lock:
            return self.model.predict(
                image,
                conf=conf,
                iou=self.settings.iou_threshold,
                imgsz=img_size or self.settings.img_size,
                device=self.device,
                classes=[PERSON_CLASS_ID],
                verbose=False,
            )[0]

    def detect(self, pre: PreprocessResult, conf: float | None = None,
               img_size: int | None = None, tracker: TrackSession | None = None,
               t: float | None = None) -> DetectionResult:
        """Run person detection on a preprocessed frame.

        `img_size` overrides the model input size for this call (e.g. 640 for
        faster live frames). With a `tracker` session, detections are linked to
        earlier frames and get stable `track_id`s; `t` is the frame time in
        seconds (wall clock for live streams, video time for files).
        Box coordinates are scaled back to the original (pre-resize) image.
        """
        conf = self.settings.conf_threshold if conf is None else conf
        # When tracking, also keep weak boxes: ByteTrack uses them to continue existing tracks
        predict_conf = min(conf, self.settings.track_low_conf) if tracker else conf

        t0 = time.perf_counter()
        result = self._predict(pre.image, predict_conf, img_size)
        total_ms = (time.perf_counter() - t0) * 1000
        boxes = result.boxes.cpu().numpy()

        if tracker is not None:
            tracked = tracker.update(boxes, conf, time.time() if t is None else t)
            detections = [
                Detection.from_xyxy(*(tb.xyxy / pre.scale), tb.score,
                                    track_id=tb.track_id, tracked_s=tb.tracked_s)
                for tb in tracked
            ]
            detections.sort(key=lambda d: d.track_id)  # stable order across frames
            confs = np.array([d.confidence for d in detections])
        else:
            xyxy = boxes.xyxy / pre.scale
            confs = boxes.conf
            detections = [Detection.from_xyxy(*b, c) for b, c in zip(xyxy, confs)]
            detections.sort(key=lambda d: d.confidence, reverse=True)

        avg = round(float(confs.mean()), 4) if len(confs) else None
        return DetectionResult(
            count=len(detections),
            detections=detections,
            avg_confidence=avg,
            inference_ms=round(result.speed.get("inference", total_ms), 1),
            total_ms=round(total_ms, 1),
            image_size=pre.original_size,
            speed={k: round(v, 1) for k, v in result.speed.items()},
        )


@lru_cache
def get_detector() -> PersonDetector:
    """Shared detector instance (loaded once per process)."""
    return PersonDetector(get_settings())
