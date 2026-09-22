"""BOT-051.5 -- generador determinista del dataset OOS de Signal Quality +
matriz de coverage + readiness por factor.

Usa como features primarias los snapshots PRODUCTIVOS ya capturados en `t0`
(`execution/src/score_store.py`, via `strategy.signal_quality`) -- nunca los
recalcula retrospectivamente. Une (join, nunca reescribe) cada snapshot con
su `OutcomeObservation` mas reciente (`execution/src/outcome_store.py`) por
`ticket` (== `order_ticket` == `position_id`, ver
`execution/src/signal_quality_reconciliation.py`).

100% offline/read-only respecto a MT5 y respecto a los JSONL (solo lee).
Determinista: correrlo dos veces sin datos nuevos produce el mismo CSV
byte-a-byte (mismo orden -- ordenado por ticket).

Modulo de libreria -- lo importan tanto `api/app.py`
(`GET /signal-quality/oos-status`) como el script de linea de comandos
`scripts/build_signal_quality_oos_dataset.py` (que solo llama a `main()`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import score_store, outcome_store
from .signal_quality_reconciliation import is_oos_eligible

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"

ALIGNMENT_SUBSTANTIVE_STATES = (
    "AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL", "ALIGNED_SINGLE", "ALIGNED_CONFIRMED",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Estados de readiness permitidos (seccion 13 del enunciado) -- nunca PASS/FAIL/OOS_VALIDATED.
READY_NO_DATA = "NO_DATA"
READY_ACCUMULATING = "ACCUMULATING"
READY_FOR_ANALYSIS = "READY_FOR_OOS_ANALYSIS"


def _row_for_ticket(ticket: int, sq_raw: dict, outcome: dict | None) -> dict:
    sq = sq_raw.get("signal_quality") or {}
    diag = sq_raw.get("signal_quality_diagnostics") or {}
    prov = sq_raw.get("provenance") or {}
    outcome = outcome or {}

    momentum = sq.get("momentum") or {}
    alignment = sq.get("alignment") or {}
    structure = sq.get("structure") or {}
    context = sq.get("context") or {}

    factors_present = [momentum, alignment, structure, context]
    sq_complete = bool(sq) and all(f.get("status") == "AVAILABLE" for f in factors_present)

    order_final_state = outcome.get("order_final_state")
    filled = order_final_state == "FILLED"
    closed = filled and outcome.get("close_time_utc") is not None

    return {
        # identity
        "signal_event_id": ticket,
        "order_ticket": ticket,
        "position_id": outcome.get("position_id"),
        # provenance
        "sq_schema_version": sq.get("schema_version"),
        "bot_version": prov.get("bot_version"),
        "git_commit": prov.get("git_commit"),
        "limit_created_time_utc": sq.get("observed_at_time_utc"),
        "oos_eligible": is_oos_eligible(sq.get("observed_at_time_utc", ""), sq.get("schema_version", "")) if sq else False,
        # features (captured at t0, never recomputed)
        "direction": sq.get("direction"),
        "momentum_status": momentum.get("status"),
        "roc_atr_3": momentum.get("value"),
        "alignment_status": alignment.get("status"),
        "alignment": alignment.get("value"),
        "structure_status": structure.get("status"),
        "origin_dist_atr": structure.get("value"),
        "context_status": context.get("status"),
        "weekday": context.get("value"),
        # technical observability
        "sq_complete": sq_complete,
        "structure_replay_match": diag.get("structure_replay_matches_signal"),
        "diagnostic_reason": diag.get("fatal_reason") or (
            ",".join(f"{k}={v}" for k, v in (diag.get("unavailable_reasons") or {}).items()) or None
        ),
        # lifecycle
        "order_final_state": order_final_state,
        "filled": filled,
        "fill_time_utc": outcome.get("fill_time_utc"),
        "closed": closed,
        "close_time_utc": outcome.get("close_time_utc"),
        # evaluation only -- NEVER used to define/redefine the features above
        "pnl_net": outcome.get("pnl_net"),
        "realized_r": outcome.get("realized_r"),
        "close_reason": outcome.get("close_reason"),
    }


def build_dataset(symbol: str, magic: int) -> pd.DataFrame:
    sq_raw_all = score_store.load_all_raw(symbol, magic)
    outcomes = outcome_store.load_all(symbol, magic)
    sq_tickets = sorted(t for t, row in sq_raw_all.items() if "signal_quality" in row)
    rows = [_row_for_ticket(t, sq_raw_all[t], outcomes.get(t)) for t in sq_tickets]
    return pd.DataFrame(rows)


def readiness(df: pd.DataFrame) -> dict:
    """Un factor pasa de NO_DATA a ACCUMULATING en cuanto hay >=1 evento OOS
    elegible con ese factor AVAILABLE. READY_FOR_OOS_ANALYSIS exige, ademas
    de N>0, cobertura real de la hipotesis congelada de ese factor -- NO una
    regla arbitraria de "N>=50" (seccion 13, prohibido explicitamente):

      Momentum:  ambas direcciones (LONG y SHORT) representadas.
      Alignment: al menos 3 de los 5 estados sustantivos observados
                 (AGAINST_CONFIRMED/AGAINST_SINGLE/NEUTRAL/ALIGNED_SINGLE/
                 ALIGNED_CONFIRMED) -- BOT-047.2.3 documenta asimetria
                 LONG/SHORT fuerte, asi que "cualquier N" no alcanza.
      Structure: ambas direcciones representadas Y >=1 evento con
                 structure_replay_match=True (la reserva de BOT-051.4).
      Context:   >=2 dias de semana distintos observados (BOT-050.2 solo
                 congelo weekday/Viernes con ownership independiente -- no
                 tiene sentido analizar antes de ver al menos Viernes vs
                 algun otro dia).

    Estos criterios quedan codificados y documentados para cuando exista mas
    volumen -- no son una promesa de que "alcanzara" con poca N."""
    elig = df[df["oos_eligible"] == True] if len(df) else df  # noqa: E712
    closed = elig[elig["closed"] == True] if len(elig) else elig  # noqa: E712

    def _state(n_available: int, criterion_met: bool) -> str:
        if n_available == 0:
            return READY_NO_DATA
        if criterion_met:
            return READY_FOR_ANALYSIS
        return READY_ACCUMULATING

    mom_avail = closed[closed["momentum_status"] == "AVAILABLE"] if len(closed) else closed
    mom_criterion = len(mom_avail) > 0 and set(mom_avail["direction"].unique()) >= {"LONG", "SHORT"}
    momentum_state = _state(len(mom_avail), mom_criterion)

    align_avail = closed[closed["alignment_status"] == "AVAILABLE"] if len(closed) else closed
    align_states_seen = set(align_avail["alignment"].unique()) if len(align_avail) else set()
    align_criterion = len(align_states_seen & set(ALIGNMENT_SUBSTANTIVE_STATES)) >= 3
    alignment_state = _state(len(align_avail), align_criterion)

    struct_avail = closed[closed["structure_status"] == "AVAILABLE"] if len(closed) else closed
    struct_criterion = (
        len(struct_avail) > 0
        and set(struct_avail["direction"].unique()) >= {"LONG", "SHORT"}
        and bool((struct_avail["structure_replay_match"] == True).any())  # noqa: E712
    )
    structure_state = _state(len(struct_avail), struct_criterion)

    ctx_avail = closed[closed["context_status"] == "AVAILABLE"] if len(closed) else closed
    ctx_days_seen = set(ctx_avail["weekday"].unique()) if len(ctx_avail) else set()
    ctx_criterion = len(ctx_days_seen) >= 2
    context_state = _state(len(ctx_avail), ctx_criterion)

    return {
        "momentum": momentum_state, "alignment": alignment_state,
        "structure": structure_state, "context": context_state,
    }


def coverage_matrix(df: pd.DataFrame) -> pd.DataFrame:
    elig = df[df["oos_eligible"] == True] if len(df) else df  # noqa: E712
    rows = []
    rows.append({"section": "general", "metric": "limits_total", "value": len(elig)})
    rows.append({"section": "general", "metric": "filled", "value": int((elig["filled"] == True).sum()) if len(elig) else 0})  # noqa: E712
    rows.append({"section": "general", "metric": "non_filled", "value": int((elig["filled"] == False).sum()) if len(elig) else 0})  # noqa: E712
    rows.append({"section": "general", "metric": "closed", "value": int((elig["closed"] == True).sum()) if len(elig) else 0})  # noqa: E712
    rows.append({"section": "general", "metric": "long", "value": int((elig["direction"] == "LONG").sum()) if len(elig) else 0})
    rows.append({"section": "general", "metric": "short", "value": int((elig["direction"] == "SHORT").sum()) if len(elig) else 0})

    for factor, status_col, value_col in [
        ("momentum", "momentum_status", "roc_atr_3"),
        ("structure", "structure_status", "origin_dist_atr"),
    ]:
        n_avail = int((elig[status_col] == "AVAILABLE").sum()) if len(elig) else 0
        n_unavail = int((elig[status_col] == "UNAVAILABLE").sum()) if len(elig) else 0
        rows.append({"section": factor, "metric": "available", "value": n_avail})
        rows.append({"section": factor, "metric": "unavailable", "value": n_unavail})
        if n_avail:
            vals = elig.loc[elig[status_col] == "AVAILABLE", value_col]
            rows.append({"section": factor, "metric": "observed_min", "value": float(vals.min())})
            rows.append({"section": factor, "metric": "observed_max", "value": float(vals.max())})

    if len(elig):
        n_replay_match = int((elig["structure_replay_match"] == True).sum())  # noqa: E712
        n_replay_mismatch = int((elig["structure_replay_match"] == False).sum())  # noqa: E712
    else:
        n_replay_match = n_replay_mismatch = 0
    rows.append({"section": "structure", "metric": "replay_match", "value": n_replay_match})
    rows.append({"section": "structure", "metric": "replay_mismatch", "value": n_replay_mismatch})

    for state in ALIGNMENT_SUBSTANTIVE_STATES + ("UNAVAILABLE",):
        n = int((elig["alignment"] == state).sum()) if len(elig) else 0
        rows.append({"section": "alignment", "metric": f"state_{state}", "value": n})

    for wd in WEEKDAYS:
        n = int((elig["weekday"] == wd).sum()) if len(elig) else 0
        rows.append({"section": "context", "metric": f"weekday_{wd}", "value": n})

    return pd.DataFrame(rows)


def oos_status_summary(symbol: str, magic: int) -> dict:
    """Resumen compacto para `GET /signal-quality/oos-status` (api/app.py) --
    JSON-friendly (sin DataFrames). Read-only, no consulta MT5 (solo los
    JSONL ya persistidos) -- barato de llamar en cada refresh del panel."""
    df = build_dataset(symbol, magic)
    elig = df[df["oos_eligible"] == True] if len(df) else df  # noqa: E712
    closed = elig[elig["closed"] == True] if len(elig) else elig  # noqa: E712

    from .signal_quality_reconciliation import (
        SIGNAL_QUALITY_OOS_ACCUMULATION_START_UTC, SIGNAL_QUALITY_OOS_ACCUMULATION_START_COMMIT,
    )

    return {
        "accumulation_start_utc": SIGNAL_QUALITY_OOS_ACCUMULATION_START_UTC.isoformat(),
        "accumulation_start_commit": SIGNAL_QUALITY_OOS_ACCUMULATION_START_COMMIT,
        "genuine_live_limits": int(len(elig)),
        "evaluable_closed_trades": int(len(closed)),
        "full_sq_available": int((elig["sq_complete"] == True).sum()) if len(elig) else 0,  # noqa: E712
        "readiness": readiness(df),
        "structure_replay": {
            "match": int((elig["structure_replay_match"] == True).sum()) if len(elig) else 0,  # noqa: E712
            "mismatch": int((elig["structure_replay_match"] == False).sum()) if len(elig) else 0,  # noqa: E712
        },
        "coverage": coverage_matrix(df).to_dict(orient="records"),
        "errors": int(df["diagnostic_reason"].notna().sum()) if len(df) and "diagnostic_reason" in df else 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSDc")
    ap.add_argument("--magic", type=int, default=900001)
    args = ap.parse_args()

    df = build_dataset(args.symbol, args.magic)
    print(f"Total snapshots con signal_quality: {len(df)}")
    if len(df):
        print(f"OOS eligible (>= freeze cutoff, schema vigente): {int(df['oos_eligible'].sum())}")

    dataset_path = REPORTS_DIR / "BOT-051.5-signal-quality-oos-dataset.csv"
    df.to_csv(dataset_path, index=False)
    print(f"Wrote {dataset_path.relative_to(REPO_ROOT)} ({len(df)} filas)")

    coverage_df = coverage_matrix(df)
    coverage_path = REPORTS_DIR / "BOT-051.5-signal-quality-oos-coverage.csv"
    coverage_df.to_csv(coverage_path, index=False)
    print(f"Wrote {coverage_path.relative_to(REPO_ROOT)} ({len(coverage_df)} filas)")

    ready = readiness(df)
    print("\nReadiness (NO_DATA / ACCUMULATING / READY_FOR_OOS_ANALYSIS):")
    for factor, state in ready.items():
        print(f"  {factor}: {state}")

    print("\n(pnl_gross/pnl_net/realized_r/close_reason son 'evaluation only' -- "
          "nunca se usan para definir/redefinir momentum_status/alignment/origin_dist_atr/weekday arriba)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
