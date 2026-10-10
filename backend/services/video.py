"""Background video analysis: detect + track people through an uploaded video.

Jobs run one at a time in a worker thread. The browser polls the job for
progress and, when done, plays its own copy of the video with the returned
per-frame tracks drawn on top (no server-side video re-encoding needed).

The uploaded file is deleted as soon as processing ends. Jobs and results live
in memory only (the most recent `video_jobs_kept` are kept; a restart clears them).
"""

import logging
import statistics
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import cv2

from backend.config import Settings, get_settings
from backend.models.video import (
    VideoFrame, VideoInfo, VideoJob, VideoOptions, VideoPerson, VideoResult, VideoSummary,
)
from backend.services.detector import PersonDetector, get_detector
from backend.services.tracking import TrackSession
from backend.utils.preprocessing import preprocess

logger = logging.getLogger("detecto.video")

FALLBACK_FPS = 25.0


class JobCancelled(Exception):
    pass


class _Job:
    """Mutable job state; converted to the VideoJob schema for responses."""

    def __init__(self, filename: str, path: Path, options: VideoOptions):
        self.id = uuid.uuid4().hex
        self.filename = filename
        self.path = path
        self.options = options
        self.status = "queued"
        self.progress = 0.0
        self.created_at = datetime.now(timezone.utc)
        self.error: str | None = None
        self.result: VideoResult | None = None
        self.cancel = threading.Event()

    def to_model(self, include_result: bool = True) -> VideoJob:
        return VideoJob(
            id=self.id, filename=self.filename, status=self.status,
            progress=round(self.progress, 3), created_at=self.created_at,
            options=self.options, error=self.error,
            result=self.result if include_result else None,
        )


def analyse_video(path: Path, options: VideoOptions, settings: Settings, detector: PersonDetector,
                  on_progress=lambda p: None, should_stop=lambda: False) -> VideoResult:
    """Detect and track people through a video file. Raises ValueError for unreadable/too long videos."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Could not read this video. Use an MP4 (H.264), WebM or MOV file.")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 0 < fps <= 240 else FALLBACK_FPS
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total / fps if total > 0 else 0.0
        if duration > settings.max_video_seconds:
            raise ValueError(f"Video is {duration:.0f} s long; the limit is {settings.max_video_seconds:.0f} s.")

        step = max(1, round(fps / options.sample_fps))
        analysed_fps = fps / step
        session = TrackSession(f"video-{path.stem}", settings, fps=analysed_fps)

        frames: list[VideoFrame] = []
        inference: list[float] = []
        t_start = time.perf_counter()
        index = 0
        while True:
            if should_stop():
                raise JobCancelled()
            if not cap.grab():  # grab() skips decoding for frames we don't analyse
                break
            if index % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                t = index / fps
                res = detector.detect(preprocess(frame, settings, enhance=options.enhance),
                                      conf=options.conf, img_size=options.img_size, tracker=session, t=t)
                inference.append(res.inference_ms)
                frames.append(VideoFrame(t=round(t, 3), boxes=[
                    [d.track_id, *d.bbox, d.confidence] for d in res.detections
                ]))
                if total > 0:
                    on_progress(min(0.999, (index + 1) / total))
            index += 1
    finally:
        cap.release()

    if not frames:
        raise ValueError("No frames could be decoded from this video.")

    processing_s = time.perf_counter() - t_start
    duration = duration or frames[-1].t
    counts = [len(f.boxes) for f in frames]
    peak = max(counts)
    return VideoResult(
        video=VideoInfo(width=width, height=height, fps=round(fps, 2), duration_s=round(duration, 2),
                        frames_total=total if total > 0 else index, analysed_fps=round(analysed_fps, 2)),
        summary=VideoSummary(
            unique_people=session.unique_people,
            peak_people=peak,
            peak_t=frames[counts.index(peak)].t if peak else None,
            avg_people=round(statistics.mean(counts), 2),
            frames_analysed=len(frames),
            avg_inference_ms=round(statistics.mean(inference), 1) if inference else None,
            processing_s=round(processing_s, 1),
            speed_factor=round(duration / processing_s, 2) if processing_s > 0 else 0.0,
        ),
        people=[VideoPerson(**p) for p in session.people()],
        frames=frames,
    )


class VideoJobs:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.upload_dir = settings.db_path.parent / "videos"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: OrderedDict[str, _Job] = OrderedDict()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video")

    def new_upload_path(self, suffix: str) -> Path:
        return self.upload_dir / f"{uuid.uuid4().hex}{suffix}"

    def submit(self, path: Path, filename: str, options: VideoOptions) -> _Job:
        job = _Job(filename, path, options)
        with self._lock:
            self._jobs[job.id] = job
            self._prune()
        self._executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> _Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Cancel a running/queued job, or forget a finished one."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in ("queued", "processing"):
                job.cancel.set()
            else:
                del self._jobs[job_id]
            return True

    def _run(self, job: _Job) -> None:
        if job.cancel.is_set():
            job.status = "cancelled"
            job.path.unlink(missing_ok=True)
            return
        job.status = "processing"
        logger.info("Video job %s started (%s)", job.id, job.filename)
        try:
            job.result = analyse_video(
                job.path, job.options, self.settings, get_detector(),
                on_progress=lambda p: setattr(job, "progress", p),
                should_stop=job.cancel.is_set,
            )
            job.progress = 1.0
            job.status = "done"
            s = job.result.summary
            logger.info("Video job %s done: %d unique people, %d frames in %.1f s",
                        job.id, s.unique_people, s.frames_analysed, s.processing_s)
        except JobCancelled:
            job.status = "cancelled"
            logger.info("Video job %s cancelled", job.id)
        except ValueError as exc:
            job.status, job.error = "error", str(exc)
        except Exception:  # keep the worker alive; report a generic error
            logger.exception("Video job %s failed", job.id)
            job.status, job.error = "error", "Processing failed unexpectedly. See the server log."
        finally:
            job.path.unlink(missing_ok=True)  # never keep uploaded videos

    def _prune(self) -> None:
        finished = [jid for jid, j in self._jobs.items() if j.status in ("done", "error", "cancelled")]
        for jid in finished[: max(0, len(finished) - self.settings.video_jobs_kept)]:
            del self._jobs[jid]


@lru_cache
def get_video_jobs() -> VideoJobs:
    return VideoJobs(get_settings())
