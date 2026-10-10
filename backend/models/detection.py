"""Request/response schemas for the /detect endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.faces import FaceIdentity, FaceResult


class PersonDetection(BaseModel):
    bbox: list[float] = Field(description="[x1, y1, x2, y2] in original image pixels")
    confidence: float
    center: list[float] = Field(description="[cx, cy]")
    width: float
    height: float
    track_id: int | None = Field(None, description="Stable ID within a tracking session (session=...)")
    tracked_s: float | None = Field(None, description="Seconds this track has been visible")
    identity: FaceIdentity | None = Field(None, description="Recognised face inside this box (faces=true)")


class TrackingInfo(BaseModel):
    session_id: str
    unique_people: int = Field(description="Different track IDs seen in this session")
    active: int = Field(description="Tracks visible in this frame")
    fps: float = Field(description="Frame rate the tracker is assuming")


class Timings(BaseModel):
    """Per-stage processing time in milliseconds."""
    decode_ms: float
    preprocess_ms: float
    inference_ms: float  # model forward pass only
    detect_ms: float  # full predict() call incl. letterbox + NMS
    faces_ms: float = 0.0  # face detection + recognition (faces=true)
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
    faces: list[FaceResult] | None = Field(
        None, description="All faces found and who they match (only when faces=true)"
    )
    tracking: TrackingInfo | None = Field(None, description="Session totals (only with session=...)")
    annotated_image: str | None = Field(
        None, description="JPEG data URL with boxes drawn (when return_image=true)"
    )


class Base64ImageRequest(BaseModel):
    image: str = Field(description="Base64 JPEG/PNG, plain or as a data URL")
    source: str | None = Field(None, description="Label stored in history, e.g. 'webcam'")
