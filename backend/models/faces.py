"""Schemas for face enrolment and recognition."""

from datetime import datetime

from pydantic import BaseModel, Field


class Person(BaseModel):
    id: int
    name: str
    photos: int = Field(description="Number of stored face embeddings (photos are not stored)")
    created_at: datetime


class PeopleResponse(BaseModel):
    available: bool = Field(description="False when the face model files are missing")
    threshold: float = Field(description="Cosine similarity needed for a match")
    people: list[Person]


class PhotoResult(BaseModel):
    file: str
    ok: bool
    reason: str | None = None  # why a photo was not used


class EnrollResponse(BaseModel):
    person: Person
    results: list[PhotoResult]


class FaceIdentity(BaseModel):
    """Who a detected face belongs to (name is None for an unknown face)."""
    person_id: int | None
    name: str | None
    similarity: float = Field(description="Cosine similarity to the closest enrolled face")
    from_track: bool = Field(
        False, description="True when the face isn't visible now but this track was recognised earlier"
    )


class FaceResult(FaceIdentity):
    bbox: list[float] = Field(description="[x1, y1, x2, y2] in original image pixels")
    score: float = Field(description="Face-detection confidence")
