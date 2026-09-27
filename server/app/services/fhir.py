"""FHIR R4 bundle for the mock HIS (CONTRACTS.md §8, §10.6).

fhir.resources v7+ defaults to R5 models; we validate against the R4B package (matches ABDM's R4 for these
resources). Identifier/code systems are neutral `urn:medikiosk:*` placeholders — swap in the official ABDM /
NAMASTE system URIs when the real integration is built. Rejected facts never leave the hospital.
"""

import html
from typing import Any

from fhir.resources.R4B.bundle import Bundle
from sqlmodel import Session as DB
from sqlmodel import col, select

from app.enums import AnswerStatus, Section, Trust
from app.ids import iso_z, new_id, utcnow
from app.models import Answer, Diagnosis, Fact, Outbox, Patient, Session, Staff
from app.services import graph, summary, tokens

TRUST_SYSTEM = "urn:medikiosk:trust"
HOSPITAL_ID_SYSTEM = "urn:medikiosk:hospital-id"
ABHA_SYSTEM = "urn:medikiosk:abha-number"
CODE_SYSTEMS = {
    "NAMASTE": "urn:medikiosk:namaste",
    "ICD11_TM2": "urn:medikiosk:icd11-tm2",
    "ICD10": "urn:medikiosk:icd10",
}
INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
GENDER = {"M": "male", "F": "female", "O": "other"}


def _meta(trust: str) -> dict[str, Any]:
    return {"tag": [{"system": TRUST_SYSTEM, "code": trust}]}


def _ref(resource: dict[str, Any]) -> dict[str, str]:
    return {"reference": f"urn:uuid:{resource['id']}"}


def _res(kind: str, trust: str, **fields: Any) -> dict[str, Any]:
    return {"resourceType": kind, "id": new_id(), "meta": _meta(trust), **fields}


