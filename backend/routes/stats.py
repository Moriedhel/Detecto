"""Statistics endpoints.

GET /stats          summary of stored detections + runtime/model info
GET /stats/hourly   detections grouped per hour (timeline or hour-of-day)

Both accept the same record filters as /history (time range, min_confidence,
min_count), so dashboards show numbers that agree with the history table.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.config import Settings, get_settings
from backend.db import DetectionRepository, get_repository
from backend.models.record import RecordFilter, TimeRange
from backend.models.stats import HourlyQuery, HourlyStats, RuntimeInfo, StatsResponse

router = APIRouter(prefix="/stats", tags=["stats"])

RepoDep = Annotated[DetectionRepository, Depends(get_repository)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _check_range(q: TimeRange) -> None:
    if q.start and q.end and q.start > q.end:
        raise HTTPException(400, "`start` must be before `end`.")


@router.get("", response_model=StatsResponse, summary="Summary statistics and performance")
def get_stats(request: Request, repo: RepoDep, settings: SettingsDep,
              q: Annotated[RecordFilter, Query()]):
    _check_range(q)
    detector = getattr(request.app.state, "detector", None)
    started = getattr(request.app.state, "started_at", time.time())
    return StatsResponse(
        summary=repo.summary(q),
        runtime=RuntimeInfo(
            model=settings.model_name,
            device=detector.device if detector else settings.device,
            conf_threshold=settings.conf_threshold,
            img_size=settings.img_size,
            uptime_s=round(time.time() - started, 1),
        ),
    )


@router.get("/hourly", response_model=HourlyStats, summary="Detections grouped by hour")
def get_hourly(repo: RepoDep, q: Annotated[HourlyQuery, Query()]):
    _check_range(q)
    return HourlyStats(mode=q.mode, tz_offset_minutes=q.tz_offset_minutes, buckets=repo.hourly(q))
