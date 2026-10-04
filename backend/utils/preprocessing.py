"""Image validation, decoding and preprocessing.

Pipeline used by /detect:
    raw bytes / base64 -> validate -> decode (BGR ndarray) -> resize -> optional CLAHE

Pixel normalization (0-255 -> 0-1) and letterboxing to the model input size
are done inside Ultralytics' predictor, so they are not repeated here.
"""

import base64
import binascii
import re
from dataclasses import dataclass

import cv2
import numpy as np

from backend.config import Settings

# Magic bytes for supported formats; content-type headers can't be trusted alone
_SIGNATURES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w/+.-]+);base64,", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Errors (each carries the HTTP status the API should return)
# ---------------------------------------------------------------------------

class ImageError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class EmptyFileError(ImageError):
    status_code = 400


class FileTooLargeError(ImageError):
    status_code = 413


class UnsupportedFormatError(ImageError):
    status_code = 415


class InvalidImageError(ImageError):
    status_code = 400


# ---------------------------------------------------------------------------
# Validation & decoding
# ---------------------------------------------------------------------------

def sniff_format(data: bytes) -> str | None:
    """Return the MIME type detected from the file signature, or None."""
    for mime, sig in _SIGNATURES.items():
        if data.startswith(sig):
            return mime
    return None


def validate_bytes(data: bytes, content_type: str | None, settings: Settings) -> str:
    """Check that the payload is a non-empty, size-limited JPEG/PNG.

    Returns the detected MIME type. Raises an ImageError subclass on failure.
    """
    if not data:
        raise EmptyFileError("Uploaded file is empty.")

    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"File is {len(data) / 1_048_576:.1f} MB; limit is {settings.max_upload_mb} MB."
        )

    allowed = ", ".join(settings.allowed_content_types)
    if content_type and content_type not in settings.allowed_content_types:
        raise UnsupportedFormatError(f"Unsupported type '{content_type}'. Allowed: {allowed}.")

    detected = sniff_format(data)
    if detected is None or detected not in settings.allowed_content_types:
        raise UnsupportedFormatError(f"File content is not a supported image. Allowed: {allowed}.")

    return detected


def decode_base64(payload: str) -> tuple[bytes, str | None]:
    """Decode a base64 string (optionally a data URL). Returns (bytes, mime-or-None)."""
    payload = payload.strip()
    mime = None
    match = _DATA_URL_RE.match(payload)
    if match:
        mime = match.group("mime").lower()
        payload = payload[match.end():]

    try:
        return base64.b64decode(payload, validate=True), mime
    except (binascii.Error, ValueError):
        raise InvalidImageError("Invalid base64 image data.")


def decode_image(data: bytes) -> np.ndarray:
    """Decode image bytes into a BGR uint8 array."""
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise InvalidImageError("Image could not be decoded (file may be corrupt).")
    return img


def load_image(data: bytes, content_type: str | None, settings: Settings) -> np.ndarray:
    """Validate and decode raw upload bytes in one call."""
    validate_bytes(data, content_type, settings)
    return decode_image(data)


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def resize_max_side(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Downscale so the longest side is <= max_side (never upscales).

    Returns (image, scale) where scale = new_size / original_size; divide
    box coordinates by `scale` to map them back to the original image.
    """
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img, 1.0
    scale = max_side / longest
    resized = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return resized, scale


def enhance_contrast(img: np.ndarray, clip_limit: float = 2.0, tile: int = 8) -> np.ndarray:
    """Apply CLAHE to the lightness channel; helps with dark or washed-out frames."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


@dataclass
class PreprocessResult:
    image: np.ndarray  # image to feed to the model
    scale: float  # resize factor applied (processed / original)
    original_size: tuple[int, int]  # (width, height) of the input
    contrast_enhanced: bool


def preprocess(img: np.ndarray, settings: Settings, enhance: bool | None = None) -> PreprocessResult:
    """Resize and optionally contrast-enhance a decoded frame.

    `enhance` overrides settings.enhance_contrast when given (per-request toggle).
    """
    h, w = img.shape[:2]
    out, scale = resize_max_side(img, settings.max_image_side)
    use_clahe = settings.enhance_contrast if enhance is None else enhance
    if use_clahe:
        out = enhance_contrast(out)
    return PreprocessResult(image=out, scale=scale, original_size=(w, h), contrast_enhanced=use_clahe)
