"""Download the OpenCV face models used by face recognition into backend/weights/.

Usage (from project root):
    .\\.venv\\Scripts\\python.exe scripts/download_face_models.py
"""

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402

ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"
MODELS = {
    "face_detection_yunet_2023mar.onnx": f"{ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
MIN_BYTES = 100_000  # guards against saving a Git LFS pointer instead of the model


def main() -> None:
    weights = get_settings().weights_dir
    weights.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        target = weights / name
        if target.exists() and target.stat().st_size >= MIN_BYTES:
            print(f"ok       {name} (already present)")
            continue
        print(f"download {name} ...")
        urllib.request.urlretrieve(url, target)
        size = target.stat().st_size
        if size < MIN_BYTES:
            target.unlink()
            raise SystemExit(f"{name}: download looks wrong ({size} bytes)")
        print(f"ok       {name} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
