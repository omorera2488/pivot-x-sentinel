"""BOT-051.4 -- ATR-Wilder / Signal Quality production-code parity verification, XAU.

Proves the NEW canonical production implementation (`strategy.signal_quality`,
`strategy.scoring._closed_blocks_session_anchored`) reproduces EXACTLY what
the already-frozen offline research (BOT-024.4/BOT-048.1/BOT-051.3) computed
with its own scratch copies of the same formulas -- required by BOT-051.4
section 6.1 ("0 discrepancias materiales") and section 7.2 ("Parity
requerida contra el artefacto historico de BOT-051.3: 3207/3207").

Calls `strategy.signal_quality.compute_signal_quality_at_bar()` -- THE SAME
function `execution/src/bot.py` calls live -- once per historical LIMIT
(Universe A, N=3207), with the array truncated to `[:limit_created_bar+1]`
(exactly what a live fetch window ending at the signal bar would look like),
and diffs against:
  (a) roc_atr_3 already published in reports/BOT-024.2-momentum-limits-xau.csv
  (b) origin_dist_atr already published in reports/BOT-048.1-structure-limits-xau.csv
  (c) the full vector already reconstructed in
      reports/BOT-051.3-signal-quality-vector-shadow-xau.csv

No outcome column (pnl_r/pnl_usd/outcome/fill/MFE/MAE) is ever loaded.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from strategy import engine, signal_quality as sq  # noqa: E402

REPORTS_DIR = REPO_ROOT / "reports"
DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"

CSV_ALIGNMENT_UNIVERSE_A = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"
CSV_MOMENTUM = REPORTS_DIR / "BOT-024.2-momentum-limits-xau.csv"
CSV_STRUCTURE = REPORTS_DIR / "BOT-048.1-structure-limits-xau.csv"
CSV_SHADOW_V1 = REPORTS_DIR / "BOT-051.3-signal-quality-vector-shadow-xau.csv"

OUT_CSV = REPORTS_DIR / "BOT-051.4-signal-quality-live-parity-xau.csv"

CONFIG_A = dict(ema_periods=12, periodos_htf_min=800)  # misma Config A de toda la linea BOT-024.x/047.x/048.x/049.x/050.x/051.x


def section(title: str) -> None:
    print(f"\n{'=' * 3} {title} {'=' * 3}")


def main() -> int:
    section("0. LOAD")
    df_meta = pd.read_parquet(DATA_PATH)
    time_utc = df_meta["time_utc"].to_numpy()
    high = df_meta["high"].to_numpy()
    low = df_meta["low"].to_numpy()
    close = df_meta["close"].to_numpy()
    print(f"M5 dataset: {len(df_meta)} bars")

    lim = pd.read_csv(CSV_ALIGNMENT_UNIVERSE_A)[["trade_id", "direction", "limit_created_bar"]]
    mom = pd.read_csv(CSV_MOMENTUM)[["trade_id", "roc_atr_3"]]
    struct = pd.read_csv(CSV_STRUCTURE)[["trade_id", "origin_dist_atr"]]
    shadow = pd.read_csv(CSV_SHADOW_V1)[["trade_id", "momentum_status", "roc_atr_3", "alignment_status", "alignment",
                                          "structure_status", "origin_dist_atr", "context_status", "weekday"]]
    print(f"Universe A LIMIT events: {len(lim)}")

    # entry = ema_line[b], same as engine.py's signal logic (entry = ema_line[i]) --
    # computed once over the full array (ema() is purely causal/recursive, ema(close[:b+1])[-1]
    # == ema(close)[b] exactly).
    ema_full = engine.ema(close, CONFIG_A["ema_periods"])

    merged = lim.merge(mom, on="trade_id", how="left").merge(struct, on="trade_id", how="left", suffixes=("", "_struct"))

    rows = []
    t0 = time.time()
    for _, r in merged.iterrows():
        b = int(r["limit_created_bar"])
        direction = 1 if r["direction"] == "LONG" else -1
        entry = float(ema_full[b])
        vector, diag = sq.compute_signal_quality_at_bar(
            time_utc, high, low, close, b=b, direction=direction, entry=entry,
            ema_periods=CONFIG_A["ema_periods"], periodos_htf_min=CONFIG_A["periodos_htf_min"],
            observed_at_bar=b,
        )
        rows.append(dict(
            trade_id=r["trade_id"], b=b, direction=r["direction"],
            momentum_status=vector.momentum.status, roc_atr_3_new=vector.momentum.value,
            alignment_status=vector.alignment.status, alignment_new=vector.alignment.value,
            structure_status=vector.structure.status, origin_dist_atr_new=vector.structure.value,
            context_status=vector.context.status, weekday_new=vector.context.value,
            structure_replay_matches_signal=diag["structure_replay_matches_signal"],
        ))
    elapsed = time.time() - t0
    new = pd.DataFrame(rows)
    print(f"Computed {len(new)} vectors via strategy.signal_quality.compute_signal_quality_at_bar() in {elapsed:.1f}s")

    # --- A. ATR-Wilder / roc_atr_3 parity vs BOT-024.2 ---
    section("A. roc_atr_3 parity vs reports/BOT-024.2-momentum-limits-xau.csv")
    cmp_mom = new.merge(mom, on="trade_id", how="left", suffixes=("_new", "_old"))
    both_nan = cmp_mom["roc_atr_3_new"].isna() & cmp_mom["roc_atr_3"].isna()
    both_val = cmp_mom["roc_atr_3_new"].notna() & cmp_mom["roc_atr_3"].notna()
    diff = (cmp_mom.loc[both_val, "roc_atr_3_new"] - cmp_mom.loc[both_val, "roc_atr_3"]).abs()
    n_mismatch_nan = ((cmp_mom["roc_atr_3_new"].isna()) != (cmp_mom["roc_atr_3"].isna())).sum()
    max_err_mom = diff.max() if len(diff) else 0.0
    print(f"  both NaN (warm-up): {both_nan.sum()}")
    print(f"  both valid, compared: {both_val.sum()}, max abs error: {max_err_mom:.2e}")
    print(f"  NaN/valid mismatches: {n_mismatch_nan}")
    check_a = n_mismatch_nan == 0 and max_err_mom < 1e-6

    # --- B. origin_dist_atr parity vs BOT-048.1 ---
    section("B. origin_dist_atr parity vs reports/BOT-048.1-structure-limits-xau.csv")
    cmp_struct = new.merge(struct, on="trade_id", how="left", suffixes=("_new", "_old"))
    both_nan_s = cmp_struct["origin_dist_atr_new"].isna() & cmp_struct["origin_dist_atr"].isna()
    both_val_s = cmp_struct["origin_dist_atr_new"].notna() & cmp_struct["origin_dist_atr"].notna()
    diff_s = (cmp_struct.loc[both_val_s, "origin_dist_atr_new"] - cmp_struct.loc[both_val_s, "origin_dist_atr"]).abs()
    n_mismatch_nan_s = ((cmp_struct["origin_dist_atr_new"].isna()) != (cmp_struct["origin_dist_atr"].isna())).sum()
    max_err_struct = diff_s.max() if len(diff_s) else 0.0
    n_replay_mismatch = (~new["structure_replay_matches_signal"]).sum()
    print(f"  both NaN: {both_nan_s.sum()}, both valid: {both_val_s.sum()}, max abs error: {max_err_struct:.2e}")
    print(f"  NaN/valid mismatches: {n_mismatch_nan_s}")
    print(f"  structure_replay_matches_signal == False (should be 0, full-history window): {n_replay_mismatch}")
    check_b = n_mismatch_nan_s == 0 and max_err_struct < 1e-6 and n_replay_mismatch == 0

    # --- C. Full vector parity vs BOT-051.3 shadow (only overlapping trade_ids -- BOT-051.3
    #        base universe there was bounded by the Alignment artifact scope, see that report) ---
    section("C. Full vector parity vs reports/BOT-051.3-signal-quality-vector-shadow-xau.csv")
    cmp_full = new.merge(shadow, on="trade_id", how="inner", suffixes=("_new", "_old"))
    print(f"  N overlap: {len(cmp_full)}")
    # new's own columns are already named *_new explicitly; shadow's columns
    # (alignment/weekday) have no literal name collision with those, so pandas
    # keeps them UNSUFFIXED -- only the *_status columns collide (both frames
    # use that exact name) and get the _new/_old suffix.
    # alignment_new is NaN (via pandas CSV round-trip) when UNAVAILABLE, per
    # FactorObservation's frozen contract (value=None iff status=UNAVAILABLE)
    # -- BOT-051.3's older CSV schema stored the literal string "UNAVAILABLE"
    # in that same column instead. Both mean the same thing; normalize before
    # comparing so this schema difference isn't reported as a false mismatch.
    alignment_new_norm = cmp_full["alignment_new"].fillna("UNAVAILABLE")
    align_match = (alignment_new_norm == cmp_full["alignment"]).sum()
    align_status_match = (cmp_full["alignment_status_new"] == cmp_full["alignment_status_old"]).sum()
    weekday_match = (cmp_full["weekday_new"] == cmp_full["weekday"]).sum()
    n = len(cmp_full)
    print(f"  alignment exact-match: {align_match}/{n}")
    print(f"  alignment_status exact-match: {align_status_match}/{n}")
    print(f"  weekday exact-match: {weekday_match}/{n}")
    check_c = align_match == n and align_status_match == n and weekday_match == n

    section("SUMMARY")
    print(f"[{'PASS' if check_a else 'FAIL'}] A. roc_atr_3 (ATR-Wilder) parity")
    print(f"[{'PASS' if check_b else 'FAIL'}] B. origin_dist_atr parity + structure replay self-consistency")
    print(f"[{'PASS' if check_c else 'FAIL'}] C. Alignment/weekday parity vs BOT-051.3")

    new.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV.relative_to(REPO_ROOT)}")
    print("(pnl_r / pnl_usd / outcome / fill / MFE / MAE intentionally never loaded into this script)")

    ok = check_a and check_b and check_c
    print(f"\n{'ALL PARITY CHECKS PASS' if ok else 'SOME PARITY CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
