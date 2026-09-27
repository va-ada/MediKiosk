"""Patient files under DATA_DIR (documents, voice answers), encrypted per patient (§10.8)."""

from pathlib import Path

from app.config import settings
from app.errors import ApiError
from app.services import crypto


def _path(patient_id: str, relpath: str) -> Path:
    base = (settings.data_dir / "patients" / patient_id).resolve()
    path = (base / relpath).resolve()
    if not path.is_relative_to(base):  # never let a crafted relpath escape the patient's folder
        raise ValueError(f"unsafe path: {relpath!r}")
    return path


def store_file(patient_id: str, relpath: str, data: bytes) -> str:
    """Encrypt with the patient's data key and write nonce + ciphertext. 410 if the patient was erased."""
    path = _path(patient_id, relpath)
    blob = crypto.encrypt_for(patient_id, data, relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return relpath


def load_file(patient_id: str, relpath: str) -> bytes:
    """Decrypt. 410 `patient_erased` once the key is destroyed; 404 if the file is gone."""
    path = _path(patient_id, relpath)
    if not path.exists():
        raise ApiError(404, "not_found", "File not found")
    return crypto.decrypt_for(patient_id, path.read_bytes(), relpath)
