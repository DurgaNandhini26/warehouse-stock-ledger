from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, status

from app.api import schemas
from app.api.deps import IdPath, Limit, Offset, OptionalId, SessionDep
from app.api.presenters import movement_out
from app.db import repositories as repo
from app.domain.enums import MovementType
from app.domain.errors import NotFound, RuleViolation
from app.domain.movements import MovementRequest, adjustment_request
from app.services.movements import post_movement, reverse_movement

router = APIRouter(tags=["movements"])
IST = ZoneInfo("Asia/Kolkata")


def _to_request(body: schemas.MovementCreate) -> MovementRequest:
    if isinstance(body, schemas.AdjustmentCreate):
        return adjustment_request(body.location_id, body.quantity, body.reason_code, body.reason)
    return MovementRequest(
        type=body.type,
        quantity=body.quantity,
        from_location_id=getattr(body, "from_location_id", None),
        to_location_id=getattr(body, "to_location_id", None),
        unit_cost=getattr(body, "unit_cost", None),
        reason=body.reason,
    )


def _row_or_404(session, movement_id: int):
    row = repo.get_movement_row(session, movement_id)
    if row is None:
        raise NotFound(
            f"movement {movement_id} does not exist",
            code="MOVEMENT_NOT_FOUND",
            details={"movement_id": movement_id},
        )
    return row


@router.post("/movements", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def create_movement(body: schemas.MovementCreate, session: SessionDep):
    """Post an IN, OUT, TRANSFER or ADJUSTMENT. The body's `type` selects the required fields."""
    movement = post_movement(
        session,
        body.product_id,
        _to_request(body),
        created_by=body.created_by,
        reference=body.reference,
    )
    return movement_out(_row_or_404(session, movement.id))


@router.get("/movements", response_model=schemas.Page[schemas.MovementOut])
def list_movements(
    session: SessionDep,
    product_id: OptionalId = None,
    location_id: OptionalId = None,
    type: MovementType | None = None,
    reference: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[date | None, Query(description="IST calendar date, inclusive")] = None,
    date_to: Annotated[date | None, Query(description="IST calendar date, inclusive")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    """Newest first. Dates are interpreted as calendar days in IST (Asia/Kolkata)."""
    if date_from and date_to and date_from > date_to:
        raise RuleViolation(
            "date_from must be on or before date_to", code="INVALID_DATE_RANGE", field="date_from"
        )
    filters = repo.MovementFilters(
        product_id=product_id,
        location_id=location_id,
        type=type.value if type else None,
        reference=reference,
        created_from=_ist_midnight(date_from) if date_from else None,
        created_before=_ist_midnight(date_to, next_day=True) if date_to else None,
    )
    rows, total = repo.list_movements(session, filters, limit, offset)
    return schemas.Page(
        items=[movement_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/movements/{movement_id}", response_model=schemas.MovementOut)
def get_movement(movement_id: IdPath, session: SessionDep):
    return movement_out(_row_or_404(session, movement_id))


@router.post(
    "/movements/{movement_id}/reversal",
    response_model=schemas.MovementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reversal(movement_id: IdPath, body: schemas.ReversalCreate, session: SessionDep):
    """Correct a mistake by posting its exact inverse. The original stays, marked as reversed."""
    reversal = reverse_movement(
        session, movement_id, reason=body.reason, created_by=body.created_by
    )
    return movement_out(_row_or_404(session, reversal.id))


def _ist_midnight(day: date, *, next_day: bool = False) -> datetime:
    if day.year < 2000 or day.year > 2999:
        raise RuleViolation("dates must be between years 2000 and 2999", code="INVALID_DATE_RANGE")
    if next_day:
        day += timedelta(days=1)
    return datetime.combine(day, time.min, tzinfo=IST)
