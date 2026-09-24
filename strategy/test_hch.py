"""BOT-052.2 -- causality / parity / restart-recovery tests for
strategy/hch.py (the canonical HCH engine, frozen from BOT-052.1's causal
reconstruction of the TradingView "Lector de confluencias").

Complements, does not duplicate, scripts/test_confluence_reader.py's 25
existing tests (BOT-052.1) -- those already exhaustively cover the batch
pipeline (prefix parity, future perturbation, static no-lookahead scan,
synthetic HCH geometry) and, since scripts/confluence_reader.py::emulate_hch()
is now a thin wrapper around strategy.hch.HCHEngine (BOT-052.2 Phase 2), they
already exercise this module's core loop indirectly. This file adds what did
NOT exist before BOT-052.2:

  A. exact historical parity against the COMMITTED BOT-052.1 artifact
     (reports/BOT-052.1-confluence-reader-events.csv) -- an INDEPENDENT check,
     not just "my code agrees with itself";
  B. unit tests for hch_state_for_signal() (HCH/NO_HCH/UNAVAILABLE), never
     tested standalone before BOT-052.2 (that logic lived inline in the
     research script discover_confluence_reader_xau.py::confluence_row());
  C. no-outcome-leakage (structural, same discipline as
     strategy/test_signal_quality.py);
  D. restart/recovery parity: a cold-started engine, replayed only the last
     N bars before a cut point, must reach the EXACT same state as a
     continuous run at that point (BOT-052.2 Phase 5 -- proves the chosen
     lookback_buckets=3 warm-up window used by execution/src/bot.py is
     genuinely sufficient, with real data, not asserted by faith);
  E. raw-arrow state consumption: HCH state MUST reflect every arrow,
     including ones a downstream execution layer would reject for invalid
     stop or concurrency -- feeding only the accepted subset silently
     diverges from the frozen Pine semantics (BOT-052.1 section 3.1);
  F. special regression: removing future bars after an HCH-tagged event does
     not change that event's frozen HCH state (explicitly required by
     BOT-052.2 Phase 7).

Uso:
    .venv/Scripts/python.exe strategy/test_hch.py
"""
from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from strategy.hch import (  # noqa: E402
    HCHEngine, HCHStepResult, HCH_STATE_HCH, HCH_STATE_NO_HCH, HCH_STATE_UNAVAILABLE,
    hch_state_for_signal,
)

FAILURES: list[str] = []
NAN = math.nan


