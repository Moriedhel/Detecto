"""Schemas for /stats endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.models.record import TimeRange


class SummaryStats(BaseModel):
    """Aggregates over stored detections (optionally within a time range)."""
    total_detections: int  # processed images/frames
    frames_with_people: int
    total_people: int
    avg_people: float | None
    max_people: int | None
    avg_confidence: float | None  # mean over all detected persons (weighted by count)
    avg_inference_ms: float | None
    p50_inference_ms: float | None
    p95_inference_ms: float | None
    max_inference_ms: float | None
    avg_total_ms: float | None
    first_timestamp: datetime | None
    last_timestamp: datetime | None


class RuntimeInfo(BaseModel):
    model: str
    device: str
    conf_threshold: float
    img_size: int
    uptime_s: float


class StatsResponse(BaseModel):
    summary: SummaryStats
    runtime: RuntimeInfo


class HourlyQuery(TimeRange):
    mode: Literal["timeline", "hour_of_day"] = Field(
        "timeline",
        description="timeline: one bucket per calendar hour; "
                    "hour_of_day: buckets 0-23 aggregated across days",
    )
    tz_offset_minutes: int = Field(
        0, ge=-840, le=840,
        description="Shift buckets to local time, e.g. 180 for UTC+3 "
                    "(JS: -new Date().getTimezoneOffset())",
    )


class HourlyBucket(BaseModel):
    hour: str  # "2026-10-01T14:00" (timeline) or "14" (hour_of_day), local to tz_offset
    detections: int
    avg_people: float
    max_people: int
    avg_confidence: float | None


class HourlyStats(BaseModel):
    mode: str
    tz_offset_minutes: int
    buckets: list[HourlyBucket]
