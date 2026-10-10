"""Video analysis endpoints.

POST   /videos        upload a video and start an analysis job (202 + job)
GET    /videos/{id}   job status and progress; includes the result when done
DELETE /videos/{id}   cancel a running job or forget a finished one
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from backend.config import Settings, get_settings
from backend.models.video import VideoJob, VideoOptions
from backend.services.video import VideoJobs, get_video_jobs

router = APIRouter(prefix="/videos", tags=["video"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
JobsDep = Annotated[VideoJobs, Depends(get_video_jobs)]

VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
               "video/x-msvideo": ".avi", "video/x-matroska": ".mkv"}
VIDEO_EXTENSIONS = set(VIDEO_TYPES.values()) | {".m4v"}
CHUNK = 1024 * 1024


@router.post("", response_model=VideoJob, status_code=202, summary="Upload a video for analysis")
def upload_video(
    settings: SettingsDep,
    jobs: JobsDep,
    file: Annotated[UploadFile, File(description="MP4 (H.264), WebM, MOV, AVI or MKV")],
    conf: Annotated[float | None, Query(ge=0, le=1, description="Confidence threshold")] = None,
    img_size: Annotated[int | None, Query(ge=320, le=1920, multiple_of=32,
                                          description="Model input size (default DETECTO_VIDEO_IMG_SIZE)")] = None,
    sample_fps: Annotated[float | None, Query(gt=0, le=30, description="Frames analysed per video second")] = None,
    enhance: Annotated[bool, Query(description="CLAHE contrast boost")] = False,
):
    ext = Path(file.filename or "").suffix.lower()
    if file.content_type not in VIDEO_TYPES and ext not in VIDEO_EXTENSIONS:
        raise HTTPException(415, "Unsupported file type. Upload an MP4, WebM, MOV, AVI or MKV video.")

    # Stream to disk with a size limit (videos can be large)
    path = jobs.new_upload_path(ext or VIDEO_TYPES.get(file.content_type, ".mp4"))
    limit = settings.max_video_mb * 1024 * 1024
    written = 0
    try:
        with open(path, "wb") as out:
            while chunk := file.file.read(CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, f"Video is larger than {settings.max_video_mb} MB.")
                out.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    if written == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "Uploaded file is empty.")

    options = VideoOptions(
        conf=settings.conf_threshold if conf is None else conf,
        img_size=img_size or settings.video_img_size,
        sample_fps=sample_fps or settings.video_sample_fps,
        enhance=enhance,
    )
    return jobs.submit(path, file.filename or path.name, options).to_model()


@router.get("/{job_id}", response_model=VideoJob, summary="Job status, progress and result")
def get_job(job_id: str, jobs: JobsDep):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Video job not found (jobs are kept in memory and cleared on restart).")
    return job.to_model()


@router.delete("/{job_id}", status_code=204, summary="Cancel or forget a job")
def delete_job(job_id: str, jobs: JobsDep):
    if not jobs.cancel(job_id):
        raise HTTPException(404, "Video job not found.")
