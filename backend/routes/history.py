"""History endpoints.

GET    /history              list stored detections (filters + pagination)
GET    /history/export.csv   download matching detections as CSV
GET    /history/{id}         one stored detection
DELETE /reset                clear all history (POST also accepted)
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.db import DetectionRepository, get_repository
from backend.models.record import (
    DetectionRecord,
    ExportQuery,
    HistoryPage,
    HistoryQuery,
    TimeRange,
)
from backend.utils.export import iter_csv

router = APIRouter(tags=["history"])

RepoDep = Annotated[DetectionRepository, Depends(get_repository)]


class ResetResponse(BaseModel):
    deleted: int


def _check_range(q: TimeRange) -> None:
    if q.start and q.end and q.start > q.end:
        raise HTTPException(400, "`start` must be before `end`.")


@router.get("/history", response_model=HistoryPage, summary="List past detections")
def list_history(repo: RepoDep, q: Annotated[HistoryQuery, Query()]):
    """Filter by time range (ISO 8601; UTC if no offset), minimum average
    confidence and minimum people count. Results are paginated with
    `limit`/`offset`; `total` is the number of matches before paging."""
    _check_range(q)
    return repo.list(q)


# Declared before /history/{record_id} so "export.csv" isn't parsed as an id
@router.get(
    "/history/export.csv",
    summary="Export detections as CSV",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file download"}},
)
def export_history_csv(repo: RepoDep, q: Annotated[ExportQuery, Query()]):
    """Same filters as `/history`, without pagination: every matching record
    is exported. Streams in batches, so large histories don't load into memory."""
    _check_range(q)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        iter_csv(repo.iter_records(q), include_detections=q.include_detections),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="detecto_history_{stamp}.csv"'},
    )


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