def check(label: str, condition: bool, evidence: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


# --------------------------------------------------------------------------- B. hch_state_for_signal()
def test_hch_state_for_signal():
    step_hch = HCHStepResult(
        sell_pivot=True, buy_pivot=False, hch_sell_formed=False, hch_buy_formed=False,
        res1=100.0, res2=105.0, res3=99.0, sop1=NAN, sop2=NAN, sop3=NAN,
        hch_sell_level=100.0, hch_buy_level=NAN, hch_sell_form_bar=3.0, hch_buy_form_bar=NAN,
        new_res=False, new_sup=False,
    )
    state, audit = hch_state_for_signal(-1, step_hch)
    check("pivot=True -> HCH", state == HCH_STATE_HCH, state)
    check("audit carries the 3 pivots for the side used", audit["hch_pivot_1"] == 100.0
          and audit["hch_pivot_2"] == 105.0 and audit["hch_pivot_3"] == 99.0)
    check("audit carries active level + formation bar", audit["hch_active_level"] == 100.0
          and audit["hch_formation_bar"] == 3)

    step_no_hch = HCHStepResult(
        sell_pivot=False, buy_pivot=False, hch_sell_formed=False, hch_buy_formed=False,
        res1=100.0, res2=105.0, res3=99.0, sop1=NAN, sop2=NAN, sop3=NAN,
        hch_sell_level=NAN, hch_buy_level=NAN, hch_sell_form_bar=NAN, hch_buy_form_bar=NAN,
        new_res=False, new_sup=False,
    )
    state2, audit2 = hch_state_for_signal(-1, step_no_hch)
    check("pivot=False but 3 pivots known -> NO_HCH", state2 == HCH_STATE_NO_HCH, state2)
    check("NO_HCH: active level/formation bar are None (already consumed/never formed)",
          audit2["hch_active_level"] is None and audit2["hch_formation_bar"] is None)

    step_cold = HCHStepResult(
        sell_pivot=False, buy_pivot=False, hch_sell_formed=False, hch_buy_formed=False,
        res1=100.0, res2=NAN, res3=NAN, sop1=NAN, sop2=NAN, sop3=NAN,
        hch_sell_level=NAN, hch_buy_level=NAN, hch_sell_form_bar=NAN, hch_buy_form_bar=NAN,
        new_res=False, new_sup=False,
    )
    state3, audit3 = hch_state_for_signal(-1, step_cold)
    check("fewer than 3 pivots known -> UNAVAILABLE (cold start)", state3 == HCH_STATE_UNAVAILABLE, state3)
    check("UNAVAILABLE: pivot_2/pivot_3 are None (JSON-safe, not NaN)",
          audit3["hch_pivot_2"] is None and audit3["hch_pivot_3"] is None)

    # BUY side (direction > 0) must read sop1/2/3 and buy_pivot, never the sell side.
    step_buy = HCHStepResult(
        sell_pivot=False, buy_pivot=True, hch_sell_formed=False, hch_buy_formed=False,
        res1=NAN, res2=NAN, res3=NAN, sop1=50.0, sop2=45.0, sop3=51.0,
        hch_sell_level=NAN, hch_buy_level=50.0, hch_sell_form_bar=NAN, hch_buy_form_bar=7.0,
        new_res=False, new_sup=False,
    )
    state4, audit4 = hch_state_for_signal(1, step_buy)
    check("direction>0 (LONG) reads the BUY/support side, not sell/resistance",
          state4 == HCH_STATE_HCH and audit4["hch_pivot_1"] == 50.0)


# --------------------------------------------------------------------------- C. no-outcome-leakage
def test_no_outcome_leakage():
    forbidden = {"pnl", "pnl_r", "pnl_usd", "outcome", "win", "loss", "fill_bar",
                 "mfe", "mae", "close_reason", "tp_hit", "sl_hit", "duration", "fill"}
    for fn in (HCHEngine.step, hch_state_for_signal):
        sig = inspect.signature(fn)
        leaked = forbidden & set(sig.parameters.keys())
        check(f"{fn.__qualname__}() has no outcome-shaped parameter", not leaked, f"leaked={leaked}")


# --------------------------------------------------------------------------- shared real-data fixture
def _load_full_run():
    import confluence_reader as cr
    df = pd.read_parquet(REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet")
    arrs = (df["time_utc"].to_numpy(np.int64), df["time_server"].to_numpy(np.int64), df["open"].to_numpy(float),
            df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float),
            df["spread"].to_numpy(float))
    feats = cr.build_bar_features(*arrs)
    return feats, cr.MINTICK_PRIMARY


def _step_at(feats: dict, b: int) -> HCHStepResult:
    h = feats["hch"]
    return HCHStepResult(
        sell_pivot=bool(h["sell_pivot"][b]), buy_pivot=bool(h["buy_pivot"][b]),
        hch_sell_formed=bool(h["hch_sell_formed"][b]), hch_buy_formed=bool(h["hch_buy_formed"][b]),
        res1=h["res1"][b], res2=h["res2"][b], res3=h["res3"][b],
        sop1=h["sop1"][b], sop2=h["sop2"][b], sop3=h["sop3"][b],
        hch_sell_level=h["hch_sell_level"][b], hch_buy_level=h["hch_buy_level"][b],
        hch_sell_form_bar=h["hch_sell_form_bar"][b], hch_buy_form_bar=h["hch_buy_form_bar"][b],
        new_res=bool(h["new_res"][b]), new_sup=bool(h["new_sup"][b]),
    )


# --------------------------------------------------------------------------- A. historical parity vs committed CSV
def test_historical_parity_vs_committed_csv():
    events_path = REPO_ROOT / "reports" / "BOT-052.1-confluence-reader-events.csv"
    if not events_path.exists():
        check("reports/BOT-052.1-confluence-reader-events.csv exists (BOT-052.1 artifact)", False,
              "cannot run parity check without the committed golden file")
        return
    events = pd.read_csv(events_path)
    check("Universe A row count matches BOT-052.1 (3207)", len(events) == 3207, f"got {len(events)}")

    counts = events["HCH_state"].value_counts()
    check("Universe A HCH count == 234", counts.get("HCH", 0) == 234, f"got {counts.get('HCH', 0)}")
    check("Universe A NO_HCH count == 2972", counts.get("NO_HCH", 0) == 2972, f"got {counts.get('NO_HCH', 0)}")
    check("Universe A UNAVAILABLE count == 1", counts.get("UNAVAILABLE", 0) == 1, f"got {counts.get('UNAVAILABLE', 0)}")

    feats, mintick = _load_full_run()
    direction_map = {"LONG": 1, "SHORT": -1}
    mismatches = []
    for _, row in events.iterrows():
        b = int(row["limit_created_bar"])
        d = direction_map[row["direction"]]
        state, _audit = hch_state_for_signal(d, _step_at(feats, b))
        if state != row["HCH_state"]:
            mismatches.append((row["trade_id"], b, row["direction"], state, row["HCH_state"]))
    check(f"Event-level HCH_state parity: {len(events)}/{len(events)} exact match "
          "(strategy.hch.hch_state_for_signal() reproduces the committed BOT-052.1 artifact one for one)",
          not mismatches, f"first mismatches: {mismatches[:5]}")

    # Universe B (evaluable/filled trades) -- same golden numbers from BOT-052.1.
    filled = events[events["filled"] == True]  # noqa: E712
    check("Universe B row count matches BOT-052.1 (2474)", len(filled) == 2474, f"got {len(filled)}")
    fcounts = filled["HCH_state"].value_counts()
    check("Universe B HCH count == 161", fcounts.get("HCH", 0) == 161, f"got {fcounts.get('HCH', 0)}")
    check("Universe B NO_HCH count == 2313", fcounts.get("NO_HCH", 0) == 2313, f"got {fcounts.get('NO_HCH', 0)}")


# --------------------------------------------------------------------------- D. restart/recovery parity
def test_restart_recovery_parity():
    """BOT-052.2 Phase 5 -- the SAME lookback window execution/src/bot.py's
    replay_startup() reuses for HCH warm-up (lookback_buckets=3 *
    periodos_htf_min=800 = 2400min = 480 M5 bars) must reconstruct the EXACT
    same res1-3/sop1-3 state a continuous run has at that point -- not just
    "eventually available"."""
    feats, mintick = _load_full_run()
    res_src, sup_src = feats["res_src"], feats["sup_src"]
    sell_sig, buy_sig = feats["sell_sig"], feats["buy_sig"]
    n = len(res_src)
    LOOKBACK_BARS = 480  # execution/src/bot.py: lookback_buckets(3) * periodos_htf_min(800) / 5min

    rng = np.random.default_rng(29)
    cuts = sorted(set(int(x) for x in rng.integers(LOOKBACK_BARS + 50, n - 1, 40)))
    bad = []
    not_warm = []
    for cut in cuts:
        start = cut - LOOKBACK_BARS
        eng = HCHEngine()
        for i in range(start, cut + 1):
            eng.step(i, res_src[i], sup_src[i], bool(sell_sig[i]), bool(buy_sig[i]), mintick)
        have3 = not (math.isnan(eng.res1) or math.isnan(eng.res2) or math.isnan(eng.res3)
                     or math.isnan(eng.sop1) or math.isnan(eng.sop2) or math.isnan(eng.sop3))
        if not have3:
            not_warm.append(cut)
            continue
        full_state = (feats["hch"]["res1"][cut], feats["hch"]["res2"][cut], feats["hch"]["res3"][cut],
                      feats["hch"]["sop1"][cut], feats["hch"]["sop2"][cut], feats["hch"]["sop3"][cut])
        restart_state = (eng.res1, eng.res2, eng.res3, eng.sop1, eng.sop2, eng.sop3)
        if not np.allclose(full_state, restart_state, equal_nan=True):
            bad.append((cut, full_state, restart_state))
    check(f"480-bar (lookback_buckets=3) replay reaches EXACT parity with the continuous run "
          f"at all {len(cuts)} sampled restart points", not bad, f"first mismatches: {bad[:3]}")
    check("480 bars was enough to fully warm up (res1-3 AND sop1-3) at every sampled restart point "
          "(empirical justification for reusing this window instead of inventing a new one, BOT-052.2 Phase 5)",
          not not_warm, f"cold cuts: {not_warm[:5]}")


# --------------------------------------------------------------------------- E. raw-arrow consumption
def test_raw_arrow_consumption_required():
    """BOT-052.1 section 3.1: the Pine indicator's plotshape fires (and HCH
    consumes/checks) on EVERY arrow, including ones a downstream execution
    layer discards for invalid stop or concurrency. Demonstrates that
    skipping a "rejected" arrow produces a DIFFERENT HCH trajectory than
    including it -- i.e. execution/src/bot.py MUST feed HCHEngine the raw
    signal.senal_venta/senal_compra (BOT-051.4's unfiltered fields), never a
    post-concurrency-filtered stream."""
    # resistance forms an HCH pattern; TWO sell arrows land on the shoulder:
    # the first "rejected" (simulating a concurrency/stop-invalid arrow the
    # bot would have discarded) and the second real.
    res = np.array([10, 12, NAN, 11, 11, 11], dtype=float)
    sup = np.full(6, 5.0)
    mintick = 0.001

    # Including BOTH arrows (matches the Pine / BOT-052.1 semantics):
    # the first arrow consumes the HCH level -> the second gets NO_HCH.
    sell_all = np.array([0, 0, 0, 0, 1, 1], dtype=bool)
    eng_all = HCHEngine()
    steps_all = [eng_all.step(i, res[i], sup[i], bool(sell_all[i]), False, mintick) for i in range(6)]
    check("including the raw (later-rejected) arrow: it consumes the HCH level",
          steps_all[4].sell_pivot)
    check("...so the SECOND arrow on the same level sees NO_HCH (level already consumed)",
          not steps_all[5].sell_pivot)

    # Feeding ONLY the accepted-LIMIT subset (skipping the first arrow, as a
    # BUGGY integration filtering by concurrency/validity BEFORE HCH would
    # do): the level is still active for the second arrow -> wrongly HCH.
    sell_filtered = np.array([0, 0, 0, 0, 0, 1], dtype=bool)
    eng_filtered = HCHEngine()
    steps_filtered = [eng_filtered.step(i, res[i], sup[i], bool(sell_filtered[i]), False, mintick) for i in range(6)]
    check("feeding only the ACCEPTED arrow (wrong integration) diverges: the level is still "
          "active, so the same bar 5 arrow would be misclassified as HCH instead of NO_HCH -- "
          "proves execution/src/bot.py must feed the RAW signal.senal_venta/senal_compra stream",
          steps_filtered[5].sell_pivot and not steps_all[5].sell_pivot)


# --------------------------------------------------------------------------- F. future-bar removal after an HCH-tagged event
def test_future_removal_does_not_change_tagged_event():
    feats, mintick = _load_full_run()
    hch_idx = np.flatnonzero(feats["hch"]["sell_pivot"] | feats["hch"]["buy_pivot"])
    check("at least one real HCH-tagged bar exists in the dataset (sanity check for this test itself)",
          len(hch_idx) > 0)
    if len(hch_idx) == 0:
        return
    tagged_bar = int(hch_idx[len(hch_idx) // 2])  # a real HCH event, not the very first/last

    import confluence_reader as cr
    df = pd.read_parquet(REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet")
    df_truncated = df.iloc[:tagged_bar + 1]
    df_extended = df.copy()
    rng = np.random.default_rng(3)
    idx = df_extended.index > tagged_bar
    noise = rng.normal(0, 30, int(idx.sum()))
    for col in ("open", "high", "low", "close"):
        df_extended.loc[idx, col] = df_extended.loc[idx, col] + noise
    df_extended.loc[idx, "high"] = df_extended.loc[idx, ["open", "high", "low", "close"]].max(axis=1) + 1
    df_extended.loc[idx, "low"] = df_extended.loc[idx, ["open", "high", "low", "close"]].min(axis=1) - 1

    def arrs(d):
        return (d["time_utc"].to_numpy(np.int64), d["time_server"].to_numpy(np.int64), d["open"].to_numpy(float),
                d["high"].to_numpy(float), d["low"].to_numpy(float), d["close"].to_numpy(float),
                d["spread"].to_numpy(float))

    feats_trunc = cr.build_bar_features(*arrs(df_truncated))
    feats_ext = cr.build_bar_features(*arrs(df_extended))
    same = all(
        (math.isnan(feats["hch"][k][tagged_bar]) and math.isnan(feats_trunc["hch"][k][tagged_bar])
         and math.isnan(feats_ext["hch"][k][tagged_bar]))
        or (feats["hch"][k][tagged_bar] == feats_trunc["hch"][k][tagged_bar] == feats_ext["hch"][k][tagged_bar])
        for k in ("sell_pivot", "buy_pivot", "res1", "res2", "res3", "sop1", "sop2", "sop3")
    )
    check(f"HCH state at the tagged bar ({tagged_bar}) is IDENTICAL whether computed from the full "
          "dataset, truncated right after it, or with all FUTURE bars scrambled -- removing/changing "
          "the future cannot retroactively alter an already-frozen HCH snapshot (BOT-052.2 Phase 7 "
          "special regression)", same)


if __name__ == "__main__":
    test_hch_state_for_signal()
    test_no_outcome_leakage()
    test_historical_parity_vs_committed_csv()
    test_restart_recovery_parity()
    test_raw_arrow_consumption_required()
    test_future_removal_does_not_change_tagged_event()
    print(f"\n{'ALL PASS' if not FAILURES else f'{len(FAILURES)} FAILURE(S): {FAILURES}'}")
    sys.exit(1 if FAILURES else 0)
