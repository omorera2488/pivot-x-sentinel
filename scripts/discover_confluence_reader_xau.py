"""BOT-052.1 -- Confluence Reader Historical Discovery, XAU.

RESEARCH ONLY / NO PRODUCTION CHANGES / NO SCORE / NO GATE / NO WEIGHTS.
Reconstructs the TradingView "Lector de confluencias" (Daily Open `D`, `HCH`,
EMA context) causally at `limit_created_bar` for every Universe A LIMIT and
measures whether it carries robust, non-redundant information about trade
quality. See reports/BOT-052.1-confluence-reader-historical-discovery.md.

Canonical inputs (reused, never regenerated):
  - backtests/data/XAUUSDc_M5_latest.parquet (same dataset as BOT-024..BOT-051)
  - Config A (scripts/confluence_reader.CONFIG_A, identical to BOT-050.1)
  - reports/BOT-050.1-context-limits-xau.csv   -> Universe A (3,207 LIMITs) + outcomes/PnL
  - reports/BOT-051.3-signal-quality-vector-shadow-xau.csv -> frozen SQ v1 factors
Recent-trade sanity check (Phase 8, read-only): execution/data/{scores,outcomes}
live stores + reports/BOT-052.1-recent-bars-xau.csv (M5 bars snapshotted from
MT5 read-only by --snapshot-recent; the analysis itself never touches MT5).

Usage:
    .venv/Scripts/python.exe scripts/discover_confluence_reader_xau.py [--snapshot-recent] \
        > reports/BOT-052.1-CONFLUENCE-READER-EVIDENCE.log
"""
from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import confluence_reader as cr  # noqa: E402
from strategy import hch as hch_mod  # noqa: E402 -- BOT-052.2: HCH_SHOULDER_TOL now lives here

DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
REPORTS = REPO_ROOT / "reports"
CSV_A = REPORTS / "BOT-050.1-context-limits-xau.csv"
CSV_SQ = REPORTS / "BOT-051.3-signal-quality-vector-shadow-xau.csv"
RECENT_BARS = REPORTS / "BOT-052.1-recent-bars-xau.csv"
LIVE_SCORES = REPO_ROOT / "execution" / "data" / "scores" / "XAUUSDc_900001.jsonl"
LIVE_OUTCOMES = REPO_ROOT / "execution" / "data" / "outcomes" / "XAUUSDc_900001.jsonl"

OUT_EVENTS = REPORTS / "BOT-052.1-confluence-reader-events.csv"
OUT_SUMMARY = REPORTS / "BOT-052.1-confluence-reader-summary.csv"
OUT_AUDIT = REPORTS / "BOT-052.1-confluence-reader-causality-audit.csv"
OUT_ROBUST = REPORTS / "BOT-052.1-confluence-reader-robustness.csv"
OUT_REDUND = REPORTS / "BOT-052.1-confluence-reader-redundancy.csv"
OUT_CF = REPORTS / "BOT-052.1-confluence-reader-counterfactual.csv"
OUT_RECENT = REPORTS / "BOT-052.1-confluence-reader-recent-trades.csv"

EXPECTED_A, EXPECTED_B = 3207, 2474
BOOT_N, BOOT_SEED = 5000, 52
PRIMARY_D = "TV22"
FAILURES: list[str] = []


