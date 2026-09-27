from datetime import date
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlmodel import Session as DB
from sqlmodel import col, select

from app import audit
from app import db as app_db
from app.auth import current_staff, kiosk_id, kiosk_or_staff
from app.config import settings
from app.db import DbSession
from app.enums import DocStatus, DocType, Section, SessionStatus, SourceType, Trust
from app.errors import ApiError
from app.ids import iso_z, new_id
from app.models import Consent, Document, Fact, Staff
from app.routers.sessions import get_session_or_404
from app.services.files import load_file, store_file
from app.ws import hub

router = APIRouter(tags=["documents"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
NLP_TIMEOUT_SEC = 60
UPLOADABLE = {SessionStatus.triaged, SessionStatus.history, SessionStatus.documents, SessionStatus.verifying}
ENTITY_SECTION = {"lab": Section.labs.value, "drug": Section.drugs.value, "diagnosis": Section.pmh.value}
UNREADABLE_TEXT = "Unreadable — see image"


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def document_public(d: Document) -> dict[str, Any]:
    return {
        "id": d.id,
        "session_id": d.session_id,
        "patient_id": d.patient_id,
        "page_no": d.page_no,
        "doc_type": d.doc_type,
        "doc_date": d.doc_date.isoformat() if d.doc_date else None,
        "ocr_json": d.ocr_json,
        "status": d.status,
        "pinned": d.pinned,
        "created_at": iso_z(d.created_at),
        "image_url": f"/api/documents/{d.id}/image",
    }


def _latest_consent(db: DB, session_id: str) -> Consent | None:
    return db.exec(
        select(Consent).where(Consent.session_id == session_id).order_by(col(Consent.created_at).desc())
    ).first()


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def facts_from_entities(doc: Document, entities: list[dict[str, Any]]) -> list[Fact]:
    """Report entities → from_report facts. Unreadable ones are never guessed (rule 6)."""
    facts = []
    for e in entities:
        section = ENTITY_SECTION.get(e.get("kind"))
        if section is None:
            continue
        value = dict(e.get("value") or {})
        readable = bool(e.get("readable", True))
        if section == Section.drugs:
            value["found_in_documents"] = True
        if not readable:
            value["readable"] = False
        key = str(value.get("test") or value.get("name") or e.get("kind"))
        facts.append(
            Fact(
                session_id=doc.session_id,
                patient_id=doc.patient_id,
                section=section,
                key=key,
                value=value,
                text_en=e.get("text_en") if readable and e.get("text_en") else UNREADABLE_TEXT,
                trust=Trust.from_report.value,
                source_type=SourceType.document.value,
                source_id=doc.id,
                bbox=e.get("bbox"),
            )
        )
    return facts


def _is_abnormal_lab(f: Fact) -> bool:
    return f.section == Section.labs and str((f.value or {}).get("flag", "")).lower() in {"low", "high"}


def process_document(doc_id: str) -> None:
    """Background: OCR via NLP /document → Document fields + facts. Runs with its own DB session."""
    with DB(app_db.engine) as db:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        try:
            image = load_file(doc.patient_id, doc.file_path)
            res = httpx.post(
                f"{settings.nlp_url}/document",
                files={"image": ("page", image, sniff_image(image) or "")},
                timeout=NLP_TIMEOUT_SEC,
            )
            res.raise_for_status()
            out = res.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            doc.status = DocStatus.failed.value
            db.add(doc)
            audit.record(db, "system", "document.failed", "document", doc.id, {"error": type(exc).__name__})
            db.commit()
            hub.emit("queue", "document.processed", document_public(doc))
            return
        doc_type = out.get("doc_type")
        doc.doc_type = doc_type if doc_type in {t.value for t in DocType} else DocType.unknown.value
        doc.doc_date = _parse_date(out.get("doc_date"))
        doc.ocr_json = {"lines": out.get("lines") or [], "entities": out.get("entities") or []}
        facts = facts_from_entities(doc, out.get("entities") or [])
        db.add_all(facts)
        doc.pinned = doc.doc_type == DocType.discharge_summary or any(_is_abnormal_lab(f) for f in facts)
        doc.status = DocStatus.processed.value
        db.add(doc)
        db.flush()
        audit.record(
            db,
            "system",
            "document.process",
            "document",
            doc.id,
            {
                "doc_type": doc.doc_type,
                "doc_date": str(doc.doc_date) if doc.doc_date else None,
                "fact_ids": [f.id for f in facts],
                "unreadable": sum(1 for f in facts if f.text_en == UNREADABLE_TEXT),
            },
        )
        db.commit()
        db.refresh(doc)
        hub.emit("queue", "document.processed", document_public(doc))


@router.post("/api/sessions/{session_id}/documents")
def upload_document(
    session_id: str,
    db: DbSession,
    background: BackgroundTasks,
    kiosk: Annotated[str, Depends(kiosk_id)],
    image: Annotated[UploadFile, File()],
    page_no: Annotated[int, Form(ge=1, le=50)] = 1,
) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    if s.status not in {x.value for x in UPLOADABLE}:
        raise ApiError(409, "invalid_state", f"Session is {s.status}; documents can't be added now")
    consent = _latest_consent(db, s.id)
    if consent is None or not consent.scan or consent.revoked_at is not None:
        raise ApiError(403, "forbidden", "The patient did not agree to scanning reports")
    data = image.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(413, "too_large", "Image is larger than 10 MB")
    if sniff_image(data) is None:
        raise ApiError(422, "validation_error", "Image must be a JPEG or PNG photo")
    doc_id = new_id()
    rel = store_file(s.patient_id, f"docs/{doc_id}.bin", data)
    doc = Document(id=doc_id, session_id=s.id, patient_id=s.patient_id, file_path=rel, page_no=page_no)
    db.add(doc)
    db.flush()
    audit.record(
        db,
        f"kiosk:{kiosk}",
        "document.create",
        "document",
        doc.id,
        {"session_id": s.id, "page_no": page_no, "bytes": len(data)},
    )
    db.commit()
    db.refresh(doc)
    background.add_task(process_document, doc.id)
    return document_public(doc)


@router.get("/api/documents/{doc_id}")
def get_document(doc_id: str, db: DbSession, _actor: Annotated[str, Depends(kiosk_or_staff)]) -> dict[str, Any]:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise ApiError(404, "not_found", "Document not found")
    return document_public(doc)


@router.get("/api/documents/{doc_id}/image")
def get_document_image(doc_id: str, db: DbSession, _staff: Annotated[Staff, Depends(current_staff())]) -> Response:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise ApiError(404, "not_found", "Document not found")
    data = load_file(doc.patient_id, doc.file_path)  # S18: raises 410 patient_erased after erasure
    return Response(
        content=data, media_type=sniff_image(data) or "application/octet-stream", headers={"Cache-Control": "no-store"}
    )
