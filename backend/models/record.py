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


class TimeRange(BaseModel):
    """Optional inclusive time window (UTC if no timezone given)."""
    start: datetime | None = None
    end: datetime | None = None


class HistoryFilter(TimeRange):
    """Filters shared by history listing and export (all optional)."""
    min_confidence: float | None = Field(None, ge=0, le=1)  # on avg_confidence
    min_count: int | None = Field(None, ge=0)
    newest_first: bool = True


class HistoryQuery(HistoryFilter):
    """History filters plus pagination."""
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class ExportQuery(HistoryFilter):
    """History filters for CSV export (no pagination: exports all matches)."""
    include_detections: bool = Field(False, description="Add a JSON column with every person's box")


class HistoryPage(BaseModel):
    total: int  # matching records before limit/offset
    items: list[DetectionRecord]
