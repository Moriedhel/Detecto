"""Data models for stored detection results and history queries."""

from datetime import datetime

from pydantic import BaseModel, Field


class PersonBox(BaseModel):
    """Compact per-person data kept in history (enough for heatmaps/tracking)."""
    bbox: list[float]  # [x1, y1, x2, y2] in original image pixels
    confidence: float
    center: list[float]  # [cx, cy]


class DetectionRecordCreate(BaseModel):
    """Fields provided when saving a detection result."""
    count: int = Field(ge=0)
    avg_confidence: float | None = Field(None, ge=0, le=1)  # None when count == 0
    inference_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)
    source: str | None = None  # filename, "base64", "webcam", ...
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    conf_threshold: float = Field(ge=0, le=1)
    contrast_enhanced: bool = False
    detections: list[PersonBox] = []


class DetectionRecord(DetectionRecordCreate):
    """A stored detection result."""
    id: int
    timestamp: datetime  # UTC


class HistoryQuery(BaseModel):
    """Filters for listing history (all optional)."""
    start: datetime | None = None  # inclusive, UTC if no timezone given
    end: datetime | None = None  # inclusive
    min_confidence: float | None = Field(None, ge=0, le=1)  # on avg_confidence
    min_count: int | None = Field(None, ge=0)
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    newest_first: bool = True


class HistoryPage(BaseModel):
    total: int  # matching records before limit/offset
    items: list[DetectionRecord]
