from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.auth import current_staff
from app.models import Staff
from app.services import terminology

router = APIRouter(prefix="/api/terminology", tags=["terminology"])


@router.get("/search")
def search(
    _doctor: Annotated[Staff, Depends(current_staff(["doctor"]))],
    q: Annotated[str, Query(max_length=100)] = "",
    system: Annotated[Literal["NAMASTE", "ICD11_TM2", "ICD10"] | None, Query()] = None,
) -> list[dict[str, Any]]:
    return terminology.search(q, system)
