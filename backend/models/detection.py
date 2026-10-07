"""Request/response schemas for the /detect endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class PersonDetection(BaseModel):
    bbox: list[float] = Field(description="[x1, y1, x2, y2] in original image pixels")
    confidence: float
    center: list[float] = Field(description="[cx, cy]")
    width: float
    height: float


class Timings(BaseModel):
    """Per-stage processing time in milliseconds."""
    decode_ms: float
    preprocess_ms: float
    inference_ms: float  # model forward pass only
    detect_ms: float  # full predict() call incl. letterbox + NMS
    overlay_ms: float
    total_ms: float  # whole request pipeline (decode -> response)


class DetectResponse(BaseModel):
    record_id: int | None = Field(description="History id, or null when save=false")
    saved: bool
    timestamp: datetime
    img_size: int = Field(description="Model input size used for this request")
    count: int
    avg_confidence: float | None
    detections: list[PersonDetection]
    image_width: int
    image_height: int
    conf_threshold: float
    contrast_enhanced: bool
    timings: Timings
    annotated_image: str | None = Field(
        None, description="JPEG data URL with boxes drawn (when return_image=true)"
    )


class Base64ImageRequest(BaseModel):
    image: str = Field(description="Base64 JPEG/PNG, plain or as a data URL")
    source: str | None = Field(None, description="Label stored in history, e.g. 'webcam'")
