"""BOT-051.3 -- Signal Quality Vector Shadow Reconstruction / Observability, XAU.

Closes the artifact-scope gap left open by BOT-051.2: the Alignment
consensus artifact (`reports/BOT-047.2.2-boundary-event-comparison-xau.csv`)
only covered Universe B (filled+closed trades, N=2474), while Momentum/
Structure/Context are already computed for the full Universe A (N=3207,
every LIMIT created, filled or not).

This script does NOT create a new Alignment definition. It reuses, 100%
unmodified, the exact causal functions already frozen and audited in
`scripts/analyze_d1_structural_alignment_xau.py` (BOT-047.2.1) --
`build_naive_blocks`, `naive_trend_at`, `build_true_blocks`, `true_trend_at`,
`alignment_label` -- and simply evaluates them for every Universe A LIMIT
instead of only the Universe B subset that BOT-047.2.2 happened to iterate
over. The block-classification functions operate purely on `bar_idx`
against a D1 block structure derived from the full M5 time series; they have
no dependency on whether the event later filled.

Also performs the standalone causal re-slice verification of `roc_atr_3`
that BOT-024.4 left as an explicit non-blocking limitation: ATR-Wilder is a
purely causal recursive filter (atr[i] depends only on high/low/close[0..i]),
so truncating the array to [:b+1] and recomputing must reproduce the
already-published `roc_atr_3` exactly.

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
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_d1_structural_alignment_xau import (  # noqa: E402
    build_naive_blocks, naive_trend_at, build_true_blocks, true_trend_at,
    alignment_label, LOOKBACK_LEGACY, DATA_PATH,
)

REPORTS_DIR = REPO_ROOT / "reports"
CSV_ALIGNMENT_UNIVERSE_A = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"   # trade_id, direction, limit_created_bar (N=3207)
CSV_ALIGNMENT_OLD_ARTIFACT = REPORTS_DIR / "BOT-047.2.2-boundary-event-comparison-xau.csv"  # N=2474, previous freeze
CSV_MOMENTUM = REPORTS_DIR / "BOT-024.2-momentum-limits-xau.csv"     # trade_id, roc_atr_3 (N=3207)
CSV_STRUCTURE = REPORTS_DIR / "BOT-048.1-structure-limits-xau.csv"   # trade_id, origin_dist_atr (N=3207)
CSV_CONTEXT = REPORTS_DIR / "BOT-050.1-context-limits-xau.csv"       # trade_id, weekday (N=3207)

OUT_CSV = REPORTS_DIR / "BOT-051.3-signal-quality-vector-shadow-xau.csv"

ATR_PERIOD = 14
ROC_LOOKBACK = 3


def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = ATR_PERIOD) -> np.ndarray:
    """Verbatim reused formula (same as backtests/scripts/07_bot045_regime_dataset.py::atr_wilder
    and scripts/discover_momentum_features_xau.py::atr_wilder, BOT-024.2/BOT-024.4) --
    purely causal recursive filter, atr[i] depends only on high/low/close[0..i]."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n <= period:
        return atr
    atr[period] = tr[1:period + 1].mean()
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def consensus(b0: str, b1: str) -> str:
    """Exact rule frozen in reports/BOT-047.2.3-...FREEZE.md, reused verbatim
    from scripts/reconstruct_signal_quality_vector_v1_xau.py (BOT-051.2),
    re-verified there against the published state distribution (0 discrepancies)."""
    if b0 == "UNAVAILABLE" or b1 == "UNAVAILABLE":
        return "UNAVAILABLE"
    if b0 == "AGAINST" and b1 == "AGAINST":
        return "AGAINST_CONFIRMED"
    if b0 == "ALIGNED" and b1 == "ALIGNED":
        return "ALIGNED_CONFIRMED"
    against_count = (b0 == "AGAINST") + (b1 == "AGAINST")
    aligned_count = (b0 == "ALIGNED") + (b1 == "ALIGNED")
    if against_count == 1 and (b0 == "NEUTRAL_MIXED" or b1 == "NEUTRAL_MIXED"):
        return "AGAINST_SINGLE"
    if aligned_count == 1 and (b0 == "NEUTRAL_MIXED" or b1 == "NEUTRAL_MIXED"):
        return "ALIGNED_SINGLE"
    if b0 == "NEUTRAL_MIXED" and b1 == "NEUTRAL_MIXED":
        return "NEUTRAL"
    return "FLIP_UNDEFINED"


