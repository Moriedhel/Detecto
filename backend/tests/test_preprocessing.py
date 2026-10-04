import base64

import cv2
import numpy as np
import pytest

from backend.config import Settings
from backend.utils import preprocessing as pp


@pytest.fixture
def settings():
    return Settings(max_upload_mb=1, max_image_side=640, enhance_contrast=False)


def _encode(img: np.ndarray, ext: str) -> bytes:
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def img():
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (300, 400, 3), dtype=np.uint8)


# --- validation -------------------------------------------------------------

@pytest.mark.parametrize("ext,mime", [(".jpg", "image/jpeg"), (".png", "image/png")])
def test_valid_images_decode(img, settings, ext, mime):
    data = _encode(img, ext)
    assert pp.validate_bytes(data, mime, settings) == mime
    assert pp.load_image(data, mime, settings).shape == img.shape


def test_empty_file_rejected(settings):
    with pytest.raises(pp.EmptyFileError) as e:
        pp.validate_bytes(b"", "image/png", settings)
    assert e.value.status_code == 400


def test_too_large_rejected(settings):
    data = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
    with pytest.raises(pp.FileTooLargeError) as e:
        pp.validate_bytes(data, "image/png", settings)
    assert e.value.status_code == 413


def test_wrong_content_type_rejected(img, settings):
    with pytest.raises(pp.UnsupportedFormatError) as e:
        pp.validate_bytes(_encode(img, ".png"), "image/gif", settings)
    assert e.value.status_code == 415


def test_spoofed_content_rejected(settings):
    # Claims to be PNG but is plain text
    with pytest.raises(pp.UnsupportedFormatError):
        pp.validate_bytes(b"hello, not an image", "image/png", settings)


def test_unsupported_real_format_rejected(img, settings):
    # A real BMP image with no content type given
    with pytest.raises(pp.UnsupportedFormatError):
        pp.validate_bytes(_encode(img, ".bmp"), None, settings)


def test_corrupt_image_rejected(settings):
    data = b"\x89PNG\r\n\x1a\n" + b"garbage" * 10
    with pytest.raises(pp.InvalidImageError):
        pp.load_image(data, "image/png", settings)


# --- base64 -----------------------------------------------------------------

def test_base64_plain_and_data_url(img):
    raw = _encode(img, ".jpg")
    b64 = base64.b64encode(raw).decode()

    assert pp.decode_base64(b64) == (raw, None)
    assert pp.decode_base64(f"data:image/jpeg;base64,{b64}") == (raw, "image/jpeg")


def test_invalid_base64_rejected():
    with pytest.raises(pp.InvalidImageError):
        pp.decode_base64("not*valid*base64!!")


# --- preprocessing ----------------------------------------------------------

def test_small_image_not_resized(img):
    out, scale = pp.resize_max_side(img, 640)
    assert scale == 1.0 and out.shape == img.shape


def test_large_image_downscaled():
    big = np.zeros((1000, 2000, 3), dtype=np.uint8)
    out, scale = pp.resize_max_side(big, 640)
    assert out.shape[:2] == (320, 640)
    assert scale == pytest.approx(0.32)


def test_clahe_increases_contrast():
    # Low-contrast gradient squeezed into 100..130
    grad = np.tile(np.linspace(100, 130, 256, dtype=np.uint8), (256, 1))
    low = cv2.merge([grad, grad, grad])
    out = pp.enhance_contrast(low)
    assert out.shape == low.shape
    assert out.std() > low.std()


def test_preprocess_respects_override(img, settings):
    res = pp.preprocess(img, settings, enhance=True)
    assert res.contrast_enhanced is True
    assert res.original_size == (400, 300)
    assert pp.preprocess(img, settings).contrast_enhanced is False