def check(label, cond, evidence=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not cond:
        FAILURES.append(label)


def section(t):
    print(f"\n=== {t} ===")


def load_bars(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def bar_arrays(df):
    return (df["time_utc"].to_numpy(np.int64), df["time_server"].to_numpy(np.int64),
            df["open"].to_numpy(float), df["high"].to_numpy(float), df["low"].to_numpy(float),
            df["close"].to_numpy(float), df["spread"].to_numpy(float))


# ---------------------------------------------------------------------------
# Per-event confluence row (same function for history and recent live trades)
# ---------------------------------------------------------------------------
def confluence_row(f: dict, close: np.ndarray, b: int, d: int) -> dict:
    h = f["hch"]
    row = {"close_at_signal": close[b]}
    for v in cr.D_VARIANTS:
        row[f"daily_open_{v}"] = f[f"daily_open_{v}"][b]
        row[f"D_state_{v}"] = cr.d_state(d, close[b], f[f"daily_open_{v}"][b], bool(f[f"daily_open_avail_{v}"][b]))
    side = "sell" if d < 0 else "buy"
    lvl_key = "res" if d < 0 else "sop"
    row["hch_level_src"] = f["res_src"][b] if d < 0 else f["sup_src"][b]
    row["hch_pivot_1"] = h[f"{lvl_key}1"][b]
    row["hch_pivot_2"] = h[f"{lvl_key}2"][b]
    row["hch_pivot_3"] = h[f"{lvl_key}3"][b]
    row["hch_active_level"] = h[f"hch_{side}_level"][b]
    row["hch_form_bar"] = h[f"hch_{side}_form_bar"][b]
    have3 = not any(math.isnan(row[f"hch_pivot_{k}"]) for k in (1, 2, 3))
    pivot = bool(h[f"{side}_pivot"][b])
    row["HCH_state"] = "HCH" if pivot else ("NO_HCH" if have3 else "UNAVAILABLE")
    dstate = row[f"D_state_{PRIMARY_D}"]
    if dstate == "UNAVAILABLE" or row["HCH_state"] == "UNAVAILABLE":
        combo = "UNAVAILABLE"
    else:
        dd = dstate == "ALIGNED"
        combo = {(True, True): "D+HCH", (True, False): "D_ONLY", (False, True): "HCH_ONLY",
                 (False, False): "NEITHER"}[(dd, pivot)]
    row["combo_state"] = combo
    # Pine label text exactly as the indicator would print it
    row["pine_label"] = {"D+HCH": "D✓ HCH✓", "D_ONLY": "D✓", "HCH_ONLY": "HCH✓", "NEITHER": "(normal)"}.get(combo, "")
    e50, e200, e15 = f["ema50"][b], f["ema200"][b], f["ema200_m15_smooth"][b]
    row.update(ema50_m5=e50, ema200_m5=e200, ema200_m15_prev=f["ema200_m15_prev"][b], ema200_m15_smooth=e15)
    ema_ok = b >= cr.EMA_WARMUP_M5["ema200_m15"] and not math.isnan(e15)
    st = cr.ema_states(d, close[b], e50, e200, e15)
    for k, val in st.items():
        row[k] = ("ALIGNED" if val else "AGAINST") if ema_ok else "UNAVAILABLE"
    return row


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def cohort_stats(g: pd.DataFrame) -> dict:
    n = len(g)
    if n == 0:
        return dict(N=0)
    pnl = g["pnl_usd"]
    gp, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    out = dict(N=n, wins=int((g["outcome"] == "win").sum()), losses=int((g["outcome"] == "loss").sum()),
               timeouts=int((g["outcome"] == "timeout").sum()))
    out.update(WR=out["wins"] / n, pnl_total=pnl.sum(), pnl_mean=pnl.mean(), pnl_median=pnl.median(),
               PF=(gp / gl) if gl > 0 else float("inf"), ExpR=g["pnl_r"].mean())
    for dname in ("LONG", "SHORT"):
        s = g[g["direction"] == dname]
        out[f"N_{dname}"] = len(s)
        out[f"ExpR_{dname}"] = s["pnl_r"].mean() if len(s) else float("nan")
        out[f"WR_{dname}"] = (s["outcome"] == "win").mean() if len(s) else float("nan")
    return out


def fmt(s: dict) -> str:
    if s.get("N", 0) == 0:
        return "N=0"
    return (f"N={s['N']:4d} W/L/T={s['wins']}/{s['losses']}/{s['timeouts']} WR={s['WR']:.3f} "
            f"PnL={s['pnl_total']:+9.2f} mean={s['pnl_mean']:+.3f} med={s['pnl_median']:+.3f} "
            f"PF={s['PF']:.3f} ExpR={s['ExpR']:+.4f} | LONG N={s['N_LONG']} ExpR={s['ExpR_LONG']:+.4f} "
            f"| SHORT N={s['N_SHORT']} ExpR={s['ExpR_SHORT']:+.4f}")


def boot_diff(a: np.ndarray, b: np.ndarray, seed=BOOT_SEED, n=BOOT_N):
    if len(a) < 2 or len(b) < 2:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), (n, len(a)))
    ib = rng.integers(0, len(b), (n, len(b)))
    d = a[ia].mean(1) - b[ib].mean(1)
    return a.mean() - b.mean(), np.percentile(d, 2.5), np.percentile(d, 97.5)


def seq_metrics(g: pd.DataFrame) -> dict:
    g = g.sort_values(["exit_bar", "limit_created_bar"])
    out = {}
    for col in ("pnl_usd", "pnl_r"):
        eq = g[col].cumsum().to_numpy()
        peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
        out[f"maxDD_{col}"] = float((peak - eq).max()) if len(eq) else 0.0
    streak = best = 0
    for o in g["outcome"]:
        streak = streak + 1 if o == "loss" else 0
        best = max(best, streak)
    out["longest_losing_streak"] = best
    return out


def cramers_v(x: pd.Series, y: pd.Series) -> float:
    ct = pd.crosstab(x, y).to_numpy().astype(float)
    if ct.size == 0 or min(ct.shape) < 2:
        return float("nan")
    n = ct.sum()
    exp = ct.sum(1, keepdims=True) * ct.sum(0, keepdims=True) / n
    chi2 = ((ct - exp) ** 2 / exp).sum()
    return math.sqrt(chi2 / (n * (min(ct.shape) - 1)))


