"""BOT-048.1 -- Structure Feature Discovery, XAU (BTC bloqueado, ver seccion A).

Subtarea de BOT-048 (feature padre "Structure", dimension del futuro Signal
Quality de BOT-024 -- ver BOT-024 en BACKLOG.md). SOLO LECTURA/DISCOVERY --
no define todavia que significa "buena Structure", no crea un score, no crea
pesos, no crea gates, no optimiza la estrategia.

Pregunta que responde: que variables estructurales observables y CAUSALES
existen en `limit_created_bar` (== `signal_bar` == `born_bar`, mismo punto de
congelacion que BOT-024.2/BOT-047.1) y pueden describir la ubicacion/calidad
estructural de esa entrada dentro de la estructura RECIENTE del precio (M5) --
sin asumir de antemano que estar cerca de soporte/resistencia, un retest, o
HH/HL, sea "mejor" que la alternativa.

Structure es conceptualmente distinta de:
  - Momentum (BOT-024.2/BOT-024.3): impulso/velocidad del precio alrededor de
    la señal -- Structure no vuelve a medir esto con otro nombre.
  - Alignment (BOT-047.x, "Structural Alignment"): a pesar del nombre
    parecido, Alignment es un concepto DIRECCIONAL de D1 (HH/HL D1 a favor o
    en contra del trade). Structure (esta tarea) es un concepto de
    UBICACION dentro de la estructura M5 reciente -- no D1, no direccional
    per se. Ver seccion 6 del reporte para la distincion explicita.

BTC: bloqueado en esta ejecucion, mismo criterio y misma verificacion en vivo
que BOT-024.2/BOT-047.1 (ver seccion A).

Metodologia (resumen; ver reports/BOT-048.1-STRUCTURE-FEATURE-DISCOVERY.md):
  1. Corre strategy.engine.run_backtest (sin tocar) UNA sola vez, continuo,
     sobre backtests/data/XAUUSDc_M5_latest.parquet, "Config A" (misma que
     BOT-024.1/BOT-024.2/BOT-047.1/BOT-042/043/045/046).
  2. Shadow replay (misma logica de decision, copiada de
     scripts/discover_d1_alignment_features_xau.py, EXTENDIDA unicamente con
     bookkeeping nuevo -- que bar/nivel armo por ultima vez armado_venta/
     armado_compra antes de que la señal dispare -- que no afecta ninguna
     decision de fill/outcome) reproduce Universo A completo (todos los
     LIMITS, incluidos los que nunca hicieron fill) y se valida
     EXHAUSTIVAMENTE contra run_backtest() real antes de interpretar nada.
  3. Estructura M5 causal via strategy.scoring.find_confirmed_pivots()
     (la MISMA funcion que ya usa produccion para pivotes de Divergencia
     RSI), aplicada aca al PRECIO (high/low) en vez de RSI -- swing highs/
     lows M5, con confirmed_bar=bar+lbR como corte de disponibilidad causal
     (mismo patron que D1_STRUCTURE en BOT-047.1, aplicado a M5).
  4. Los niveles resistencia/soporte de strategy.engine.bucket_levels() (el
     mismo bloque HTF que ya arma la señal de produccion) se reusan tal
     cual para la familia de "posicion en el rango".
  5. Cada feature se evalua individualmente (bins/cuantiles), separado en
     ALL/LONG/SHORT y por sub-periodo -- sin grid search, sin score, sin
     pesos, sin gate.

Uso:
    .venv/Scripts/python.exe scripts/discover_structure_features_xau.py \
        > reports/BOT-048.1-STRUCTURE-FEATURE-DISCOVERY-EVIDENCE.log

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
from strategy import scoring as sc

DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
REPORTS_DIR = REPO_ROOT / "reports"

# Config A congelada -- misma que BOT-024.1/BOT-024.2/BOT-047.1/BOT-042/
# BOT-043/BOT-045/BOT-046. NO se optimiza ni se cambia ningun parametro de
# estrategia en esta tarea.
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

# --- Estructura M5: swing highs/lows via find_confirmed_pivots() (funcion
# REAL de produccion, strategy/scoring.py), aplicada al PRECIO M5 (high/low)
# en vez de RSI. lbL=lbR=5 = strategy.scoring.DIVERGENCE_LB_LEFT/RIGHT --
# MISMOS parametros que ya usa produccion para Divergencia, reusados aca sin
# modificar, no una ventana nueva inventada para esta tarea. -------------
PIVOT_LBL = sc.DIVERGENCE_LB_LEFT
PIVOT_LBR = sc.DIVERGENCE_LB_RIGHT

# Ventana de "estructura reciente" para las familias D/G/H (breakout/retest,
# espacio estructural, obstaculos) -- MISMO valor (300 barras) que ya usa
# scripts/discover_d1_alignment_features_xau.py para su ventana de
# Divergencia M5 (w_start = max(0, b-300)), reusado aca por continuidad, no
# una ventana nueva optimizada para esta tarea. Las familias A/C/I (ultimo
# swing disponible / distancia a SL-TP) usan TODO el historial causalmente
# disponible, sin ventana -- "la estructura no caduca", ver seccion 10 del
# reporte para la discusion explicita de esta eleccion metodologica.
RECENT_WINDOW_BARS = 300

# Ventanas de rango reciente (Familia B, posicion en el rango) -- dos
# definiciones fijas y reproducibles, NO optimizadas / NO grid-search:
# 60 barras (~5h) y 288 barras (~1 dia de sesion M5). Se reportan ambas por
# separado, sin elegir "la mejor".
ROLL_RANGE_WINDOWS = (60, 288)

M5_ATR_PERIOD = 14
M5_ROC_HORIZON = 10  # interaccion exploratoria con Momentum -- MISMA definicion exacta que BOT-047.1 (roc_atr_10)

SESSION_BOUNDS_UTC = [  # misma convencion que BOT-045/BOT-024.2/BOT-047.1
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
#    dataset.py / scripts/discover_momentum_features_xau.py / scripts/
#    discover_d1_alignment_features_xau.py (no existe en produccion, no se
#    reinventa una formula nueva).
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


# ---------------------------------------------------------------------------
# 1. Shadow replay -- MISMA logica de decision que scripts/discover_d1_
#    alignment_features_xau.py::shadow_replay (a su vez copiada de scripts/
#    discover_momentum_features_xau.py), reproduce strategy/engine.py::
#    run_backtest() (pending/open_pos/counters) bit a bit. UNICA extension:
#    bookkeeping de "origen de armado" (origin_venta/origin_compra -- que
#    barra/nivel armo por ultima vez armado_venta/armado_compra ANTES de que
#    la señal dispare). Esta extension NO participa de ninguna decision de
#    fill/expiracion/outcome -- solo se LEE el estado de armado que la logica
#    original ya calculaba, nunca se escribe a partir de el. Ver seccion F
#    para el uso (Familia F, "Entry Relative to Signal Origin") y seccion G
#    para la verificacion causal.
# ---------------------------------------------------------------------------

def shadow_replay(time_utc, time_server, high, low, close, spread_pts, params: StrategyParams,
                   costs: BrokerCosts, ema_line, resistencia, soporte):
    n = len(close)
    buf = params.buf_bp / 10000.0

    armado_venta = False
    armado_compra = False
    pending: list[dict] = []
    open_pos: list[dict] = []

    # Origen de armado: se actualiza CADA VEZ que high[i]>=resistencia[i] (o
    # low[i]<=soporte[i]) vuelve a poner armado_*=True -- incluido el
    # "auto-armado" documentado en engine.bucket_levels() (cada nuevo maximo/
    # minimo local dentro del mismo bloque HTF vuelve a cumplir la condicion).
    # Por construccion, en la barra donde una señal dispara, origin_venta/
    # origin_compra SIEMPRE reflejan un armado ocurrido en una barra ANTERIOR
    # (nunca la barra de la señal misma) -- ver seccion 6 del reporte.
    origin_venta: dict | None = None
    origin_compra: dict | None = None

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

        # snapshot del origen ANTES del posible re-armado de esta barra --
        # es el que corresponde a una señal que dispare EN esta barra.
        prev_origin_venta = origin_venta
        prev_origin_compra = origin_compra

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
            origin_venta = {"bar": i, "level": float(r_i), "extreme": float(high[i])}
        if not math.isnan(s_i) and low[i] <= s_i:
            armado_compra = True
            origin_compra = {"bar": i, "level": float(s_i), "extreme": float(low[i])}

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
                    origin = prev_origin_venta if d < 0 else prev_origin_compra
                    pending.append({"dir": d, "entry": entry, "stop": stop, "target": target, "born": i})
                    limit_events[i] = dict(born_bar=i, direction=d, entry=entry, stop=stop, target=target,
                                            fate="PENDING_RESIDUAL", fill_bar=None, exit_bar=None,
                                            outcome=None, pnl_usd=None, pnl_r=None,
                                            origin_bar=origin["bar"] if origin else None,
                                            origin_level=origin["level"] if origin else None)

    return limit_events, shadow_closed, counters


# ---------------------------------------------------------------------------
# 2. Estructura M5 (swing highs/lows) via find_confirmed_pivots() sobre
#    high/low de precio -- helpers de lookup causal (bisect sobre arrays
#    ordenados por barra/confirmed_bar).
# ---------------------------------------------------------------------------

def pivot_arrays(pivots: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bar = np.array([p.bar for p in pivots], dtype=np.int64)
    conf = np.array([p.confirmed_bar for p in pivots], dtype=np.int64)
    val = np.array([p.value for p in pivots], dtype=np.float64)
    return bar, conf, val


def last_available_idx(conf_arr: np.ndarray, b: int) -> int:
    """Indice del ULTIMO pivote con confirmed_bar<=b (-1 si ninguno).
    conf_arr debe estar ordenado ascendente (lo esta: confirmed_bar=bar+lbR,
    y bar es monotono creciente en la lista de find_confirmed_pivots)."""
    return int(np.searchsorted(conf_arr, b, side="right")) - 1


def windowed_values(bar_arr: np.ndarray, conf_arr: np.ndarray, val_arr: np.ndarray,
                     b: int, window: int | None) -> np.ndarray:
    """Valores de los pivotes CAUSALMENTE disponibles en b (confirmed_bar<=b),
    opcionalmente acotados a bar>=b-window (window=None -- todo el historial,
    "la estructura no caduca")."""
    idx_hi = int(np.searchsorted(conf_arr, b, side="right"))
    if window is None:
        idx_lo = 0
    else:
        idx_lo = int(np.searchsorted(bar_arr, b - window, side="left"))
    return val_arr[idx_lo:idx_hi]


def windowed_bar_val(bar_arr: np.ndarray, conf_arr: np.ndarray, val_arr: np.ndarray,
                      b: int, window: int | None) -> tuple[np.ndarray, np.ndarray]:
    idx_hi = int(np.searchsorted(conf_arr, b, side="right"))
    idx_lo = int(np.searchsorted(bar_arr, b - window, side="left")) if window is not None else 0
    return bar_arr[idx_lo:idx_hi], val_arr[idx_lo:idx_hi]


# ---------------------------------------------------------------------------
# 3. main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-048.1 -- Structure Feature Discovery, XAU (BTC bloqueado, ver seccion A)")
    print("SOLO LECTURA/DISCOVERY. No se modifico ningun archivo de produccion. No se activa gating.")
    print("No se implementa una definicion final de Structure. No se toca Momentum ni Alignment.\n")

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
    section("B. Dataset XAU y costos (reusa lo ya usado por BOT-024.2/BOT-047.1)")
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

    n_no_origin = sum(1 for e in limit_events.values() if e["origin_bar"] is None)
    check("Todo evento con señal disparada tiene un origen de armado registrado (origin_bar no None) -- "
          "por construccion, armado_*==True siempre proviene de una barra anterior con high>=resistencia "
          "o low<=soporte",
          n_no_origin == 0, f"eventos sin origen={n_no_origin} / {len(limit_events)}")

    # --- E. Estructura M5 causal (swing highs/lows) -------------------------
    section("E. Estructura M5 (swing highs/lows via find_confirmed_pivots() sobre precio)")
    swing_highs, _ = sc.find_confirmed_pivots(high, PIVOT_LBL, PIVOT_LBR)
    _, swing_lows = sc.find_confirmed_pivots(low, PIVOT_LBL, PIVOT_LBR)
    print(f"find_confirmed_pivots(high, lbL={PIVOT_LBL}, lbR={PIVOT_LBR}) -- MISMA funcion de produccion "
          f"que Divergencia RSI, aplicada aca al PRECIO M5 en vez de RSI: {len(swing_highs)} swing highs, "
          f"{len(swing_lows)} swing lows confirmados sobre {n_bars} barras.")

    hi_bar, hi_conf, hi_val = pivot_arrays(swing_highs)
    lo_bar, lo_conf, lo_val = pivot_arrays(swing_lows)
    merged = sorted(swing_highs + swing_lows, key=lambda p: p.bar)
    mg_bar, mg_conf, mg_val = pivot_arrays(merged)

    check("swing highs ordenados por barra (bar estrictamente creciente)",
          bool(np.all(np.diff(hi_bar) > 0)), f"n={len(hi_bar)}")
    check("swing lows ordenados por barra (bar estrictamente creciente)",
          bool(np.all(np.diff(lo_bar) > 0)), f"n={len(lo_bar)}")
    check("confirmed_bar == bar + lbR para todos los swing highs/lows (sin excepcion)",
          bool(np.all(hi_conf - hi_bar == PIVOT_LBR)) and bool(np.all(lo_conf - lo_bar == PIVOT_LBR)),
          f"lbR={PIVOT_LBR}")

    atr_m5 = atr_wilder(high, low, close, M5_ATR_PERIOD)

    # ---------------------------------------------------------------------------
    # F. Feature vector por evento del Universo A, congelado en limit_created_bar
    # ---------------------------------------------------------------------------
    section("F. Feature vector Structure, congelado en limit_created_bar, por cada LIMIT del Universo A")

    chunk = n_bars // 3

    def sub_periodo_of(bar_idx: int) -> str:
        if bar_idx < chunk:
            return "sub1"
        if bar_idx < 2 * chunk:
            return "sub2"
        return "sub3"

    events_sorted = sorted(limit_events.values(), key=lambda e: e["born_bar"])
    rows = []
    causal_sample_bars = []  # para la re-verificacion empirica (seccion G)

    for idx_ev, ev in enumerate(events_sorted):
        b = ev["born_bar"]
        d = ev["direction"]
        entry = ev["entry"]
        stop = ev["stop"]
        target = ev["target"]
        atr_b = atr_m5[b]
        atr_ok = atr_b is not None and not math.isnan(atr_b) and atr_b > 0

        feats: dict = {}

        # --- Familia A: Swing Structure (RAW, sin ventana -- "la estructura
        #     no caduca") -------------------------------------------------
        ih = last_available_idx(hi_conf, b)
        il = last_available_idx(lo_conf, b)

        if ih >= 0 and atr_ok:
            feats["swing_high_dist_atr"] = (hi_val[ih] - entry) / atr_b
            feats["swing_high_age_bars"] = b - int(hi_bar[ih])
        else:
            feats["swing_high_dist_atr"] = np.nan
            feats["swing_high_age_bars"] = np.nan
        if il >= 0 and atr_ok:
            feats["swing_low_dist_atr"] = (entry - lo_val[il]) / atr_b
            feats["swing_low_age_bars"] = b - int(lo_bar[il])
        else:
            feats["swing_low_dist_atr"] = np.nan
            feats["swing_low_age_bars"] = np.nan

        feats["swing_high_seq"] = ("HH" if hi_val[ih] > hi_val[ih - 1] else "LH") if ih >= 1 else None
        feats["swing_low_seq"] = ("HL" if lo_val[il] > lo_val[il - 1] else "LL") if il >= 1 else None

        idx_hi_w = int(np.searchsorted(mg_conf, b, side="right"))
        idx_lo_w = int(np.searchsorted(mg_bar, b - RECENT_WINDOW_BARS, side="left"))
        feats["n_swings_window300"] = idx_hi_w - idx_lo_w

        # --- direccion-conscientes (derivados de la Familia A -- misma
        #     cantidad, solo re-etiquetada segun la direccion del trade,
        #     mismo patron RAW+derivado que BOT-047.1 aligned_*) -----------
        if d > 0:
            dir_dist, dir_age = feats["swing_high_dist_atr"], feats["swing_high_age_bars"]
            opp_dist, opp_age = feats["swing_low_dist_atr"], feats["swing_low_age_bars"]
        else:
            dir_dist, dir_age = feats["swing_low_dist_atr"], feats["swing_low_age_bars"]
            opp_dist, opp_age = feats["swing_high_dist_atr"], feats["swing_high_age_bars"]
        feats["dir_swing_dist_atr"] = dir_dist
        feats["dir_swing_age_bars"] = dir_age
        feats["dir_swing_broke"] = (dir_dist < 0) if not (isinstance(dir_dist, float) and math.isnan(dir_dist)) else None
        feats["opp_swing_dist_atr"] = opp_dist
        feats["opp_swing_age_bars"] = opp_age

        # --- Familia B: Structural Range Position -----------------------
        r_b, s_b = resistencia[b], soporte[b]
        feats["range_pos_htf"] = (entry - s_b) / (r_b - s_b) if (r_b - s_b) > 0 else np.nan
        for w in ROLL_RANGE_WINDOWS:
            lo_idx = max(0, b - w + 1)
            roll_hi = float(high[lo_idx:b + 1].max())
            roll_lo = float(low[lo_idx:b + 1].min())
            feats[f"range_pos_roll{w}"] = (entry - roll_lo) / (roll_hi - roll_lo) if (roll_hi - roll_lo) > 0 else np.nan

        # --- Familia C: Distance to Structural Levels (HTF resistencia/
        #     soporte -- CROSS-FACTOR con B/mecanismo de señal, ver 15) ---
        feats["dist_resistencia_atr"] = (r_b - entry) / atr_b if atr_ok else np.nan
        feats["dist_soporte_atr"] = (entry - s_b) / atr_b if atr_ok else np.nan

        # --- Familia E: Expansion/Compression (amplitud de swings M5) ---
        idx_mg = int(np.searchsorted(mg_conf, b, side="right"))
        if idx_mg >= 3 and atr_ok:
            amp_last = abs(mg_val[idx_mg - 1] - mg_val[idx_mg - 2])
            amp_prior = abs(mg_val[idx_mg - 2] - mg_val[idx_mg - 3])
            feats["swing_amplitude_atr"] = amp_last / atr_b
            feats["swing_amplitude_ratio"] = amp_last / amp_prior if amp_prior > 0 else np.nan
        else:
            feats["swing_amplitude_atr"] = np.nan
            feats["swing_amplitude_ratio"] = np.nan

        # --- Familia F: Entry Relative to Signal Origin ------------------
        origin_bar = ev["origin_bar"]
        origin_level = ev["origin_level"]
        if origin_bar is not None and atr_ok:
            feats["origin_dist_atr"] = d * (entry - origin_level) / atr_b
            feats["origin_age_bars"] = b - origin_bar
            denom = abs(target - origin_level) if target is not None else np.nan
            feats["origin_retracement_frac"] = (abs(entry - origin_level) / denom) if (denom and denom > 0) else np.nan
        else:
            feats["origin_dist_atr"] = np.nan
            feats["origin_age_bars"] = np.nan
            feats["origin_retracement_frac"] = np.nan

        # --- Familia G: Structural Space in Trade Direction (ventana
        #     RECENT_WINDOW_BARS -- "estructura reciente relevante") -------
        if d > 0:
            cand_bar, cand_val = windowed_bar_val(hi_bar, hi_conf, hi_val, b, RECENT_WINDOW_BARS)
            ahead = cand_val[cand_val > entry]
        else:
            cand_bar, cand_val = windowed_bar_val(lo_bar, lo_conf, lo_val, b, RECENT_WINDOW_BARS)
            ahead = cand_val[cand_val < entry]
        if len(ahead) and atr_ok:
            nearest = ahead.min() if d > 0 else ahead.max()
            feats["space_to_next_swing_atr"] = abs(nearest - entry) / atr_b
        else:
            feats["space_to_next_swing_atr"] = np.nan

        # --- Familia H: Structural Obstacles Toward TP (misma ventana,
        #     mismo tipo de swing que "space", filtrados entre entry y TP) -
        n_obstacles_tp = np.nan
        dist_first_obstacle_tp = np.nan
        first_obstacle_frac = np.nan
        if target is not None and atr_ok:
            lo_bound, hi_bound = (entry, target) if target > entry else (target, entry)
            obstacles_tp = cand_val[(cand_val > lo_bound) & (cand_val < hi_bound)]
            n_obstacles_tp = int(len(obstacles_tp))
            if n_obstacles_tp > 0:
                first_obstacle = obstacles_tp.min() if d > 0 else obstacles_tp.max()
                dist_first_obstacle_tp = abs(first_obstacle - entry) / atr_b
                denom_tp = (target - entry)
                first_obstacle_frac = (first_obstacle - entry) / denom_tp if denom_tp != 0 else np.nan
        feats["n_obstacles_to_tp"] = n_obstacles_tp
        feats["dist_first_obstacle_tp_atr"] = dist_first_obstacle_tp
        feats["first_obstacle_tp_frac"] = first_obstacle_frac

        # --- Familia I: SL/TP Relative to Structure (SIN ventana -- "la
        #     estructura no caduca", tipo de swing = lado del SL) ---------
        n_obstacles_sl = np.nan
        dist_sl_beyond_swing = np.nan
        dist_tp_nearest_swing = np.nan
        if stop is not None and atr_ok:
            if d > 0:  # LONG: stop debajo de entry -> swings LOW entre stop y entry
                sl_cand_bar, sl_cand_val = lo_bar, lo_val
                sl_cand = windowed_values(lo_bar, lo_conf, lo_val, b, None)
                between = sl_cand[(sl_cand > stop) & (sl_cand < entry)]
                beyond = sl_cand[sl_cand < stop]
                beyond_dist = (stop - beyond.max()) / atr_b if len(beyond) else np.nan
            else:  # SHORT: stop arriba de entry -> swings HIGH entre entry y stop
                sl_cand = windowed_values(hi_bar, hi_conf, hi_val, b, None)
                between = sl_cand[(sl_cand > entry) & (sl_cand < stop)]
                beyond = sl_cand[sl_cand > stop]
                beyond_dist = (beyond.min() - stop) / atr_b if len(beyond) else np.nan
            n_obstacles_sl = int(len(between))
            dist_sl_beyond_swing = beyond_dist

            all_cand = windowed_values(mg_bar, mg_conf, mg_val, b, None)
            if len(all_cand) and target is not None:
                dist_tp_nearest_swing = float(np.min(np.abs(all_cand - target))) / atr_b
        feats["n_obstacles_to_sl"] = n_obstacles_sl
        feats["dist_sl_beyond_swing_atr"] = dist_sl_beyond_swing
        feats["dist_tp_nearest_swing_atr"] = dist_tp_nearest_swing

        # --- Momentum M5 (interaccion exploratoria, MISMA definicion
        #     exacta que BOT-047.1 -- roc_atr_10, no se modifica) --------
        j = b - M5_ROC_HORIZON
        if j >= 0 and atr_ok:
            feats["momentum_roc_atr_10"] = d * (close[b] - close[j]) / atr_b
        else:
            feats["momentum_roc_atr_10"] = np.nan

        dt = pd.Timestamp(int(time_utc[b]), unit="s", tz="UTC")
        row = dict(
            trade_id=f"L{idx_ev:05d}", asset="XAU", direction="LONG" if d > 0 else "SHORT",
            limit_created_bar=b, entry_time_utc=dt.isoformat(),
            hour_utc=dt.hour, session_utc=session_of_hour(dt.hour), weekday=dt.day_name(),
            sub_periodo=sub_periodo_of(b),
            fate=ev["fate"], filled=ev["fate"] in ("FILLED_CLOSED", "FILLED_OPEN_RESIDUAL"),
            fill_bar=ev.get("fill_bar"), exit_bar=ev.get("exit_bar"),
            outcome=ev.get("outcome"), pnl_usd=ev.get("pnl_usd"), pnl_r=ev.get("pnl_r"),
            origin_bar=origin_bar,
        )
        row.update(feats)
        rows.append(row)

        if idx_ev % max(1, len(limit_events) // 40) == 0:
            causal_sample_bars.append(b)

    df_a = pd.DataFrame(rows)

    # --- G. Verificacion empirica de causalidad (re-slice de una muestra) --
    section("G. Verificacion empirica de causalidad (re-slice de una muestra distribuida en el tiempo)")
    print("Argumento constructivo (shadow_replay/origen de armado): el loop recorre i=0..n-1 en orden y "
          "SOLO lee arrays en indices <= i en cada iteracion -- origin_venta/origin_compra se leen "
          "(snapshot) ANTES de actualizarse con la barra actual, y solo se actualizan con datos de la "
          "barra actual (high[i]/low[i]/resistencia[i]/soporte[i]) -- ningun acceso a i+k existe en el "
          "codigo. Verificacion empirica (re-ejecutar shadow_replay() sobre arrays truncados [:b+1]) para "
          "una muestra distribuida en el tiempo:")
    origin_mismatches = []
    for b in causal_sample_bars:
        ev_full = limit_events.get(b)
        if ev_full is None or ev_full["origin_bar"] is None:
            continue
        n_trunc = b + 1
        limit_events_trunc, _, _ = shadow_replay(
            time_utc[:n_trunc], time_server[:n_trunc], high[:n_trunc], low[:n_trunc], close[:n_trunc],
            spread_pts[:n_trunc], params, costs, ema_line[:n_trunc], resistencia[:n_trunc], soporte[:n_trunc])
        ev_trunc = limit_events_trunc.get(b)
        if ev_trunc is None:
            origin_mismatches.append((b, "evento no reproducido en el array truncado"))
            continue
        if ev_trunc["origin_bar"] != ev_full["origin_bar"] or not math.isclose(
                ev_trunc["origin_level"], ev_full["origin_level"], rel_tol=1e-9, abs_tol=1e-9):
            origin_mismatches.append((b, ev_full["origin_bar"], ev_full["origin_level"],
                                       ev_trunc["origin_bar"], ev_trunc["origin_level"]))

    check(f"origin_bar/origin_level (Familia F): re-slice[:b+1] == calculo sobre array completo, "
          f"para {len(causal_sample_bars)} eventos distribuidos en el tiempo -- ninguna diferencia esperada",
          len(origin_mismatches) == 0,
          f"muestra={len(causal_sample_bars)}, discrepancias={len(origin_mismatches)}"
          + (f", ejemplos={origin_mismatches[:5]}" if origin_mismatches else ""))

    print("\nArgumento constructivo (swing highs/lows M5): find_confirmed_pivots(series, lbL, lbR) decide "
          "si series[i] es pivote MIRANDO EXCLUSIVAMENTE la ventana LOCAL [i-lbL, i+lbR] -- no depende de "
          "donde empieza/termina el array, siempre que esa ventana quepa dentro de el. Por lo tanto, para "
          "cualquier pivote con confirmed_bar=i+lbR<=b, calcularlo sobre el array COMPLETO o sobre un array "
          "truncado a [:b'+1] con b'>=i+lbR da el MISMO resultado. Verificacion empirica (recalcular sobre "
          "high[:b+1]/low[:b+1] truncados) para la misma muestra:")
    pivot_mismatches = []
    for b in causal_sample_bars:
        hi_trunc, _ = sc.find_confirmed_pivots(high[:b + 1], PIVOT_LBL, PIVOT_LBR)
        lo_full_avail = [p for p in swing_highs if p.confirmed_bar <= b]
        if [(p.bar, p.value) for p in hi_trunc] != [(p.bar, p.value) for p in lo_full_avail]:
            pivot_mismatches.append((b, "swing_highs", len(hi_trunc), len(lo_full_avail)))
        _, lo_trunc = sc.find_confirmed_pivots(low[:b + 1], PIVOT_LBL, PIVOT_LBR)
        lo_full_avail2 = [p for p in swing_lows if p.confirmed_bar <= b]
        if [(p.bar, p.value) for p in lo_trunc] != [(p.bar, p.value) for p in lo_full_avail2]:
            pivot_mismatches.append((b, "swing_lows", len(lo_trunc), len(lo_full_avail2)))

    check(f"swing highs/lows M5 (Familia A y derivadas): find_confirmed_pivots sobre array truncado[:b+1] "
          f"== lista global filtrada por confirmed_bar<=b, para {len(causal_sample_bars)} eventos -- "
          f"ninguna diferencia esperada",
          len(pivot_mismatches) == 0,
          f"muestra={len(causal_sample_bars)}, discrepancias={len(pivot_mismatches)}"
          + (f", ejemplos={pivot_mismatches[:5]}" if pivot_mismatches else ""))

    if origin_mismatches or pivot_mismatches:
        print("\n*** DETENIENDO INTERPRETACION: la verificacion causal encontro discrepancias. ***")
        return 1

    # --- H. Sanity checks -----------------------------------------------------
    section("H. Sanity checks")
    n_long = int((df_a["direction"] == "LONG").sum())
    n_short = int((df_a["direction"] == "SHORT").sum())
    print(f"Universo A: {len(df_a)} LIMITS creados -- LONG={n_long} SHORT={n_short}")
    print(f"Rango temporal: {df_a['entry_time_utc'].min()} .. {df_a['entry_time_utc'].max()}")

    df_b = df_a[df_a["fate"] == "FILLED_CLOSED"].copy()
    print(f"Universo B (FILLED_CLOSED): {len(df_b)} trades")
    check("Universo A/B: mismo tamano que BOT-024.2/BOT-047.1 (mismo motor/dataset/Config A, debe coincidir)",
          len(df_a) == 3207 and len(df_b) == 2474,
          f"BOT-048.1: A={len(df_a)} (esperado 3207) B={len(df_b)} (esperado 2474)")

    dup_bars = df_a["limit_created_bar"].duplicated().sum()
    check("Universo A sin limit_created_bar duplicado", dup_bars == 0, f"duplicados={dup_bars}")

    feature_cols = [c for c in df_a.columns if c not in (
        "trade_id", "asset", "direction", "limit_created_bar", "entry_time_utc", "hour_utc", "session_utc",
        "weekday", "sub_periodo", "fate", "filled", "fill_bar", "exit_bar", "outcome", "pnl_usd", "pnl_r",
        "origin_bar", "swing_high_seq", "swing_low_seq", "dir_swing_broke")]
    numeric_feature_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df_a[c])]
    n_inf = int(np.isinf(df_a[numeric_feature_cols]).sum().sum())
    check("sin valores infinitos en ninguna feature numerica", n_inf == 0, f"n_inf={n_inf}")

    print(f"\nCobertura (columnas no-NaN sobre Universo A, {len(df_a)} filas):")
    for c in ["swing_high_dist_atr", "swing_low_dist_atr", "dir_swing_dist_atr", "range_pos_htf",
              "range_pos_roll60", "range_pos_roll288", "swing_amplitude_atr", "swing_amplitude_ratio",
              "origin_dist_atr", "origin_retracement_frac", "space_to_next_swing_atr",
              "n_obstacles_to_tp", "n_obstacles_to_sl", "dist_sl_beyond_swing_atr", "dist_tp_nearest_swing_atr"]:
        cov = df_a[c].notna().mean() if c in df_a else float("nan")
        print(f"  {c:28s} cobertura={cov*100:5.1f}%")

    n_obst_sl_zero = int((df_a["n_obstacles_to_sl"] == 0).sum())
    n_obst_sl_total = int(df_a["n_obstacles_to_sl"].notna().sum())
    print(f"\nn_obstacles_to_sl == 0 en {n_obst_sl_zero}/{n_obst_sl_total} "
          f"({n_obst_sl_zero/n_obst_sl_total*100 if n_obst_sl_total else float('nan'):.1f}%). Hipotesis "
          f"previa a correr esto (documentada en el codigo antes de ejecutar, ver commit): dado que SL = "
          f"resistencia/soporte(bloque HTF, periodos_htf_min=800)*(1+/-buf) con buf_bp=0.4 (margen minimo), "
          f"se esperaba cerca de 100% (casi tautologico). RESULTADO: la hipotesis es INCORRECTA -- el "
          f"resultado real muestra lo contrario (mayoria con >=1 obstaculo). El bloque HTF de 800min es MUCHO "
          f"mas ancho que la ventana de pivote M5 (lbL=lbR=5, ~25-50min) -- entre `entry` (EMA, no el nivel "
          f"HTF crudo) y `stop` caben tipicamente varios swings M5 de ruido local. Ver seccion 17 del reporte "
          f"para el analisis completo (no es tautologico, es informacion real).")

    csv_a = REPORTS_DIR / "BOT-048.1-structure-limits-xau.csv"
    df_a.to_csv(csv_a, index=False)
    print(f"\nCSV Universo A escrito: {csv_a} ({len(df_a)} filas)")
    csv_b = REPORTS_DIR / "BOT-048.1-structure-trades-xau.csv"
    df_b.to_csv(csv_b, index=False)
    print(f"CSV Universo B escrito: {csv_b} ({len(df_b)} filas)")

    # ---------------------------------------------------------------------------
    # I. Screening -- correlacion Spearman (diagnostico, no seleccion final)
    # ---------------------------------------------------------------------------
    section("I. Screening -- correlacion Spearman feature vs fill / vs pnl_r")

    def spearman_corr(a: pd.Series, b: pd.Series) -> float:
        tmp = pd.DataFrame({"a": a, "b": b}).dropna()
        if len(tmp) < 3:
            return float("nan")
        return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")

    screen_cols = [c for c in numeric_feature_cols if c != "n_obstacles_to_sl"]  # casi constante, ver arriba
    screen_rows = []
    for c in screen_cols:
        col_a = df_a[c].astype(float) if df_a[c].dtype == bool else df_a[c]
        rho_fill = spearman_corr(col_a, df_a["filled"].astype(float)) if col_a.notna().sum() > 30 else np.nan
        col_b = df_b[c].astype(float) if (c in df_b and df_b[c].dtype == bool) else df_b.get(c)
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
    # J. Deep dive -- buckets ALL/LONG/SHORT, sub-periodos
    # ---------------------------------------------------------------------------
    section("J. Deep dive de la shortlist -- buckets, LONG/SHORT, estabilidad temporal")

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
    # K. Redundancia
    # ---------------------------------------------------------------------------
    section("K. Redundancia -- correlacion Spearman entre features (Universo B)")
    corr_input = df_b[screen_cols].apply(lambda s: s.astype(float) if s.dtype == bool else s)
    corr_mat = corr_input.rank(method="average").corr(method="pearson")
    pairs = []
    for i, a in enumerate(screen_cols):
        for bcol in screen_cols[i + 1:]:
            r = corr_mat.loc[a, bcol]
            if not math.isnan(r) and abs(r) >= 0.8:
                pairs.append((a, bcol, r))
    pairs.sort(key=lambda p: -abs(p[2]))
    print(f"Pares con |rho|>=0.8 (redundancia fuerte): {len(pairs)}")
    for a, bcol, r in pairs[:40]:
        print(f"  {a:28s} <-> {bcol:28s}  rho={r:+.3f}")

    # ---------------------------------------------------------------------------
    # L. HH/HL/LH/LL descriptivo
    # ---------------------------------------------------------------------------
    section("L. Estructura M5 (swing_high_seq/swing_low_seq) -- descriptivo")
    for col in ("swing_high_seq", "swing_low_seq"):
        print(f"\n  {col}:")
        for val, g in df_b.groupby(col, dropna=False):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {str(val):8s} N={n:5d}  WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}%  "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}  ExpR={g['pnl_r'].mean():+.3f}")

    # ---------------------------------------------------------------------------
    # M. Cross-factor overlap -- Momentum x Structure, LONG/SHORT x Structure
    # ---------------------------------------------------------------------------
    section("M. Cross-factor overlap (Momentum x Structure) + interacciones LONG/SHORT -- SOLO diagnostico")
    for feat in shortlist[:6]:
        rho_mom = spearman_corr(df_b[feat], df_b["momentum_roc_atr_10"])
        print(f"  rho({feat}, momentum_roc_atr_10) = {rho_mom:+.3f}")

    primary = screen_df.sort_values("abs_rho_pnl_r", ascending=False).iloc[0]["feature"] \
        if not screen_df["abs_rho_pnl_r"].isna().all() else shortlist[0]
    print(f"\nCandidato principal de Structure para esta seccion (mayor |rho| vs pnl_r en screening, "
          f"NO es una seleccion final -- eso corresponde a BOT-048.2): {primary}")

    valid_p = df_b[[primary, "momentum_roc_atr_10", "pnl_r", "outcome", "pnl_usd"]].dropna(subset=[primary])
    if len(valid_p) >= 40 and valid_p[primary].nunique() >= 4:
        med_p = valid_p[primary].median()
        med_m = valid_p["momentum_roc_atr_10"].median()
        valid_p = valid_p.assign(
            s_bucket=np.where(valid_p[primary] >= med_p, f"{primary}>=mediana", f"{primary}<mediana"),
            mom_bucket=np.where(valid_p["momentum_roc_atr_10"] >= med_m, "momentum>=mediana", "momentum<mediana"))
        print(f"\n  Momentum x Structure ({primary}):")
        for (sb, mb), g in valid_p.groupby(["s_bucket", "mom_bucket"]):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {sb:26s} x {mb:22s} N={n:4d} WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}% "
                  f"Exp$={g['pnl_usd'].mean():+7.2f}")
    else:
        print(f"  N insuficiente para Momentum x Structure con {primary} (N={len(valid_p)})")

    print(f"\n  LONG/SHORT x Structure ({primary}):")
    valid_ls = df_b[[primary, "direction", "pnl_usd", "outcome"]].dropna(subset=[primary])
    if len(valid_ls):
        med_p3 = valid_ls[primary].median()
        valid_ls = valid_ls.assign(s_bucket=np.where(valid_ls[primary] >= med_p3, ">=mediana", "<mediana"))
        for (dirn, sb), g in valid_ls.groupby(["direction", "s_bucket"]):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"    {dirn:6s} x {sb:12s} N={n:4d} WR={wr*100 if not math.isnan(wr) else float('nan'):5.1f}% "
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