def _answer_values(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    out = []
    for v in values:
        if isinstance(v, bool):
            out.append({"valueBoolean": v})
        elif isinstance(v, int):
            out.append({"valueInteger": v})
        elif isinstance(v, float):
            out.append({"valueDecimal": v})
        elif v is not None:
            out.append({"valueString": str(v)})
    return out


def _lab_observation(f: Fact, patient_ref: dict, encounter_ref: dict) -> dict[str, Any]:
    v = f.value or {}
    obs: dict[str, Any] = {
        "status": "final",
        "category": [{"text": "laboratory"}],
        "code": {"text": str(v.get("test") or f.key)},
        "subject": patient_ref,
        "encounter": encounter_ref,
        "note": [{"text": f.text_en}],
    }
    if isinstance(v.get("value"), int | float) and not isinstance(v.get("value"), bool):
        obs["valueQuantity"] = {"value": v["value"], **({"unit": v["unit"]} if v.get("unit") else {})}
    else:
        obs["valueString"] = f.text_en
    rng: dict[str, Any] = {}
    for bound in ("low", "high"):
        if isinstance(v.get(f"ref_{bound}"), int | float):
            rng[bound] = {"value": v[f"ref_{bound}"], **({"unit": v["unit"]} if v.get("unit") else {})}
    if rng:
        obs["referenceRange"] = [rng]
    code = {"low": "L", "high": "H", "normal": "N"}.get(str(v.get("flag", "")).lower())
    if code:
        obs["interpretation"] = [{"coding": [{"system": INTERPRETATION, "code": code}]}]
    if v.get("date"):
        obs["effectiveDateTime"] = str(v["date"])
    return obs


def _div(text: str) -> dict[str, str]:
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{text}</div>'}


def build_bundle(db: DB, session: Session) -> dict[str, Any]:
    patient = db.get(Patient, session.patient_id)
    token = tokens.latest_token(db, session.id)
    doctor = db.get(Staff, token.doctor_id) if token and token.doctor_id else None
    facts = [
        f
        for f in db.exec(select(Fact).where(Fact.session_id == session.id).order_by(col(Fact.created_at)))
        if f.trust != Trust.rejected
    ]

    identifiers = [{"system": HOSPITAL_ID_SYSTEM, "value": patient.hospital_id}]
    if patient.abha_number:
        identifiers.append({"system": ABHA_SYSTEM, "value": patient.abha_number})
    p = _res(
        "Patient",
        Trust.patient_said.value,
        identifier=identifiers,
        name=[{"text": patient.name}],
        gender=GENDER.get(patient.sex, "unknown"),
        communication=[{"language": {"text": "Hindi" if patient.language == "hi" else "English"}}],
    )
    p_ref = _ref(p)
    period = {"start": iso_z(session.created_at)}
    if session.closed_at:
        period["end"] = iso_z(session.closed_at)
    enc = _res(
        "Encounter",
        Trust.doctor_verified.value,
        status="finished" if session.closed_at else "in-progress",
        **{
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory",
            }
        },
        subject=p_ref,
        period=period,
        serviceType={"text": session.department or "general"},
    )
    e_ref = _ref(enc)
    resources: list[dict[str, Any]] = [p, enc]

    for f in facts:
        if f.key == "chief_complaint":
            resources.append(
                _res(
                    "Condition",
                    f.trust,
                    subject=p_ref,
                    encounter=e_ref,
                    code={"text": f.text_en},
                    category=[{"text": "chief complaint"}],
                    **({"note": [{"text": f.patient_words}]} if f.patient_words else {}),
                )
            )
        elif f.section == Section.allergies and not (f.key == "allergy" and (f.value or {}).get("value") is False):
            resources.append(
                _res(
                    "AllergyIntolerance",
                    f.trust,
                    patient=p_ref,
                    encounter=e_ref,
                    code={
                        "text": str((f.value or {}).get("value") or f.text_en)
                        if f.key == "allergy_detail"
                        else f.text_en
                    },
                )
            )
        elif f.section == Section.drugs:
            v = f.value or {}
            dosage = ", ".join(str(v[k]) for k in ("dose", "frequency", "duration") if v.get(k))
            resources.append(
                _res(
                    "MedicationStatement",
                    f.trust,
                    status="unknown",
                    subject=p_ref,
                    context=e_ref,
                    medicationCodeableConcept={"text": str(v.get("name") or f.text_en)},
                    informationSource={"display": "report" if v.get("found_in_documents") else "patient"},
                    **({"dosage": [{"text": dosage}]} if dosage else {}),
                )
            )
        elif f.section == Section.labs:
            resources.append(_res("Observation", f.trust, **_lab_observation(f, p_ref, e_ref)))
        elif f.section == Section.ayush and f.source_type == "doctor":
            resources.append(
                _res(
                    "Observation",
                    f.trust,
                    status="final",
                    category=[{"text": "exam"}],
                    code={"text": f.key.removeprefix("exam_").capitalize()},
                    subject=p_ref,
                    encounter=e_ref,
                    valueString=f.text_en,
                )
            )

    for d in db.exec(select(Diagnosis).where(Diagnosis.session_id == session.id).order_by(col(Diagnosis.created_at))):
        code: dict[str, Any] = {
            "coding": [
                {
                    "system": CODE_SYSTEMS.get(c["system"], "urn:medikiosk:unknown"),
                    "code": c["code"],
                    "display": c["display"],
                }
                for c in d.codes
            ]
        }
        if d.text:
            code["text"] = d.text
        resources.append(
            _res(
                "Condition",
                Trust.doctor_verified.value,
                subject=p_ref,
                encounter=e_ref,
                code=code,
                category=[{"text": "encounter diagnosis"}],
            )
        )

    # Answers whose facts the doctor rejected stay in the hospital too (rule: rejected facts never leave).
    rejected_answers = set(
        db.exec(
            select(Fact.source_id).where(
                Fact.session_id == session.id, Fact.trust == Trust.rejected, Fact.source_type == "answer"
            )
        ).all()
    )
    items = []
    for a in db.exec(
        select(Answer)
        .where(Answer.session_id == session.id, Answer.status == AnswerStatus.confident)
        .order_by(col(Answer.created_at))
    ):
        if a.id in rejected_answers:
            continue
        found = graph.get_graph().question(a.question_id)
        for name, value in (a.slots or {}).items():
            answers = _answer_values(value)
            if answers:
                items.append(
                    {
                        "linkId": f"{a.question_id}.{name}" if a.question_id == "triage" else a.question_id,
                        "text": found[1]["text_en"] if found else name,
                        "answer": answers,
                    }
                )
    qr_trust = Trust.patient_said.value
    resources.append(
        _res(
            "QuestionnaireResponse",
            qr_trust,
            status="completed",
            subject=p_ref,
            encounter=e_ref,
            authored=iso_z(session.submitted_at or session.created_at),
            item=items or None,
        )
    )

    latest, _ = summary.store_if_changed(db, session)  # never compose from a stale summary
    sections = []
    for sec in (latest.payload.get("sections") if latest else []) or []:
        lines = [html.escape(i["text"]) for i in sec.get("items", [])]
        if sec.get("narrative"):
            lines.insert(0, html.escape(sec["narrative"]))
        if lines:
            sections.append({"title": sec["title"], "text": _div("<br/>".join(lines))})
    resources.append(
        _res(
            "Composition",
            Trust.doctor_verified.value,
            status="final",
            type={"text": "OPD case history"},
            subject=p_ref,
            encounter=e_ref,
            date=iso_z(utcnow()),
            author=[{"display": doctor.name if doctor else "MediKiosk"}],
            title=f"OPD history — {patient.name}",
            section=sections or None,
        )
    )

    bundle = {
        "resourceType": "Bundle",
        "id": new_id(),
        "type": "collection",
        "timestamp": iso_z(utcnow()),
        "entry": [
            {"fullUrl": f"urn:uuid:{r['id']}", "resource": {k: v for k, v in r.items() if v is not None}}
            for r in resources
        ],
    }
    Bundle.model_validate(bundle)  # raises if anything is not valid FHIR R4B
    return bundle


def enqueue_bundle(db: DB, session: Session) -> Outbox:
    """Queue the bundle for the outbox worker (§10.6). Idempotent per summary version. Does not commit."""
    row, _ = summary.store_if_changed(db, session)
    key = f"{session.id}:v{row.version}"
    existing = db.exec(select(Outbox).where(Outbox.idempotency_key == key)).first()
    if existing:
        return existing
    ob = Outbox(
        kind="fhir_bundle",
        session_id=session.id,
        patient_id=session.patient_id,
        payload=build_bundle(db, session),
        idempotency_key=key,
        status="pending",
        next_attempt_at=utcnow(),
    )
    db.add(ob)
    db.flush()
    return ob
