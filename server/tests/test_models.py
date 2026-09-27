from datetime import date

from sqlmodel import Session, select

from app import models as m
from app.ids import new_id


def test_every_table_round_trips(db: Session) -> None:
    staff = m.Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", room="Room 1", pin_hash="x")
    patient = m.Patient(hospital_id="MK-000001", name="Kamla Devi", age=62, sex="F", language="hi")
    db.add_all([staff, patient])
    db.flush()
    session = m.Session(
        patient_id=patient.id, kiosk_id="KIOSK-01", informant="self", status="identifying", legal_basis="consent"
    )
    db.add(session)
    db.flush()
    fact = m.Fact(
        session_id=session.id,
        patient_id=patient.id,
        section="labs",
        key="haemoglobin",
        value={
            "test": "Haemoglobin",
            "value": 10.2,
            "unit": "g/dL",
            "ref_low": 12.0,
            "ref_high": 15.0,
            "flag": "low",
            "date": "2026-08-12",
        },
        text_en="Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW",
        trust="from_report",
        source_type="document",
        bbox=[120, 340, 400, 28],
    )
    db.add(fact)
    db.flush()
    rows = [
        m.Consent(
            session_id=session.id, capture=True, scan=True, share_hospital=True, link_abha=False, check_passed=True
        ),
        m.Token(
            display="A-001",
            prefix="A",
            number=1,
            day=date(2026, 10, 12),
            patient_id=patient.id,
            session_id=session.id,
            department="ayurveda",
            lane="normal",
            status="waiting",
            arrival_seq=1,
        ),
        m.Answer(
            session_id=session.id, question_id="jp_site", source="tap", slots={"site": "knee"}, status="confident"
        ),
        m.Document(session_id=session.id, patient_id=patient.id, file_path="docs/x.bin", ocr_json={"lines": []}),
        m.Readback(session_id=session.id, fact_id=fact.id, response="yes"),
        m.Alert(
            id=new_id(),
            kiosk_id="KIOSK-01",
            level="emergency",
            reason_code="chest_pain",
            reason_text="Emergency button: chest pain",
            source="button",
        ),
        m.Summary(session_id=session.id, version=1, payload={"session_id": session.id}),
        m.SectionView(session_id=session.id, staff_id=staff.id, section="hpi"),
        m.SectionApproval(session_id=session.id, staff_id=staff.id, section="hpi"),
        m.Diagnosis(
            session_id=session.id,
            staff_id=staff.id,
            codes=[{"system": "NAMASTE", "code": "SAMPLE-NAM-001", "display": "Sandhigata Vata"}],
        ),
        m.AuditLog(
            actor="system",
            action="test",
            entity="patient",
            entity_id=patient.id,
            details={"a": 1},
            prev_hash="0" * 64,
            hash="f" * 64,
        ),
        m.Outbox(
            session_id=session.id,
            patient_id=patient.id,
            payload={"resourceType": "Bundle"},
            idempotency_key=f"{session.id}:v1",
        ),
        m.PatientKey(patient_id=patient.id, wrapped_key="abc="),
        m.Setting(key="island_mode", value=False),
    ]
    db.add_all(rows)
    db.commit()

    for model in m.ALL_TABLES:
        assert db.exec(select(model)).first() is not None, model.__tablename__

    assert len(m.ALL_TABLES) == 18
    assert db.get(m.Fact, fact.id).value["flag"] == "low"
    assert db.get(m.Setting, "island_mode").value is False
    audit = db.exec(select(m.AuditLog)).one()
    assert isinstance(audit.id, int)