def stratified_delta(df: pd.DataFrame, flag: str, stratum: str) -> tuple[float, int]:
    """Weighted mean of within-stratum ExpR(flag) - ExpR(not flag), weights =
    harmonic mean of the two cell sizes. Strata with an empty cell are dropped."""
    num = den = 0.0
    used = 0
    for _, g in df.groupby(stratum, observed=True):
        a, b = g[g[flag]]["pnl_r"], g[~g[flag]]["pnl_r"]
        if len(a) == 0 or len(b) == 0:
            continue
        w = 2 * len(a) * len(b) / (len(a) + len(b))
        num += w * (a.mean() - b.mean())
        den += w
        used += 1
    return (num / den if den else float("nan")), used


# ---------------------------------------------------------------------------
def snapshot_recent_bars():
    """Read-only MT5 copy of recent M5 bars for the Phase 8 sanity check."""
    import MetaTrader5 as mt5
    from execution.src.mt5_utils import measure_broker_offset_seconds, resolve_symbol
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    sym = resolve_symbol("XAUUSDc")
    mt5.symbol_select(sym, True)
    off = measure_broker_offset_seconds(sym)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 8000)
    mt5.shutdown()
    df = pd.DataFrame(rates)
    df["time_server"] = df["time"].astype("int64")
    df["time_utc"] = df["time_server"] - round(off)       # same correction as execution/src/bot.py
    df = df.iloc[:-1]                                       # drop the still-forming bar
    df[["time", "time_server", "time_utc", "open", "high", "low", "close", "spread"]].to_csv(RECENT_BARS, index=False)
    print(f"snapshot: {len(df)} bars of {sym}, offset={off:+.2f}s -> {RECENT_BARS.name}")


