"""BOT-052.2 Phase 9 -- regresion del puente OOS de HCH
(`execution/src/hch_oos_dataset.py`).

100% offline: JSONL temporales (mismo patron que
`execution/src/test_signal_quality_oos_bridge.py`, BOT-051.5), nunca
consulta MT5. Cubre: filtro "hch presente" como frontera OOS (sin fecha
hardcodeada), join por ticket con outcome_store, clasificacion win/loss/tie
por signo de pnl_net (nunca close_reason), cohortes HCH/NO_HCH/UNAVAILABLE
separadas, determinismo, retencion de los factores crudos de Signal Quality
para analisis futuro, y que ninguna funcion de este modulo declara
exito/fracaso.

Uso:
    python execution/src/test_hch_oos_dataset.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src import outcome_store, score_store  # noqa: E402
from execution.src import hch_oos_dataset as hch_oos  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


SQ_BASE = {
    "schema_version": "1.0.0", "observed_at_bar": 1,
    "observed_at_time_utc": "2026-09-24T10:00:00+00:00", "direction": "LONG",
    "momentum": {"status": "AVAILABLE", "value": 0.4},
    "alignment": {"status": "AVAILABLE", "value": "ALIGNED_SINGLE"},
    "structure": {"status": "AVAILABLE", "value": 1.2},
    "context": {"status": "AVAILABLE", "value": "Monday"},
}


def _hch(state: str, **extra) -> dict:
    base = {
        "hch_state": state, "hch_version": "1.0.0",
        "hch_captured_at": "2026-09-24T10:00:00+00:00",
        "hch_consumed_on_signal_bar": 42,
        "hch_pivot_1": 2500.1, "hch_pivot_2": 2500.5, "hch_pivot_3": 2500.2,
        "hch_active_level": None, "hch_formation_bar": 10,
    }
    base.update(extra)
    return base


def _outcome(ticket: int, pnl_net: float | None, realized_r=None,
             closed: bool = True, filled: bool = True) -> dict:
    return {
        "ticket": ticket, "symbol": "SYM0", "magic": 1,
        "order_final_state": "FILLED" if filled else "CANCELED",
        "fill_time_utc": "2026-09-24T10:01:00+00:00" if filled else None,
        "position_id": ticket if filled else None,
        "close_time_utc": "2026-09-24T11:00:00+00:00" if closed else None,
        "pnl_gross": pnl_net, "commission": 0.0, "swap": 0.0, "pnl_net": pnl_net,
        "realized_r": realized_r, "close_reason": "TP" if (pnl_net or 0) > 0 else "SL",
        "open_deal_ticket": ticket * 10, "close_deal_ticket": (ticket * 10 + 1) if closed else None,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        score_store.DATA_DIR = Path(tmp) / "scores"
        outcome_store.DATA_DIR = Path(tmp) / "outcomes"

        print("=== A. Sin ningun ticket con `hch` -- dataset vacio, no crashea ===")
        score_store.record("SYM0", 1, 9001, {"total": 0}, signal_quality=SQ_BASE)  # BOT-051.x, sin hch
        df_empty = hch_oos.build_dataset("SYM0", 1)
        check("un ticket viejo (sin hch) queda EXCLUIDO -- 'hch' in row es la frontera exacta",
              len(df_empty) == 0, f"len={len(df_empty)}")

        print("\n=== B. Ticket con hch pero sin outcome reconciliado (LIMIT recien nacida) ===")
        score_store.record("SYM0", 1, 9002, {"total": 0}, signal_quality=SQ_BASE,
                            hch=_hch("HCH", hch_active_level=2500.5))
        df = hch_oos.build_dataset("SYM0", 1)
        check("aparece en el dataset (no requiere outcome)", 9002 in set(df["order_ticket"]))
        row = df[df["order_ticket"] == 9002].iloc[0]
        check("filled/closed False sin outcome, hch_state preservado tal cual",
              not row["filled"] and not row["closed"] and row["hch_state"] == "HCH")
        check("factores crudos de Signal Quality retenidos (para BOT-052.3, nunca recalculados)",
              row["momentum_status"] == "AVAILABLE" and row["roc_atr_3"] == 0.4
              and row["alignment"] == "ALIGNED_SINGLE" and row["weekday"] == "Monday")

        print("\n=== C. Cohortes HCH vs NO_HCH vs UNAVAILABLE -- W/L/T, WR, PF, ExpR, PnL ===")
        # HCH: 2 ganadoras, 1 perdedora
        score_store.record("SYM0", 1, 9101, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("HCH"))
        outcome_store.record("SYM0", 1, _outcome(9101, pnl_net=50.0, realized_r=1.5))
        score_store.record("SYM0", 1, 9102, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("HCH"))
        outcome_store.record("SYM0", 1, _outcome(9102, pnl_net=30.0, realized_r=1.0))
        score_store.record("SYM0", 1, 9103, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("HCH"))
        outcome_store.record("SYM0", 1, _outcome(9103, pnl_net=-40.0, realized_r=-1.0))
        # NO_HCH: 1 perdedora
        score_store.record("SYM0", 1, 9104, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("NO_HCH"))
        outcome_store.record("SYM0", 1, _outcome(9104, pnl_net=-20.0, realized_r=-1.0))
        # UNAVAILABLE: 1 ganadora
        score_store.record("SYM0", 1, 9105, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("UNAVAILABLE"))
        outcome_store.record("SYM0", 1, _outcome(9105, pnl_net=10.0, realized_r=0.5))

        s = hch_oos.summary("SYM0", 1)
        check("total_new_limits cuenta TODOS los tickets con hch (incluye 9002 sin outcome)",
              s["total_new_limits"] == 6, f"total={s['total_new_limits']}")
        # 9002 (seccion B) tambien es "HCH" -- 4 HCH en total (9002+9101+9102+9103)
        check("state_counts correcto", s["state_counts"] == {"HCH": 4, "NO_HCH": 1, "UNAVAILABLE": 1},
              f"{s['state_counts']}")

        hch_c = s["cohorts"]["HCH"]
        check("cohort HCH: N=3 W/L/T=2/1/0", hch_c["N"] == 3 and hch_c["wins"] == 2 and hch_c["losses"] == 1,
              f"{hch_c}")
        check("cohort HCH: WR=2/3", abs(hch_c["WR"] - 2 / 3) < 1e-9)
        check("cohort HCH: PF = gross_profit/gross_loss = 80/40 = 2.0", abs(hch_c["PF"] - 2.0) < 1e-9)
        check("cohort HCH: ExpR = mean(1.5, 1.0, -1.0)", abs(hch_c["ExpR"] - (1.5 + 1.0 - 1.0) / 3) < 1e-9)
        check("cohort HCH: PnL total = 50+30-40 = 40.0", abs(hch_c["pnl_total"] - 40.0) < 1e-9)

        no_hch_c = s["cohorts"]["NO_HCH"]
        check("cohort NO_HCH: N=1 W/L/T=0/1/0, WR=0", no_hch_c["N"] == 1 and no_hch_c["wins"] == 0
              and no_hch_c["losses"] == 1 and no_hch_c["WR"] == 0.0)

        unavail_c = s["cohorts"]["UNAVAILABLE"]
        check("cohort UNAVAILABLE: N=1 W/L/T=1/0/0, WR=1.0", unavail_c["N"] == 1 and unavail_c["wins"] == 1
              and unavail_c["WR"] == 1.0)

        print("\n=== D. Clasificacion win/loss usa pnl_net, NUNCA close_reason ===")
        # close_reason="SL" pero con pnl_net positivo (ej. break-even move) -- debe contar como win
        score_store.record("SYM0", 1, 9201, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("HCH"))
        outcome_store.record("SYM0", 1, {**_outcome(9201, pnl_net=5.0, realized_r=0.1), "close_reason": "SL"})
        df2 = hch_oos.build_dataset("SYM0", 1)
        row9201 = df2[df2["order_ticket"] == 9201].iloc[0]
        check("outcome='win' pese a close_reason='SL', porque pnl_net > 0 (misma convencion que _aciertos_pct())",
              row9201["outcome"] == "win" and row9201["close_reason"] == "SL")

        print("\n=== E. realized_r no numerico ('UNAVAILABLE') no rompe ExpR, se excluye del promedio ===")
        score_store.record("SYM0", 1, 9301, {"total": 0}, signal_quality=SQ_BASE, hch=_hch("HCH"))
        outcome_store.record("SYM0", 1, {**_outcome(9301, pnl_net=15.0), "realized_r": "UNAVAILABLE"})
        df3 = hch_oos.build_dataset("SYM0", 1)
        row9301 = df3[df3["order_ticket"] == 9301].iloc[0]
        import pandas as pd
        check("realized_r no numerico se convierte a None/NaN en el dataset (nunca crashea aguas abajo)",
              row9301["realized_r"] is None or pd.isna(row9301["realized_r"]))

        print("\n=== F. Determinismo -- misma llamada, mismo resultado (ordenado por ticket) ===")
        df_a = hch_oos.build_dataset("SYM0", 1)
        df_b = hch_oos.build_dataset("SYM0", 1)
        check("build_dataset() es determinista (misma entrada -> mismo DataFrame)", df_a.equals(df_b))
        check("ordenado por ticket ascendente", list(df_a["order_ticket"]) == sorted(df_a["order_ticket"]))

        print("\n=== G. summary()/cohort_stats() nunca calculan significancia ni deciden gate ===")
        # a diferencia del scan de docstrings (que necesariamente MENCIONA estos
        # terminos para prohibirlos -- ver modulo), esto inspecciona las claves
        # REALMENTE devueltas por las funciones que producen resultados.
        forbidden_keys = ["p_value", "significant", "bootstrap_ci", "gate", "recommend", "threshold", "validated"]
        summary_keys = set(s.keys()) | set(s["cohorts"]["HCH"].keys())
        leaked = [k for k in forbidden_keys if any(k in sk.lower() for sk in summary_keys)]
        check("summary()/cohort_stats() no exponen ninguna clave de significancia/gate/recomendacion",
              not leaked, f"leaked={leaked} keys={summary_keys}")

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
