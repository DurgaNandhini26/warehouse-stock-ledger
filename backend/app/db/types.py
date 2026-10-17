"""Column types that keep money and quantities exact on every database.

SQLite has no real DECIMAL type (SQLAlchemy would round-trip through binary floats), so
decimals are stored as scaled integers: a quantity of 12.345 kg is stored as 12345 with
scale 3, a cost of Rs 41.2500 as 412500 with scale 4. The same representation is used on
PostgreSQL so both databases behave identically and SQL SUM() stays exact.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.types import TypeDecorator


class ScaledDecimal(TypeDecorator[Decimal]):
    impl = BigInteger
    cache_ok = True

    def __init__(self, scale: int) -> None:
        super().__init__()
        self.scale = scale

    def process_bind_param(self, value: Decimal | None, dialect) -> int | None:
        if value is None:
            return None
        scaled = Decimal(value).scaleb(self.scale)
        if scaled != scaled.to_integral_value():
            # Callers must quantize first; silently rounding here would hide a bug.
            raise ValueError(f"{value} has more than {self.scale} decimal places")
        return int(scaled)

    def process_result_value(self, value: int | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(int(value)).scaleb(-self.scale)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC; always hands back timezone-aware UTC datetimes (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use UTC-aware values")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