def main():
    if "--snapshot-recent" in sys.argv:
        snapshot_recent_bars()

    # ------------------------------------------------------------------ 0
    section("0. Canonical inputs")
    bars = load_bars(DATA_PATH)
    t_utc, t_srv, o, h, l, c, sp = bar_arrays(bars)
    print(f"dataset: {DATA_PATH.relative_to(REPO_ROOT)} bars={len(bars)} "
          f"{pd.Timestamp(t_utc[0], unit='s')} -> {pd.Timestamp(t_utc[-1], unit='s')} UTC")
    print(f"Config A: {cr.CONFIG_A}  shared: {cr.SHARED}")
    ua = pd.read_csv(CSV_A)
    sq = pd.read_csv(CSV_SQ)
    check("Universe A count == 3,207", len(ua) == EXPECTED_A, f"rows={len(ua)}")
    ub_mask = ua["fate"] == "FILLED_CLOSED"
    check("Universe B count == 2,474", ub_mask.sum() == EXPECTED_B, f"FILLED_CLOSED={ub_mask.sum()}")
    check("SQ shadow covers Universe A 1:1 by trade_id/limit_created_bar",
          len(sq) == EXPECTED_A and (sq["trade_id"].values == ua["trade_id"].values).all()
          and (sq["limit_created_bar"].values == ua["limit_created_bar"].values).all())
    check("Price resolution is 0.001 (mintick used for HCH equality)",
          np.allclose(h * 1000, np.round(h * 1000)) and np.allclose(l * 1000, np.round(l * 1000)))

    # ------------------------------------------------------------------ 1
    section("1. Per-bar reconstruction (scripts/confluence_reader.build_bar_features)")
    f = cr.build_bar_features(t_utc, t_srv, o, h, l, c, sp)
    sl = f["signal_log"]
    print(f"arrows (all, incl. discarded): {len(sl)} | sell={int(f['sell_sig'].sum())} buy={int(f['buy_sig'].sum())}")
    check("rising edge == raw arrows (two arrows never on consecutive bars)",
          (f["sell_sig"] == f["sell_raw"]).all() and (f["buy_sig"] == f["buy_raw"]).all())
    sig_dir = {s["bar"]: s["dir"] for s in sl}
    dirs = ua["direction"].map({"LONG": 1, "SHORT": -1}).to_numpy()
    bars_a = ua["limit_created_bar"].to_numpy()
    match = all(sig_dir.get(int(b)) == int(d) for b, d in zip(bars_a, dirs))
    check("Every Universe A LIMIT is an arrow of the Pine replica at limit_created_bar with the same direction",
          match, f"{sum(sig_dir.get(int(b)) == int(d) for b, d in zip(bars_a, dirs))}/{len(bars_a)}")
    print(f"arrows not in Universe A (stop invalid / concurrency): {len(sl) - len(bars_a)} -- they still "
          f"feed the HCH state (Pine consumes an HCH level on ANY arrow)")
    hch = f["hch"]
    print(f"resistance events={int(hch['new_res'].sum())} support events={int(hch['new_sup'].sum())} "
          f"HCH sell formations={int(hch['hch_sell_formed'].sum())} HCH buy formations={int(hch['hch_buy_formed'].sum())}")
    print(f"HCH checks on ANY arrow: sell={int(hch['sell_pivot'].sum())} buy={int(hch['buy_pivot'].sum())}")

    # geometry of the formations (explains what HCH means with causal running levels)
    form_res = np.flatnonzero(hch["hch_sell_formed"])
    form_sup = np.flatnonzero(hch["hch_buy_formed"])
    fr_nb = np.mean([bool(np.isnan(f["res_src"][i - 1])) for i in form_res if i > 0]) if len(form_res) else float("nan")
    fs_nb = np.mean([bool(np.isnan(f["sup_src"][i - 1])) for i in form_sup if i > 0]) if len(form_sup) else float("nan")
    print(f"share of HCH formations whose right shoulder is the FIRST plotted level of a new HTF block: "
          f"sell={fr_nb:.3f} buy={fs_nb:.3f}  (running highs/lows only rise/fall inside a block, so a "
          f"lower right shoulder can only come from a block reset)")

    # ------------------------------------------------------------------ 2
    section("2. Event dataset (Universe A, one row per LIMIT)")
    rows = [confluence_row(f, c, int(b), int(d)) for b, d in zip(bars_a, dirs)]
    ev = pd.concat([ua.reset_index(drop=True), pd.DataFrame(rows),
                    sq[["roc_atr_3", "momentum_status", "alignment", "alignment_status", "origin_dist_atr",
                        "structure_status"]].reset_index(drop=True)], axis=1)
    entry_by_bar = {s["bar"]: s["entry"] for s in sl}
    ev["entry_limit_price"] = [entry_by_bar[int(b)] for b in bars_a]
    ev["month"] = pd.to_datetime(ev["entry_time_utc"]).dt.strftime("%Y-%m")
    ev["D_boundary_primary"] = PRIMARY_D
    ev.to_csv(OUT_EVENTS, index=False)
    print(f"wrote {OUT_EVENTS.name}: {len(ev)} rows x {ev.shape[1]} cols")

    B = ev[ev["fate"] == "FILLED_CLOSED"].copy()
    for v in cr.D_VARIANTS:
        B[f"D_{v}"] = B[f"D_state_{v}"] == "ALIGNED"
        ev[f"D_{v}"] = ev[f"D_state_{v}"] == "ALIGNED"
    B["HCH"] = B["HCH_state"] == "HCH"
    ev["HCH"] = ev["HCH_state"] == "HCH"
    B["DHCH"] = B["combo_state"] == "D+HCH"
    for k in cr.EMA_STATES:
        B[k + "_ok"] = B[k] == "ALIGNED"

    summary: list[dict] = []

    def add(cand, cohort, universe, g, **extra):
        s = cohort_stats(g) if universe == "B" else dict(N=len(g))
        summary.append(dict(candidate=cand, cohort=cohort, universe=universe, **s, **extra))
        return s

    # ------------------------------------------------------------------ 3
    section("3. Coverage (Universe A and B)")
    for uname, U in (("A", ev), ("B", B)):
        tot = len(U)
        print(f"-- Universe {uname}: N={tot}")
        for col in [f"D_state_{v}" for v in cr.D_VARIANTS] + ["HCH_state", "combo_state"] + list(cr.EMA_STATES):
            vc = U[col].value_counts()
            parts = []
            for state, k in vc.items():
                lk = int(((U[col] == state) & (U["direction"] == "LONG")).sum())
                parts.append(f"{state}={k} ({k / tot:.1%}; L={lk} S={k - lk})")
                summary.append(dict(candidate=col, cohort=state, universe=f"{uname}_coverage", N=int(k),
                                    pct=k / tot, N_LONG=lk, N_SHORT=int(k - lk)))
            print(f"   {col:22s} " + " | ".join(parts))

    # fill behaviour (Universe A) -- where logically meaningful
    print("-- Fill rate in Universe A by state (a filter acts on LIMITs, fills are downstream)")
    for col in (f"D_{PRIMARY_D}", "HCH"):
        for val, g in ev.groupby(col):
            fr = (g["fate"] == "FILLED_CLOSED").mean()
            print(f"   {col}={val}: N={len(g)} fill_rate={fr:.3f}")
            summary.append(dict(candidate=col, cohort=f"{val}", universe="A_fill_rate", N=len(g), fill_rate=fr))

    # ------------------------------------------------------------------ 4
    section("4. Outcomes (Universe B)")
    print("MAE/MFE: NOT reproducibly available in the canonical CSVs -> not reported.")
    print(f"ALL: {fmt(add('ALL', 'ALL', 'B', B))}")
    for v in cr.D_VARIANTS:
        print(f"-- Daily Open [{v}]")
        for lab, g in (("D_check", B[B[f"D_{v}"]]), ("no_D_check", B[~B[f"D_{v}"]]),
                       ("AGAINST", B[B[f"D_state_{v}"] == "AGAINST"]),
                       ("UNAVAILABLE", B[B[f"D_state_{v}"] == "UNAVAILABLE"])):
            print(f"   {lab:12s} {fmt(add(f'D_{v}', lab, 'B', g))}")
    print("-- HCH")
    for lab, g in (("HCH_check", B[B["HCH"]]), ("no_HCH_check", B[~B["HCH"]])):
        print(f"   {lab:12s} {fmt(add('HCH', lab, 'B', g))}")
    print("-- Combined (D primary = TV22)")
    for lab in ("D+HCH", "D_ONLY", "HCH_ONLY", "NEITHER", "UNAVAILABLE"):
        print(f"   {lab:12s} {fmt(add('COMBO', lab, 'B', B[B['combo_state'] == lab]))}")
    print("-- EMA context (declared states, see confluence_reader.EMA_STATES)")
    for k, desc in cr.EMA_STATES.items():
        print(f"   {k}: {desc}")
        for lab in ("ALIGNED", "AGAINST", "UNAVAILABLE"):
            print(f"      {lab:12s} {fmt(add(k, lab, 'B', B[B[k] == lab]))}")

    # ------------------------------------------------------------------ 5
    section("5. Robustness (Universe B): ExpR(flag) - ExpR(not flag) by partition")
    flags = {f"D_{v}": f"D_{v}" for v in cr.D_VARIANTS}
    flags.update({"HCH": "HCH", "DHCH": "DHCH"})
    flags.update({k: k + "_ok" for k in cr.EMA_STATES})
    ema_avail = B["E1_px_ema50"] != "UNAVAILABLE"
    robust_rows = []
    partitions = {"ALL": pd.Series("ALL", index=B.index), "direction": B["direction"],
                  "sub_periodo": B["sub_periodo"], "month": B["month"], "weekday": B["weekday"],
                  "atr_regime": B["atr_regime_bucket"].fillna("UNAVAILABLE")}
    for name, col in flags.items():
        base = B[ema_avail] if name.startswith("E") else B
        a_all, b_all = base[base[col]]["pnl_r"].to_numpy(), base[~base[col]]["pnl_r"].to_numpy()
        dlt, lo, hi = boot_diff(a_all, b_all)
        print(f"-- {name}: N_flag={len(a_all)} N_other={len(b_all)} dExpR={dlt:+.4f} "
              f"bootstrap95%=[{lo:+.4f},{hi:+.4f}] {'EXCLUDES 0' if (lo > 0 or hi < 0) else 'includes 0'}")
        robust_rows.append(dict(candidate=name, partition="ALL", bucket="ALL", N_flag=len(a_all), N_other=len(b_all),
                                ExpR_flag=a_all.mean() if len(a_all) else np.nan, ExpR_other=b_all.mean(),
                                dExpR=dlt, boot_lo=lo, boot_hi=hi))
        for pname, pser in partitions.items():
            if pname == "ALL":
                continue
            pos = neg = 0
            parts = []
            for bucket, g in base.groupby(pser.loc[base.index]):
                a, b = g[g[col]]["pnl_r"], g[~g[col]]["pnl_r"]
                if len(a) < 1 or len(b) < 1:
                    continue
                dd = a.mean() - b.mean()
                pos += dd > 0
                neg += dd < 0
                robust_rows.append(dict(candidate=name, partition=pname, bucket=bucket, N_flag=len(a), N_other=len(b),
                                        ExpR_flag=a.mean(), ExpR_other=b.mean(), dExpR=dd))
                parts.append(f"{bucket}:{dd:+.3f}(n={len(a)})")
            print(f"   {pname:11s} sign+={pos} sign-={neg} :: " + " ".join(parts))
    # HCH tolerance sensitivity (predeclared, symmetric, small: 1.00 / 1.25 / 1.50)
    print("-- HCH shoulder tolerance sensitivity (predeclared 1.00/1.25/1.50; 1.25 = Pine canonical)")
    for tol in (1.00, 1.25, 1.50):
        # BOT-052.2: the tolerance constant moved to strategy/hch.py (single
        # canonical implementation, shared with production) -- mutate it
        # there so HCHEngine.step() (which reads its OWN module's global)
        # actually picks up the sensitivity value, not confluence_reader's
        # now-inert re-exported copy.
        old = hch_mod.HCH_SHOULDER_TOL
        hch_mod.HCH_SHOULDER_TOL = tol
        hh = cr.emulate_hch(f["res_src"], f["sup_src"], f["sell_sig"], f["buy_sig"], cr.MINTICK_PRIMARY)
        hch_mod.HCH_SHOULDER_TOL = old
        flag = np.array([bool(hh["sell_pivot" if d < 0 else "buy_pivot"][b]) for b, d in zip(bars_a, dirs)])
        fl_b = flag[ub_mask.to_numpy()]
        a, b = B["pnl_r"].to_numpy()[fl_b], B["pnl_r"].to_numpy()[~fl_b]
        dlt, lo, hi = boot_diff(a, b)
        print(f"   tol={tol:.2f}: HCH A={flag.sum()} B={fl_b.sum()} ExpR_HCH={a.mean():+.4f} "
              f"ExpR_no={b.mean():+.4f} d={dlt:+.4f} [{lo:+.4f},{hi:+.4f}]")
        robust_rows.append(dict(candidate="HCH", partition="tolerance_sensitivity", bucket=f"{tol:.2f}",
                                N_flag=len(a), N_other=len(b), ExpR_flag=a.mean(), ExpR_other=b.mean(),
                                dExpR=dlt, boot_lo=lo, boot_hi=hi))
    pd.DataFrame(robust_rows).to_csv(OUT_ROBUST, index=False)

    # Daily boundary agreement
    print("-- Daily boundary agreement across variants (Universe A)")
    for v in ("UTC00", "NY18"):
        agree = (ev[f"D_state_{PRIMARY_D}"] == ev[f"D_state_{v}"]).mean()
        flips = ((ev[f"D_state_{PRIMARY_D}"] == "ALIGNED") & (ev[f"D_state_{v}"] == "AGAINST")).sum() + \
                ((ev[f"D_state_{PRIMARY_D}"] == "AGAINST") & (ev[f"D_state_{v}"] == "ALIGNED")).sum()
        print(f"   {PRIMARY_D} vs {v}: identical state {agree:.3%}, ALIGNED<->AGAINST flips={flips}")

    # ------------------------------------------------------------------ 6
    section("6. Incremental information / redundancy vs frozen SQ v1 (Universe B)")
    red = []
    Bc = B.copy()
    Bc["roc_t"] = pd.qcut(Bc["roc_atr_3"], 3, labels=["roc_T1", "roc_T2", "roc_T3"])
    Bc["origin_t"] = pd.qcut(Bc["origin_dist_atr"], 3, labels=["org_T1", "org_T2", "org_T3"])
    Bc["align6"] = Bc["alignment"].fillna("UNAVAILABLE")
    for name, col in (("D_TV22", "D_TV22"), ("HCH", "HCH"), ("DHCH", "DHCH"),
                      ("E1_px_ema50", "E1_px_ema50_ok"), ("E2_px_ema200", "E2_px_ema200_ok"),
                      ("E3_px_ema200m15", "E3_px_ema200m15_ok"), ("E4_ema50_vs_ema200", "E4_ema50_vs_ema200_ok"),
                      ("E5_px_all3", "E5_px_all3_ok")):
        base = Bc[Bc["E1_px_ema50"] != "UNAVAILABLE"] if name.startswith("E") else Bc
        flag = base[col]
        raw = base[flag]["pnl_r"].mean() - base[~flag]["pnl_r"].mean()
        roc_ok = base["roc_atr_3"].notna()
        org_ok = base["origin_dist_atr"].notna()
        r_roc = np.corrcoef(flag[roc_ok].astype(float), base.loc[roc_ok, "roc_atr_3"])[0, 1]
        r_org = np.corrcoef(flag[org_ok].astype(float), base.loc[org_ok, "origin_dist_atr"])[0, 1]
        v_al = cramers_v(flag, base["align6"])
        v_wd = cramers_v(flag, base["weekday"])
        adj = {s: stratified_delta(base, col, s) for s in ("roc_t", "align6", "origin_t", "weekday")}
        print(f"-- {name}: raw dExpR={raw:+.4f} | r_pb(roc_atr_3)={r_roc:+.3f} r_pb(origin_dist_atr)={r_org:+.3f} "
              f"V(alignment6)={v_al:.3f} V(weekday)={v_wd:.3f}")
        print("   stratified dExpR: " + " ".join(f"{s}={adj[s][0]:+.4f}(k={adj[s][1]})" for s in adj))
        red.append(dict(candidate=name, raw_dExpR=raw, r_pb_roc_atr_3=r_roc, r_pb_origin_dist_atr=r_org,
                        cramers_v_alignment6=v_al, cramers_v_weekday=v_wd,
                        **{f"strat_dExpR_{s}": adj[s][0] for s in adj}))
    print("-- Cross-tab D (TV22) x frozen 6-state D1 Alignment consensus (Universe B)")
    for (al, dd), g in Bc.groupby(["align6", "D_TV22"]):
        s = cohort_stats(g)
        print(f"   {al:18s} D={'ALIGNED' if dd else 'not   '}: N={s['N']:4d} WR={s['WR']:.3f} ExpR={s['ExpR']:+.4f} "
              f"(L n={s['N_LONG']} {s['ExpR_LONG']:+.3f} | S n={s['N_SHORT']} {s['ExpR_SHORT']:+.3f})")
        red.append(dict(candidate="D_TV22_x_alignment6", stratum=al, D_aligned=bool(dd), N=s["N"], WR=s["WR"],
                        ExpR=s["ExpR"], N_LONG=s["N_LONG"], ExpR_LONG=s["ExpR_LONG"],
                        N_SHORT=s["N_SHORT"], ExpR_SHORT=s["ExpR_SHORT"]))
    print("-- HCH vs origin_dist_atr (Structure) -- distribution")
    for val, g in Bc.groupby("HCH"):
        print(f"   HCH={val}: N={len(g)} origin_dist_atr median={g['origin_dist_atr'].median():.3f} "
              f"mean={g['origin_dist_atr'].mean():.3f}")
    pd.DataFrame(red).to_csv(OUT_REDUND, index=False)

    # ------------------------------------------------------------------ 7
    section("7. Counterfactual strict filter (RESEARCH ONLY, naive subset -- see limitation)")
    print("LIMITATION: with una_operacion_a_la_vez=True a skipped trade would have freed the slot for arrows that "
          "were blocked by concurrency; this naive subset does NOT re-simulate that path dependence.")
    cf = []
    base_s = cohort_stats(B)
    base_q = seq_metrics(B)
    cf.append(dict(filter="NONE (baseline)", retained=len(B), skipped=0, **{k: base_s[k] for k in ("WR", "PF", "ExpR")},
                   pnl_retained=base_s["pnl_total"], **base_q))
    print(f"baseline: {fmt(base_s)} maxDD$={base_q['maxDD_pnl_usd']:.2f} maxDD_R={base_q['maxDD_pnl_r']:.2f} "
          f"streak={base_q['longest_losing_streak']}")
    for name, col in [(f"D_{v}", f"D_{v}") for v in cr.D_VARIANTS] + [("HCH", "HCH"), ("D_or_HCH", None), ("DHCH", "DHCH")] + \
                     [(k, k + "_ok") for k in cr.EMA_STATES]:
        keep = (B["D_TV22"] | B["HCH"]) if col is None else B[col]
        kept, skip = B[keep], B[~keep]
        s = cohort_stats(kept) if len(kept) else dict(N=0, WR=np.nan, PF=np.nan, ExpR=np.nan, pnl_total=0.0)
        q = seq_metrics(kept) if len(kept) else dict(maxDD_pnl_usd=np.nan, maxDD_pnl_r=np.nan, longest_losing_streak=0)
        row = dict(filter=name, retained=len(kept), skipped=len(skip),
                   skipped_wins=int((skip["outcome"] == "win").sum()), skipped_losses=int((skip["outcome"] == "loss").sum()),
                   skipped_timeouts=int((skip["outcome"] == "timeout").sum()),
                   pnl_retained=kept["pnl_usd"].sum(), pnl_removed=skip["pnl_usd"].sum(),
                   r_removed=skip["pnl_r"].sum(),
                   WR=s["WR"], PF=s["PF"], ExpR=s["ExpR"],
                   dWR=s["WR"] - base_s["WR"], dPF=s["PF"] - base_s["PF"], dExpR=s["ExpR"] - base_s["ExpR"], **q)
        cf.append(row)
        print(f"{name:20s} kept={row['retained']:4d} skipped={row['skipped']:4d} (W={row['skipped_wins']} "
              f"L={row['skipped_losses']} T={row['skipped_timeouts']}) PnL kept={row['pnl_retained']:+.2f} "
              f"removed={row['pnl_removed']:+.2f} | WR {row['WR']:.3f} ({row['dWR']:+.3f}) PF {row['PF']:.3f} "
              f"({row['dPF']:+.3f}) ExpR {row['ExpR']:+.4f} ({row['dExpR']:+.4f}) maxDD$={q['maxDD_pnl_usd']:.2f} "
              f"maxDD_R={q['maxDD_pnl_r']:.2f} streak={q['longest_losing_streak']}")
    pd.DataFrame(cf).to_csv(OUT_CF, index=False)

    # ------------------------------------------------------------------ 8
    section("8. Causality audit sample (inputs of every confluence at boundary events)")
    audit = []
    tu = pd.to_datetime(t_utc, unit="s")
    cats = {
        "utc_day_transition": [b for b in bars_a if tu[b].hour == 0 and tu[b].minute < 15],
        "tv22_day_transition": [b for b in bars_a if tu[b].hour == 22 and tu[b].minute < 15],
        "m15_transition": [b for b in bars_a if tu[b].minute % 15 == 0],
        "htf_block_reset_or_level_update": [b for b in bars_a if f["new_bucket"][b] or hch["new_res"][b] or hch["new_sup"][b]],
        "hch_check": [b for b in bars_a if hch["sell_pivot"][b] or hch["buy_pivot"][b]],
    }
    ev_idx = {int(b): i for i, b in enumerate(bars_a)}
    for cat, blist in cats.items():
        for b in blist[:12]:
            r = ev.iloc[ev_idx[int(b)]]
            kmin = int(np.flatnonzero(f[f"day_key_{PRIMARY_D}"] == f[f"day_key_{PRIMARY_D}"][b])[0])
            audit.append(dict(category=cat, trade_id=r["trade_id"], bar=int(b), time_utc=str(tu[b]),
                              direction=r["direction"], close=c[b],
                              tv22_day_first_bar=kmin, tv22_day_first_time=str(tu[kmin]),
                              daily_open_TV22=r["daily_open_TV22"], D_state_TV22=r["D_state_TV22"],
                              daily_open_UTC00=r["daily_open_UTC00"], D_state_UTC00=r["D_state_UTC00"],
                              daily_open_NY18=r["daily_open_NY18"], D_state_NY18=r["D_state_NY18"],
                              htf_block_start=str(pd.Timestamp(int(f["bucket_start"][b]), unit="s")),
                              new_htf_block=bool(f["new_bucket"][b]), res_src=f["res_src"][b], sup_src=f["sup_src"][b],
                              pivot_1=r["hch_pivot_1"], pivot_2=r["hch_pivot_2"], pivot_3=r["hch_pivot_3"],
                              hch_active_level=r["hch_active_level"], hch_form_bar=r["hch_form_bar"],
                              HCH_state=r["HCH_state"],
                              m15_bucket_start=str(pd.Timestamp(int(t_utc[b] // 900 * 900), unit="s")),
                              ema200_m15_prev=r["ema200_m15_prev"], ema200_m15_smooth=r["ema200_m15_smooth"],
                              ema50=r["ema50_m5"], ema200=r["ema200_m5"],
                              max_input_bar=int(b)))
    ad = pd.DataFrame(audit)
    ad.to_csv(OUT_AUDIT, index=False)
    check("Audit: every input bar <= event bar (daily-open source bar and HCH formation bar)",
          bool((ad["tv22_day_first_bar"] <= ad["bar"]).all() and (ad["hch_form_bar"].fillna(-1) <= ad["bar"]).all()),
          f"rows={len(ad)} categories={ad['category'].value_counts().to_dict()}")

    # ------------------------------------------------------------------ 9
    section("9. Recent live trades sanity check (Phase 8)")
    recent_rows = []
    if not (RECENT_BARS.exists() and LIVE_SCORES.exists() and LIVE_OUTCOMES.exists()):
        print("NOT VERIFIABLE: recent bars snapshot or live stores missing")
    else:
        rb = pd.read_csv(RECENT_BARS)
        rt_utc, rt_srv, ro, rh, rl, rc, rsp = bar_arrays(rb)
        rf = cr.build_bar_features(rt_utc, rt_srv, ro, rh, rl, rc, rsp)
        pos_by_time = {int(t) // 300 * 300: i for i, t in enumerate(rt_srv)}
        scores = [json.loads(x) for x in LIVE_SCORES.read_text().splitlines() if x.strip()]
        outs = {}
        for x in LIVE_OUTCOMES.read_text().splitlines():
            if x.strip():
                rec = json.loads(x)
                outs[rec["ticket"]] = rec                       # last record per ticket wins
        seen = set()
        for s in scores:
            sqv = s.get("signal_quality")
            if not sqv or s["ticket"] in seen:
                continue
            seen.add(s["ticket"])
            oc = outs.get(s["ticket"], {})
            if oc.get("order_final_state") != "FILLED":
                continue
            t_obs = pd.Timestamp(sqv["observed_at_time_utc"])
            b = pos_by_time.get(int(t_obs.timestamp()) // 300 * 300)
            d = 1 if sqv["direction"] == "LONG" else -1
            base = dict(ticket=s["ticket"], signal_time_utc=str(t_obs), direction=sqv["direction"],
                        fill_time_utc=oc.get("fill_time_utc"), close_reason=oc.get("close_reason"),
                        pnl_net=oc.get("pnl_net"))
            if b is None:
                recent_rows.append(dict(**base, matched=False, note="signal bar not in snapshot"))
                continue
            is_arrow = bool((rf["sell_sig"] if d < 0 else rf["buy_sig"])[b])
            row = confluence_row(rf, rc, b, d)
            recent_rows.append(dict(**base, matched=is_arrow, bar_time_server=str(pd.Timestamp(int(rt_srv[b]), unit="s")),
                                    **{k: row[k] for k in ("close_at_signal", "daily_open_TV22", "D_state_TV22",
                                                           "D_state_UTC00", "D_state_NY18", "HCH_state", "combo_state",
                                                           "pine_label", "E1_px_ema50", "E2_px_ema200",
                                                           "E3_px_ema200m15")}))
        rr = pd.DataFrame(recent_rows)
        rr.to_csv(OUT_RECENT, index=False)
        print(f"filled live trades with SQ record: {len(rr)}; replica arrow at the logged bar: "
              f"{int(rr['matched'].sum()) if len(rr) else 0}")
        if len(rr):
            with pd.option_context("display.width", 250, "display.max_columns", 30):
                print(rr[["ticket", "signal_time_utc", "direction", "close_reason", "pnl_net", "matched",
                          "D_state_TV22", "D_state_UTC00", "HCH_state", "pine_label", "E3_px_ema200m15"]].to_string(index=False))
            last5 = rr.dropna(subset=["close_reason"]).tail(5)
            print("-- last 5 CLOSED filled entries:")
            print(last5[["ticket", "signal_time_utc", "direction", "close_reason", "pnl_net", "pine_label"]].to_string(index=False))

    pd.DataFrame(summary).to_csv(OUT_SUMMARY, index=False)
    section("RESULT")
    print(f"FAILURES={len(FAILURES)} {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