def section(title: str) -> None:
    print(f"\n{'=' * 3} {title} {'=' * 3}")


def main() -> int:
    section("0. LOAD SOURCE ARTIFACTS (no feature recomputed except Alignment full-Universe extension)")
    df_meta = pd.read_parquet(DATA_PATH)
    n_bars = len(df_meta)
    time_utc = df_meta["time_utc"].to_numpy()
    open_ = df_meta["open"].to_numpy()
    high = df_meta["high"].to_numpy()
    low = df_meta["low"].to_numpy()
    close = df_meta["close"].to_numpy()
    print(f"M5 dataset: {n_bars} bars, {pd.to_datetime(time_utc[0], unit='s')} .. {pd.to_datetime(time_utc[-1], unit='s')}")

    lim_a = pd.read_csv(CSV_ALIGNMENT_UNIVERSE_A)[["trade_id", "direction", "limit_created_bar"]]
    old_artifact = pd.read_csv(CSV_ALIGNMENT_OLD_ARTIFACT)[["trade_id", "B0_alignment", "B1_alignment"]]
    mom = pd.read_csv(CSV_MOMENTUM)[["trade_id", "roc_atr_3"]]
    struct = pd.read_csv(CSV_STRUCTURE)[["trade_id", "origin_dist_atr"]]
    ctx = pd.read_csv(CSV_CONTEXT)[["trade_id", "weekday"]]

    print(f"Universe A (LIMIT creation events): {len(lim_a)}")
    print(f"Old Alignment artifact (Universe B, previous freeze): {len(old_artifact)}")
    print(f"Momentum/Structure/Context sources: {len(mom)}/{len(struct)}/{len(ctx)} (all Universe A)")

    # -----------------------------------------------------------------
    section("1. FULL-UNIVERSE ALIGNMENT RECONSTRUCTION (frozen BOT-047.2.3 functions, unmodified)")
    # -----------------------------------------------------------------
    bucket_id_naive, block_ids_naive, blocks_naive = build_naive_blocks(time_utc, high, low)
    d1_true, closing_bar_true, blocks_true = build_true_blocks(time_utc, open_, high, low, close)

    rows = []
    for _, r in lim_a.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1
        state_b0, _ = naive_trend_at(bucket_id_naive, block_ids_naive, blocks_naive, b, LOOKBACK_LEGACY)
        state_b1, _ = true_trend_at(closing_bar_true, blocks_true, b, LOOKBACK_LEGACY)
        b0_align = alignment_label(state_b0, d)
        b1_align = alignment_label(state_b1, d)
        rows.append(dict(
            trade_id=r["trade_id"], direction=r["direction"], limit_created_bar=b,
            B0_alignment=b0_align, B1_alignment=b1_align,
            alignment=consensus(b0_align, b1_align),
        ))
    full_align = pd.DataFrame(rows)

    n_flip_undefined = (full_align["alignment"] == "FLIP_UNDEFINED").sum()
    check1 = n_flip_undefined == 0
    print(f"[{'PASS' if check1 else 'FAIL'}] FLIP_UNDEFINED cases (should be 0): {n_flip_undefined}")

    print("\nFull-Universe A Alignment Consensus distribution (N=3207):")
    print(full_align["alignment"].value_counts())

    # -----------------------------------------------------------------
    section("2. PARITY CHECK vs previous Universe-B artifact (BOT-047.2.2, N=2474)")
    # -----------------------------------------------------------------
    parity = old_artifact.merge(
        full_align[["trade_id", "B0_alignment", "B1_alignment", "alignment"]],
        on="trade_id", how="left", suffixes=("_old", "_new"),
    )
    n_overlap = len(parity)
    b0_match = (parity["B0_alignment_old"] == parity["B0_alignment_new"]).sum()
    b1_match = (parity["B1_alignment_old"] == parity["B1_alignment_new"]).sum()
    b0_mismatch = n_overlap - b0_match
    b1_mismatch = n_overlap - b1_match
    print(f"N overlap with old Universe B artifact: {n_overlap}")
    print(f"B0_alignment exact-match: {b0_match}/{n_overlap} (mismatches: {b0_mismatch})")
    print(f"B1_alignment exact-match: {b1_match}/{n_overlap} (mismatches: {b1_mismatch})")
    if b0_mismatch or b1_mismatch:
        mism = parity[(parity["B0_alignment_old"] != parity["B0_alignment_new"]) |
                       (parity["B1_alignment_old"] != parity["B1_alignment_new"])]
        print("MISMATCH SAMPLES (first 10):")
        print(mism.head(10).to_string())
    check2 = (b0_mismatch == 0) and (b1_mismatch == 0)
    print(f"[{'PASS' if check2 else 'FAIL'}] Alignment parity vs BOT-047.2.2 == 100%")

    # -----------------------------------------------------------------
    section("3. MOMENTUM STANDALONE CAUSAL RE-SLICE (closes BOT-024.4 pending limitation #3)")
    # -----------------------------------------------------------------
    t0 = time.time()
    mom_check = mom.merge(lim_a[["trade_id", "limit_created_bar", "direction"]], on="trade_id", how="left")
    n_checked = 0
    n_unavailable_warmup = 0
    n_discrepancies = 0
    max_abs_error = 0.0
    mismatches = []
    for _, r in mom_check.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1
        published = r["roc_atr_3"]
        j = b - ROC_LOOKBACK
        if j < 0 or b < ATR_PERIOD:
            n_unavailable_warmup += 1
            if not pd.isna(published):
                mismatches.append((r["trade_id"], "expected NaN (warm-up) but published has a value", published))
                n_discrepancies += 1
            continue
        n_checked += 1
        high_t, low_t, close_t = high[:b + 1], low[:b + 1], close[:b + 1]
        atr_t = atr_wilder(high_t, low_t, close_t, ATR_PERIOD)
        atr_i = atr_t[b]
        if pd.isna(atr_i) or atr_i <= 0:
            recomputed = np.nan
        else:
            recomputed = d * (close[b] - close[j]) / atr_i
        if pd.isna(published) and pd.isna(recomputed):
            continue
        if pd.isna(published) or pd.isna(recomputed):
            mismatches.append((r["trade_id"], "one NaN one not", (published, recomputed)))
            n_discrepancies += 1
            continue
        err = abs(published - recomputed)
        max_abs_error = max(max_abs_error, err)
        if err > 1e-9:
            mismatches.append((r["trade_id"], "value mismatch", (published, recomputed, err)))
            n_discrepancies += 1
    elapsed = time.time() - t0
    print(f"N checked (re-sliced + recomputed): {n_checked}")
    print(f"N unavailable due to legitimate warm-up (b<{ATR_PERIOD} or b-{ROC_LOOKBACK}<0): {n_unavailable_warmup}")
    print(f"N discrepancies: {n_discrepancies}")
    print(f"Max absolute error: {max_abs_error:.2e}")
    print(f"Elapsed: {elapsed:.1f}s")
    if mismatches:
        print("MISMATCH SAMPLES (first 10):", mismatches[:10])
    check3 = n_discrepancies == 0
    print(f"[{'PASS' if check3 else 'FAIL'}] Momentum (roc_atr_3) standalone causal re-slice: exact reproduction")

    # -----------------------------------------------------------------
    section("4. JOINT VECTOR ASSEMBLY -- full Universe A (N=3207)")
    # -----------------------------------------------------------------
    vec = full_align[["trade_id", "direction", "limit_created_bar", "alignment"]].merge(
        mom, on="trade_id", how="left", validate="one_to_one", indicator="momentum_join"
    ).merge(
        struct, on="trade_id", how="left", validate="one_to_one", indicator="structure_join"
    ).merge(
        ctx, on="trade_id", how="left", validate="one_to_one", indicator="context_join"
    )
    time_map = pd.Series(pd.to_datetime(time_utc, unit="s"))
    vec["limit_created_time_utc"] = vec["limit_created_bar"].map(lambda b: time_map.iloc[int(b)])

    for factor, col, join_col in [("momentum", "momentum_join", "momentum_join"),
                                   ("structure", "structure_join", "structure_join"),
                                   ("context", "context_join", "context_join")]:
        matched = (vec[join_col] == "both").sum()
        print(f"Join {factor}: {matched}/{len(vec)}")

    vec["momentum_status"] = vec["roc_atr_3"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
    vec["structure_status"] = vec["origin_dist_atr"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
    vec["context_status"] = vec["weekday"].apply(lambda v: "UNAVAILABLE" if pd.isna(v) else "AVAILABLE")
    vec["alignment_status"] = vec["alignment"].apply(lambda v: "UNAVAILABLE" if v == "UNAVAILABLE" else "AVAILABLE")

    vec["all_available"] = (
        (vec["momentum_status"] == "AVAILABLE")
        & (vec["alignment_status"] == "AVAILABLE")
        & (vec["structure_status"] == "AVAILABLE")
        & (vec["context_status"] == "AVAILABLE")
    )

    n_total = len(vec)
    n_produced = vec["trade_id"].notna().sum()
    n_full = vec["all_available"].sum()
    n_partial = n_total - n_full

    section("5. SUMMARY -- Full Universe A audit")
    print(f"N total LIMITs (Universe A): {n_total}")
    print(f"N vectors produced: {n_produced}")
    print(f"N fully AVAILABLE (4/4): {n_full}")
    print(f"N with >=1 UNAVAILABLE: {n_partial}")
    for factor in ["momentum", "alignment", "structure", "context"]:
        n_unavail = (vec[f"{factor}_status"] == "UNAVAILABLE").sum()
        print(f"  UNAVAILABLE[{factor}] = {n_unavail} ({n_unavail/n_total:.2%})")
    n_reconstruction_failures = n_total - n_produced
    print(f"N reconstruction failures (no vector at all): {n_reconstruction_failures}")
    print(f"N parity mismatches against BOT-051.2 overlap (N=2474): {b0_mismatch + b1_mismatch}")

    # sanity: NEUTRAL must never appear in UNAVAILABLE count
    neutral_but_unavailable = ((vec["alignment"] == "NEUTRAL") & (vec["alignment_status"] == "UNAVAILABLE")).sum()
    print(f"\n[{'PASS' if neutral_but_unavailable == 0 else 'FAIL'}] NEUTRAL rows never counted as UNAVAILABLE: {neutral_but_unavailable}")

    dupes = vec["trade_id"].duplicated().sum()
    print(f"[{'PASS' if dupes == 0 else 'FAIL'}] Duplicate trade_id in final vector table: {dupes}")

    invalid_enum = (~vec["alignment"].isin(
        {"AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL", "ALIGNED_SINGLE", "ALIGNED_CONFIRMED", "UNAVAILABLE"}
    )).sum()
    print(f"[{'PASS' if invalid_enum == 0 else 'FAIL'}] Invalid Alignment enum values: {invalid_enum}")

    out_cols = [
        "trade_id", "limit_created_bar", "limit_created_time_utc", "direction",
        "momentum_status", "roc_atr_3",
        "alignment_status", "alignment",
        "structure_status", "origin_dist_atr",
        "context_status", "weekday",
        "all_available",
    ]
    vec[out_cols].to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV.relative_to(REPO_ROOT)} ({len(vec)} rows)")
    print("(pnl_r / pnl_usd / outcome / fill / MFE / MAE intentionally never loaded into this script)")

    all_checks = [check1, check2, check3, neutral_but_unavailable == 0, dupes == 0, invalid_enum == 0]
    print(f"\n{'ALL CHECKS PASS' if all(all_checks) else 'SOME CHECKS FAILED'} ({sum(all_checks)}/{len(all_checks)})")
    return 0 if all(all_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
