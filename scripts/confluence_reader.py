"""BOT-052.1 -- causal reconstruction of the TradingView "Lector de confluencias".

RESEARCH ONLY. Nothing in `strategy/`, `execution/`, `api/` or `panel/`
imports this module. It changes no entry, gate, score or execution behaviour.

Source of truth: the Pine v6 script "Lector de confluencias" supplied for
BOT-052.1, committed next to this module as
`basecode_tradingview/Lector de confluencias.pine` (a verbatim copy). Line
numbers quoted below refer to that file.

The Pine reads four EXTERNAL series (`input.source`, L7-L11) from the
"original" indicator. In this repo the original is
`basecode_tradingview/5m EMA y Pivotes ZS -- trade boxes.txt`, which the bot
replicates bit for bit with `usarCausal=true` (strategy/engine.py). The
mapping used here:

    sellSource        <- plotshape "Venta"  = senalVenta ? resistencia : na
    buySource         <- plotshape "Compra" = senalCompra ? soporte : na
    resistenciaSource <- plot "Resistencia" = nuevoBucket ? na : resistencia
    soporteSource     <- plot "Soporte"     = nuevoBucket ? na : soporte

with resistencia/soporte = strategy.engine.bucket_levels() (runHigh/runLow of
the forming HTF block, Config A periodos=800) and the signals taken from
strategy.engine.run_backtest(signal_log=...) -- EVERY arrow, including the
ones the bot later discarded for invalid stop or concurrency, because the Pine
plotshape fires for every arrow.

Every function below is causal: the value at bar i depends only on bars <= i.
`scripts/test_confluence_reader.py` asserts that with prefix-truncation tests.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, para "import strategy"

# ---------------------------------------------------------------------------
# Daily Open (`D`) -- Pine L81-L87 + L135-L139
#   openD = request.security(tickerid, "D", open, gaps_off, lookahead_on)
#   compraMatchD = buySignal and close > openD ; ventaMatchD = sellSignal and close < openD
# `open` of the CURRENT daily bar with lookahead_on is the first price of the
# session day: known from the first intraday bar of the day onwards, so it is
# causal (lookahead_on on `open` does not leak; it would on high/low/close).
# The only unknown is WHERE TradingView's daily session starts for the user's
# chart symbol. Variants are declared here, before any outcome analysis.
# ---------------------------------------------------------------------------
D_VARIANTS = {
    # Primary: the TradingView session anchor already MEASURED for this project
    # (strategy/htf_session.py, XAUUSD feed TVC, 22:00 UTC) -- the same anchor
    # the bot uses for its HTF blocks. Fixed UTC, no DST (same as the bot).
    "TV22": "22:00 UTC fixed (measured TV session anchor, strategy/htf_session.py; BOT-047 B1)",
    # Sensitivity 1: MT5/Exness server day. Server time is UTC+0, so the MT5 D1
    # bar opens at 00:00 UTC (BOT-047 B0 boundary).
    "UTC00": "00:00 UTC (MT5/Exness D1 bar, server=UTC+0; BOT-047 B0)",
    # Sensitivity 2: 18:00 America/New_York, DST-aware (CME metals session).
    # Equals 22:00 UTC during US DST and 23:00 UTC otherwise -- tests whether
    # the unmeasured winter behaviour of the TV session matters.
    "NY18": "18:00 America/New_York, DST-aware (22:00 UTC in US summer, 23:00 UTC in winter)",
}

_NY = ZoneInfo("America/New_York")


def day_keys(time_utc: np.ndarray, variant: str) -> np.ndarray:
    """Integer session-day key per bar (bars sharing a key share a daily open)."""
    t = np.asarray(time_utc, dtype=np.int64)
    if variant == "TV22":
        return (t + 2 * 3600) // 86400          # day starts 22:00 UTC
    if variant == "UTC00":
        return t // 86400
    if variant == "NY18":
        out = np.empty(len(t), dtype=np.int64)
        cache: dict[int, int] = {}
        for i, s in enumerate(t):
            hour_key = int(s) // 3600
            if hour_key not in cache:
                ny = datetime.fromtimestamp(hour_key * 3600, tz=timezone.utc).astimezone(_NY)
                shifted = (ny.replace(tzinfo=None) + timedelta(hours=6)).date()  # 18:00 NY -> next date
                cache[hour_key] = shifted.toordinal()
            out[i] = cache[hour_key]
        return out
    raise ValueError(variant)


def daily_open_series(time_utc: np.ndarray, open_: np.ndarray, variant: str):
    """(daily_open, available) per bar. daily_open = open of the FIRST bar of
    the session day (what request.security('D', open) returns). The first day
    of the dataset is UNAVAILABLE when it starts mid-session (its real open is
    before the data), detected as: first bar is not the first bar of a day in
    the 24h+ sense -- conservatively, the whole first day key is unavailable."""
    keys = day_keys(time_utc, variant)
    n = len(keys)
    d_open = np.full(n, np.nan)
    avail = np.zeros(n, dtype=bool)
    cur_key = None
    cur_open = math.nan
    for i in range(n):
        if keys[i] != cur_key:
            cur_key = keys[i]
            cur_open = open_[i]
        d_open[i] = cur_open
        avail[i] = keys[i] != keys[0]
    return d_open, avail


def d_state(direction: int, close_i: float, d_open_i: float, available: bool) -> str:
    """ALIGNED (D check), AGAINST, EQUAL (close == openD: Pine gives no check,
    strict inequality L135-L136) or UNAVAILABLE."""
    if not available or math.isnan(d_open_i):
        return "UNAVAILABLE"
    if close_i == d_open_i:
        return "EQUAL"
    up = close_i > d_open_i
    return "ALIGNED" if (up if direction > 0 else not up) else "AGAINST"


# ---------------------------------------------------------------------------
# HCH -- Pine L150-L283.
#
# BOT-052.2: the per-bar state machine itself moved to `strategy/hch.py`
# (`HCHEngine`) so production (`execution/src/bot.py`) and research (here)
# share ONE implementation -- see that module's docstring for the full Pine
# line-number provenance. This function is now a thin batch wrapper: same
# public signature/return shape as before BOT-052.2, so
# `scripts/test_confluence_reader.py`'s 25 pre-existing tests (unchanged)
# still exercise it end to end and prove the refactor is behaviour-preserving.
# ---------------------------------------------------------------------------
from strategy.hch import HCH_SHOULDER_TOL, HCHEngine  # noqa: E402


def emulate_hch(res_src: np.ndarray, sup_src: np.ndarray, sell_sig: np.ndarray, buy_sig: np.ndarray,
                mintick: float):
    """Bar-by-bar emulation of the Pine HCH detector (batch wrapper around
    `strategy.hch.HCHEngine`, see that module for the canonical logic).

    res_src/sup_src: the plotted Resistencia/Soporte series (NaN = na).
    sell_sig/buy_sig: bool arrays, the rising edge of the signal plots.
    Returns a dict of per-bar arrays; `sell_pivot[i]`/`buy_pivot[i]` are the
    hchVentaPivote/hchCompraPivote values (the HCH check on a signal bar).
    """
    n = len(res_src)
    out = {k: np.full(n, np.nan) for k in (
        "res1", "res2", "res3", "sop1", "sop2", "sop3", "hch_sell_level", "hch_buy_level",
        "hch_sell_form_bar", "hch_buy_form_bar")}
    out["sell_pivot"] = np.zeros(n, dtype=bool)
    out["buy_pivot"] = np.zeros(n, dtype=bool)
    out["new_res"] = np.zeros(n, dtype=bool)
    out["new_sup"] = np.zeros(n, dtype=bool)
    out["hch_sell_formed"] = np.zeros(n, dtype=bool)
    out["hch_buy_formed"] = np.zeros(n, dtype=bool)

    engine = HCHEngine()
    for i in range(n):
        r = engine.step(i, res_src[i], sup_src[i], bool(sell_sig[i]), bool(buy_sig[i]), mintick)
        out["sell_pivot"][i] = r.sell_pivot
        out["buy_pivot"][i] = r.buy_pivot
        out["hch_sell_formed"][i] = r.hch_sell_formed
        out["hch_buy_formed"][i] = r.hch_buy_formed
        out["res1"][i], out["res2"][i], out["res3"][i] = r.res1, r.res2, r.res3
        out["sop1"][i], out["sop2"][i], out["sop3"][i] = r.sop1, r.sop2, r.sop3
        out["hch_sell_level"][i] = r.hch_sell_level
        out["hch_buy_level"][i] = r.hch_buy_level
        out["hch_sell_form_bar"][i] = r.hch_sell_form_bar
        out["hch_buy_form_bar"][i] = r.hch_buy_form_bar
        out["new_res"][i] = r.new_res
        out["new_sup"][i] = r.new_sup
    return out


def plotted_levels(resistencia: np.ndarray, soporte: np.ndarray, new_bucket: np.ndarray):
    """Original indicator L359-L360: resPlot = nuevoBucket ? na : resistencia."""
    res = np.where(new_bucket, np.nan, resistencia)
    sup = np.where(new_bucket, np.nan, soporte)
    return res, sup


# ---------------------------------------------------------------------------
# EMAs -- Pine L36-L52 (visual only: never read by the D/HCH checks)
# ---------------------------------------------------------------------------
M15_S = 15 * 60
ALPHA_EMA200 = 2.0 / 201.0     # Pine L50


def pine_ema(x: np.ndarray, period: int) -> np.ndarray:
    """ta.ema: seeded with the first value (same as strategy.engine.ema)."""
    out = np.empty(len(x))
    a = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * a + out[i - 1] * (1 - a)
    return out


def ema200_m15_smooth(time_utc: np.ndarray, close: np.ndarray):
    """Pine L42-L52:
        prev = request.security("15", ta.ema(close,200)[1], lookahead_on)
        smooth = prev + alpha*(close_M5 - prev)
    lookahead_on + [1] = the EMA of the LAST COMPLETED M15 bar (the standard
    non-repainting idiom), then nudged by the current M5 close. Returns
    (m15_prev_ema, smooth)."""
    t = np.asarray(time_utc, dtype=np.int64)
    k = t // M15_S
    # M15 close = close of the last M5 bar of each M15 period
    last_idx = np.flatnonzero(np.r_[k[1:] != k[:-1], True])
    m15_keys = k[last_idx]
    m15_ema = pine_ema(close[last_idx], 200)
    pos = np.searchsorted(m15_keys, k, side="left")   # index of the M15 bar containing bar i
    prev = np.where(pos >= 1, m15_ema[np.clip(pos - 1, 0, None)], np.nan)
    smooth = prev + ALPHA_EMA200 * (close - prev)
    return prev, smooth


# Warm-up (declared before outcomes): 3x the EMA length in its own timeframe.
EMA_WARMUP_M5 = {"ema50": 150, "ema200": 600, "ema200_m15": 3 * 200 * 3}

EMA_STATES = {
    "E1_px_ema50": "close on the trade side of EMA50 M5 (LONG: close>ema50; SHORT: close<ema50)",
    "E2_px_ema200": "close on the trade side of EMA200 M5",
    "E3_px_ema200m15": "close on the trade side of the Pine-smoothed EMA200 M15",
    "E4_ema50_vs_ema200": "EMA50 M5 on the trade side of EMA200 M5 (LONG: ema50>ema200)",
    "E5_px_all3": "E1 and E2 and E3 all true (price on the trade side of every plotted EMA)",
}


def ema_states(direction: int, close_i: float, e50: float, e200: float, e200m15: float) -> dict:
    sgn = 1 if direction > 0 else -1
    e1 = sgn * (close_i - e50) > 0
    e2 = sgn * (close_i - e200) > 0
    e3 = sgn * (close_i - e200m15) > 0
    e4 = sgn * (e50 - e200) > 0
    return {"E1_px_ema50": e1, "E2_px_ema200": e2, "E3_px_ema200m15": e3,
            "E4_ema50_vs_ema200": e4, "E5_px_all3": e1 and e2 and e3}


def signals_from_log(signal_log: list[dict], n: int):
    sell = np.zeros(n, dtype=bool)
    buy = np.zeros(n, dtype=bool)
    for s in signal_log:
        if s["dir"] < 0:
            sell[s["bar"]] = True
        else:
            buy[s["bar"]] = True
    return sell, buy


def rising_edge(sig: np.ndarray) -> np.ndarray:
    """Pine L123-L130: signal = active and not active[1]."""
    prev = np.r_[False, sig[:-1]]
    return sig & ~prev


# ---------------------------------------------------------------------------
# Full per-bar pipeline (shared by the discovery script, the recent-trade
# sanity check and the causality tests -- one code path for all three).
# ---------------------------------------------------------------------------
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)
MINTICK_PRIMARY = 0.001   # XAUUSDc price resolution (3 decimals, verified on the dataset)


def _signal_only_costs():
    """run_backtest() needs a BrokerCosts, but the arrows (signal_log) do not
    depend on costs: they are logged before any fill/cost logic. Neutral
    values; PnL from this run is never used."""
    from strategy.costs import BrokerCosts
    return BrokerCosts(point=0.001, contract_size=1.0, tick_value=0.1, tick_size=0.001,
                       swap_long_points=0.0, swap_short_points=0.0, spread_fallback_points=0.0)


def build_bar_features(time_utc, time_server, open_, high, low, close, spread_pts,
                       mintick: float = MINTICK_PRIMARY) -> dict:
    from strategy.engine import StrategyParams, bucket_levels, ema, run_backtest
    from strategy.htf_session import bucket_start_utc_seconds

    params = StrategyParams(**CONFIG_A, **SHARED)
    n = len(close)
    ema_line = ema(close, params.ema_periods)
    resistencia, soporte = bucket_levels(time_utc, high, low, params.periodos_htf_min)
    bstart = bucket_start_utc_seconds(np.asarray(time_utc, dtype=np.int64), params.periodos_htf_min)
    new_bucket = np.r_[False, bstart[1:] != bstart[:-1]]
    signal_log: list[dict] = []
    run_backtest(time_utc, time_server, open_, high, low, close, spread_pts, params, _signal_only_costs(),
                 ema_line=ema_line, resistencia=resistencia, soporte=soporte, signal_log=signal_log)
    sell_raw, buy_raw = signals_from_log(signal_log, n)
    sell_sig, buy_sig = rising_edge(sell_raw), rising_edge(buy_raw)
    res_src, sup_src = plotted_levels(resistencia, soporte, new_bucket)
    hch = emulate_hch(res_src, sup_src, sell_sig, buy_sig, mintick)
    feats = dict(signal_log=signal_log, sell_raw=sell_raw, buy_raw=buy_raw, sell_sig=sell_sig, buy_sig=buy_sig,
                 resistencia=resistencia, soporte=soporte, new_bucket=new_bucket, bucket_start=bstart,
                 res_src=res_src, sup_src=sup_src, hch=hch,
                 ema50=pine_ema(close, 50), ema200=pine_ema(close, 200))
    feats["ema200_m15_prev"], feats["ema200_m15_smooth"] = ema200_m15_smooth(time_utc, close)
    for v in D_VARIANTS:
        feats[f"daily_open_{v}"], feats[f"daily_open_avail_{v}"] = daily_open_series(time_utc, open_, v)
        feats[f"day_key_{v}"] = day_keys(time_utc, v)
    return feats
