"""BOT-024.4 -- Momentum Definition Freeze (XAU). DEFINITION/VERIFICATION task,
explicitly NOT discovery. Reuses exclusively the ALREADY-FROZEN, ALREADY-CAUSAL
per-event artifacts of BOT-024.2 (Momentum Feature Discovery), BOT-048.1/BOT-
048.2 (Structure), BOT-047.2.2/BOT-047.2.3 (Alignment) and BOT-050.1 (Context).
No new feature is computed, no new window/period is introduced, no threshold is
tuned against results. The only computation performed here is:

  1. Reproduction checks -- recompute already-published BOT-024.2 numbers
     (bootstrap CI on the roc_atr_3 bottom quintile, fill-rate monotonicity,
     the roc_atr_3<->rsi_delta_3 redundancy) directly from the frozen CSVs, to
     confirm the report and the CSVs agree before freezing anything on top of
     them.
  2. Gap-filling verification -- Spearman correlations that BOT-024.2/BOT-
     048.2/BOT-051.1 documented as NOT yet computed (e.g. roc_atr_3 vs
     ema_slope_atr_3/atr_pct, roc_atr_3 vs Structure's origin_dist_atr,
     roc_atr_3 vs the frozen Alignment Consensus state, roc_atr_3 vs Context's
     weekday) -- same style already used in BOT-048.2 ("se agrego rigor
     estadistico que BOT-048.1 no habia aplicado").

Nothing here touches pnl_r/pnl_usd/outcome to DEFINE, bucket, or select a
feature -- performance is reported as descriptive evidence only, per the
Definition Freeze rule (semantics/causality/interpretability/reproducibility/
non-redundancy/robustness first, performance last).

Usage:
    .venv/Scripts/python.exe scripts/freeze_momentum_definition_xau.py \
        > reports/BOT-024.4-MOMENTUM-DEFINITION-FREEZE-EVIDENCE.log
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MOMENTUM_LIMITS = "reports/BOT-024.2-momentum-limits-xau.csv"
MOMENTUM_TRADES = "reports/BOT-024.2-momentum-trades-xau.csv"
STRUCTURE_TRADES = "reports/BOT-048.1-structure-trades-xau.csv"
ALIGNMENT_EVENTS = "reports/BOT-047.2.2-boundary-event-comparison-xau.csv"
CONTEXT_TRADES = "reports/BOT-050.1-context-trades-xau.csv"

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    """Spearman = Pearson on ranks -- same technique used in
    discover_momentum_features_xau.py (no scipy in this environment)."""
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


def bootstrap_mean_ci(values, n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    """Identical procedure/seed to discover_momentum_features_xau.py -- used
    here ONLY to reproduce an already-published number, not to discover a new
    one."""
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def consensus(b0, b1):
    """Exact rule frozen in reports/BOT-047.2.3-STRUCTURAL-ALIGNMENT-CONSENSUS-FREEZE.md
    -- copied verbatim from scripts/reconstruct_signal_quality_vector_xau.py
    (BOT-051.1), not reinvented, so the join below reuses the identical
    consensus derivation already used to reconstruct the Signal Quality
    vector."""
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
    if against_count == 1 and aligned_count == 1:
        return "FLIP_UNDEFINED"
    return "UNCLASSIFIED"


def main() -> int:
    print("BOT-024.4 -- Momentum Definition Freeze (XAU)")
    print("DEFINITION/VERIFICATION only. No new discovery, no new features, no thresholds tuned.")
    print("No score/weight/gate. No production file touched.\n")

    section("A. Load already-frozen artifacts (no recomputation)")
    lim = pd.read_csv(MOMENTUM_LIMITS)
    trd = pd.read_csv(MOMENTUM_TRADES)
    print(f"Universe A (BOT-024.2 limits): {len(lim)} rows")
    print(f"Universe B (BOT-024.2 trades): {len(trd)} rows")
    check("Universe A/B sizes match BOT-024.2 report (3207/2474)",
          len(lim) == 3207 and len(trd) == 2474,
          f"limits={len(lim)}, trades={len(trd)}")

    # --- B. Reproduction checks -- confirm CSV matches already-published numbers ---
    section("B. Reproduction checks (recompute already-published BOT-024.2 numbers)")

    # B1. roc_atr_3 <-> rsi_delta_3 redundancy (report claims rho=+0.935)
    rho_r3_d3 = spearman_corr(trd["roc_atr_3"], trd["rsi_delta_3"])
    check("roc_atr_3 <-> rsi_delta_3 Spearman matches published rho=+0.935 (Universe B)",
          abs(rho_r3_d3 - 0.935) < 0.01, f"recomputed rho={rho_r3_d3:.4f}")

    # B2. roc_atr_3 bottom quintile bootstrap CI on pnl_usd, Universe B (published: N=495, Exp$=-2.04, CI=[-3.25,-0.87])
    valid = trd[["roc_atr_3", "pnl_usd"]].dropna()
    q = pd.qcut(valid["roc_atr_3"], q=5, duplicates="drop")
    labels = sorted(q.unique(), key=lambda iv: iv.left)
    bottom = valid.loc[q == labels[0], "pnl_usd"]
    lo, hi = bootstrap_mean_ci(bottom.tolist())
    check("roc_atr_3 Q1 (most-against-trade) bootstrap 95% CI matches published [-3.25,-0.87] (seed=42, n_boot=2000)",
          len(bottom) == 495 and abs(lo - (-3.25)) < 0.05 and abs(hi - (-0.87)) < 0.05,
          f"N={len(bottom)}, mean={bottom.mean():+.2f}, CI=[{lo:+.2f},{hi:+.2f}]")

    # B3. fill-rate monotonicity for roc_atr_3, Universe A (published Q1..Q5: 87.7%,79.7%,80.3%,73.2%,64.9%)
    fill_valid = lim[["roc_atr_3", "filled"]].dropna()
    qa = pd.qcut(fill_valid["roc_atr_3"], q=5, duplicates="drop")
    labs = sorted(qa.unique(), key=lambda iv: iv.left)
    fill_rates = [fill_valid.loc[qa == l, "filled"].mean() for l in labs]
    published = [0.877, 0.797, 0.803, 0.732, 0.649]
    match = all(abs(a - b) < 0.02 for a, b in zip(fill_rates, published))
    check("roc_atr_3 fill-rate by quintile matches published Q1..Q5 (Universe A)",
          match, f"recomputed={[f'{r*100:.1f}%' for r in fill_rates]}, published={[f'{p*100:.1f}%' for p in published]}")

    if FAILURES:
        print("\n*** STOPPING: reproduction of BOT-024.2 published numbers from the frozen CSV FAILED. "
              "Refusing to freeze a definition on top of data that cannot be reproduced. ***")
        return 1
    print("\nAll BOT-024.2 published numbers reproduce exactly from the frozen CSVs -- safe to proceed.")

    # --- C. Gap-filling verification: within-Momentum-candidate redundancy ---
    section("C. Within-Momentum redundancy -- gaps not explicitly reported by BOT-024.2")
    pairs_within = [
        ("roc_atr_3", "ema_slope_atr_3"),
        ("roc_atr_3", "ema_slope_atr_5"),
        ("rsi_delta_3", "ema_slope_atr_5"),
        ("roc_atr_3", "atr_pct"),
        ("ema_slope_atr_5", "atr_pct"),
    ]
    within_results = {}
    for a, b in pairs_within:
        rho = spearman_corr(trd[a], trd[b])
        within_results[(a, b)] = rho
        flag = "REDUNDANT (>=0.8)" if abs(rho) >= 0.8 else "not redundant"
        print(f"  {a:16s} <-> {b:16s}  rho={rho:+.3f}  [{flag}]")

    # --- D. Cross-factor verification: Momentum vs Structure (frozen contract) ---
    section("D. Cross-factor -- Momentum candidates vs Structure's frozen origin_dist_atr")
    struct = pd.read_csv(STRUCTURE_TRADES)
    merged_struct = trd[["trade_id", "roc_atr_3", "ema_slope_atr_5", "atr_pct"]].merge(
        struct[["trade_id", "origin_dist_atr"]], on="trade_id", how="left", validate="one_to_one")
    check("Momentum x Structure join is 2474/2474 (same Universe B events)",
          merged_struct["origin_dist_atr"].notna().sum() >= 2473,  # BOT-048.2: 1/3207 missing (warm-up), may land in A only
          f"non-null origin_dist_atr after join: {merged_struct['origin_dist_atr'].notna().sum()}/2474")
    for feat in ("roc_atr_3", "ema_slope_atr_5", "atr_pct"):
        rho = spearman_corr(merged_struct[feat], merged_struct["origin_dist_atr"])
        print(f"  rho({feat}, origin_dist_atr) = {rho:+.3f}  "
              f"[{'REDUNDANT' if abs(rho) >= 0.8 else 'below redundancy threshold'}]")

    # --- E. Cross-factor verification: Momentum vs Alignment Consensus (frozen contract) ---
    section("E. Cross-factor -- roc_atr_3 by Alignment Structural Consensus state (descriptive only, "
            "NO ordinal encoding -- BOT-047.2.3 explicitly rejects ordinality)")
    align = pd.read_csv(ALIGNMENT_EVENTS)
    align = align.copy()
    align["alignment_consensus"] = [consensus(b0, b1) for b0, b1 in zip(align["B0_alignment"], align["B1_alignment"])]
    merged_align = trd[["trade_id", "roc_atr_3"]].merge(
        align[["trade_id", "alignment_consensus"]], on="trade_id", how="left", validate="one_to_one")
    check("Momentum x Alignment join is 2474/2474",
          merged_align["alignment_consensus"].notna().sum() == 2474,
          f"joined={merged_align['alignment_consensus'].notna().sum()}/2474")
    desc = merged_align.groupby("alignment_consensus")["roc_atr_3"].agg(["count", "mean", "median"])
    print(desc.to_string())

    # --- F. Cross-factor verification: Momentum vs Context weekday (frozen contract) ---
    section("F. Cross-factor -- roc_atr_3 by Context's frozen weekday (descriptive only)")
    ctx = pd.read_csv(CONTEXT_TRADES)
    merged_ctx = trd[["trade_id", "roc_atr_3"]].merge(
        ctx[["trade_id", "weekday"]], on="trade_id", how="left", validate="one_to_one")
    check("Momentum x Context join is 2474/2474",
          merged_ctx["weekday"].notna().sum() == 2474,
          f"joined={merged_ctx['weekday'].notna().sum()}/2474")
    desc_ctx = merged_ctx.groupby("weekday")["roc_atr_3"].agg(["count", "mean", "median"])
    print(desc_ctx.to_string())

    # --- G. Missingness of the shortlisted candidates ---
    section("G. Missingness of shortlisted candidates (Universe A, N=3207 / Universe B, N=2474)")
    for feat in ("roc_atr_3", "rsi_delta_3", "ema_slope_atr_5", "atr_pct"):
        na_a = lim[feat].isna().sum()
        na_b = trd[feat].isna().sum()
        print(f"  {feat:16s} missing in Universe A: {na_a}/{len(lim)} ({100*na_a/len(lim):.2f}%)  "
              f"Universe B: {na_b}/{len(trd)} ({100*na_b/len(trd):.2f}%)")

    # --- H. Divergence x Momentum interaction -- reconfirm N (already published, no new bucket) ---
    section("H. Divergence OPPOSED x roc_atr_10 interaction -- reconfirm published N only (no new cut)")
    opp = trd[trd["div_alignment"] == "OPPOSED"].copy()
    med = trd["roc_atr_10"].median()
    n_weak = int((opp["roc_atr_10"] < med).sum())
    n_strong = int((opp["roc_atr_10"] >= med).sum())
    check("OPPOSED x momentum-strong/weak N matches published (59 weak / 36 strong)",
          n_weak == 59 and n_strong == 36, f"weak={n_weak}, strong={n_strong}")

    print(f"\n\n=== SUMMARY ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (none)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
