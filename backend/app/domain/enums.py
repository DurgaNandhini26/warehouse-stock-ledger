from enum import StrEnum


class Unit(StrEnum):
    KG = "kg"
    PCS = "pcs"
    LITRE = "litre"


class MovementType(StrEnum):
    IN = "IN"
    OUT = "OUT"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"


class AdjustmentReason(StrEnum):
    DAMAGED = "damaged"
    EXPIRED = "expired"
    COUNT_CORRECTION = "count_correction"
    THEFT = "theft"
    OTHER = "other"  # requires a free-text note
