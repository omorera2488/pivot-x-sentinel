"""BOT-052.2 Phase 9 -- OOS bridge for HCH shadow observations.

Reproducible, read-only, deterministic (same inputs -> same CSV, ordered by
ticket): joins the `hch` snapshot captured at t0 (`execution/src/bot.py` via
`strategy/hch.py::hch_state_for_signal()`, persisted by
`execution/src/score_store.py`) with its `OutcomeObservation`
(`execution/src/outcome_store.py`) by `ticket`, exactly the same join
identity BOT-051.5 already established for Signal Quality
(`execution/src/signal_quality_oos_dataset.py`).

The `hch` field did not exist on any ticket before this commit -- every row
this module ever surfaces is therefore intrinsically OOS relative to
BOT-052.1's historical discovery (frozen on data through 2026-09-15,
`reports/BOT-052.1-confluence-reader-historical-discovery.md`). No separate
date cutoff is needed or used: `"hch" in row` IS the precise boundary,
sharper than any hardcoded timestamp would be.

This module NEVER declares success/failure, NEVER computes a p-value/bootstrap
CI, and NEVER recommends adding HCH to a gate -- it only accumulates and
reports counts/cohort stats so BOT-052.3 (blocked on OOS, see BACKLOG.md) has
something to analyze once N is meaningful. Per-cohort stats (WR/PF/ExpR/PnL)
are computed with the SAME formula as
`scripts/discover_confluence_reader_xau.py::cohort_stats()` (BOT-052.1) for
direct comparability against the historical HCH/NO_HCH numbers in that
report, using the live `pnl_net`/`realized_r` fields
(`execution/src/outcome_store.py`) instead of the historical CSV's
`pnl_usd`/`pnl_r`. Win/loss classification uses `pnl_net > 0` / `< 0`, the
same convention `execution/src/bot.py::_aciertos_pct()` and
`panel/app.js::closedTrades()` already use -- never `close_reason`, which
encodes the MT5 deal reason code (TP/SL/CLIENT/...), not the P&L sign.

Module of library functions -- imported by
`scripts/build_hch_oos_dataset.py` (CLI wrapper, `main()` only). Retains the
raw Signal Quality factor values (momentum/alignment/structure/context) on
each row so a future HCH x Signal Quality interaction analysis (BOT-052.3)
never has to recompute anything -- it only joins on `ticket` again.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from . import score_store, outcome_store

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"

HCH_STATES = ("HCH", "NO_HCH", "UNAVAILABLE")

# Documented for context only (see module docstring) -- NOT used as a filter.
# BOT-052.1's historical discovery used data through this date; every row
# this module surfaces postdates it by construction (the `hch` field itself
# did not exist in production before BOT-052.2).
HCH_HISTORICAL_DISCOVERY_CUTOFF_UTC = "2026-09-15"


def _row_for_ticket(ticket: int, raw: dict, outcome: dict | None) -> dict:
    hch = raw.get("hch") or {}
    sq = raw.get("signal_quality") or {}
    outcome = outcome or {}

    momentum = sq.get("momentum") or {}
    alignment = sq.get("alignment") or {}
    structure = sq.get("structure") or {}
    context = sq.get("context") or {}

    order_final_state = outcome.get("order_final_state")
    filled = order_final_state == "FILLED"
    pnl_net = outcome.get("pnl_net")
    closed = filled and outcome.get("close_time_utc") is not None and pnl_net is not None

    realized_r = outcome.get("realized_r")
    realized_r_numeric = realized_r if isinstance(realized_r, (int, float)) else None

    outcome_label = None
    if closed:
        outcome_label = "win" if pnl_net > 0 else ("loss" if pnl_net < 0 else "tie")

    return {
        # identity
        "order_ticket": ticket,
        "position_id": outcome.get("position_id"),
        "direction": sq.get("direction"),
        "limit_created_time_utc": sq.get("observed_at_time_utc") or hch.get("hch_captured_at"),
        # hch (t0, never recomputed -- see strategy/hch.py::hch_state_for_signal)
        "hch_state": hch.get("hch_state"),
        "hch_version": hch.get("hch_version"),
        "hch_captured_at": hch.get("hch_captured_at"),
        "hch_pivot_1": hch.get("hch_pivot_1"),
        "hch_pivot_2": hch.get("hch_pivot_2"),
        "hch_pivot_3": hch.get("hch_pivot_3"),
        "hch_active_level": hch.get("hch_active_level"),
        "hch_formation_bar": hch.get("hch_formation_bar"),
        "hch_consumed_on_signal_bar": hch.get("hch_consumed_on_signal_bar"),
        # raw Signal Quality factor values, retained for future interaction
        # analysis (BOT-052.3) -- joined here, never redefined.
        "momentum_status": momentum.get("status"),
        "roc_atr_3": momentum.get("value"),
        "alignment_status": alignment.get("status"),
        "alignment": alignment.get("value"),
        "structure_status": structure.get("status"),
        "origin_dist_atr": structure.get("value"),
        "context_status": context.get("status"),
        "weekday": context.get("value"),
        # lifecycle
        "order_final_state": order_final_state,
        "filled": filled,
        "fill_time_utc": outcome.get("fill_time_utc"),
        "closed": closed,
        "close_time_utc": outcome.get("close_time_utc"),
        # evaluation only -- NEVER used to define/redefine hch_state above
        "pnl_net": pnl_net,
        "realized_r": realized_r_numeric,
        "close_reason": outcome.get("close_reason"),
        "outcome": outcome_label,
    }


def build_dataset(symbol: str, magic: int) -> pd.DataFrame:
    """Every ticket whose t0 snapshot carries an `hch` key -- i.e. every
    LIMIT captured since BOT-052.2 went live. Ordered by ticket for
    determinism."""
    raw_all = score_store.load_all_raw(symbol, magic)
    outcomes = outcome_store.load_all(symbol, magic)
    tickets = sorted(t for t, row in raw_all.items() if "hch" in row)
    rows = [_row_for_ticket(t, raw_all[t], outcomes.get(t)) for t in tickets]
    return pd.DataFrame(rows)


def cohort_stats(g: pd.DataFrame) -> dict:
    """Same formula as `scripts/discover_confluence_reader_xau.py::
    cohort_stats()` (BOT-052.1), applied to CLOSED live trades only, so the
    numbers are directly comparable to that report's historical HCH/NO_HCH
    rows. `g` must already be filtered to `closed == True`."""
    n = len(g)
    if n == 0:
        return {"N": 0, "wins": 0, "losses": 0, "ties": 0, "WR": math.nan,
                "PF": math.nan, "ExpR": math.nan, "pnl_total": 0.0, "pnl_mean": math.nan}
    pnl = g["pnl_net"]
    gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    r = g["realized_r"].dropna()
    wins = int((g["outcome"] == "win").sum())
    losses = int((g["outcome"] == "loss").sum())
    ties = int((g["outcome"] == "tie").sum())
    return {
        "N": n, "wins": wins, "losses": losses, "ties": ties,
        "WR": wins / n,
        "PF": (gp / gl) if gl > 0 else float("inf"),
        "ExpR": float(r.mean()) if len(r) else math.nan,
        "pnl_total": float(pnl.sum()), "pnl_mean": float(pnl.mean()),
    }


def hch_cohort_report(df: pd.DataFrame) -> dict:
    """Per-state (HCH/NO_HCH/UNAVAILABLE) breakdown: total captured, filled,
    evaluable (closed), and cohort_stats() on the closed subset. Direction
    only ever COMES FROM the frozen HCH classification -- this function never
    filters/reorders trades, it only groups what already happened."""
    out = {}
    for state in HCH_STATES:
        sub = df[df["hch_state"] == state] if len(df) else df
        closed = sub[sub["closed"] == True] if len(sub) else sub  # noqa: E712
        out[state] = {
            "captured": int(len(sub)),
            "filled": int((sub["filled"] == True).sum()) if len(sub) else 0,  # noqa: E712
            "evaluable_closed": int(len(closed)),
            **cohort_stats(closed),
        }
    return out


def summary(symbol: str, magic: int) -> dict:
    """JSON-friendly summary -- no DataFrames. Mirrors the shape of
    `signal_quality_oos_dataset.oos_status_summary()` but for HCH; not yet
    wired to an API endpoint (Phase 9 asks for a report/script, not a live
    endpoint -- can be added later without changing this function)."""
    df = build_dataset(symbol, magic)
    closed = df[df["closed"] == True] if len(df) else df  # noqa: E712
    return {
        "historical_discovery_cutoff_utc": HCH_HISTORICAL_DISCOVERY_CUTOFF_UTC,
        "total_new_limits": int(len(df)),
        "filled": int((df["filled"] == True).sum()) if len(df) else 0,  # noqa: E712
        "evaluable_closed": int(len(closed)),
        "state_counts": {s: int((df["hch_state"] == s).sum()) if len(df) else 0 for s in HCH_STATES},
        "cohorts": hch_cohort_report(df),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSDc")
    ap.add_argument("--magic", type=int, default=900001)
    args = ap.parse_args()

    df = build_dataset(args.symbol, args.magic)
    dataset_path = REPORTS_DIR / "BOT-052.2-hch-oos-dataset.csv"
    df.to_csv(dataset_path, index=False)
    print(f"Wrote {dataset_path.relative_to(REPO_ROOT)} ({len(df)} filas)")

    s = summary(args.symbol, args.magic)
    print(f"\nTotal LIMITs nuevas con hch capturado: {s['total_new_limits']}")
    print(f"Filled: {s['filled']} | Evaluable (cerradas): {s['evaluable_closed']}")
    print(f"Estado HCH: {s['state_counts']}")
    print("\nCohortes (solo cerradas):")
    for state, c in s["cohorts"].items():
        if c["evaluable_closed"] == 0:
            print(f"  {state}: captured={c['captured']} filled={c['filled']} evaluable=0")
            continue
        print(f"  {state}: captured={c['captured']} filled={c['filled']} evaluable={c['evaluable_closed']} "
              f"W/L/T={c['wins']}/{c['losses']}/{c['ties']} WR={c['WR']:.3f} PF={c['PF']:.3f} "
              f"ExpR={c['ExpR']:.4f} PnL={c['pnl_total']:+.2f}")

    print(f"\n(cutoff historico de referencia BOT-052.1: {s['historical_discovery_cutoff_utc']} -- "
          "toda fila de este dataset es OOS por construccion, el campo hch no existia antes de BOT-052.2)")
    print("\nNO se declara exito/fracaso ni se recomienda gate/threshold desde esta muestra -- "
          "solo se acumula para BOT-052.3 (BLOCKED_ON_OOS, ver BACKLOG.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
