"""Drawing detection overlays and encoding images for API responses."""

import base64

import cv2
import numpy as np

from backend.services.detector import Detection

BOX_COLOR = (0, 200, 0)  # BGR green
TEXT_COLOR = (255, 255, 255)


def draw_detections(img: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """Return a copy of `img` with boxes, confidence labels and a count banner.

    Line width and font scale adapt to the image size so overlays stay
    readable without cluttering small or large frames.
    """
    out = img.copy()
    h, w = out.shape[:2]
    thickness = max(1, round(min(h, w) / 400))
    font_scale = max(0.4, min(h, w) / 1200)

    for i, det in enumerate(detections, start=1):
        x1, y1, x2, y2 = (int(round(v)) for v in det.bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), BOX_COLOR, thickness)

        label = f"#{i} {det.confidence:.0%}"
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        ty = max(y1, th + base + 2)  # keep label inside the image at the top edge
        cv2.rectangle(out, (x1, ty - th - base - 2), (x1 + tw + 4, ty), BOX_COLOR, -1)
        cv2.putText(out, label, (x1 + 2, ty - base), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, TEXT_COLOR, 1, cv2.LINE_AA)

    banner = f"People: {len(detections)}"
    (bw, bh), base = cv2.getTextSize(banner, cv2.FONT_HERSHEY_SIMPLEX, font_scale * 1.4, 2)
    cv2.rectangle(out, (0, 0), (bw + 16, bh + base + 12), (0, 0, 0), -1)
    cv2.putText(out, banner, (8, bh + 6), cv2.FONT_HERSHEY_SIMPLEX,
                font_scale * 1.4, TEXT_COLOR, 2, cv2.LINE_AA)
    return out


def encode_jpeg_base64(img: np.ndarray, quality: int = 85, data_url: bool = True) -> str:
    """Encode a BGR image as base64 JPEG (optionally as a data URL for <img src>)."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("Failed to encode image.")
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}" if data_url else b64
