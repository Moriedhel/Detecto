"""Schemas for video analysis jobs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "processing", "done", "error", "cancelled"]


class VideoOptions(BaseModel):
    conf: float
    img_size: int
    sample_fps: float
    enhance: bool


class VideoInfo(BaseModel):
    width: int
    height: int
    fps: float = Field(description="Frame rate of the file")
    duration_s: float
    frames_total: int
    analysed_fps: float = Field(description="Frames analysed per second of video")


class VideoPerson(BaseModel):
    track_id: int
    first_t: float = Field(description="Video time (s) the person first appeared")
    last_t: float
    duration_s: float
    frames: int = Field(description="Analysed frames the person was in")
    best_confidence: float


class VideoSummary(BaseModel):
    unique_people: int = Field(description="Different tracked people (tracks of 3+ frames)")
    peak_people: int
    peak_t: float | None
    avg_people: float
    frames_analysed: int
    avg_inference_ms: float | None
    processing_s: float
    speed_factor: float = Field(description="Video seconds processed per wall-clock second")


class VideoFrame(BaseModel):
    t: float = Field(description="Video time in seconds")
    boxes: list[list[float]] = Field(description="[track_id, x1, y1, x2, y2, confidence] per person")


class VideoResult(BaseModel):
    video: VideoInfo
    summary: VideoSummary
    people: list[VideoPerson]
    frames: list[VideoFrame]


class VideoJob(BaseModel):
    id: str
    filename: str
    status: JobStatus
    progress: float = Field(description="0-1")
    created_at: datetime
    options: VideoOptions
    error: str | None = None
    result: VideoResult | None = Field(None, description="Present when status is 'done'")
