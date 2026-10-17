"""Posting and reversing movements: the only code paths that change stock.

Every call is one database transaction:
  1. lock the product row (serialises all movements of that product - rule 3 under concurrency)
  2. read the cached balances and average cost *after* the lock
  3. ask the pure domain layer for a plan (or a rule violation)
  4. insert ONE movement row, apply each balance delta, update the average cost
If anything in 2-4 fails the whole transaction rolls back (rule 4: a TRANSFER is all or nothing).
"""

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import repositories as repo
from app.db.models import Movement, Product
from app.db.session import transaction
from app.domain.enums import AdjustmentReason, MovementType, Unit
from app.domain.errors import AlreadyReversed, DomainError, NotFound
from app.domain.movements import (
    MovementRequest,
    PostedMovement,
    ProductState,
    plan_movement,
    reversal_request,
)
from app.services.catalog import location_not_found, product_not_found
from app.services.clock import utc_now

log = logging.getLogger(__name__)


def post_movement(
    session: Session,
    product_id: int,
    request: MovementRequest,
    *,
    created_by: str,
    reference: str | None = None,
    now: datetime | None = None,
) -> Movement:
    try:
        with transaction(session):
            product = repo.lock_product(session, product_id)
            if product is None:
                raise product_not_found(product_id)
            movement = _record(
                session,
                product,
                request,
                created_by=created_by,
                reference=reference,
                now=now,
                reverses=None,
            )
    except DomainError as exc:
        _log_rejection(exc, product_id=product_id, type=request.type.value)
        raise
    _log_posted(movement)
    return movement


def reverse_movement(
    session: Session,
    movement_id: int,
    *,
    reason: str,
    created_by: str,
    now: datetime | None = None,
) -> Movement:
    try:
        with transaction(session):
            original = repo.get_movement(session, movement_id)
            if original is None:
                raise NotFound(
                    f"movement {movement_id} does not exist",
                    code="MOVEMENT_NOT_FOUND",
                    details={"movement_id": movement_id},
                )
            # Lock first, then check "already reversed": two racing reversals queue on the lock
            # and the second one sees the first. The UNIQUE index is the backstop.
            product = repo.lock_product(session, original.product_id)
            assert product is not None  # FK guarantees it
            posted = _as_posted(original, repo.reversal_of(session, original.id))
            request = reversal_request(posted, reason)
            try:
                reversal = _record(
                    session,
                    product,
                    request,
                    created_by=created_by,
                    reference=original.reference,
                    now=now,
                    reverses=original.id,
                )
            except IntegrityError as exc:
                raise AlreadyReversed(
                    f"movement {movement_id} was already reversed",
                    details={"movement_id": movement_id},
                ) from exc
    except DomainError as exc:
        _log_rejection(exc, movement_id=movement_id, action="reverse")
        raise
    _log_posted(reversal)
    return reversal


def _record(
    session: Session,
    product: Product,
    request: MovementRequest,
    *,
    created_by: str,
    reference: str | None,
    now: datetime | None,
    reverses: int | None,
) -> Movement:
    location_ids = [i for i in (request.from_location_id, request.to_location_id) if i is not None]
    _ensure_locations_exist(session, request)

    state = ProductState(
        unit=Unit(product.unit),
        avg_cost=product.avg_cost,
        on_hand=repo.total_on_hand(session, product.id),
    )
    balances = repo.balances_for(session, product.id, location_ids)
    plan = plan_movement(request, state, balances, is_reversal=reverses is not None)

    movement = repo.insert_movement(
        session,
        type=request.type.value,
        product_id=product.id,
        from_location_id=request.from_location_id,
        to_location_id=request.to_location_id,
        quantity=request.quantity,
        unit_cost=plan.unit_cost,
        value=plan.value,
        reason_code=request.reason_code.value if request.reason_code else None,
        reason=request.reason.strip() if request.reason and request.reason.strip() else None,
        reference=reference.strip() if reference and reference.strip() else None,
        created_at=now or utc_now(),
        created_by=created_by.strip(),
        reverses_movement_id=reverses,
    )
    for location_id, delta in plan.deltas.items():
        repo.apply_balance_delta(session, product.id, location_id, delta)
    product.avg_cost = plan.new_avg_cost
    session.flush()
    return movement


def _ensure_locations_exist(session: Session, request: MovementRequest) -> None:
    wanted = {
        "from_location_id": request.from_location_id,
        "to_location_id": request.to_location_id,
    }
    present = repo.existing_location_ids(session, [v for v in wanted.values() if v is not None])
    for field, location_id in wanted.items():
        if location_id is not None and location_id not in present:
            raise location_not_found(location_id, field=field)


def _as_posted(movement: Movement, reversed_by: int | None) -> PostedMovement:
    return PostedMovement(
        id=movement.id,
        type=MovementType(movement.type),
        quantity=movement.quantity,
        from_location_id=movement.from_location_id,
        to_location_id=movement.to_location_id,
        unit_cost=movement.unit_cost,
        reason_code=AdjustmentReason(movement.reason_code) if movement.reason_code else None,
        reverses_movement_id=movement.reverses_movement_id,
        reversed_by_movement_id=reversed_by,
    )


def _log_posted(movement: Movement) -> None:
    log.info(
        "movement posted",
        extra={
            "ctx": {
                "movement_id": movement.id,
                "type": movement.type,
                "product_id": movement.product_id,
                "from_location_id": movement.from_location_id,
                "to_location_id": movement.to_location_id,
                "quantity": movement.quantity,
                "reverses_movement_id": movement.reverses_movement_id,
            }
        },
    )


def _log_rejection(exc: DomainError, **context: object) -> None:
    log.warning(
        "movement rejected",
        extra={"ctx": {"code": exc.code, "reason": exc.message, **context, **exc.details}},
    )
