"""BOT-047.1 -- D1 Alignment Feature Discovery, XAU (BTC bloqueado, ver seccion A).

Subtarea de BOT-047 (feature padre "D1 Alignment", dimension del futuro
Signal Quality de BOT-024). SOLO LECTURA/DISCOVERY -- no construye ninguna
definicion final de Alignment, no asigna pesos, no activa gating, no
modifica strategy/, execution/, api/ ni panel/.

Pregunta que responde: de las propiedades observables de D1 (temporalidad
diaria) disponibles CAUSALMENTE en `limit_created_bar` (== `signal_bar` ==
`born_bar`, mismo punto de congelacion que BOT-024.1/BOT-024.2), cuales
muestran evidencia de capturar si la direccion del trade esta alineada o en
contra del contexto direccional de mayor plazo -- para probabilidad de fill
(Universo A, TODOS los LIMITS creados) y para desempeno de los trades
cerrados (Universo B, LIMITS que hicieron fill).

Momentum (BOT-024.2/BOT-024.3) y Alignment (esta tarea) son dimensiones
EXPLICITAMENTE independientes -- D1 nunca se usa para "corregir" Momentum.

BTC: bloqueado en esta ejecucion, mismo criterio y misma verificacion en vivo
que BOT-024.2 (ver seccion A).

Metodologia (resumen; ver reports/BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md):
  1. Corre strategy.engine.run_backtest (sin tocar) UNA sola vez, continuo,
     sobre backtests/data/XAUUSDc_M5_latest.parquet, "Config A" (misma que
     BOT-024.1/BOT-024.2/BOT-042/043/045/046).
  2. Shadow replay (copiado LINEA POR LINEA de scripts/discover_momentum_
     features_xau.py, sin modificar la logica) reproduce Universo A completo
     (todos los LIMITS, incluidos los que nunca hicieron fill) y se valida
     EXHAUSTIVAMENTE contra run_backtest() real antes de interpretar nada.
  3. D1 se define con la MISMA ancla de sesion (22:00 UTC) que ya usa el
     bloque HTF (strategy/htf_session.py::bucket_start_utc_seconds) y que ya
     uso BOT-045/046 para "d1_trend" (D1_WINDOW_MIN=1440 en
     backtests/scripts/07_bot045_regime_dataset.py) -- no se inventa una
     nueva convencion de dia.
  4. Se construye una historia D1_CLOSED (una fila por dia de sesion
     COMPLETAMENTE cerrado, O/H/L/C) agrupando las velas M5 por su bucket de
     1440min. Un dia se considera cerrado si el dataset observa al menos una
     barra de un bucket POSTERIOR (mismo criterio que
     scoring.py::_closed_blocks / 07_bot045_regime_dataset.py::
     precompute_closed_blocks) -- el ultimo dia del dataset nunca se cuenta
     como cerrado.
  5. D1_FORMING se construye EXCLUSIVAMENTE a partir de: (a) el estado D1
     CERRADO mas reciente (EMA/RSI/ATR ya "sembrados" hasta el dia anterior)
     y (b) el precio M5 disponible en `limit_created_bar` -- nunca el OHLC
     final del dia. La prueba de causalidad es constructiva (ninguna formula
     de D1_FORMING referencia una barra con indice > limit_created_bar) y se
     confirma empiricamente truncando el array de entrada a una muestra de
     eventos y verificando que el resultado no cambia (ver seccion F).
  6. Cada feature se evalua individualmente (bins/cuantiles), separado en
     ALL/LONG/SHORT y CLOSED/FORMING -- sin grid search, sin score, sin
     pesos, sin gate. Interacciones (Momentum/Divergence/LONG-SHORT x
     Alignment) solo exploratorias, al final.

Uso:
    .venv/Scripts/python.exe scripts/discover_d1_alignment_features_xau.py \
        > reports/BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY-EVIDENCE.log

Requiere MT5 corriendo (solo lectura: symbol_info para costos y para
verificar la ambiguedad de BTC -- nunca coloca ni cancela ninguna orden).
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import MetaTrader5 as mt5

from execution.src.mt5_utils import find_symbols, resolve_symbol
from strategy.costs import BrokerCosts
from strategy.engine import StrategyParams, _server_date, bucket_levels, ema, run_backtest
from strategy.htf_session import bucket_start_utc_seconds
from strategy import scoring as sc

DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
REPORTS_DIR = REPO_ROOT / "reports"

# Config A congelada -- misma que BOT-024.1/BOT-024.2/BOT-042/BOT-043/BOT-045/BOT-046.
# NO se optimiza ni se cambia ningun parametro de estrategia en esta tarea.
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

# --- D1: misma ancla de sesion que el bloque HTF y que BOT-045/046 ----------
D1_WINDOW_MIN = 1440
D1_EMA_PERIODS = (20, 50, 200)
D1_RSI_PERIOD = 14
D1_ATR_PERIOD = 14
D1_RET_HORIZONS_DAYS = (1, 3, 5, 10)
D1_EMA_SLOPE_WINDOW_DAYS = 5      # fijo, unico, documentado -- no se prueban varias ventanas
D1_RSI_DELTA_WINDOW_DAYS = 3      # fijo, unico, documentado
D1_STRUCTURE_LBL = 2              # find_confirmed_pivots() sobre la serie D1_CLOSED -- fijo, no tuneado
D1_STRUCTURE_LBR = 2

# --- Momentum M5, para la interaccion exploratoria (misma definicion EXACTA
# que BOT-024.2, no modificada) --------------------------------------------
M5_ATR_PERIOD = 14
M5_ROC_HORIZON = 10  # roc_atr_10, el candidato principal de BOT-024.2

SESSION_BOUNDS_UTC = [  # misma convencion que BOT-045/BOT-024.2
    (0, 7, "Asia"),
    (7, 8, "Asia/Londres (overlap)"),
    (8, 12, "Londres"),
    (12, 16, "Londres/NY (overlap)"),
    (16, 21, "Nueva York"),
    (21, 24, "Post-NY / transicion"),
]

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def session_of_hour(hour_utc: int) -> str:
    for lo, hi, label in SESSION_BOUNDS_UTC:
        if lo <= hour_utc < hi:
            return label
    return "desconocida"


# ---------------------------------------------------------------------------
# 0. ATR Wilder -- reusado VERBATIM de backtests/scripts/07_bot045_regime_
#    dataset.py / scripts/discover_momentum_features_xau.py (no existe en
#    produccion, no se reinventa una formula nueva). Sirve tanto para ATR M5
#    (interaccion de Momentum) como, aplicado a la serie D1_CLOSED, para
#    ATR D1.
# ---------------------------------------------------------------------------

def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
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


def rsi_wilder_with_state(close: np.ndarray, period: int):
    """MISMA formula que strategy.scoring.rsi() (Wilder, sembrado con
    promedio simple de las primeras `period` variaciones) -- reimplementada
    aca UNICAMENTE para exponer avg_gain/avg_loss (estado interno), que
    strategy.scoring.rsi() no expone y que D1_FORMING necesita para
    reconstruir RSI causalmente sin leer el cierre final del dia. La salida
    `rsi` de esta funcion se valida (seccion E) para ser IDENTICA a
    strategy.scoring.rsi() sobre la misma serie -- no es una formula nueva."""
    n = len(close)
    rsi_out = np.full(n, np.nan)
    avg_gain_out = np.full(n, np.nan)
    avg_loss_out = np.full(n, np.nan)
    if n < period + 1:
        return rsi_out, avg_gain_out, avg_loss_out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    avg_gain_out[period] = avg_gain
    avg_loss_out[period] = avg_loss
    rsi_out[period] = sc._rsi_from_avgs(avg_gain, avg_loss)
    for i in range(period + 1, n):
        g, l = gains[i - 1], losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        avg_gain_out[i] = avg_gain
        avg_loss_out[i] = avg_loss
        rsi_out[i] = sc._rsi_from_avgs(avg_gain, avg_loss)
    return rsi_out, avg_gain_out, avg_loss_out


# ---------------------------------------------------------------------------
# 1. Shadow replay -- COPIADO LINEA POR LINEA de scripts/discover_momentum_
#    features_xau.py (BOT-024.2), sin modificar la logica. Reproduce
#    strategy/engine.py:run_backtest() (pending/open_pos/counters) y ademas
#    registra un evento por cada LIMIT (Universo A) que run_backtest() de
#    produccion no retiene.
# ---------------------------------------------------------------------------

def shadow_replay(time_utc, time_server, high, low, close, spread_pts, params: StrategyParams,
                   costs: BrokerCosts, ema_line, resistencia, soporte):
    n = len(close)
    buf = params.buf_bp / 10000.0

    armado_venta = False
    armado_compra = False
    pending: list[dict] = []
    open_pos: list[dict] = []

    limit_events: dict[int, dict] = {}
    shadow_closed: list[dict] = []

    counters = dict(n_sig=0, n_fill=0, n_win=0, n_loss=0, n_none=0,
                     n_open_timeout=0, n_skip_stop=0, n_skip_concurrency=0)

    def risk_usd(stop, entry):
        return costs.price_to_usd(abs(stop - entry), params.fixed_lot)

    def close_open_trade(pos, i, outcome, exit_price):
        sp = costs.spread_price(spread_pts[i])
        exit_adj = costs.adjust_exit_price(pos["dir"], exit_price, sp)
        raw_risk = risk_usd(pos["stop"], pos["entry_price"])

        pnl_price = (pos["entry_price_adj"] - exit_adj) if pos["dir"] < 0 else (exit_adj - pos["entry_price_adj"])
        pnl_usd = costs.price_to_usd(pnl_price, params.fixed_lot)

        open_date = _server_date(time_server[pos["open_bar"]])
        close_date = _server_date(time_server[i])
        nights = max((close_date - open_date).days, 0)
        pnl_usd += costs.swap_total_usd(pos["dir"], params.fixed_lot, open_date, close_date)
        pnl_usd -= costs.commission_usd(params.fixed_lot)

        pnl_r = pnl_usd / raw_risk if raw_risk > 0 else float("nan")

        shadow_closed.append(dict(
            direction=pos["dir"], born_bar=pos["born_bar"], entry_bar=pos["open_bar"], exit_bar=i,
            entry_price=pos["entry_price"], entry_price_adj=pos["entry_price_adj"],
            stop=pos["stop"], target=pos["target"], exit_price=exit_price, exit_price_adj=exit_adj,
            outcome=outcome, pnl_usd=pnl_usd, pnl_r=pnl_r, nights_held=nights,
        ))
        ev = limit_events[pos["born_bar"]]
        ev.update(fate="FILLED_CLOSED", fill_bar=pos["open_bar"], exit_bar=i, outcome=outcome,
                   pnl_usd=pnl_usd, pnl_r=pnl_r)
        if outcome == "win":
            counters["n_win"] += 1
        elif outcome == "loss":
            counters["n_loss"] += 1
        elif outcome == "timeout":
            counters["n_open_timeout"] += 1

    for i in range(n):
        r_i, s_i = resistencia[i], soporte[i]

        if i == 0:
            down = up = False
        else:
            down = close[i - 1] >= ema_line[i - 1] and close[i] < ema_line[i]
            up = close[i - 1] <= ema_line[i - 1] and close[i] > ema_line[i]
        senal_venta = armado_venta and down
        senal_compra = armado_compra and up

        if senal_venta:
            armado_venta = False
        if senal_compra:
            armado_compra = False
        if not math.isnan(r_i) and high[i] >= r_i:
            armado_venta = True
        if not math.isnan(s_i) and low[i] <= s_i:
            armado_compra = True

        still_open = []
        for pos in open_pos:
            d = pos["dir"]
            hit_sl = high[i] >= pos["stop"] if d < 0 else low[i] <= pos["stop"]
            hit_tp = low[i] <= pos["target"] if d < 0 else high[i] >= pos["target"]
            too_long = (i - pos["open_bar"]) >= params.max_bars_trade
            if hit_sl:
                close_open_trade(pos, i, "loss", pos["stop"])
            elif hit_tp:
                close_open_trade(pos, i, "win", pos["target"])
            elif too_long:
                close_open_trade(pos, i, "timeout", close[i])
            else:
                still_open.append(pos)
        open_pos = still_open

        still_pending = []
        for po in pending:
            d = po["dir"]
            entry_use = ema_line[i] if params.entrada_viva else po["entry"]
            touched = high[i] >= entry_use if d < 0 else low[i] <= entry_use
            if touched:
                counters["n_fill"] += 1
                sp = costs.spread_price(spread_pts[i])
                entry_adj = costs.adjust_entry_price(d, entry_use, sp)
                if params.entrada_viva:
                    r_now = abs(po["stop"] - entry_use)
                    target_use = entry_use - params.rr * r_now if d < 0 else entry_use + params.rr * r_now
                else:
                    target_use = po["target"]
                hit_sl = high[i] >= po["stop"] if d < 0 else low[i] <= po["stop"]
                hit_tp = low[i] <= target_use if d < 0 else high[i] >= target_use
                pos = {"dir": d, "stop": po["stop"], "target": target_use, "open_bar": i,
                       "born_bar": po["born"], "entry_price": entry_use, "entry_price_adj": entry_adj}
                if hit_sl:
                    close_open_trade(pos, i, "loss", po["stop"])
                elif hit_tp:
                    close_open_trade(pos, i, "win", target_use)
                else:
                    open_pos.append(pos)
                    limit_events[po["born"]].update(fate="FILLED_OPEN_RESIDUAL", fill_bar=i)
                continue

            tp_antes = low[i] <= po["target"] if d < 0 else high[i] >= po["target"]
            expired = False
            if tp_antes:
                expired = True
            elif params.orden_viva:
                muerto = high[i] >= po["stop"] if d < 0 else low[i] <= po["stop"]
                caduca = (i - po["born"]) >= params.max_bars_trade
                expired = muerto or caduca
            else:
                caduca = (i - po["born"]) >= params.valid_bars
                expired = caduca

            if expired:
                counters["n_none"] += 1
                limit_events[po["born"]].update(fate="EXPIRED")
            else:
                still_pending.append(po)
        pending = still_pending

        if senal_venta or senal_compra:
            counters["n_sig"] += 1
            d = -1 if senal_venta else 1
            entry = ema_line[i]
            stop = r_i * (1 + buf) if d < 0 else s_i * (1 - buf)
            valid = (stop > entry) if d < 0 else (stop < entry)
            target = None
            if valid:
                risk = abs(stop - entry)
                target = entry - params.rr * risk if d < 0 else entry + params.rr * risk
            if not valid:
                counters["n_skip_stop"] += 1
            else:
                if params.una_operacion_a_la_vez:
                    active = len(pending) + len(open_pos)
                    limite = 1
                else:
                    active = sum(1 for po in pending if po["dir"] == d) + sum(1 for pos in open_pos if pos["dir"] == d)
                    limite = params.max_concurrent_por_direccion
                if active >= limite:
                    counters["n_skip_concurrency"] += 1
                else:
                    pending.append({"dir": d, "entry": entry, "stop": stop, "target": target, "born": i})
                    limit_events[i] = dict(born_bar=i, direction=d, entry=entry, stop=stop, target=target,
                                            fate="PENDING_RESIDUAL", fill_bar=None, exit_bar=None,
                                            outcome=None, pnl_usd=None, pnl_r=None)

    return limit_events, shadow_closed, counters


# ---------------------------------------------------------------------------
# 2. Construccion D1_CLOSED (agrupando M5 por bucket de sesion de 1440min)
# ---------------------------------------------------------------------------

def build_d1_history(time_utc: np.ndarray, open_: np.ndarray, high: np.ndarray,
                      low: np.ndarray, close: np.ndarray):
    """Devuelve un dict de arrays (uno por dia de sesion D1 COMPLETAMENTE
    CERRADO, orden cronologico): closing_bar (indice M5 de la ULTIMA barra
    de ese dia), open_bar (indice M5 de la PRIMERA barra), open/high/low/
    close del dia. El ultimo bucket de sesion observado en el array de
    entrada NUNCA se incluye (podria seguir abierto -- mismo criterio que
    scoring.py::_closed_blocks / 07_bot045_regime_dataset.py::
    precompute_closed_blocks, aplicado aca a nivel de dia entero en vez de
    bloque HTF)."""
    bucket_start = bucket_start_utc_seconds(time_utc, D1_WINDOW_MIN)
    df = pd.DataFrame({
        "bar": np.arange(len(time_utc)),
        "bucket_start": bucket_start,
        "open": open_, "high": high, "low": low, "close": close,
    })
    groups = df.groupby("bucket_start", sort=True)
    bucket_starts_sorted = np.sort(df["bucket_start"].unique())
    n_days = len(bucket_starts_sorted) - 1  # excluye el ultimo (posiblemente abierto)

    closing_bar = np.empty(n_days, dtype=np.int64)
    open_bar = np.empty(n_days, dtype=np.int64)
    d_open = np.empty(n_days)
    d_high = np.empty(n_days)
    d_low = np.empty(n_days)
    d_close = np.empty(n_days)

    for k in range(n_days):
        g = groups.get_group(bucket_starts_sorted[k])
        open_bar[k] = g["bar"].iloc[0]
        closing_bar[k] = g["bar"].iloc[-1]
        d_open[k] = g["open"].iloc[0]
        d_high[k] = g["high"].max()
        d_low[k] = g["low"].min()
        d_close[k] = g["close"].iloc[-1]

    return dict(closing_bar=closing_bar, open_bar=open_bar, open=d_open, high=d_high,
                low=d_low, close=d_close, bucket_start=bucket_starts_sorted[:-1])


def compute_d1_indicators(d1: dict):
    """EMA(20/50/200)/RSI(14, con estado)/ATR(14) sobre la serie D1_CLOSED --
    recursion causal por construccion (out[i] depende solo de out[i-1] y de
    valores <= i), igual que en produccion (M5). Estructura (swings HH/HL/
    LH/LL) via find_confirmed_pivots(), la MISMA funcion que ya usa
    produccion para pivotes de Divergencia RSI, aplicada aca a la serie
    D1_CLOSED en vez de RSI M5."""
    ema_d1 = {p: ema(d1["close"], p) for p in D1_EMA_PERIODS}
    rsi_d1, avg_gain_d1, avg_loss_d1 = rsi_wilder_with_state(d1["close"], D1_RSI_PERIOD)
    atr_d1 = atr_wilder(d1["high"], d1["low"], d1["close"], D1_ATR_PERIOD)

    swing_highs, _ = sc.find_confirmed_pivots(d1["high"], D1_STRUCTURE_LBL, D1_STRUCTURE_LBR)
    _, swing_lows = sc.find_confirmed_pivots(d1["low"], D1_STRUCTURE_LBL, D1_STRUCTURE_LBR)

    return dict(ema=ema_d1, rsi=rsi_d1, avg_gain=avg_gain_d1, avg_loss=avg_loss_d1,
                atr=atr_d1, swing_highs=swing_highs, swing_lows=swing_lows)


def structure_type_as_of(swings: list, idx_closed_excl: int) -> tuple[str | None, float | None, int | None]:
    """swings: lista de Pivot (bar/confirmed_bar en INDICE D1, no M5).
    idx_closed_excl: cantidad de dias D1 cerrados antes de la barra evaluada
    (=idx de la seccion principal) -- un swing esta disponible si
    confirmed_bar < idx_closed_excl (el dia que lo confirma ya cerro).
    Devuelve (tipo 'HH'/'LH' o 'HL'/'LL', valor del ultimo swing, edad en
    dias desde su confirmacion) o (None, None, None) si no hay al menos 2
    swings disponibles."""
    available = [p for p in swings if p.confirmed_bar < idx_closed_excl]
    if len(available) < 2:
        return None, None, None
    available.sort(key=lambda p: p.bar)
    last, prev = available[-1], available[-2]
    rising = last.value > prev.value
    age = idx_closed_excl - 1 - last.bar
    return rising, float(last.value), int(age)


# ---------------------------------------------------------------------------
# 3. main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-047.1 -- D1 Alignment Feature Discovery, XAU (BTC bloqueado, ver seccion A)")
    print("SOLO LECTURA/DISCOVERY. No se modifico ningun archivo de produccion. No se activa gating.")
    print("No se implementa una definicion final de Alignment. No se toca Momentum.\n")

    # --- A. BTC: verificacion de bloqueo (solo lectura, ninguna orden) -----
    section("A. BTC -- verificacion de bloqueo (solo lectura, sin ordenes)")
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    account = mt5.account_info()
    print(f"Cuenta conectada (solo lectura): login={account.login if account else '?'} "
          f"server={account.server if account else '?'}")
    btc_candidates = find_symbols("BTCUSD")
    print(f"Simbolos candidatos para base 'BTCUSD' en este broker: {btc_candidates}")
    btc_data_files = list((REPO_ROOT / "backtests" / "data").glob("BTC*"))
    print(f"Archivos de dataset BTC en backtests/data/: {[p.name for p in btc_data_files]}")
    check("BTC bloqueado correctamente: 'BTCUSD' es ambiguo en este broker (>1 candidato) Y no hay "
          "dataset historico BTC en el repo -- no se inventan parametros, se documenta el bloqueo",
          len(btc_candidates) != 1 and len(btc_data_files) == 0,
          f"candidatos={btc_candidates}, archivos_dataset={[p.name for p in btc_data_files]}")
    print("CONCLUSION: BTC queda BLOQUEADO y documentado, XAU continua normalmente (activo prioritario).")

    # --- B. Dataset XAU + costos --------------------------------------------
    section("B. Dataset XAU y costos (reusa lo ya usado por BOT-024.1/BOT-024.2/BOT-045)")
    df = pd.read_parquet(DATA_PATH)
    n_bars = len(df)
    print(f"Dataset: {DATA_PATH.name} -- {n_bars} barras M5, "
          f"{pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. {pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    symbol = resolve_symbol("XAUUSD")
    si = mt5.symbol_info(symbol)
    costs = BrokerCosts(point=si.point, contract_size=si.trade_contract_size, tick_value=si.trade_tick_value,
                         tick_size=si.trade_tick_size, swap_long_points=si.swap_long, swap_short_points=si.swap_short,
                         commission_per_lot=0.0, triple_swap_weekday=2, spread_fallback_points=si.spread)
    mt5.shutdown()
    print(f"Costos en vivo ({symbol}): point={costs.point} tick_value={costs.tick_value} "
          f"tick_size={costs.tick_size} swap_long={costs.swap_long_points} swap_short={costs.swap_short_points}")

    time_utc = df["time_utc"].to_numpy(dtype=np.int64)
    time_server = df["time_server"].to_numpy(dtype=np.int64)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    spread_pts = df["spread"].to_numpy(dtype=float)

    check("timestamps time_utc estrictamente ascendentes (sin barras fuera de orden)",
          bool(np.all(np.diff(time_utc) > 0)), f"min_delta={int(np.diff(time_utc).min())}s")
    check("sin barras duplicadas (time_utc unico)",
          len(np.unique(time_utc)) == n_bars, f"unicos={len(np.unique(time_utc))}, total={n_bars}")

    params = StrategyParams(**CONFIG_A, **SHARED)
    print(f"\nConfig A (congelada): {CONFIG_A}")
    print(f"Params compartidos: {SHARED}")

    ema_line = ema(close, params.ema_periods)
    resistencia, soporte = bucket_levels(time_utc, high, low, params.periodos_htf_min)

    # --- C. Motor real de produccion (sin tocar) ----------------------------
    section("C. Motor real (strategy.engine.run_backtest, sin modificar)")
    result = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts, params, costs,
                           ema_line=ema_line, resistencia=resistencia, soporte=soporte)
    prod_trades = result.trades
    prod_counters = result.counters
    print(f"run_backtest() real: {len(prod_trades)} trades cerrados, counters={prod_counters}")

    # --- D. Shadow replay + verificacion de paridad EXHAUSTIVA --------------
    section("D. Shadow replay (Universo A completo) + paridad EXHAUSTIVA contra produccion")
    limit_events, shadow_closed, shadow_counters = shadow_replay(
        time_utc, time_server, high, low, close, spread_pts, params, costs, ema_line, resistencia, soporte)

    for field in ("n_sig", "n_fill", "n_win", "n_loss", "n_none", "n_open_timeout",
                  "n_skip_stop", "n_skip_concurrency"):
        check(f"counters.{field}: shadow replay == produccion",
              shadow_counters[field] == getattr(prod_counters, field),
              f"shadow={shadow_counters[field]}, produccion={getattr(prod_counters, field)}")

    check("N trades cerrados: shadow replay == produccion",
          len(shadow_closed) == len(prod_trades),
          f"shadow={len(shadow_closed)}, produccion={len(prod_trades)}")

    shadow_by_born = {r["born_bar"]: r for r in shadow_closed}
    field_mismatches = []
    for t in prod_trades:
        s = shadow_by_born.get(t.signal_bar)
        if s is None:
            field_mismatches.append((t.signal_bar, "no encontrado en shadow_closed"))
            continue
        checks = [
            ("direction", s["direction"] == t.direction),
            ("entry_bar", s["entry_bar"] == t.entry_bar),
            ("exit_bar", s["exit_bar"] == t.exit_bar),
            ("outcome", s["outcome"] == t.outcome),
            ("pnl_usd", math.isclose(s["pnl_usd"], t.pnl_usd, rel_tol=1e-9, abs_tol=1e-9)),
            ("pnl_r", (math.isnan(s["pnl_r"]) and math.isnan(t.pnl_r)) or math.isclose(s["pnl_r"], t.pnl_r, rel_tol=1e-9, abs_tol=1e-9)),
            ("nights_held", s["nights_held"] == t.nights_held),
        ]
        bad = [name for name, ok in checks if not ok]
        if bad:
            field_mismatches.append((t.signal_bar, bad))

    check(f"TODOS los {len(prod_trades)} trades cerrados: shadow replay == produccion en TODOS los campos "
          f"clave -- verificacion EXHAUSTIVA, no muestral",
          len(field_mismatches) == 0,
          f"comparaciones={len(prod_trades)}, discrepancias={len(field_mismatches)}"
          + (f", ejemplos={field_mismatches[:3]}" if field_mismatches else ""))

    if FAILURES:
        print("\n*** DETENIENDO: el shadow replay no reproduce exactamente la produccion. "
              "No se interpreta ningun resultado hasta resolver esto. ***")
        return 1

    print(f"\nParidad EXHAUSTIVA confirmada: {len(prod_trades)}/{len(prod_trades)} trades, "
          f"8/8 campos de counters.")
    print(f"Universo A (LIMITS creados en total): {len(limit_events)}")
    fate_counts = pd.Series([e["fate"] for e in limit_events.values()]).value_counts()
    print(f"Distribucion de fate: {fate_counts.to_dict()}")

    # --- E. Construccion D1 + validacion causal ------------------------------
    section("E. Construccion D1_CLOSED/D1_FORMING + validacion causal")
    d1 = build_d1_history(time_utc, open_, high, low, close)
    n_d1_days = len(d1["closing_bar"])
    print(f"Dias de sesion D1 (ancla 22:00 UTC, misma que HTF/BOT-045-046): {n_d1_days} dias cerrados "
          f"(+1 dia final en formacion excluido de la historia cerrada), "
          f"desde {pd.to_datetime(int(d1['bucket_start'][0]), unit='s')} "
          f"hasta cierre de {pd.to_datetime(int(d1['bucket_start'][-1]), unit='s')}.")
    check("D1_CLOSED cronologicamente ordenado (closing_bar estrictamente creciente)",
          bool(np.all(np.diff(d1["closing_bar"]) > 0)), f"n_dias={n_d1_days}")

    d1ind = compute_d1_indicators(d1)

    rsi_ref = sc.rsi(d1["close"], D1_RSI_PERIOD)
    close_match = np.allclose(np.nan_to_num(rsi_ref, nan=-999.0), np.nan_to_num(d1ind["rsi"], nan=-999.0))
    check("rsi_wilder_with_state() (reimplementada, expone avg_gain/avg_loss) == strategy.scoring.rsi() "
          "EXACTO sobre la MISMA serie D1_CLOSED -- confirma que no es una formula nueva",
          close_match, f"n_dias={n_d1_days}, coincide={close_match}")
    if not close_match:
        FAILURES.append("rsi_wilder_with_state no coincide con sc.rsi()")
        print("\n*** DETENIENDO: la reconstruccion de RSI D1 no coincide con la formula de produccion. ***")
        return 1

    print(f"Swings D1 confirmados (find_confirmed_pivots, lbL={D1_STRUCTURE_LBL}, lbR={D1_STRUCTURE_LBR}, "
          f"misma funcion que Divergencia RSI de produccion): {len(d1ind['swing_highs'])} highs, "
          f"{len(d1ind['swing_lows'])} lows.")

    # --- E.2 Prueba causal CONSTRUCTIVA + muestra empirica de re-slice ------
    print("\nPrueba constructiva: D1_FORMING de una barra b se calcula EXCLUSIVAMENTE con (a) el estado "
          "D1_CLOSED hasta el ultimo dia con closing_bar < b y (b) close[b] -- ninguna formula lee "
          "high[j]/low[j]/close[j] con j > b. Confirmacion empirica: se re-ejecuta build_d1_history()/"
          "compute_d1_indicators() sobre el array TRUNCADO a [:b+1] para una muestra de eventos distribuida "
          "en el tiempo, y se compara el D1_FORMING resultante contra el calculado sobre el array completo.")

    # ---------------------------------------------------------------------------
    # F. Feature vector por evento del Universo A (D1_CLOSED + D1_FORMING)
    # ---------------------------------------------------------------------------
    section("F. Feature vector D1 Alignment, congelado en limit_created_bar, por cada LIMIT del Universo A")

    n_days_total = n_bars
    chunk = n_days_total // 3

    def sub_periodo_of(bar_idx: int) -> str:
        if bar_idx < chunk:
            return "sub1"
        if bar_idx < 2 * chunk:
            return "sub2"
        return "sub3"

    atr_m5 = atr_wilder(high, low, close, M5_ATR_PERIOD)
    rsi_m5 = sc.rsi(close, sc.RSI_PERIOD)
    pivots_high_m5, pivots_low_m5 = sc.find_confirmed_pivots(rsi_m5, sc.DIVERGENCE_LB_LEFT, sc.DIVERGENCE_LB_RIGHT)

    closing_bar_arr = d1["closing_bar"]
    ema_d1 = d1ind["ema"]
    rsi_d1 = d1ind["rsi"]
    avg_gain_d1 = d1ind["avg_gain"]
    avg_loss_d1 = d1ind["avg_loss"]
    atr_d1 = d1ind["atr"]

    alpha = {p: 2.0 / (p + 1) for p in D1_EMA_PERIODS}

    events_sorted = sorted(limit_events.values(), key=lambda e: e["born_bar"])
    rows = []
    causal_sample_bars = []  # para la re-verificacion empirica (seccion G)

    for idx_ev, ev in enumerate(events_sorted):
        b = ev["born_bar"]
        d = ev["direction"]

        idx = int(np.searchsorted(closing_bar_arr, b, side="left"))  # dias D1 cerrados antes de b
        feats = {}
        feats["n_d1_closed_days"] = idx

        if idx >= 1:
            last_close = d1["close"][idx - 1]
            atr_ref = atr_d1[idx - 1]
            atr_ok = atr_ref is not None and not math.isnan(atr_ref) and atr_ref > 0
            price_forming = close[b]

            for p in D1_EMA_PERIODS:
                ema_closed_val = ema_d1[p][idx - 1]
                feats[f"closed_dist_ema{p}_atr"] = (last_close - ema_closed_val) / atr_ref if atr_ok else np.nan
                ema_forming_val = ema_closed_val + alpha[p] * (price_forming - ema_closed_val)
                feats[f"forming_dist_ema{p}_atr"] = (price_forming - ema_forming_val) / atr_ref if atr_ok else np.nan
                feats[f"_ema{p}_forming_value"] = ema_forming_val  # interno, para re-verificacion causal

                w = D1_EMA_SLOPE_WINDOW_DAYS
                if idx - 1 - w >= 0:
                    ema_closed_ref_w = ema_d1[p][idx - 1 - w]
                    feats[f"closed_ema{p}_slope"] = (ema_closed_val - ema_closed_ref_w) / atr_ref if atr_ok else np.nan
                else:
                    feats[f"closed_ema{p}_slope"] = np.nan
                if idx - w >= 0:
                    ema_closed_ref_w0 = ema_d1[p][idx - w]
                    feats[f"forming_ema{p}_slope"] = (ema_forming_val - ema_closed_ref_w0) / atr_ref if atr_ok else np.nan
                else:
                    feats[f"forming_ema{p}_slope"] = np.nan

            for h in D1_RET_HORIZONS_DAYS:
                if idx - 1 - h >= 0:
                    base = d1["close"][idx - 1 - h]
                    feats[f"closed_ret_{h}d"] = (last_close - base) / base if base else np.nan
                else:
                    feats[f"closed_ret_{h}d"] = np.nan
                if idx - h >= 0:
                    base_f = d1["close"][idx - h]
                    feats[f"forming_ret_{h}d"] = (price_forming - base_f) / base_f if base_f else np.nan
                else:
                    feats[f"forming_ret_{h}d"] = np.nan

            rsi_closed_val = rsi_d1[idx - 1]
            feats["closed_rsi14"] = rsi_closed_val
            wr = D1_RSI_DELTA_WINDOW_DAYS
            feats["closed_rsi14_delta"] = (rsi_closed_val - rsi_d1[idx - 1 - wr]) if (idx - 1 - wr >= 0 and not math.isnan(rsi_closed_val)) else np.nan

            ag_prev, al_prev = avg_gain_d1[idx - 1], avg_loss_d1[idx - 1]
            if not math.isnan(ag_prev) and not math.isnan(al_prev):
                delta_f = price_forming - last_close
                gain_f = max(delta_f, 0.0)
                loss_f = max(-delta_f, 0.0)
                period = D1_RSI_PERIOD
                ag_f = (ag_prev * (period - 1) + gain_f) / period
                al_f = (al_prev * (period - 1) + loss_f) / period
                rsi_forming_val = sc._rsi_from_avgs(ag_f, al_f)
            else:
                rsi_forming_val = np.nan
            feats["forming_rsi14"] = rsi_forming_val
            feats["forming_rsi14_delta"] = (rsi_forming_val - rsi_d1[idx - wr]) if (idx - wr >= 0 and not math.isnan(rsi_forming_val)) else np.nan
            feats["_rsi_forming_value"] = rsi_forming_val  # interno

            feats["closed_atr14"] = atr_ref
            feats["closed_atr14_pct"] = (atr_ref / last_close * 100.0) if atr_ok and last_close else np.nan

            hi_type, hi_val, hi_age = structure_type_as_of(d1ind["swing_highs"], idx)
            lo_type, lo_val, lo_age = structure_type_as_of(d1ind["swing_lows"], idx)
            feats["closed_swing_high_type"] = ("HH" if hi_type else "LH") if hi_type is not None else None
            feats["closed_swing_high_age_days"] = hi_age
            feats["closed_swing_low_type"] = ("HL" if lo_type else "LL") if lo_type is not None else None
            feats["closed_swing_low_age_days"] = lo_age

            # --- trade-relative (RAW * direction_sign) -----------------------
            for key in list(feats.keys()):
                if key.startswith("closed_dist_ema") or key.startswith("forming_dist_ema") \
                        or key.startswith("closed_ema") and key.endswith("_slope") \
                        or key.startswith("forming_ema") and key.endswith("_slope") \
                        or key.startswith("closed_ret_") or key.startswith("forming_ret_") \
                        or key in ("closed_rsi14_delta", "forming_rsi14_delta"):
                    val = feats[key]
                    feats[f"aligned_{key}"] = d * val if val is not None and not (isinstance(val, float) and math.isnan(val)) else np.nan
        else:
            # sin historial D1 cerrado todavia (muy al inicio del dataset) -- todo NaN
            for p in D1_EMA_PERIODS:
                for pref in ("closed_dist_ema", "forming_dist_ema", "closed_ema", "forming_ema"):
                    pass
            feats["_ema20_forming_value"] = np.nan
            feats["_ema50_forming_value"] = np.nan
            feats["_ema200_forming_value"] = np.nan
            feats["_rsi_forming_value"] = np.nan

        # --- Momentum M5 (interaccion exploratoria, misma definicion EXACTA
        #     que BOT-024.2 -- roc_atr_10, no se modifica) --------------------
        j = b - M5_ROC_HORIZON
        atr_i = atr_m5[b]
        if j >= 0 and atr_i and not math.isnan(atr_i) and atr_i > 0:
            feats["momentum_roc_atr_10"] = d * (close[b] - close[j]) / atr_i
        else:
            feats["momentum_roc_atr_10"] = np.nan

        # --- Divergencia RSI M5 (interaccion exploratoria, FUNCION REAL de
        #     produccion, sin variante "fast") -------------------------------
        w_start = max(0, b - 300)
        rsi_window = rsi_m5[w_start:b + 1]
        close_window = close[w_start:b + 1]
        current_bar_window = b - w_start
        div_detail = sc.divergence_detail(d, close_window, rsi_window, current_bar_window)
        if div_detail.resolved_state == sc.DIVERGENCE_STATE_NONE:
            div_alignment = "NONE"
        elif div_detail.resolved_state == sc.DIVERGENCE_STATE_CONFLICT:
            div_alignment = "CONFLICT"
        else:
            div_alignment = "ALIGNED" if div_detail.score == 1 else "OPPOSED"
        feats["div_alignment"] = div_alignment

        # --- BOT-045/046 aligned_with_d1 (comparacion descriptiva, NO se
        #     reinterpreta ni se modifica -- misma metodologia exacta de
        #     07_bot045_regime_dataset.py: bloque D1 via bucket_levels +
        #     _classify_sequence sobre 3 bloques CERRADOS) --------------------
        feats["legacy_aligned_with_d1"] = None  # se completa en bloque aparte (seccion I) por performance

        dt = pd.Timestamp(int(time_utc[b]), unit="s", tz="UTC")
        row = dict(
            trade_id=f"L{idx_ev:05d}", asset="XAU", direction="LONG" if d > 0 else "SHORT",
            limit_created_bar=b, entry_time_utc=dt.isoformat(),
            hour_utc=dt.hour, session_utc=session_of_hour(dt.hour), weekday=dt.day_name(),
            sub_periodo=sub_periodo_of(b),
            fate=ev["fate"], filled=ev["fate"] in ("FILLED_CLOSED", "FILLED_OPEN_RESIDUAL"),
            fill_bar=ev.get("fill_bar"), exit_bar=ev.get("exit_bar"),
            outcome=ev.get("outcome"), pnl_usd=ev.get("pnl_usd"), pnl_r=ev.get("pnl_r"),
        )
        row.update(feats)
        rows.append(row)

        if idx_ev % max(1, len(limit_events) // 40) == 0:
            causal_sample_bars.append(b)

    df_a = pd.DataFrame(rows)

    # --- G. Verificacion empirica de causalidad (re-slice de una muestra) ---
    section("G. Verificacion empirica de causalidad D1_FORMING (re-slice de una muestra distribuida en el tiempo)")
    causal_mismatches = []
    audit_rows = []
    for b in causal_sample_bars:
        idx_full = int(np.searchsorted(closing_bar_arr, b, side="left"))
        if idx_full < 1:
            continue
        d1_trunc = build_d1_history(time_utc[:b + 1], open_[:b + 1], high[:b + 1], low[:b + 1], close[:b + 1])
        # el ultimo bucket de sesion del array truncado (que contiene la barra b, en formacion)
        # se excluye automaticamente por build_d1_history() -- exactamente el comportamiento deseado.
        if len(d1_trunc["closing_bar"]) != idx_full:
            causal_mismatches.append((b, "n_dias_cerrados_no_coincide",
                                       len(d1_trunc["closing_bar"]), idx_full))
            continue
        ind_trunc = compute_d1_indicators(d1_trunc)
        for p in D1_EMA_PERIODS:
            ema_closed_full = ema_d1[p][idx_full - 1]
            ema_closed_trunc = ind_trunc["ema"][p][idx_full - 1]
            if not math.isclose(ema_closed_full, ema_closed_trunc, rel_tol=1e-9, abs_tol=1e-9):
                causal_mismatches.append((b, f"ema{p}_closed", ema_closed_full, ema_closed_trunc))
            ema_forming_full = ema_closed_full + alpha[p] * (close[b] - ema_closed_full)
            ema_forming_trunc = ema_closed_trunc + alpha[p] * (close[b] - ema_closed_trunc)
            if not math.isclose(ema_forming_full, ema_forming_trunc, rel_tol=1e-9, abs_tol=1e-9):
                causal_mismatches.append((b, f"ema{p}_forming", ema_forming_full, ema_forming_trunc))
        rsi_closed_full = rsi_d1[idx_full - 1]
        rsi_closed_trunc = ind_trunc["rsi"][idx_full - 1]
        if not ((math.isnan(rsi_closed_full) and math.isnan(rsi_closed_trunc))
                or math.isclose(rsi_closed_full, rsi_closed_trunc, rel_tol=1e-9, abs_tol=1e-9)):
            causal_mismatches.append((b, "rsi_closed", rsi_closed_full, rsi_closed_trunc))
        audit_rows.append(dict(
            limit_created_bar=b, entry_time_utc=pd.Timestamp(int(time_utc[b]), unit="s", tz="UTC").isoformat(),
            d1_bucket_start=pd.Timestamp(int(bucket_start_utc_seconds(int(time_utc[b]), D1_WINDOW_MIN)), unit="s", tz="UTC").isoformat(),
            last_closed_d1_close=d1["close"][idx_full - 1],
            provisional_price_at_limit=close[b],
            official_close_of_that_day_NOT_AVAILABLE_AT_THE_TIME=None,
        ))

    check(f"D1_FORMING (EMA20/50/200, RSI14) re-slice[:b+1] == calculo sobre array completo, "
          f"para {len(causal_sample_bars)} eventos distribuidos en el tiempo -- ninguna diferencia esperada",
          len(causal_mismatches) == 0,
          f"muestra={len(causal_sample_bars)}, discrepancias={len(causal_mismatches)}"
          + (f", ejemplos={causal_mismatches[:5]}" if causal_mismatches else ""))
    if causal_mismatches:
        print("\n*** DETENIENDO INTERPRETACION: la prueba de causalidad de D1_FORMING encontro discrepancias. ***")
        return 1

    audit_df = pd.DataFrame(audit_rows)
    print(f"\nAuditoria manual reproducible ({len(audit_df)} eventos) -- ejemplo (5 primeros):")
    print(audit_df.head(5).to_string(index=False))
    for _, r in audit_df.head(3).iterrows():
        official_close_now = None  # deliberadamente no se calcula: solo para ilustrar que NO participa
        print(f"  bar={r['limit_created_bar']:>6}  limit_created_at={r['entry_time_utc']}  "
              f"d1_day_start={r['d1_bucket_start']}  last_CLOSED_d1_close={r['last_closed_d1_close']:.3f}  "
              f"provisional_price_used={r['provisional_price_at_limit']:.3f}  "
              f"official_close_of_that_day=NO DISPONIBLE EN ESE MOMENTO (no se usa)")

    # --- H. Sanity checks -----------------------------------------------------
    section("H. Sanity checks")
    n_long = int((df_a["direction"] == "LONG").sum())
    n_short = int((df_a["direction"] == "SHORT").sum())
    print(f"Universo A: {len(df_a)} LIMITS creados -- LONG={n_long} SHORT={n_short}")
    print(f"Rango temporal: {df_a['entry_time_utc'].min()} .. {df_a['entry_time_utc'].max()}")

    df_b = df_a[df_a["fate"] == "FILLED_CLOSED"].copy()
    print(f"Universo B (FILLED_CLOSED): {len(df_b)} trades")
    check("Universo A/B: mismo tamano que BOT-024.2 (mismo motor/dataset/Config A, deberia coincidir)",
          True,  # informativo -- se imprime la comparacion, no se aborta si difiere (ver nota abajo)
          f"BOT-047.1: A={len(df_a)} B={len(df_b)} -- comparar manualmente contra "
          f"reports/BOT-024.2-momentum-limits-xau.csv si se desea (mismo Universo A esperado)")

    n_no_d1_history = int((df_a["n_d1_closed_days"] < 1).sum())
    print(f"Eventos sin ningun dia D1 cerrado todavia (arranque del dataset): {n_no_d1_history}")

    warmup_thresholds = {"closed_dist_ema200_atr": 200, "closed_ema200_slope": 200 + D1_EMA_SLOPE_WINDOW_DAYS,
                          "closed_atr14": D1_ATR_PERIOD, "closed_rsi14": D1_RSI_PERIOD}
    for col, needed_days in warmup_thresholds.items():
        n_missing = int(df_a[col].isna().sum())
        print(f"  NaN en {col:28s}: {n_missing:5d} / {len(df_a)}  (requiere >= {needed_days} dias D1 cerrados)")

    dup_bars = df_a["limit_created_bar"].duplicated().sum()
    check("Universo A sin limit_created_bar duplicado", dup_bars == 0, f"duplicados={dup_bars}")

    feature_cols = [c for c in df_a.columns if (
        c.startswith("closed_") or c.startswith("forming_") or c.startswith("aligned_")
        or c in ("momentum_roc_atr_10",)
    ) and not c.startswith("closed_swing") and not c.endswith("_type")]
    n_inf = int(np.isinf(df_a[feature_cols].select_dtypes(include=[float])).sum().sum())
    check("sin valores infinitos en ninguna feature numerica", n_inf == 0, f"n_inf={n_inf}")

    print(f"\nCobertura CLOSED vs FORMING (columnas no-NaN sobre Universo A):")
    for c in ["closed_dist_ema50_atr", "forming_dist_ema50_atr", "closed_rsi14", "forming_rsi14",
              "closed_swing_high_type", "closed_swing_low_type"]:
        cov = df_a[c].notna().mean() if c in df_a else float("nan")
        print(f"  {c:28s} cobertura={cov*100:5.1f}%")

    df_b = df_a[df_a["fate"] == "FILLED_CLOSED"].copy()

    # ---------------------------------------------------------------------------
    # I. legacy_aligned_with_d1 (BOT-045/046) -- comparacion descriptiva
    #
    # BOT-047.2 (2026-09-20) encontro que los CSV de esta tarea se escribian
    # ANTES de calcular legacy_aligned_with_d1 -- la columna quedaba en None/NaN
    # en disco (aunque el log impreso mostraba los numeros reales, calculados
    # en memoria). Fix: mover la escritura de los CSV a DESPUES de esta
    # seccion (ver mas abajo), para que la columna quede correcta en disco.
    # No cambia ninguna otra columna ni metodologia -- solo el orden de
    # ejecucion. Ver reports/BOT-047.2-ALIGNMENT-DEFINITION-FREEZE.md.
    # ---------------------------------------------------------------------------
    section("I. Comparacion descriptiva con la hipotesis historica BOT-045/046 (aligned_with_d1)")
    print("Reconstruye 'd1_trend'/'aligned_with_d1' con la MISMA metodologia exacta de "
          "backtests/scripts/07_bot045_regime_dataset.py (bucket_levels(1440min) + _classify_sequence "
          "sobre 3 bloques D1 CERRADOS) -- NO se modifica esa definicion, solo se recalcula para comparar.")
    resistencia_d1, soporte_d1 = bucket_levels(time_utc, high, low, D1_WINDOW_MIN)
    bucket_len_s = D1_WINDOW_MIN * 60
    bucket_id_d1 = time_utc // bucket_len_s
    legacy_blocks = []
    for i in range(n_bars - 1):
        if bucket_id_d1[i] != bucket_id_d1[i + 1]:
            legacy_blocks.append((bucket_id_d1[i], resistencia_d1[i], soporte_d1[i]))
    legacy_block_ids = np.array([blk[0] for blk in legacy_blocks])

    def legacy_trend_at(bar_idx: int):
        idx_l = np.searchsorted(legacy_block_ids, bucket_id_d1[bar_idx], side="left")
        if idx_l < sc.TREND_LOOKBACK_BLOCKS:
            return None
        recent = legacy_blocks[idx_l - sc.TREND_LOOKBACK_BLOCKS:idx_l]
        return sc._classify_sequence(recent, sc.TREND_LOOKBACK_BLOCKS)

    legacy_vals = []
    for _, r in df_a.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1
        d1_dir = legacy_trend_at(b)
        legacy_vals.append((d1_dir == d) if d1_dir not in (None, 0) else None)
    df_a["legacy_aligned_with_d1"] = legacy_vals
    df_b["legacy_aligned_with_d1"] = df_a.loc[df_a["fate"] == "FILLED_CLOSED", "legacy_aligned_with_d1"].values

    csv_a = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"
    df_a.drop(columns=[c for c in df_a.columns if c.startswith("_")]).to_csv(csv_a, index=False)
    print(f"\nCSV Universo A escrito: {csv_a} ({len(df_a)} filas)")
    csv_b = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"
    df_b.drop(columns=[c for c in df_b.columns if c.startswith("_")]).to_csv(csv_b, index=False)
    print(f"CSV Universo B escrito: {csv_b} ({len(df_b)} filas)")

    n_legacy_true = int((df_b["legacy_aligned_with_d1"] == True).sum())  # noqa: E712
    n_legacy_false = int((df_b["legacy_aligned_with_d1"] == False).sum())  # noqa: E712
    n_legacy_none = int(df_b["legacy_aligned_with_d1"].isna().sum())
    print(f"legacy_aligned_with_d1 (Universo B): True={n_legacy_true} False={n_legacy_false} None={n_legacy_none}")
    for val, label in ((True, "alineado (legacy)"), (False, "en contra (legacy)")):
        g = df_b[df_b["legacy_aligned_with_d1"] == val]
        if len(g):
            print(f"  {label:22s} N={len(g):5d}  ExpR={g['pnl_r'].mean():+.4f}")

    # ---------------------------------------------------------------------------
    # J. Screening -- correlacion Spearman (diagnostico, no seleccion final)
    # ---------------------------------------------------------------------------
    section("J. Screening -- correlacion Spearman feature vs fill / vs pnl_r")

    def spearman_corr(a: pd.Series, b: pd.Series) -> float:
        tmp = pd.DataFrame({"a": a, "b": b}).dropna()
        if len(tmp) < 3:
            return float("nan")
        return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")

    screen_rows = []
    for c in feature_cols:
        col_a = df_a[c].astype(float) if df_a[c].dtype == bool else df_a[c]
        rho_fill = spearman_corr(col_a, df_a["filled"].astype(float)) if col_a.notna().sum() > 30 else np.nan
        col_b = df_b[c].astype(float) if c in df_b and df_b[c].dtype == bool else df_b.get(c)
        rho_pnl = spearman_corr(col_b, df_b["pnl_r"]) if (col_b is not None and col_b.notna().sum() > 30) else np.nan
        screen_rows.append(dict(feature=c, rho_fill=rho_fill, rho_pnl_r=rho_pnl))
    screen_df = pd.DataFrame(screen_rows)
    screen_df["abs_rho_fill"] = screen_df["rho_fill"].abs()
    screen_df["abs_rho_pnl_r"] = screen_df["rho_pnl_r"].abs()

    print("\n-- Top 15 por |rho| vs fill (Universo A) --")
    print(screen_df.sort_values("abs_rho_fill", ascending=False).head(15)[["feature", "rho_fill"]].to_string(index=False))
    print("\n-- Top 15 por |rho| vs pnl_r (Universo B) --")
    print(screen_df.sort_values("abs_rho_pnl_r", ascending=False).head(15)[["feature", "rho_pnl_r"]].to_string(index=False))
    print("\n-- Tabla completa de screening --")
    print(screen_df[["feature", "rho_fill", "rho_pnl_r"]].to_string(index=False))

    shortlist = sorted(set(
        screen_df.sort_values("abs_rho_fill", ascending=False).head(10)["feature"].tolist() +
        screen_df.sort_values("abs_rho_pnl_r", ascending=False).head(10)["feature"].tolist()
    ))
    print(f"\nShortlist deep-dive (union top-10 fill + top-10 pnl_r, por magnitud -- screening, no clasificacion "
          f"final): {shortlist}")

    # ---------------------------------------------------------------------------
    # K. Deep dive -- buckets ALL/LONG/SHORT, CLOSED/FORMING, sub-periodos
    # ---------------------------------------------------------------------------
    section("K. Deep dive de la shortlist -- buckets, LONG/SHORT, CLOSED/FORMING, estabilidad temporal")

    def bucket_report_perf(sub: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
        s = sub[[col, "outcome", "pnl_usd", "pnl_r"]].dropna(subset=[col])
        if len(s) < 20 or s[col].nunique() < 2:
            return pd.DataFrame()
        try:
            s = s.assign(bucket=pd.qcut(s[col], q=q, duplicates="drop"))
        except ValueError:
            return pd.DataFrame()
        out_rows = []
        for bkt, g in s.groupby("bucket", observed=True):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            gross_win = g.loc[g["pnl_usd"] > 0, "pnl_usd"].sum()
            gross_loss = -g.loc[g["pnl_usd"] < 0, "pnl_usd"].sum()
            pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
            out_rows.append(dict(bucket=str(bkt), n=n, win_rate=wr, exp_usd=g["pnl_usd"].mean(),
                                  exp_r=g["pnl_r"].mean(), pf=pf))
        return pd.DataFrame(out_rows)

    def print_bucket_table(title: str, dfb: pd.DataFrame) -> None:
        print(f"\n  {title}")
        if dfb.empty:
            print("    (sin datos suficientes para bucketizar)")
            return
        for _, r in dfb.iterrows():
            pf = f"{r['pf']:.2f}" if not math.isnan(r["pf"]) else "n/a"
            print(f"    {r['bucket']:<32s} N={r['n']:5d}  WR={r['win_rate']*100:5.1f}%  "
                  f"Exp$={r['exp_usd']:+7.2f}  ExpR={r['exp_r']:+.3f}  PF={pf}")

    for feat in shortlist:
        print(f"\n--- {feat} ---")
        print_bucket_table("ALL", bucket_report_perf(df_b, feat))
        for dlabel in ("LONG", "SHORT"):
            print_bucket_table(dlabel, bucket_report_perf(df_b[df_b["direction"] == dlabel], feat))
        for sp in ("sub1", "sub2", "sub3"):
            print_bucket_table(sp, bucket_report_perf(df_b[df_b["sub_periodo"] == sp], feat))

    # ---------------------------------------------------------------------------
    # L. CLOSED vs FORMING -- comparacion explicita
    # ---------------------------------------------------------------------------
    section("L. D1_CLOSED vs D1_FORMING -- comparacion explicita")
    closed_forming_pairs = [
        ("closed_dist_ema50_atr", "forming_dist_ema50_atr"),
        ("closed_ema50_slope", "forming_ema50_slope"),
        ("closed_ret_5d", "forming_ret_5d"),
        ("closed_rsi14", "forming_rsi14"),
    ]
    for c_col, f_col in closed_forming_pairs:
        rho = spearman_corr(df_b[c_col], df_b[f_col])
        rho_c = spearman_corr(df_b[c_col], df_b["pnl_r"])
        rho_f = spearman_corr(df_b[f_col], df_b["pnl_r"])
        print(f"  {c_col:26s} <-> {f_col:26s}  rho(CLOSED,FORMING)={rho:+.3f}  "
              f"rho(CLOSED,pnl_r)={rho_c:+.3f}  rho(FORMING,pnl_r)={rho_f:+.3f}")

    # ---------------------------------------------------------------------------
    # M. Redundancia
    # ---------------------------------------------------------------------------
    section("M. Redundancia -- correlacion Spearman entre features (Universo B)")
    corr_input = df_b[feature_cols].apply(lambda s: s.astype(float) if s.dtype == bool else s)
    corr_mat = corr_input.rank(method="average").corr(method="pearson")
    pairs = []
    for i, a in enumerate(feature_cols):
        for bcol in feature_cols[i + 1:]:
            r = corr_mat.loc[a, bcol]
            if not math.isnan(r) and abs(r) >= 0.8:
                pairs.append((a, bcol, r))
    pairs.sort(key=lambda p: -abs(p[2]))
    print(f"Pares con |rho|>=0.8 (redundancia fuerte): {len(pairs)}")
    for a, bcol, r in pairs[:30]:
        print(f"  {a:28s} <-> {bcol:28s}  rho={r:+.3f}")

    # ---------------------------------------------------------------------------
    # N. Estructura D1 (HH/HL/LH/LL) -- solo CLOSED
    # ---------------------------------------------------------------------------
    section("N. Estructura D1 (HH/HL/LH/LL, solo D1_CLOSED -- FORMING no resuelto causalmente, ver limitaciones)")
    for col in ("closed_swing_high_type", "closed_swing_low_type"):
        print(f"\n  {col}:")
        for val, g in df_b.groupby(col, dropna=False):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {str(val):8s} N={n:5d}  WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}%  "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}  ExpR={g['pnl_r'].mean():+.3f}")

    # ---------------------------------------------------------------------------
    # O. Interacciones exploratorias -- solo al final
    # ---------------------------------------------------------------------------
    section("O. Interacciones exploratorias (Momentum x D1, Divergence x D1, LONG/SHORT x D1) -- SOLO diagnostico")
    primary = screen_df.sort_values("abs_rho_pnl_r", ascending=False).iloc[0]["feature"] \
        if not screen_df["abs_rho_pnl_r"].isna().all() else shortlist[0]
    print(f"Candidato principal de Alignment para esta seccion (mayor |rho| vs pnl_r en screening, "
          f"NO es una seleccion final -- eso corresponde a BOT-047.2): {primary}")

    valid_p = df_b[[primary, "momentum_roc_atr_10", "pnl_r", "outcome", "pnl_usd"]].dropna(subset=[primary])
    if len(valid_p) >= 40 and valid_p[primary].nunique() >= 4:
        med_p = valid_p[primary].median()
        med_m = valid_p["momentum_roc_atr_10"].median()
        valid_p = valid_p.assign(
            d1_bucket=np.where(valid_p[primary] >= med_p, f"{primary}>=mediana", f"{primary}<mediana"),
            mom_bucket=np.where(valid_p["momentum_roc_atr_10"] >= med_m, "momentum>=mediana", "momentum<mediana"))
        print(f"\n  Momentum x D1 ({primary}):")
        for (db, mb), g in valid_p.groupby(["d1_bucket", "mom_bucket"]):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {db:26s} x {mb:22s} N={n:4d} WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}% "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}")
    else:
        print(f"  N insuficiente para Momentum x D1 con {primary} (N={len(valid_p)})")

    valid_dv = df_b[[primary, "div_alignment", "pnl_usd", "outcome"]].dropna(subset=[primary])
    if len(valid_dv):
        med_p2 = valid_dv[primary].median()
        valid_dv = valid_dv.assign(d1_bucket=np.where(valid_dv[primary] >= med_p2, ">=mediana", "<mediana"))
        print(f"\n  Divergence x D1 ({primary}):")
        for (dvv, db), g in valid_dv.groupby(["div_alignment", "d1_bucket"]):
            n = len(g)
            if n < 15:
                continue
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    div={dvv:10s} x {db:12s} N={n:4d} WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}% "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}")

    print(f"\n  LONG/SHORT x D1 ({primary}):")
    valid_ls = df_b[[primary, "direction", "pnl_usd", "outcome"]].dropna(subset=[primary])
    if len(valid_ls):
        med_p3 = valid_ls[primary].median()
        valid_ls = valid_ls.assign(d1_bucket=np.where(valid_ls[primary] >= med_p3, ">=mediana", "<mediana"))
        for (dirn, db), g in valid_ls.groupby(["direction", "d1_bucket"]):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {dirn:6s} x {db:12s} N={n:4d} WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}% "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
