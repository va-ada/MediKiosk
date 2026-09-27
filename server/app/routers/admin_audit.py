from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import col, select

from app import audit
from app.auth import current_staff
from app.db import DbSession
from app.models import AuditLog

router = APIRouter(prefix="/api/admin/audit", tags=["admin"], dependencies=[Depends(current_staff(["admin"]))])


@router.get("")
def list_audit(db: DbSession, limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
    rows = db.exec(select(AuditLog).order_by(col(AuditLog.id).desc()).limit(limit))
    return [audit.to_dict(r) for r in rows]


@router.get("/verify")
def verify(db: DbSession) -> dict[str, Any]:
    valid, checked, first_bad_id = audit.verify_chain(db)
    return {"valid": valid, "checked": checked, "first_bad_id": first_bad_id}
