"""Detector tests (load the real YOLO model; first run downloads weights)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.config import get_settings
from backend.services.detector import get_detector
from backend.utils.preprocessing import preprocess
from backend.utils.visualization import draw_detections, encode_jpeg_base64

SAMPLES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def detector():
    return get_detector()


def _run(detector, name, **kw):
    img = cv2.imread(str(SAMPLES / name))
    assert img is not None, f"missing sample {name}"
    return img, detector.detect(preprocess(img, get_settings(), **kw))


def test_detects_people_in_bus_image(detector):
    img, res = _run(detector, "bus.jpg")
    assert res.count >= 3
    assert res.count == len(res.detections)
    assert 0 < res.avg_confidence <= 1
    assert res.inference_ms > 0


def test_boxes_are_in_original_coordinates(detector):
    img, res = _run(detector, "bus.jpg")
    h, w = img.shape[:2]
    assert res.image_size == (w, h)
    for d in res.detections:
        x1, y1, x2, y2 = d.bbox
        assert 0 <= x1 < x2 <= w + 1 and 0 <= y1 < y2 <= h + 1
        assert d.confidence >= get_settings().conf_threshold


def test_blank_image_has_no_people(detector):
    from backend.utils.preprocessing import PreprocessResult

    blank = np.full((480, 640, 3), 127, dtype=np.uint8)
    res = detector.detect(PreprocessResult(blank, 1.0, (640, 480), False))
    assert res.count == 0
    assert res.avg_confidence is None


def test_overlay_and_encoding(detector):
    img, res = _run(detector, "zidane.jpg")
    out = draw_detections(img, res.detections)
    assert out.shape == img.shape
    assert not np.array_equal(out, img)  # something was drawn
    assert encode_jpeg_base64(out).startswith("data:image/jpeg;base64,")
