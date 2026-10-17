"""Rule 2: balances are derived. The cache must always equal what the ledger says.

`reconcile(repair=False)` recomputes everything from the movements and reports drift without
changing anything. `reconcile(repair=True)` does the same under a lock on every product and
overwrites the cache (balances and average cost) with the recomputed values.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import repositories as repo
from app.db.session import transaction
from app.domain.valuation import weighted_average_cost
from app.services.clock import utc_now

log = logging.getLogger(__name__)
ZERO = Decimal(0)


@dataclass(frozen=True)
class BalanceDrift:
    product_id: int
    sku: str
    location_id: int
    location_code: str
    cached: Decimal
    expected: Decimal

    @property
    def difference(self) -> Decimal:
        return self.cached - self.expected


@dataclass(frozen=True)
class AverageCostDrift:
    product_id: int
    sku: str
    cached: Decimal
    expected: Decimal


@dataclass
class ReconciliationReport:
    checked_at: datetime
    balances_checked: int
    products_checked: int
    repaired: bool
    balance_drift: list[BalanceDrift] = field(default_factory=list)
    average_cost_drift: list[AverageCostDrift] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        return not self.balance_drift and not self.average_cost_drift


def replay_average_costs(session: Session) -> dict[int, Decimal]:
    """Recompute each product's average cost by replaying its movements in posting order."""
    on_hand: dict[int, Decimal] = defaultdict(lambda: ZERO)
    average: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for m in repo.all_movements_in_order(session):
        if m.type == "IN":
            average[m.product_id] = weighted_average_cost(
                on_hand[m.product_id], average[m.product_id], m.quantity, m.unit_cost or ZERO
            )
        if m.type != "TRANSFER":
            on_hand[m.product_id] += m.quantity if m.to_location_id is not None else -m.quantity
    return dict(average)


def reconcile(session: Session, *, repair: bool) -> ReconciliationReport:
    with transaction(session):
        all_products = repo.lock_all_products(session) if repair else repo.all_products(session)
        products = {p.id: p for p in all_products}
        locations = {loc.id: loc for loc in repo.all_locations(session)}
        expected = repo.expected_balances_from_movements(session)
        cached = repo.cached_balances(session)
        keys = sorted(set(expected) | set(cached))
        report = ReconciliationReport(
            checked_at=utc_now(),
            balances_checked=len(keys),
            products_checked=len(products),
            repaired=repair,
        )

        for pid, lid in keys:
            want, have = expected.get((pid, lid), ZERO), cached.get((pid, lid), ZERO)
            if want != have:
                report.balance_drift.append(
                    BalanceDrift(pid, products[pid].sku, lid, locations[lid].code, have, want)
                )
                if repair:
                    repo.set_cached_balance(session, pid, lid, want)

        replayed = replay_average_costs(session)
        for pid, product in products.items():
            want = replayed.get(pid, ZERO)
            if product.avg_cost != want:
                report.average_cost_drift.append(
                    AverageCostDrift(pid, product.sku, product.avg_cost, want)
                )
                if repair:
                    product.avg_cost = want

    level = logging.WARNING if not report.consistent else logging.INFO
    log.log(
        level,
        "reconciliation repaired drift"
        if repair and not report.consistent
        else "reconciliation run",
        extra={
            "ctx": {
                "repair": repair,
                "balances_checked": report.balances_checked,
                "balance_drift": len(report.balance_drift),
                "average_cost_drift": len(report.average_cost_drift),
            }
        },
    )
    return report
