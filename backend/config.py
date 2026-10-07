"""Application configuration.

All settings are read from environment variables prefixed with ``DETECTO_``,
falling back to a ``.env`` file in the project root, then to the defaults below.
Real environment variables always take priority over ``.env``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (folder containing backend/, frontend/, .env)
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DETECTO_",
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),  # allow field names starting with "model_"
    )

    # --- Model / inference ---
    model_name: str = "yolov8n.pt"  # Ultralytics weights; downloaded on first use
    weights_dir: Path = BACKEND_DIR / "weights"  # where weights are stored/downloaded
    device: str = "cpu"  # "cpu" or a CUDA index like "0"
    conf_threshold: float = 0.4  # minimum confidence to keep a detection
    iou_threshold: float = 0.45  # NMS overlap threshold
    # 1280 finds far more small/crowded people than 640 (see backend/evaluation/results.md)
    img_size: int = Field(1280, gt=0)  # inference input size (px)

    # --- Preprocessing ---
    max_image_side: int = Field(1280, gt=0)  # larger images are downscaled first
    enhance_contrast: bool = False  # apply CLAHE by default (can be set per request)

    # --- Storage ---
    db_path: Path = BACKEND_DIR / "data" / "detecto.db"

    # --- Uploads ---
    max_upload_mb: int = Field(10, gt=0)
    allowed_content_types: list[str] = ["image/jpeg", "image/png"]

    # --- Server ---
    cors_origins: list[str] = ["http://localhost:5173"]  # Vite dev server
    log_level: str = "INFO"
    log_file: Path | None = BACKEND_DIR / "data" / "detecto.log"  # empty to disable

    @field_validator("conf_threshold", "iou_threshold")
    @classmethod
    def _between_zero_and_one(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0 and 1")
        return v

    @field_validator("log_file", mode="before")
    @classmethod
    def _empty_means_none(cls, v):
        return None if v == "" else v

    @field_validator("db_path", "weights_dir", "log_file")
    @classmethod
    def _resolve_path(cls, v: Path | None) -> Path | None:
        # Relative paths are resolved against the project root
        return v if v is None or v.is_absolute() else ROOT_DIR / v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def model_path(self) -> Path:
        """Full path to the weights file (a path in model_name is used as-is)."""
        p = Path(self.model_name)
        return p if p.parent != Path(".") else self.weights_dir / p


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance (usable as a FastAPI dependency)."""
    settings = Settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.weights_dir.mkdir(parents=True, exist_ok=True)
    return settings
