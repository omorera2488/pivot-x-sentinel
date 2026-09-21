"""BOT-051.3 -- canonical SignalQualityVectorV1 producer.

Formalizes the schema frozen in `reports/BOT-051.2-signal-quality-contract.json`
as importable, runnable Python types -- this is the "one obvious code path"
that answers: "at the instant this LIMIT was born, what was its Signal
Quality vector?"

This module does NOT compute Momentum/Alignment/Structure/Context from raw
market data -- it assembles and validates an already-computed observation
into the frozen typed vector. Feature computation stays where each factor's
own frozen contract already lives (offline research scripts for now; see
`reports/BOT-051.3-signal-quality-vector-shadow-observability.md` section 10
for why this is NOT wired into `strategy/`/`execution/` in this task --
ATR-Wilder, needed by Momentum and Structure, does not exist anywhere in
production code today, and introducing it there is out of scope for a
shadow/observational ticket).

Design contract (frozen in BOT-051.2, reproduced here as the single
canonical implementation, not reinterpreted):

  - Exactly four quality dimensions: momentum, alignment, structure, context.
  - Economics is absent -- there is no field for it, not null, not UNAVAILABLE.
  - direction is required metadata, never a quality factor.
  - FactorObservation[T] is the single availability wrapper for all four
    factors: status derives 1:1 from each factor's own frozen contract
    (never a second independent judgment); value is present and non-null
    iff status == AVAILABLE, and None iff status == UNAVAILABLE.
  - The vector is immutable (frozen dataclasses) -- SQ(t0) cannot be mutated
    after construction, by design, not just by convention.
  - No outcome field exists anywhere in this module -- there is no pnl_r,
    pnl_usd, outcome, fill status, MFE, MAE, or trade-duration field in
    either dataclass, by construction (not merely "unused").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, Optional, TypeVar

SCHEMA_VERSION = "1.0.0"

ALIGNMENT_STATES = frozenset({
    "AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL",
    "ALIGNED_SINGLE", "ALIGNED_CONFIRMED",
})
WEEKDAY_STATES = frozenset({
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
})

T = TypeVar("T")


@dataclass(frozen=True)
class FactorObservation(Generic[T]):
    """Single canonical availability wrapper, frozen in BOT-051.2 section 4.

    status is a projection of the factor's own frozen contract, never a
    second source of truth -- for Alignment specifically, whose own enum
    (BOT-047.2.3) already includes UNAVAILABLE as one of its 6 states,
    status=UNAVAILABLE iff raw_state=="UNAVAILABLE", status=AVAILABLE for
    the other 5 substantive states (including NEUTRAL, which is a REAL
    OBSERVED VALUE, never conflated with UNAVAILABLE).
    """
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    value: Optional[T]

    def __post_init__(self) -> None:
        if self.status == "AVAILABLE" and self.value is None:
            raise ValueError("FactorObservation: status=AVAILABLE requires a non-null value")
        if self.status == "UNAVAILABLE" and self.value is not None:
            raise ValueError("FactorObservation: status=UNAVAILABLE must have value=None (never a numeric sentinel)")


@dataclass(frozen=True)
class SignalQualityVectorV1:
    """Frozen in reports/BOT-051.2-signal-quality-contract.json. Exactly
    four quality dimensions plus direction as required metadata. Economics
    is absent by design -- there is no field for it here."""
    schema_version: str
    observed_at_bar: int
    observed_at_time_utc: datetime
    direction: Literal["LONG", "SHORT"]
    momentum: FactorObservation[float]
    alignment: FactorObservation[str]
    structure: FactorObservation[float]
    context: FactorObservation[str]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unexpected schema_version {self.schema_version!r}, expected {SCHEMA_VERSION!r}")
        if self.direction not in ("LONG", "SHORT"):
            raise ValueError(f"direction must be LONG or SHORT, got {self.direction!r}")
        if self.alignment.status == "AVAILABLE" and self.alignment.value not in ALIGNMENT_STATES:
            raise ValueError(f"alignment.value {self.alignment.value!r} is not one of the 5 substantive frozen states")
        if self.context.status == "AVAILABLE" and self.context.value not in WEEKDAY_STATES:
            raise ValueError(f"context.value {self.context.value!r} is not a valid weekday")


def _float_observation(raw_value) -> FactorObservation[float]:
    """Momentum/Structure: continuous RAW, UNAVAILABLE iff the source value is NaN/None."""
    import math
    if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=float(raw_value))


def _alignment_observation(raw_state: str) -> FactorObservation[str]:
    """Alignment: status is a 1:1 projection of the factor's own frozen enum,
    never a second judgment -- raw_state=="UNAVAILABLE" is the ONLY source
    of truth for unavailability here."""
    if raw_state == "UNAVAILABLE":
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=raw_state)


def _context_observation(raw_weekday) -> FactorObservation[str]:
    """Context: no UNAVAILABLE case documented in the frozen contract
    (time_utc always available) -- still guarded defensively, never silently
    imputed."""
    if raw_weekday is None or (isinstance(raw_weekday, float)):
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=str(raw_weekday))


def produce_signal_quality_vector(
    *,
    observed_at_bar: int,
    observed_at_time_utc: datetime,
    direction: Literal["LONG", "SHORT"],
    roc_atr_3: Optional[float],
    alignment_consensus_state: str,
    origin_dist_atr: Optional[float],
    weekday: Optional[str],
) -> SignalQualityVectorV1:
    """The one canonical assembly path. Accepts already-computed causal
    values for the four frozen factors (never recomputes a feature itself)
    and returns an immutable, validated SignalQualityVectorV1.

    Deterministic: identical inputs always produce a vector that compares
    equal (dataclasses with frozen=True get structural __eq__ for free).
    Contains no outcome field by construction -- there is nowhere to pass
    pnl_r/pnl_usd/outcome/fill/MFE/MAE into this function even by mistake.
    """
    return SignalQualityVectorV1(
        schema_version=SCHEMA_VERSION,
        observed_at_bar=observed_at_bar,
        observed_at_time_utc=observed_at_time_utc,
        direction=direction,
        momentum=_float_observation(roc_atr_3),
        alignment=_alignment_observation(alignment_consensus_state),
        structure=_float_observation(origin_dist_atr),
        context=_context_observation(weekday),
    )


def produce_from_row(row) -> SignalQualityVectorV1:
    """Convenience constructor from a pandas Series / dict-like row shaped
    like reports/BOT-051.3-signal-quality-vector-shadow-xau.csv."""
    import pandas as pd
    return produce_signal_quality_vector(
        observed_at_bar=int(row["limit_created_bar"]),
        observed_at_time_utc=pd.Timestamp(row["limit_created_time_utc"]).to_pydatetime(),
        direction=row["direction"],
        roc_atr_3=row["roc_atr_3"] if pd.notna(row["roc_atr_3"]) else None,
        alignment_consensus_state=row["alignment"],
        origin_dist_atr=row["origin_dist_atr"] if pd.notna(row["origin_dist_atr"]) else None,
        weekday=row["weekday"] if pd.notna(row["weekday"]) else None,
    )
