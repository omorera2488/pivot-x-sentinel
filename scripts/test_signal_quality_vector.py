"""BOT-051.3 -- tests for the SignalQualityVectorV1 producer/schema.

Run as a plain script (project convention, no pytest installed):
    .venv/Scripts/python.exe scripts/test_signal_quality_vector.py
"""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from signal_quality_vector import (  # noqa: E402
    SCHEMA_VERSION, FactorObservation, SignalQualityVectorV1, produce_signal_quality_vector,
)

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def make_vector(**overrides) -> SignalQualityVectorV1:
    defaults = dict(
        observed_at_bar=12345,
        observed_at_time_utc=datetime(2026, 9, 18, 10, 5, 0),
        direction="LONG",
        roc_atr_3=0.42,
        alignment_consensus_state="ALIGNED_SINGLE",
        origin_dist_atr=0.68,
        weekday="Friday",
    )
    defaults.update(overrides)
    return produce_signal_quality_vector(**defaults)


def main() -> int:
    print("=== A. Schema ===")
    v = make_vector()
    quality_fields = {"momentum", "alignment", "structure", "context"}
    all_fields = {f.name for f in dataclasses.fields(v)}
    check("exactly four quality dimensions", quality_fields <= all_fields and len(quality_fields) == 4)
    check("Economics is absent from the schema (no field of any name/casing)",
          not any("econom" in f.lower() for f in all_fields), f"fields={all_fields}")
    check("direction is required and present", v.direction in ("LONG", "SHORT"))
    check("schema_version is fixed to 1.0.0", v.schema_version == SCHEMA_VERSION)

    def _bad_schema_version() -> None:
        SignalQualityVectorV1(
            schema_version="9.9.9", observed_at_bar=1, observed_at_time_utc=datetime.utcnow(),
            direction="LONG",
            momentum=FactorObservation(status="AVAILABLE", value=0.1),
            alignment=FactorObservation(status="AVAILABLE", value="ALIGNED_SINGLE"),
            structure=FactorObservation(status="AVAILABLE", value=0.1),
            context=FactorObservation(status="AVAILABLE", value="Friday"),
        )

    check("rejects an unexpected schema_version", _raises(_bad_schema_version))

    try:
        SignalQualityVectorV1(
            schema_version=SCHEMA_VERSION, observed_at_bar=1, observed_at_time_utc=datetime.utcnow(),
            direction="SIDEWAYS",  # invalid on purpose
            momentum=FactorObservation(status="AVAILABLE", value=0.1),
            alignment=FactorObservation(status="AVAILABLE", value="ALIGNED_SINGLE"),
            structure=FactorObservation(status="AVAILABLE", value=0.1),
            context=FactorObservation(status="AVAILABLE", value="Friday"),
        )
        rejected_bad_direction = False
    except ValueError:
        rejected_bad_direction = True
    check("rejects an invalid direction value", rejected_bad_direction)

    print("\n=== B. Availability semantics ===")
    avail = FactorObservation(status="AVAILABLE", value=0.42)
    check("AVAILABLE => value != null", avail.value is not None)
    unavail = FactorObservation(status="UNAVAILABLE", value=None)
    check("UNAVAILABLE => value == null", unavail.value is None)
    try:
        FactorObservation(status="AVAILABLE", value=None)
        rejected = False
    except ValueError:
        rejected = True
    check("rejects AVAILABLE with a null value (no silent gap)", rejected)
    try:
        FactorObservation(status="UNAVAILABLE", value=0.0)
        rejected2 = False
    except ValueError:
        rejected2 = True
    check("rejects UNAVAILABLE carrying a numeric sentinel (e.g. 0.0)", rejected2)

    v_neutral = make_vector(alignment_consensus_state="NEUTRAL")
    check("Alignment NEUTRAL remains AVAILABLE (real observed value, not missing)",
          v_neutral.alignment.status == "AVAILABLE" and v_neutral.alignment.value == "NEUTRAL")
    v_unavail_align = make_vector(alignment_consensus_state="UNAVAILABLE")
    check("Alignment UNAVAILABLE maps to wrapper UNAVAILABLE",
          v_unavail_align.alignment.status == "UNAVAILABLE" and v_unavail_align.alignment.value is None)

    v_no_momentum = make_vector(roc_atr_3=None)
    check("missing continuous Momentum value -> UNAVAILABLE, never a numeric sentinel",
          v_no_momentum.momentum.status == "UNAVAILABLE" and v_no_momentum.momentum.value is None)
    v_no_structure = make_vector(origin_dist_atr=float("nan"))
    check("NaN Structure value -> UNAVAILABLE (NaN treated as missing, not as 0)",
          v_no_structure.structure.status == "UNAVAILABLE" and v_no_structure.structure.value is None)

    print("\n=== C. Causality / immutability ===")
    v2 = make_vector(observed_at_bar=999)
    check("producer stores the given observed_at_bar verbatim (no fill_bar/future bar substituted)",
          v2.observed_at_bar == 999)
    try:
        v2.momentum = FactorObservation(status="AVAILABLE", value=9.99)  # type: ignore[misc]
        mutated = True
    except dataclasses.FrozenInstanceError:
        mutated = False
    check("vector is immutable -- mutating a field after construction raises", not mutated)
    try:
        v2.alignment.value = "AGAINST_CONFIRMED"  # type: ignore[misc]
        mutated_inner = True
    except dataclasses.FrozenInstanceError:
        mutated_inner = False
    check("nested FactorObservation is also immutable", not mutated_inner)

    print("\n=== D. Determinism / serialization ===")
    a = make_vector(observed_at_bar=42)
    b = make_vector(observed_at_bar=42)
    check("two calls with identical inputs produce structurally equal vectors", a == b)
    c = make_vector(observed_at_bar=43)
    check("a different observed_at_bar produces a different vector", a != c)

    print("\n=== E. No-outcome-leakage (structural) ===")
    forbidden_terms = {"pnl", "pnl_r", "pnl_usd", "outcome", "win", "loss", "fill_bar",
                        "mfe", "mae", "close_reason", "tp_hit", "sl_hit", "duration"}
    lowered_fields = {f.lower() for f in all_fields}
    leaked = forbidden_terms & lowered_fields
    check("no outcome-shaped field exists anywhere on SignalQualityVectorV1", not leaked, f"leaked={leaked}")
    fo_fields = {f.name.lower() for f in dataclasses.fields(FactorObservation)}
    leaked_fo = forbidden_terms & fo_fields
    check("no outcome-shaped field exists anywhere on FactorObservation", not leaked_fo, f"leaked={leaked_fo}")

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
