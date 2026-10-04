"""History endpoints.

GET    /history        list stored detections (filters + pagination)
GET    /history/{id}   one stored detection
DELETE /reset          clear all history (POST also accepted)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.db import DetectionRepository, get_repository
from backend.models.record import DetectionRecord, HistoryPage, HistoryQuery

router = APIRouter(tags=["history"])

RepoDep = Annotated[DetectionRepository, Depends(get_repository)]


class ResetResponse(BaseModel):
    deleted: int


@router.get("/history", response_model=HistoryPage, summary="List past detections")
def list_history(repo: RepoDep, q: Annotated[HistoryQuery, Query()]):
    """Filter by time range (ISO 8601; UTC if no offset), minimum average
    confidence and minimum people count. Results are paginated with
    `limit`/`offset`; `total` is the number of matches before paging."""
    if q.start and q.end and q.start > q.end:
        raise HTTPException(400, "`start` must be before `end`.")
    return repo.list(q)


@router.get("/history/{record_id}", response_model=DetectionRecord, summary="Get one detection")
def get_history_item(record_id: int, repo: RepoDep):
    record = repo.get(record_id)
    if record is None:
        raise HTTPException(404, f"Detection {record_id} not found.")
    return record


@router.api_route("/reset", methods=["DELETE", "POST"], response_model=ResetResponse,
                  summary="Clear all detection history")
def reset_history(repo: RepoDep):
    return ResetResponse(deleted=repo.clear())
