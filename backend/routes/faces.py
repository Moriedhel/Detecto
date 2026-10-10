"""Face enrolment endpoints.

GET    /faces/people        enrolled people (+ whether face models are available)
POST   /faces/people        enrol a person from 1+ photos (multipart: name, consent, files)
DELETE /faces/people/{id}   delete a person and all their face data

Photos are used only to compute embeddings and are never stored.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.config import Settings, get_settings
from backend.face_store import FaceStore, get_face_store
from backend.models.faces import EnrollResponse, PeopleResponse, PhotoResult
from backend.services.faces import EnrollError, FaceModelsMissing, FaceService, get_face_service
from backend.utils.preprocessing import ImageError, decode_image, validate_bytes

logger = logging.getLogger("detecto.faces")
router = APIRouter(prefix="/faces", tags=["faces"])

StoreDep = Annotated[FaceStore, Depends(get_face_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MAX_NAME_LEN = 60


def _service() -> FaceService:
    try:
        return get_face_service()
    except FaceModelsMissing as exc:
        raise HTTPException(503, f"Face recognition is unavailable: {exc}") from exc


def _models_available() -> bool:
    try:
        get_face_service()
        return True
    except FaceModelsMissing:
        return False


@router.get("/people", response_model=PeopleResponse, summary="List enrolled people")
def list_people(store: StoreDep, settings: SettingsDep):
    return PeopleResponse(
        available=_models_available(),
        threshold=settings.face_match_threshold,
        people=store.list_people(),
    )


@router.post("/people", response_model=EnrollResponse, status_code=201, summary="Enrol a person from photos")
def enroll_person(
    store: StoreDep,
    settings: SettingsDep,
    name: Annotated[str, Form(description="Display name (adds photos if the name already exists)")],
    consent: Annotated[bool, Form(description="The person agreed to be enrolled")],
    files: Annotated[list[UploadFile], File(description="1+ photos showing only this person's face")],
):
    name = " ".join(name.split())  # trim and collapse whitespace
    if not name or len(name) > MAX_NAME_LEN:
        raise HTTPException(400, f"Name must be 1–{MAX_NAME_LEN} characters.")
    if not consent:
        raise HTTPException(400, "Enrolment needs the person's consent.")
    files = [f for f in files if f.filename]
    if not files:
        raise HTTPException(400, "Add at least one photo.")
    if len(files) > settings.face_max_photos:
        raise HTTPException(400, f"At most {settings.face_max_photos} photos per request.")

    service = _service()
    embeddings, results = [], []
    for f in files:
        try:
            data = f.file.read(settings.max_upload_bytes + 1)
            validate_bytes(data, f.content_type, settings)
            embeddings.append(service.enrollment_embedding(decode_image(data)))
            results.append(PhotoResult(file=f.filename, ok=True))
        except (ImageError, EnrollError) as exc:
            reason = exc.detail if isinstance(exc, ImageError) else str(exc)
            results.append(PhotoResult(file=f.filename, ok=False, reason=reason))

    if not embeddings:
        detail = "; ".join(f"{r.file}: {r.reason}" for r in results)
        raise HTTPException(422, f"No usable photos. {detail}")

    person, created = store.get_or_create_person(name)
    store.add_embeddings(person.id, embeddings)
    logger.info("Enrolled %s (%s): %d/%d photos used",
                person.name, "new" if created else "existing", len(embeddings), len(files))
    return EnrollResponse(person=store.get_person(person.id), results=results)


@router.delete("/people/{person_id}", status_code=204, summary="Delete a person and their face data")
def delete_person(person_id: int, store: StoreDep):
    if not store.delete_person(person_id):
        raise HTTPException(404, f"Person {person_id} not found.")
