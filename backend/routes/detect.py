"""Detection endpoints.

POST /detect          multipart/form-data: `file` upload OR `image_base64` field
POST /detect/base64   JSON: {"image": "<base64 or data URL>", "source": "webcam"}

DELETE /detect/sessions/{id}   end a tracking session early (they also expire when idle)

Both detect routes accept the same query options
(conf, enhance, return_image, img_size, save, faces, session).
Routes are sync (`def`) so CPU-bound inference runs in FastAPI's thread pool.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from backend.config import Settings, get_settings
from backend.db import DetectionRepository, get_repository
from backend.face_store import FaceStore, get_face_store
from backend.models.detection import Base64ImageRequest, DetectResponse
from backend.services.detector import PersonDetector, get_detector
from backend.services.faces import FaceModelsMissing, get_face_service
from backend.services.pipeline import run_detection
from backend.services.tracking import get_tracking_sessions
from backend.utils.preprocessing import decode_base64

router = APIRouter(prefix="/detect", tags=["detection"])


class DetectOptions:
    """Per-request overrides shared by both endpoints (query parameters)."""

    def __init__(
        self,
        conf: Annotated[float | None, Query(ge=0, le=1, description="Confidence threshold (default from config)")] = None,
        enhance: Annotated[bool | None, Query(description="Apply CLAHE contrast boost (default from config)")] = None,
        return_image: Annotated[bool, Query(description="Include annotated image as base64")] = True,
        img_size: Annotated[int | None, Query(
            ge=320, le=1920, multiple_of=32,
            description="Model input size (default from config). 640 is ~2-3x faster, "
                        "1280 finds more small/distant people",
        )] = None,
        save: Annotated[bool, Query(
            description="Store the result in history. Use false for live frames "
                        "and save selectively",
        )] = True,
        faces: Annotated[bool, Query(
            description="Also recognise enrolled faces (names are returned, never stored)",
        )] = False,
        session: Annotated[str | None, Query(
            min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
            description="Tracking session id (e.g. a UUID per webcam run). Gives stable track IDs "
                        "across frames; sessions expire when idle",
        )] = None,
    ):
        self.conf = conf
        self.enhance = enhance
        self.return_image = return_image
        self.img_size = img_size
        self.save = save
        self.faces = faces
        self.session = session


# Shared dependencies (overridable in tests via app.dependency_overrides)
SettingsDep = Annotated[Settings, Depends(get_settings)]
DetectorDep = Annotated[PersonDetector, Depends(get_detector)]
RepoDep = Annotated[DetectionRepository, Depends(get_repository)]
FaceStoreDep = Annotated[FaceStore, Depends(get_face_store)]
OptionsDep = Annotated[DetectOptions, Depends()]


def _face_args(opts: DetectOptions, store: FaceStore) -> dict:
    """Face-recognition arguments for run_detection (models load on first use only)."""
    if not opts.faces:
        return {}
    try:
        return {"face_service": get_face_service(), "face_store": store}
    except FaceModelsMissing as exc:
        raise HTTPException(503, f"Face recognition is unavailable: {exc}") from exc


def _run(data, content_type, source, settings, detector, repo, opts, store):
    session = get_tracking_sessions().get(opts.session) if opts.session else None
    return run_detection(
        data, content_type=content_type, source=source,
        settings=settings, detector=detector, repo=repo,
        conf=opts.conf, enhance=opts.enhance, return_image=opts.return_image,
        img_size=opts.img_size, save=opts.save, session=session, **_face_args(opts, store),
    )


@router.post("", response_model=DetectResponse, summary="Detect people in an uploaded image")
def detect(
    settings: SettingsDep,
    detector: DetectorDep,
    repo: RepoDep,
    store: FaceStoreDep,
    opts: OptionsDep,
    file: Annotated[UploadFile | None, File(description="JPEG or PNG image")] = None,
    image_base64: Annotated[str | None, Form(description="Alternative to `file`: base64 image")] = None,
):
    if file is not None and file.filename:
        # Read at most limit+1 bytes so oversized uploads are rejected without loading them fully
        data = file.file.read(settings.max_upload_bytes + 1)
        content_type, source = file.content_type, file.filename
    elif image_base64:
        data, content_type = decode_base64(image_base64)
        source = "base64"
    else:
        raise HTTPException(400, "No image provided. Send a `file` upload or an `image_base64` field.")

    return _run(data, content_type, source, settings, detector, repo, opts, store)


@router.post("/base64", response_model=DetectResponse, summary="Detect people in a base64 image (JSON)")
def detect_base64(
    body: Base64ImageRequest,
    settings: SettingsDep,
    detector: DetectorDep,
    repo: RepoDep,
    store: FaceStoreDep,
    opts: OptionsDep,
):
    if not body.image.strip():
        raise HTTPException(400, "Field `image` is empty.")
    data, content_type = decode_base64(body.image)
    return _run(data, content_type, body.source or "base64", settings, detector, repo, opts, store)


@router.delete("/sessions/{session_id}", status_code=204, summary="End a tracking session")
def end_session(session_id: str):
    """Drops the session's tracker and IDs immediately (idle sessions expire anyway)."""
    if not get_tracking_sessions().end(session_id):
        raise HTTPException(404, "Tracking session not found (it may have expired).")
