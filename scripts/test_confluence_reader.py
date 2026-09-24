"""BOT-052.1 -- deterministic causality / parity tests for scripts/confluence_reader.py.

Run as a plain script (project convention, no pytest installed):
    .venv/Scripts/python.exe scripts/test_confluence_reader.py
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import confluence_reader as cr  # noqa: E402

FAILURES: list[str] = []
NAN = math.nan


def check(label: str, condition: bool, evidence: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def same(a, b) -> bool:
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype == bool or b.dtype == bool:
        return bool((a == b).all())
    return bool(np.array_equal(a, b, equal_nan=True))


# --------------------------------------------------------------------------- synthetic HCH
def test_hch_synthetic():
    # resistance plot: 10 -> 12 (head, same block) -> na (new block) -> 11 (right shoulder)
    res = np.array([10, 12, NAN, 11, 11, 11, 11], dtype=float)
    sup = np.full(7, 5.0)
    sell = np.array([0, 0, 0, 0, 1, 0, 1], dtype=bool)
    buy = np.zeros(7, dtype=bool)
    o = cr.emulate_hch(res, sup, sell, buy, 0.001)
    check("HCH sell forms when the right shoulder arrives (bar 3)", bool(o["hch_sell_formed"][3]) and o["hch_sell_level"][3] == 11)
    check("HCH check on the first sell arrow while level == right shoulder", bool(o["sell_pivot"][4]))
    check("HCH level is consumed: the next arrow on the same level gets no check", not o["sell_pivot"][6])
    # same-bar formation + arrow is allowed (update block runs before the check, Pine L187 < L265)
    sell2 = np.array([0, 0, 0, 1, 0, 0, 0], dtype=bool)
    o2 = cr.emulate_hch(res, sup, sell2, buy, 0.001)
    check("HCH check allowed on the same bar the pattern forms", bool(o2["sell_pivot"][3]))
    # plotted level moved away from the HCH level -> no check
    res3 = np.array([10, 12, NAN, 11, 11.5, 11.5], dtype=float)
    sell3 = np.array([0, 0, 0, 0, 0, 1], dtype=bool)
    o3 = cr.emulate_hch(res3, np.full(6, 5.0), sell3, np.zeros(6, dtype=bool), 0.001)
    check("No HCH check once the plotted resistance moved off the HCH level", not o3["sell_pivot"][5])
    # mirror for support
    sup4 = np.array([10, 8, NAN, 9, 9], dtype=float)
    buy4 = np.array([0, 0, 0, 0, 1], dtype=bool)
    o4 = cr.emulate_hch(np.full(5, 20.0), sup4, np.zeros(5, dtype=bool), buy4, 0.001)
    check("Inverse HCH on support gives a buy check", bool(o4["hch_buy_formed"][3]) and bool(o4["buy_pivot"][4]))
    # head not strictly highest -> no pattern (equality not allowed, Pine uses >)
    res5 = np.array([12, 12, NAN, 11, 11], dtype=float)  # 12 -> 12 is not a change: only 2 events
    res5b = np.array([11, 12, NAN, 12, 12], dtype=float)
    o5 = cr.emulate_hch(res5b, np.full(5, 5.0), np.array([0, 0, 0, 0, 1], dtype=bool), np.zeros(5, dtype=bool), 0.001)
    check("Head equal to a shoulder is not an HCH (strict >)", not o5["hch_sell_formed"].any())
    o5a = cr.emulate_hch(res5, np.full(5, 5.0), np.zeros(5, dtype=bool), np.zeros(5, dtype=bool), 0.001)
    check("Unchanged plotted value is not a new level", int(o5a["new_res"].sum()) == 2)


def test_shoulder_tolerance_is_vacuous():
    rng = np.random.default_rng(0)
    ok = True
    for _ in range(20000):
        r3, r1 = rng.uniform(0, 100, 2)
        r2 = max(r3, r1) + rng.uniform(1e-6, 50)          # head strictly highest
        altura = r2 - min(r3, r1)
        ok &= abs(r3 - r1) <= altura * 1.0
    check("Shoulder rule |s3-s1| <= tol*height always holds for tol>=1 once the head is highest "
          "(so tol=1.25 never filters anything)", bool(ok))


def test_d_and_edges():
    check("d_state strict: close == daily open gives EQUAL (no D check)", cr.d_state(1, 5.0, 5.0, True) == "EQUAL")
    check("d_state LONG above open is ALIGNED", cr.d_state(1, 5.1, 5.0, True) == "ALIGNED")
    check("d_state SHORT above open is AGAINST", cr.d_state(-1, 5.1, 5.0, True) == "AGAINST")
    check("d_state unavailable propagates", cr.d_state(-1, 5.1, 5.0, False) == "UNAVAILABLE")
    check("rising_edge", same(cr.rising_edge(np.array([1, 1, 0, 1], dtype=bool)), np.array([1, 0, 0, 1], dtype=bool)))
    # 22:00 UTC session day
    t = np.array([pd.Timestamp("2026-01-05 21:55", tz="UTC").timestamp(),
                  pd.Timestamp("2026-01-05 22:00", tz="UTC").timestamp()], dtype=np.int64)
    k = cr.day_keys(t, "TV22")
    check("TV22 day changes at 22:00 UTC", k[0] != k[1])
    k0 = cr.day_keys(t, "UTC00")
    check("UTC00 day does not change at 22:00 UTC", k0[0] == k0[1])
    tw = np.array([pd.Timestamp("2026-01-05 22:55", tz="UTC").timestamp(),
                   pd.Timestamp("2026-01-05 23:00", tz="UTC").timestamp()], dtype=np.int64)
    kn = cr.day_keys(tw, "NY18")
    check("NY18 in US winter changes at 23:00 UTC", kn[0] != kn[1])
    ts = np.array([pd.Timestamp("2026-07-06 21:55", tz="UTC").timestamp(),
                   pd.Timestamp("2026-07-06 22:00", tz="UTC").timestamp()], dtype=np.int64)
    ks = cr.day_keys(ts, "NY18")
    check("NY18 in US summer changes at 22:00 UTC", ks[0] != ks[1])


# --------------------------------------------------------------------------- real-data causality
FEATURE_KEYS = ["sell_sig", "buy_sig", "res_src", "sup_src", "ema50", "ema200", "ema200_m15_prev",
                "ema200_m15_smooth"] + [f"daily_open_{v}" for v in cr.D_VARIANTS] + \
               [f"daily_open_avail_{v}" for v in cr.D_VARIANTS]
HCH_KEYS = ["sell_pivot", "buy_pivot", "hch_sell_level", "hch_buy_level", "res1", "res2", "res3",
            "sop1", "sop2", "sop3", "new_res", "new_sup"]


def arrays(df):
    return (df["time_utc"].to_numpy(np.int64), df["time_server"].to_numpy(np.int64), df["open"].to_numpy(float),
            df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float),
            df["spread"].to_numpy(float))


def feats_equal_upto(fa, fb, cut) -> list[str]:
    bad = [k for k in FEATURE_KEYS if not same(fa[k][:cut], fb[k][:cut])]
    bad += [f"hch.{k}" for k in HCH_KEYS if not same(fa["hch"][k][:cut], fb["hch"][k][:cut])]
    return bad


def test_prefix_and_future_perturbation():
    df = pd.read_parquet(REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet").iloc[:15000].reset_index(drop=True)
    full = cr.build_bar_features(*arrays(df))
    again = cr.build_bar_features(*arrays(df))
    check("Deterministic replay: two full runs are identical", not feats_equal_upto(full, again, len(df)))
    rng = np.random.default_rng(521)
    cuts = sorted(set(int(x) for x in rng.integers(2500, 14900, 12)))
    bad_prefix, bad_future = [], []
    for cut in cuts:
        pre = cr.build_bar_features(*arrays(df.iloc[:cut]))
        b = feats_equal_upto(full, pre, cut)
        if b:
            bad_prefix.append((cut, b))
        # future perturbation: scramble every bar >= cut; nothing < cut may change
        pert = df.copy()
        idx = pert.index >= cut
        noise = rng.normal(0, 25, idx.sum())
        for col in ("open", "high", "low", "close"):
            pert.loc[idx, col] = pert.loc[idx, col] + noise
        pert.loc[idx, "high"] = pert.loc[idx, ["open", "high", "low", "close"]].max(axis=1) + 1
        pert.loc[idx, "low"] = pert.loc[idx, ["open", "high", "low", "close"]].min(axis=1) - 1
        fp = cr.build_bar_features(*arrays(pert))
        b = feats_equal_upto(full, fp, cut)
        if b:
            bad_future.append((cut, b))
    check(f"Prefix parity: features on bars[:cut] identical to the full run ({len(cuts)} cuts)",
          not bad_prefix, str(bad_prefix[:2]))
    check(f"Future perturbation: scrambling bars >= cut never changes a feature before cut ({len(cuts)} cuts)",
          not bad_future, str(bad_future[:2]))

    # M15 semantics: value at bar i uses only COMPLETED M15 bars (the [1] + lookahead_on idiom)
    t = df["time_utc"].to_numpy(np.int64)
    k = t // cr.M15_S
    first_in_m15 = np.r_[True, k[1:] != k[:-1]]
    i = int(np.flatnonzero(first_in_m15)[500])
    j = i + 1 if k[i + 1] == k[i] else i
    same_prev = full["ema200_m15_prev"][i] == full["ema200_m15_prev"][j]
    check("EMA200 M15 base is constant inside an M15 bar (only the M5 close nudges it)", bool(same_prev))
    prev_close_idx = i - 1
    m15_last = np.flatnonzero(np.r_[k[1:] != k[:-1], True])
    ema15 = cr.pine_ema(df["close"].to_numpy()[m15_last], 200)
    pos = int(np.searchsorted(m15_last, prev_close_idx))
    check("EMA200 M15 base at an M15 open == EMA of the M15 bar that just closed",
          math.isclose(full["ema200_m15_prev"][i], ema15[pos]))


def test_static_no_lookahead_patterns():
    pats = [r"shift\(\s*-", r"center\s*=\s*True", r"\[\s*i\s*\+\s*\d", r"\[\s*b\s*\+\s*\d", r"iloc\[\s*-"]
    for rel in ("scripts/confluence_reader.py", "strategy/hch.py"):
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        hits = [p for p in pats if re.search(p, src)]
        check(f"{rel} has no negative shifts / centered windows / [i+k] indexing", not hits, str(hits))


if __name__ == "__main__":
    test_hch_synthetic()
    test_shoulder_tolerance_is_vacuous()
    test_d_and_edges()
    test_static_no_lookahead_patterns()
    test_prefix_and_future_perturbation()
    print(f"\n{'ALL PASS' if not FAILURES else f'{len(FAILURES)} FAILURE(S): {FAILURES}'}")
    sys.exit(1 if FAILURES else 0)
