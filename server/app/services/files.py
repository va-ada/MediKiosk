"""Patient files under DATA_DIR (documents, voice answers)."""

from pathlib import Path

from app.config import settings


def _path(patient_id: str, relpath: str) -> Path:
    base = (settings.data_dir / "patients" / patient_id).resolve()
    path = (base / relpath).resolve()
    if not path.is_relative_to(base):  # never let a crafted relpath escape the patient's folder
        raise ValueError(f"unsafe path: {relpath!r}")
    return path


def store_file(patient_id: str, relpath: str, data: bytes) -> str:
    # TODO(S18): encrypt with the patient's data key before writing.
    path = _path(patient_id, relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relpath


def load_file(patient_id: str, relpath: str) -> bytes:
    # TODO(S18): decrypt; 410 patient_erased once the key is destroyed.
    return _path(patient_id, relpath).read_bytes()
