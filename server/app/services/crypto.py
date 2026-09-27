"""Per-patient encryption (CONTRACTS.md §10.8).

Each patient gets a random 32-byte data key (DEK), wrapped with AES-256-GCM under MASTER_KEY_B64 and stored
base64 as nonce(12) + ciphertext in `patient_key`. Files are nonce(12) + AES-256-GCM(DEK) ciphertext.
Erasure destroys the wrapped key ("crypto-shredding"): every file for that patient becomes unreadable.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DB

from app import db as app_db
from app.config import settings
from app.errors import ApiError
from app.ids import utcnow
from app.models import PatientKey

NONCE = 12


def _master() -> AESGCM:
    try:
        key = base64.b64decode(settings.master_key_b64, validate=True)
    except ValueError as exc:
        raise ApiError(500, "server_misconfigured", "MASTER_KEY_B64 is not valid base64") from exc
    if len(key) != 32:
        raise ApiError(500, "server_misconfigured", "MASTER_KEY_B64 must decode to 32 bytes")
    return AESGCM(key)


def _erased() -> ApiError:
    return ApiError(410, "patient_erased", "This patient's data has been erased")


def seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def open_sealed(key: bytes, blob: bytes, aad: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:NONCE], blob[NONCE:], aad)


def _unwrap(row: PatientKey) -> bytes:
    if row.destroyed_at is not None or not row.wrapped_key:
        raise _erased()
    blob = base64.b64decode(row.wrapped_key)
    master = _master()
    return master.decrypt(blob[:NONCE], blob[NONCE:], row.patient_id.encode())


def data_key(patient_id: str, create: bool = True) -> bytes:
    """The patient's DEK, created on first use. Uses its own DB session so callers' transactions are untouched."""
    with DB(app_db.engine) as db:
        row = db.get(PatientKey, patient_id)
        if row is None:
            if not create:
                raise _erased()
            dek = os.urandom(32)
            nonce = os.urandom(NONCE)
            wrapped = nonce + _master().encrypt(nonce, dek, patient_id.encode())
            db.add(PatientKey(patient_id=patient_id, wrapped_key=base64.b64encode(wrapped).decode()))
            try:
                db.commit()
                return dek
            except IntegrityError:  # another request created it first — use theirs
                db.rollback()
                row = db.get(PatientKey, patient_id)
        return _unwrap(row)


def encrypt_for(patient_id: str, plaintext: bytes, aad: str) -> bytes:
    return seal(data_key(patient_id), plaintext, f"{patient_id}:{aad}".encode())


def decrypt_for(patient_id: str, blob: bytes, aad: str) -> bytes:
    try:
        return open_sealed(data_key(patient_id, create=False), blob, f"{patient_id}:{aad}".encode())
    except InvalidTag as exc:
        raise ApiError(500, "decrypt_failed", "Stored file failed its integrity check") from exc


def destroy_key(db: DB, patient_id: str) -> PatientKey:
    """Erase: clear the wrapped key and stamp destroyed_at (idempotent). Caller commits."""
    row = db.get(PatientKey, patient_id) or PatientKey(patient_id=patient_id)
    row.wrapped_key = None
    row.destroyed_at = row.destroyed_at or utcnow()
    db.add(row)
    return row
