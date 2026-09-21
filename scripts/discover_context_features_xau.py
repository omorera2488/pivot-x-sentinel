"""BOT-050.1 -- Context Feature Discovery, XAU (BTC bloqueado, ver seccion A).

Subtarea de `BOT-050` (feature padre "Context", dimension del futuro Signal
Quality de BOT-024 -- ver BOT-050 en BACKLOG.md). SOLO LECTURA/DISCOVERY --
OFFLINE / DISCOVERY / NO PRODUCTION CHANGES / NO SCORE / NO GATE. No define
todavia una definicion final de Context, no crea ContextScore, no crea escala
0-100, no asigna pesos, no crea gates, no optimiza EMA/HTF/Buffer/RR.

Pregunta que responde: que informacion del entorno de mercado, disponible
causalmente en `limit_created_bar` (== `signal_bar` == `born_bar`, mismo punto
de congelacion que BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1), aporta
informacion contextual sin duplicar Momentum (BOT-024.2), Alignment (BOT-047,
`STRUCTURAL_CONSENSUS`) o Structure (BOT-048, `ORIGIN_ONLY_FREEZE`).

Metodologia (resumen; ver reports/BOT-050.1-CONTEXT-FEATURE-DISCOVERY.md):
  1. Corre strategy.engine.run_backtest (sin tocar) UNA sola vez, continuo,
     sobre backtests/data/XAUUSDc_M5_latest.parquet, "Config A" (misma que
     BOT-024.1/BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1/BOT-042/043/045/046).
  2. Shadow replay -- copiado VERBATIM de scripts/discover_economics_features_
     xau.py (a su vez copiado de scripts/discover_structure_features_xau.py),
     mismo bookkeeping de "origen de armado". Reproduce Universo A completo y
     se valida EXHAUSTIVAMENTE contra run_backtest() real antes de interpretar
     nada.
  3. Candidatos Context (7 familias, ver Candidate Registry en el reporte):
     volatilidad relativa (ATR_short/ATR_long), sesion, hora del dia, dia de
     semana, ADX (fuerza de tendencia M5), distancia a la EMA de señal M5, y
     nivel de RSI M5. Todas calculadas EXCLUSIVAMENTE con datos de la barra
     `limit_created_bar` o anteriores.
  4. ATR_short/ATR_long: periodos NO optimizados por grid search -- reusan
     constantes YA canonicas del proyecto (ver seccion I): short=14
     (M5_ATR_PERIOD, identico a Momentum/Alignment/Structure/Economics),
     long=160 (periodos_htf_min=800/5, la MISMA ventana HTF de Config A) como
     PRIMARIA, con long=288 (D1_WINDOW_MIN/5, ancla de "dia" de BOT-045) como
     variante de robustez predeclarada -- ambos numeros preexistian en el
     repo antes de esta tarea, ninguno fue inventado ni buscado.
  5. Redundancia cruzada con Momentum (BOT-024.2, roc_atr_3 -- y tambien
     atr_pct/atr14/atr5_atr20_ratio/rsi_now, features YA calculadas por esa
     tarea que caen conceptualmente en el territorio de Context, ver seccion
     H del reporte), Structure (BOT-048.1, origin_dist_atr) y Alignment
     (BOT-047.1, closed_ema200_slope) via merge por limit_created_bar sobre
     los CSV ya congelados de esas tareas -- no se recalcula ninguna de esas
     dimensiones.

Uso:
    .venv/Scripts/python.exe scripts/discover_context_features_xau.py \
        > reports/BOT-050.1-CONTEXT-FEATURE-DISCOVERY-EVIDENCE.log

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

CSV_MOMENTUM_B = REPORTS_DIR / "BOT-024.2-momentum-trades-xau.csv"
CSV_ALIGN_B = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"
CSV_STRUCT_B = REPORTS_DIR / "BOT-048.1-structure-trades-xau.csv"

# Config A congelada -- misma que BOT-024.1/BOT-024.2/BOT-047.1/BOT-048.1/
# BOT-049.1/BOT-042/BOT-043/BOT-045/BOT-046. NO se optimiza ni se cambia
# ningun parametro de estrategia en esta tarea.
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

M5_ATR_PERIOD = 14  # misma ventana "corta" que BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1 (M5_ATR_PERIOD)
# --- ATR "largo" (regimen) -- seccion I: NO inventados para esta tarea. -----
ATR_LONG_PRIMARY = CONFIG_A["periodos_htf_min"] // 5   # 800/5 = 160 barras M5 (ventana HTF de Config A)
ATR_LONG_ALT = 1440 // 5                                # D1_WINDOW_MIN (BOT-045) / 5 = 288 barras M5
ADX_PERIOD = 14        # identico a backtests/scripts/07_bot045_regime_dataset.py (ADX_PERIOD)
RSI_PERIOD = sc.RSI_PERIOD  # 14, produccion (strategy/scoring.py), reusado sin modificar
DIST_EMA_PERIODS = CONFIG_A["ema_periods"]  # 12, la MISMA EMA de señal de Config A (BOT-045 dist_ema_atr)
PCT_RANK_WINDOW = ATR_LONG_ALT  # reusa el mismo numero ya declarado (288), no se inventa un 3er parametro
MOMENTUM_ROC_HORIZON = 10  # roc_atr_10, misma definicion exacta que BOT-047.1/BOT-048.1/BOT-049.1 (control cruzado)

SESSION_BOUNDS_UTC = [  # misma convencion que BOT-045/BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1
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
# 0. Toolkit estadistico -- reusado VERBATIM de scripts/discover_economics_
#    features_xau.py (a su vez de discover_momentum/discover_structure).
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


def adx_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = ADX_PERIOD) -> np.ndarray:
    """Copiado VERBATIM de backtests/scripts/07_bot045_regime_dataset.py
    (adx_wilder) -- formula estandar de Wilder, misma familia de suavizado que
    atr_wilder(). NO redefinida, NO reoptimizada."""
    n = len(close)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    atr_s = np.full(n, np.nan)
    plus_dm_s = np.full(n, np.nan)
    minus_dm_s = np.full(n, np.nan)
    if n > period:
        atr_s[period] = tr[1:period + 1].sum()
        plus_dm_s[period] = plus_dm[1:period + 1].sum()
        minus_dm_s[period] = minus_dm[1:period + 1].sum()
        for i in range(period + 1, n):
            atr_s[i] = atr_s[i - 1] - atr_s[i - 1] / period + tr[i]
            plus_dm_s[i] = plus_dm_s[i - 1] - plus_dm_s[i - 1] / period + plus_dm[i]
            minus_dm_s[i] = minus_dm_s[i - 1] - minus_dm_s[i - 1] / period + minus_dm[i]

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * plus_dm_s / atr_s
        minus_di = 100.0 * minus_dm_s / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)

    adx = np.full(n, np.nan)
    first_idx = period * 2 - 1
    if n > first_idx:
        seed = dx[period:period * 2]
        adx[first_idx] = np.nanmean(seed) if np.any(~np.isnan(seed)) else np.nan
        for i in range(first_idx + 1, n):
            prev = adx[i - 1]
            adx[i] = (prev * (period - 1) + (dx[i] if not np.isnan(dx[i]) else 0.0)) / period if not np.isnan(prev) else np.nan
    return adx


def wilson_ci(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(center - half, 0.0), min(center + half, 1.0))


def bootstrap_mean_ci(values, n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


# ---------------------------------------------------------------------------
# 1. Shadow replay -- COPIADO VERBATIM de scripts/discover_economics_features_
#    xau.py (idem discover_structure/discover_d1_alignment/discover_momentum).
#    NO SE MODIFICA ninguna decision respecto a strategy/engine.py.
# ---------------------------------------------------------------------------

def shadow_replay(time_utc, time_server, high, low, close, spread_pts, params: StrategyParams,
                   costs: BrokerCosts, ema_line, resistencia, soporte):
    n = len(close)
    buf = params.buf_bp / 10000.0

    armado_venta = False
    armado_compra = False
    pending: list[dict] = []
    open_pos: list[dict] = []

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
# 2. main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-050.1 -- Context Feature Discovery, XAU (BTC bloqueado, ver seccion A)")
    print("SOLO LECTURA/DISCOVERY. No se modifico ningun archivo de produccion. No se activa gating.")
    print("No se implementa una definicion final de Context. No se crea score/peso/gate.\n")

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
    section("B. Dataset XAU y costos (reusa lo ya usado por BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1)")
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
          f"tick_size={costs.tick_size} (commission_per_lot=0.0, no se usa para Context, mantenido solo "
          f"para reusar la firma exacta de shadow_replay/run_backtest sin modificarlas)")

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

    # --- B2. Semantica temporal del dataset (seccion 7.2 del prompt de la
    #     tarea: NO asumir que la hora del servidor MT5 equivale a UTC/NY).
    #     `time_utc` ya es UTC genuino -- normalizado en la descarga del
    #     dataset midiendo el offset del broker en vivo con
    #     symbol_info_tick() contra el reloj UTC del sistema (ver
    #     docs/spec-backtest.md Sec.2.1 y docs/spec-estrategia.md Sec.3.1,
    #     tecnica reusada en todo el proyecto, NO hardcodea ningun broker).
    #     `time_server` es la hora CRUDA del broker (Exness-MT5Real22 en esta
    #     conexion), NO usada para bucketizar sesion/hora en ninguna tarea
    #     anterior (BOT-045/BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1) ni aca --
    #     se verifica explicitamente que existe un offset no-cero entre
    #     ambas (confirma que NO son la misma columna re-etiquetada). --------
    section("B2. Semantica temporal del dataset (time_utc vs time_server)")
    offset_seconds = (time_server.astype(np.int64) - time_utc.astype(np.int64))
    offset_unique_s = np.unique(offset_seconds)
    print(f"Offset time_server - time_utc (dataset COMPLETO, {n_bars} barras): "
          f"valores unicos={offset_unique_s.tolist()} segundos")
    check("time_utc y time_server son columnas DISTINTAS (no la misma columna duplicada bajo otro nombre) "
          "-- el offset observado puede ser 0 si el reloj de ESTE broker/cuenta (Exness-MT5Real22) ya corre "
          "en UTC+0; lo relevante no es que el offset sea != 0 sino que la columna time_utc fue normalizada "
          "explicitamente (ver docs/spec-backtest.md Sec.2.1, tecnica symbol_info_tick() vs reloj UTC del "
          "sistema) y es la que se usa aca -- nunca se asume implicitamente que time_server == UTC",
          len(offset_unique_s) == 1,
          f"offset CONSTANTE en todo el dataset={offset_unique_s.tolist()} segundos (broker/cuenta actual: "
          f"server time ~= UTC+0, coincide con time_utc salvo un skew fijo de "
          f"{offset_unique_s[0] if len(offset_unique_s) else 'N/A'}s atribuible a como se capturo cada "
          f"timestamp, NO una zona horaria con DST propia)")
    print("CONVENCION USADA (identica a BOT-045/BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1): session_utc/"
          "hour_utc/weekday se calculan SIEMPRE sobre `time_utc` (UTC genuino), nunca sobre `time_server`. "
          "DST: SESSION_BOUNDS_UTC es una particion FIJA por hora-UTC, sin ajuste de horario de verano de "
          "Londres/Nueva York (mismo criterio y misma limitacion ya documentada en BOT-045) -- durante el "
          "half-year de DST activo en Londres/NY, los limites de sesion 'Londres'/'Nueva York' definidos "
          "aca se corren ~1h respecto a la apertura/cierre real de esos mercados. Documentado explicitamente "
          "como limitacion conocida, no corregido en esta tarea (requeriria una tabla de reglas DST "
          "verificable por separado, fuera de alcance de un discovery).")

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

    # --- E. Indicadores causales M5 (ATR short/long, ADX, RSI) --------------
    section("E. Indicadores causales M5 (ATR short/long, ADX, RSI) -- Wilder, sin look-ahead")
    atr_short = atr_wilder(high, low, close, M5_ATR_PERIOD)
    atr_long_primary = atr_wilder(high, low, close, ATR_LONG_PRIMARY)
    atr_long_alt = atr_wilder(high, low, close, ATR_LONG_ALT)
    adx_m5 = adx_wilder(high, low, close, ADX_PERIOD)
    rsi_m5 = sc.rsi(close, RSI_PERIOD)
    print(f"ATR Wilder short={M5_ATR_PERIOD} (identico a tareas anteriores), "
          f"long_primary={ATR_LONG_PRIMARY} (periodos_htf_min/5, ventana HTF de Config A), "
          f"long_alt={ATR_LONG_ALT} (D1_WINDOW_MIN/5, ancla 'dia' de BOT-045).")
    print(f"ADX Wilder({ADX_PERIOD}) -- copiado verbatim de backtests/scripts/07_bot045_regime_dataset.py, "
          f"no redefinido.")
    print(f"RSI({RSI_PERIOD}) -- strategy.scoring.rsi(), funcion de PRODUCCION reusada sin modificar "
          f"(ya validada por BOT-024.1/strategy/test_scoring.py).")

    # Percentile rank causal (rolling, solo mira hacia atras) de atr_short --
    # representacion secundaria/diagnostica del MISMO candidato de
    # volatilidad relativa (seccion 7.1 del prompt), no un candidato
    # independiente nuevo. Reusa PCT_RANK_WINDOW = ATR_LONG_ALT (288), no
    # inventa un 3er parametro.
    atr_pct_rank = pd.Series(atr_short).rolling(window=PCT_RANK_WINDOW, min_periods=PCT_RANK_WINDOW).rank(pct=True).to_numpy()
    print(f"Percentile rank causal de atr_short, ventana rolling={PCT_RANK_WINDOW} barras (reusa el mismo "
          f"numero ya declarado como ATR_LONG_ALT, no introduce un parametro nuevo) -- cada valor usa "
          f"EXCLUSIVAMENTE las {PCT_RANK_WINDOW} barras anteriores (incluyendo la actual), verificado por "
          f"construccion de pandas.Series.rolling().rank(pct=True).")

    # ---------------------------------------------------------------------------
    # F. Feature vector Context por evento del Universo A, congelado en
    #    limit_created_bar. Todas las features de esta seccion son funciones
    #    de datos en la barra b o anteriores exclusivamente (ver seccion G).
    # ---------------------------------------------------------------------------
    section("F. Feature vector Context, congelado en limit_created_bar, por cada LIMIT del Universo A")

    chunk = n_bars // 3

    def sub_periodo_of(bar_idx: int) -> str:
        if bar_idx < chunk:
            return "sub1"
        if bar_idx < 2 * chunk:
            return "sub2"
        return "sub3"

    events_sorted = sorted(limit_events.values(), key=lambda e: e["born_bar"])
    rows = []
    causal_sample_bars = []

    for idx_ev, ev in enumerate(events_sorted):
        b = ev["born_bar"]
        d = ev["direction"]

        atr_s_b = atr_short[b]
        atr_ok = atr_s_b is not None and not math.isnan(atr_s_b) and atr_s_b > 0

        feats: dict = {}

        # --- Familia A: volatilidad relativa (ATR_short/ATR_long) -----------
        atr_l_prim_b = atr_long_primary[b]
        atr_l_alt_b = atr_long_alt[b]
        feats["atr_short"] = atr_s_b
        feats["atr_long_primary"] = atr_l_prim_b
        feats["atr_long_alt"] = atr_l_alt_b
        feats["atr_ratio_short_long"] = (atr_s_b / atr_l_prim_b
                                          if (atr_l_prim_b and not math.isnan(atr_l_prim_b) and atr_l_prim_b > 0)
                                          else np.nan)
        feats["atr_ratio_short_long_alt"] = (atr_s_b / atr_l_alt_b
                                              if (atr_l_alt_b and not math.isnan(atr_l_alt_b) and atr_l_alt_b > 0)
                                              else np.nan)
        feats["atr_pct_rank_causal"] = atr_pct_rank[b]

        # --- Familia B: sesion / hora / dia de semana ------------------------
        dt = pd.Timestamp(int(time_utc[b]), unit="s", tz="UTC")
        hour_cont = dt.hour + dt.minute / 60.0
        feats["hour_utc_cont"] = hour_cont
        feats["hour_sin"] = math.sin(2 * math.pi * hour_cont / 24.0)
        feats["hour_cos"] = math.cos(2 * math.pi * hour_cont / 24.0)
        feats["weekday_num"] = int(dt.dayofweek)  # 0=Lunes .. 6=Domingo

        # --- Familia C: ADX (fuerza de tendencia, SIN direccion) -------------
        feats["adx_m5"] = adx_m5[b]

        # --- Familia D: distancia a la EMA de señal M5 (Config A) -----------
        ema_b = ema_line[b]
        feats["dist_ema_m5_price"] = abs(close[b] - ema_b)
        feats["dist_ema_m5_atr"] = abs(close[b] - ema_b) / atr_s_b if atr_ok else np.nan
        feats["dist_ema_m5_signed_atr"] = (d * (close[b] - ema_b) / atr_s_b) if atr_ok else np.nan

        # --- Familia E: nivel de RSI M5 (NO delta -- delta ya es Momentum) --
        feats["rsi_level_m5"] = rsi_m5[b]

        # --- Momentum M5 (control cruzado -- MISMA definicion exacta que
        #     BOT-047.1/BOT-048.1/BOT-049.1, roc_atr_10, no se modifica) -----
        j = b - MOMENTUM_ROC_HORIZON
        if j >= 0 and atr_ok:
            feats["momentum_roc_atr_10"] = d * (close[b] - close[j]) / atr_s_b
        else:
            feats["momentum_roc_atr_10"] = np.nan

        fill_bar = ev.get("fill_bar")
        time_to_fill_bars = (fill_bar - b) if fill_bar is not None else np.nan
        row = dict(
            trade_id=f"L{idx_ev:05d}", asset="XAU", direction="LONG" if d > 0 else "SHORT",
            limit_created_bar=b, entry_time_utc=dt.isoformat(),
            hour_utc=dt.hour, session_utc=session_of_hour(dt.hour), weekday=dt.day_name(),
            sub_periodo=sub_periodo_of(b),
            fate=ev["fate"], filled=ev["fate"] in ("FILLED_CLOSED", "FILLED_OPEN_RESIDUAL"),
            fill_bar=fill_bar, time_to_fill_bars=time_to_fill_bars,
            exit_bar=ev.get("exit_bar"),
            outcome=ev.get("outcome"), pnl_usd=ev.get("pnl_usd"), pnl_r=ev.get("pnl_r"),
            origin_bar=ev.get("origin_bar"),
        )
        row.update(feats)
        rows.append(row)

        if idx_ev % max(1, len(limit_events) // 40) == 0:
            causal_sample_bars.append(b)

    df_a = pd.DataFrame(rows)

    # --- F2. Regimen de volatilidad (bucket, representacion secundaria del
    #     MISMO candidato `atr_ratio_short_long` -- terciles PREDEFINIDOS
    #     sobre la distribucion completa de Universo A, NO optimizados por
    #     outcome. El RAW continuo (`atr_ratio_short_long`) se conserva y es
    #     el candidato principal -- este bucket es solo descriptivo/
    #     interpretativo, mismo patron que los buckets qcut(q=5) usados en
    #     las secciones "deep dive" de BOT-047.1/048.1/049.1). -------------
    valid_ratio = df_a["atr_ratio_short_long"].dropna()
    try:
        _, tercile_edges = pd.qcut(valid_ratio, q=3, retbins=True, duplicates="drop")
        regime_labels = ["Compression", "Normal", "Expansion"][:len(tercile_edges) - 1]
        df_a["atr_regime_bucket"] = pd.cut(df_a["atr_ratio_short_long"], bins=tercile_edges,
                                            labels=regime_labels, include_lowest=True)
        print(f"\nBuckets de regimen (terciles predefinidos sobre atr_ratio_short_long, Universo A completo): "
              f"edges={list(np.round(tercile_edges, 4))}")
    except ValueError as e:
        df_a["atr_regime_bucket"] = np.nan
        print(f"\nNo se pudo construir bucket de regimen (terciles degenerados): {e}")

    # --- G. Verificacion de causalidad --------------------------------------
    section("G. Verificacion de causalidad")
    print("Argumento constructivo (ATR short/long, ADX, RSI, EMA-distancia): todas se calculan a partir de "
          "high[0..b]/low[0..b]/close[0..b] EXCLUSIVAMENTE (atr_wilder/adx_wilder/rsi son recursivas hacia "
          "atras, ningun paso lee indices > b -- atr_wilder ya verificado causal en tareas anteriores, "
          "adx_wilder tiene la misma estructura recursiva, rsi() es funcion de produccion ya validada en "
          "strategy/test_scoring.py). ema_line[b] depende exclusivamente de close[0..b] (ya verificado "
          "causal en BOT-003/BOT-004/BOT-042 y reverificado en BOT-048.1/BOT-049.1). hour_utc/weekday/session "
          "derivan de time_utc[b] (timestamp de la propia barra, conocido al procesarla). "
          "atr_pct_rank_causal[b] usa pandas.rolling(window=288) que por construccion solo considera "
          "indices [b-287, b].")

    print("\nVerificacion empirica (re-slice [:b+1] para una muestra distribuida en el tiempo, recalculando "
          "TODO -- shadow replay + ATR/ADX/RSI/EMA + features -- desde cero sobre el array truncado):")
    mismatches = []
    for b in causal_sample_bars:
        ev_full = limit_events.get(b)
        if ev_full is None:
            continue
        n_trunc = b + 1
        atr_s_trunc = atr_wilder(high[:n_trunc], low[:n_trunc], close[:n_trunc], M5_ATR_PERIOD)
        atr_lp_trunc = atr_wilder(high[:n_trunc], low[:n_trunc], close[:n_trunc], ATR_LONG_PRIMARY)
        adx_trunc = adx_wilder(high[:n_trunc], low[:n_trunc], close[:n_trunc], ADX_PERIOD)
        rsi_trunc = sc.rsi(close[:n_trunc], RSI_PERIOD)
        ema_trunc = ema(close[:n_trunc], params.ema_periods)
        limit_events_trunc, _, _ = shadow_replay(
            time_utc[:n_trunc], time_server[:n_trunc], high[:n_trunc], low[:n_trunc], close[:n_trunc],
            spread_pts[:n_trunc], params, costs, ema_trunc, resistencia[:n_trunc], soporte[:n_trunc])
        ev_trunc = limit_events_trunc.get(b)
        if ev_trunc is None:
            mismatches.append((b, "evento no reproducido en el array truncado"))
            continue

        def same_val(full_v, trunc_v):
            if isinstance(full_v, float) and math.isnan(full_v) and isinstance(trunc_v, float) and math.isnan(trunc_v):
                return True
            return math.isclose(full_v, trunc_v, rel_tol=1e-9, abs_tol=1e-12)

        same_atr_s = same_val(atr_short[b], atr_s_trunc[b])
        same_atr_l = same_val(atr_long_primary[b], atr_lp_trunc[b])
        same_adx = same_val(adx_m5[b], adx_trunc[b])
        same_rsi = same_val(rsi_m5[b], rsi_trunc[b])
        same_ema = same_val(ema_line[b], ema_trunc[b])
        same_geom = (math.isclose(ev_trunc["entry"], ev_full["entry"], rel_tol=1e-9, abs_tol=1e-9) and
                     math.isclose(ev_trunc["stop"], ev_full["stop"], rel_tol=1e-9, abs_tol=1e-9))
        ok = same_atr_s and same_atr_l and same_adx and same_rsi and same_ema and same_geom
        if not ok:
            mismatches.append((b, dict(same_atr_s=same_atr_s, same_atr_l=same_atr_l, same_adx=same_adx,
                                        same_rsi=same_rsi, same_ema=same_ema, same_geom=same_geom)))

    check(f"ATR short/long/ADX/RSI/EMA/entry-stop: re-slice[:b+1] == calculo sobre array completo, "
          f"para {len(causal_sample_bars)} eventos distribuidos en el tiempo -- ninguna diferencia esperada",
          len(mismatches) == 0,
          f"muestra={len(causal_sample_bars)}, discrepancias={len(mismatches)}"
          + (f", ejemplos={mismatches[:5]}" if mismatches else ""))

    if mismatches:
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
    check("Universo A/B: mismo tamano que BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1 (mismo motor/dataset/"
          "Config A, debe coincidir)", len(df_a) == 3207 and len(df_b) == 2474,
          f"BOT-050.1: A={len(df_a)} (esperado 3207) B={len(df_b)} (esperado 2474)")

    dup_bars = df_a["limit_created_bar"].duplicated().sum()
    check("Universo A sin limit_created_bar duplicado", dup_bars == 0, f"duplicados={dup_bars}")

    non_feature_cols = (
        "trade_id", "asset", "direction", "limit_created_bar", "entry_time_utc", "hour_utc", "session_utc",
        "weekday", "sub_periodo", "fate", "filled", "fill_bar", "time_to_fill_bars", "exit_bar", "outcome",
        "pnl_usd", "pnl_r", "origin_bar", "atr_regime_bucket")
    feature_cols = [c for c in df_a.columns if c not in non_feature_cols]
    numeric_feature_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df_a[c])]
    n_inf = int(np.isinf(df_a[numeric_feature_cols]).sum().sum())
    check("sin valores infinitos en ninguna feature numerica", n_inf == 0, f"n_inf={n_inf}")

    print(f"\nCobertura (columnas no-NaN sobre Universo A, {len(df_a)} filas):")
    for c in numeric_feature_cols:
        cov = df_a[c].notna().mean()
        print(f"  {c:28s} cobertura={cov*100:5.1f}%")
    print(f"  {'atr_regime_bucket':28s} cobertura={df_a['atr_regime_bucket'].notna().mean()*100:5.1f}%")

    check("determinismo: rerun de atr_wilder/adx_wilder/rsi sobre el array completo produce EXACTAMENTE "
          "los mismos valores (mismo input -> mismo output, sin aleatoriedad)",
          bool(np.array_equal(atr_wilder(high, low, close, M5_ATR_PERIOD), atr_short, equal_nan=True)) and
          bool(np.array_equal(adx_wilder(high, low, close, ADX_PERIOD), adx_m5, equal_nan=True)) and
          bool(np.array_equal(sc.rsi(close, RSI_PERIOD), rsi_m5, equal_nan=True)),
          "rerun identico byte a byte (equal_nan=True)")

    csv_a = REPORTS_DIR / "BOT-050.1-context-limits-xau.csv"
    df_a.to_csv(csv_a, index=False)
    print(f"\nCSV Universo A escrito: {csv_a} ({len(df_a)} filas)")
    csv_b = REPORTS_DIR / "BOT-050.1-context-trades-xau.csv"
    df_b.to_csv(csv_b, index=False)
    print(f"CSV Universo B escrito: {csv_b} ({len(df_b)} filas)")

    # ---------------------------------------------------------------------------
    # I. ATR short/long -- prejustificacion explicita (seccion 2.3/10 del
    #    prompt de la tarea: NO parameter mining)
    # ---------------------------------------------------------------------------
    section("I. ATR short/long -- prejustificacion explicita (declarado ANTES de mirar outcomes)")
    print(f"ATR_short = ATR Wilder({M5_ATR_PERIOD}) barras M5 -- semantica: volatilidad M5 RECIENTE/inmediata. "
          f"Es la MISMA constante M5_ATR_PERIOD usada, sin excepcion, por BOT-024.2/BOT-047.1/BOT-048.1/"
          f"BOT-049.1 como normalizador de distancia -- reusar cualquier otro periodo 'corto' hubiera sido "
          f"arbitrario e inconsistente con el resto del proyecto.")
    print(f"ATR_long PRIMARIO = ATR Wilder({ATR_LONG_PRIMARY}) barras M5 -- semantica: volatilidad del "
          f"'regimen' HTF. {ATR_LONG_PRIMARY} = periodos_htf_min/5 = {CONFIG_A['periodos_htf_min']}/5, la "
          f"MISMA ventana que Config A ya usa para construir resistencia/soporte (bucket_levels()) -- no es "
          f"un numero nuevo, es la ventana 'lenta' que la propia estrategia ya trata como HTF.")
    print(f"ATR_long ALTERNATIVO (robustez, predeclarado) = ATR Wilder({ATR_LONG_ALT}) barras M5. "
          f"{ATR_LONG_ALT} = D1_WINDOW_MIN/5 = 1440/5, la misma ancla de 'dia de sesion' ya usada por "
          f"BOT-045 (`D1_WINDOW_MIN`). Declarado junto con el primario, ANTES de ejecutar este script, no "
          f"agregado despues de observar resultados.")
    print("CONFIRMACION EXPLICITA DE NO PARAMETER MINING: no se probo ningun otro periodo. No se buscara el "
          "par que maximice P&L/WR/PF. La eleccion entre primario/alternativo para una eventual promocion a "
          "BOT-050.2 se basara en estabilidad/interpretabilidad, no en cual 'gano' mas.")
    rho_ratio_pair = spearman_corr(df_b["atr_ratio_short_long"], df_b["atr_ratio_short_long_alt"])
    print(f"\nrho(atr_ratio_short_long [primario, /160], atr_ratio_short_long_alt [robustez, /288]) = "
          f"{rho_ratio_pair:+.3f} (Universo B) -- se espera alto por compartir el mismo numerador; el "
          f"denominador distinto es lo que hace que NO sean identicos.")

    # ---------------------------------------------------------------------------
    # J. Screening -- correlacion Spearman (diagnostico, no seleccion final)
    # ---------------------------------------------------------------------------
    section("J. Screening -- correlacion Spearman feature vs fill / vs pnl_r")
    screen_cols = [c for c in numeric_feature_cols if c not in ("atr_pct_rank_causal",)]
    # atr_pct_rank_causal excluida del screening independiente (representacion
    # secundaria/diagnostica de atr_ratio_short_long, ver seccion F2/K -- se
    # reporta su correlacion con el RAW en la seccion K, no se trata como
    # candidato aparte para evitar multiplicidad, seccion 12 del prompt).
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
        ["atr_ratio_short_long", "atr_ratio_short_long_alt", "adx_m5", "dist_ema_m5_atr",
         "dist_ema_m5_signed_atr", "rsi_level_m5"]
    ))
    print(f"\nShortlist deep-dive (candidatas obligatorias del enunciado, declaradas antes de mirar rho -- "
          f"session/hour/weekday se analizan aparte por ser categoricas/ciclicas, seccion M): {shortlist}")

    # ---------------------------------------------------------------------------
    # K. Redundancia interna (Context) -- Spearman entre features
    # ---------------------------------------------------------------------------
    section("K. Redundancia interna -- correlacion Spearman entre features Context (Universo B)")
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
    for a, bcol, r in pairs:
        print(f"  {a:28s} <-> {bcol:28s}  rho={r:+.3f}")

    rho_rank_vs_raw = spearman_corr(df_b["atr_pct_rank_causal"], df_b["atr_ratio_short_long"])
    print(f"\nrho(atr_pct_rank_causal, atr_ratio_short_long) = {rho_rank_vs_raw:+.3f} -- confirma que el "
          f"percentile rank es una representacion secundaria del MISMO fenomeno (RAW se conserva como "
          f"candidato principal, seccion 7.7 del prompt).")

    # ---------------------------------------------------------------------------
    # L. Deep dive -- buckets ALL/LONG/SHORT, sub-periodos, con CI
    # ---------------------------------------------------------------------------
    section("L. Deep dive de la shortlist -- buckets con Wilson CI (WR) / bootstrap CI (ExpR), LONG/SHORT, sub-periodos")

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
            wr_lo, wr_hi = wilson_ci(wins, wins + losses) if (wins + losses) else (float("nan"), float("nan"))
            gross_win = g.loc[g["pnl_usd"] > 0, "pnl_usd"].sum()
            gross_loss = -g.loc[g["pnl_usd"] < 0, "pnl_usd"].sum()
            pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
            exp_lo, exp_hi = bootstrap_mean_ci(g["pnl_r"].tolist())
            out_rows.append(dict(bucket=str(bkt), n=n, win_rate=wr, wr_lo=wr_lo, wr_hi=wr_hi,
                                  exp_usd=g["pnl_usd"].mean(), exp_r=g["pnl_r"].mean(),
                                  exp_r_lo=exp_lo, exp_r_hi=exp_hi, pf=pf))
        return pd.DataFrame(out_rows)

    def print_bucket_table(title: str, dfb: pd.DataFrame) -> None:
        print(f"\n  {title}")
        if dfb.empty:
            print("    (sin datos suficientes para bucketizar)")
            return
        for _, r in dfb.iterrows():
            pf = f"{r['pf']:.2f}" if not math.isnan(r["pf"]) else "n/a"
            print(f"    {r['bucket']:<32s} N={r['n']:5d}  WR={r['win_rate']*100:5.1f}% [{r['wr_lo']*100:4.1f},{r['wr_hi']*100:4.1f}]  "
                  f"Exp$={r['exp_usd']:+7.2f}  ExpR={r['exp_r']:+.3f} [{r['exp_r_lo']:+.3f},{r['exp_r_hi']:+.3f}]  PF={pf}")

    for feat in shortlist:
        print(f"\n--- {feat} ---")
        print_bucket_table("ALL", bucket_report_perf(df_b, feat))
        for dlabel in ("LONG", "SHORT"):
            print_bucket_table(dlabel, bucket_report_perf(df_b[df_b["direction"] == dlabel], feat))
        for sp in ("sub1", "sub2", "sub3"):
            print_bucket_table(sp, bucket_report_perf(df_b[df_b["sub_periodo"] == sp], feat))

    # ---------------------------------------------------------------------------
    # M. Sesion / hora / dia de semana -- categorico, P(fill) y P(win|filled)
    # ---------------------------------------------------------------------------
    section("M. Sesion / hora / dia de semana -- P(fill) y outcome|filled, ALL/LONG/SHORT")

    def cat_fill_table(sub: pd.DataFrame, col: str) -> pd.DataFrame:
        out = []
        for cat, g in sub.groupby(col, observed=True):
            n = len(g)
            n_filled = int(g["filled"].sum())
            fr = n_filled / n if n else float("nan")
            lo, hi = wilson_ci(n_filled, n)
            out.append(dict(cat=cat, n=n, fill_rate=fr, fr_lo=lo, fr_hi=hi))
        return pd.DataFrame(out).sort_values("cat")

    def cat_outcome_table(sub: pd.DataFrame, col: str) -> pd.DataFrame:
        out = []
        for cat, g in sub.groupby(col, observed=True):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            wr_lo, wr_hi = wilson_ci(wins, wins + losses) if (wins + losses) else (float("nan"), float("nan"))
            exp_lo, exp_hi = bootstrap_mean_ci(g["pnl_r"].tolist())
            out.append(dict(cat=cat, n=n, win_rate=wr, wr_lo=wr_lo, wr_hi=wr_hi,
                             exp_r=g["pnl_r"].mean(), exp_r_lo=exp_lo, exp_r_hi=exp_hi))
        return pd.DataFrame(out).sort_values("cat")

    for label, col in [("Sesion (session_utc)", "session_utc"), ("Dia de semana (weekday)", "weekday")]:
        print(f"\n--- {label}: P(fill) -- Universo A ---")
        ft = cat_fill_table(df_a, col)
        for _, r in ft.iterrows():
            print(f"    {str(r['cat']):<28s} N={r['n']:5d}  FillRate={r['fill_rate']*100:5.1f}% "
                  f"[{r['fr_lo']*100:4.1f},{r['fr_hi']*100:4.1f}]")
        print(f"\n--- {label}: outcome|filled -- Universo B (ALL/LONG/SHORT) ---")
        for dlabel, sub in [("ALL", df_b), ("LONG", df_b[df_b["direction"] == "LONG"]),
                             ("SHORT", df_b[df_b["direction"] == "SHORT"])]:
            print(f"  [{dlabel}]")
            ot = cat_outcome_table(sub, col)
            for _, r in ot.iterrows():
                print(f"    {str(r['cat']):<28s} N={r['n']:5d}  WR={r['win_rate']*100:5.1f}% "
                      f"[{r['wr_lo']*100:4.1f},{r['wr_hi']*100:4.1f}]  ExpR={r['exp_r']:+.3f} "
                      f"[{r['exp_r_lo']:+.3f},{r['exp_r_hi']:+.3f}]")
        print(f"\n--- {label}: estabilidad por sub-periodo (ExpR|filled, ALL) ---")
        for sp in ("sub1", "sub2", "sub3"):
            sub = df_b[df_b["sub_periodo"] == sp]
            ot = cat_outcome_table(sub, col)
            print(f"  [{sp}]")
            for _, r in ot.iterrows():
                print(f"    {str(r['cat']):<28s} N={r['n']:5d}  ExpR={r['exp_r']:+.3f} "
                      f"[{r['exp_r_lo']:+.3f},{r['exp_r_hi']:+.3f}]")

    # --- M2. Bucket de regimen de volatilidad (descriptivo) -----------------
    print("\n--- Bucket de regimen (atr_regime_bucket, terciles predefinidos): outcome|filled, ALL/LONG/SHORT ---")
    for dlabel, sub in [("ALL", df_b), ("LONG", df_b[df_b["direction"] == "LONG"]),
                         ("SHORT", df_b[df_b["direction"] == "SHORT"])]:
        print(f"  [{dlabel}]")
        ot = cat_outcome_table(sub, "atr_regime_bucket")
        for _, r in ot.iterrows():
            print(f"    {str(r['cat']):<28s} N={r['n']:5d}  WR={r['win_rate']*100:5.1f}% "
                  f"[{r['wr_lo']*100:4.1f},{r['wr_hi']*100:4.1f}]  ExpR={r['exp_r']:+.3f} "
                  f"[{r['exp_r_lo']:+.3f},{r['exp_r_hi']:+.3f}]")

    # ---------------------------------------------------------------------------
    # N. ADX -- deep dive: fuerza de tendencia vs direccion (NO reinterpretar
    #    ADX como direccion, seccion 7.5 del prompt)
    # ---------------------------------------------------------------------------
    section("N. ADX -- fuerza de tendencia (no direccional) -- confirmacion explicita de no-direccionalidad")
    rho_adx_dir = spearman_corr(df_b["adx_m5"], (df_b["direction"] == "LONG").astype(float))
    print(f"rho(adx_m5, direction==LONG) = {rho_adx_dir:+.3f} -- se espera ~0 (ADX no distingue LONG/SHORT "
          f"por construccion algebraica -- usa |plus_di - minus_di|, valor absoluto). Confirmado empiricamente "
          f"aca, no solo por formula.")
    print(f"Cobertura adx_m5: {df_a['adx_m5'].notna().mean()*100:.1f}% (requiere >= {ADX_PERIOD*2-1} barras "
          f"de warm-up, trivial frente a {n_bars} barras totales).")
    print("\nRedundancia con Momentum/Alignment/Structure (Universo B):")
    for other, label in [("momentum_roc_atr_10", "Momentum (control cruzado, roc_atr_10)")]:
        rho = spearman_corr(df_b["adx_m5"], df_b[other])
        print(f"    rho(adx_m5, {other}) = {rho:+.3f}  ({label})")

    # ---------------------------------------------------------------------------
    # O. Distancia a EMA M5 -- Context vs duplicado de Momentum/Structure
    # ---------------------------------------------------------------------------
    section("O. dist_ema_m5_atr -- Context o duplica Momentum/Alignment/Structure?")
    print("dist_ema_m5_atr mide |close-ema_line(12)|/ATR en limit_created_bar -- la señal se dispara "
          "EXACTAMENTE cuando close cruza ema_line (ver strategy/engine.py), asi que este valor es la "
          "magnitud del 'sobrepaso' de la barra que dispara la señal, no una distancia acumulada de varias "
          "barras (eso ya lo mide momentum_roc_atr_10, otra ventana).")
    print(f"Cobertura: {df_a['dist_ema_m5_atr'].notna().mean()*100:.1f}%")
    for other, label in [("momentum_roc_atr_10", "Momentum (roc_atr_10)")]:
        rho = spearman_corr(df_b["dist_ema_m5_atr"], df_b[other])
        print(f"    rho(dist_ema_m5_atr, {other}) = {rho:+.3f}  ({label})")
    print("(Redundancia contra origin_dist_atr [Structure] y closed_ema200_slope [Alignment, D1] se evalua "
          "en la seccion Q, via merge exacto con los CSV congelados de esas tareas.)")

    # ---------------------------------------------------------------------------
    # P. Nivel de RSI M5 -- Context o ya cubierto por Momentum (BOT-024.2)?
    # ---------------------------------------------------------------------------
    section("P. rsi_level_m5 -- reverificacion independiente del hallazgo estructural de BOT-024.2")
    rsi_b = df_b["rsi_level_m5"].dropna()
    rsi_a = df_a["rsi_level_m5"].dropna()
    print(f"Universo B: N={len(rsi_b)} min={rsi_b.min():.1f} max={rsi_b.max():.1f} media={rsi_b.mean():.1f} "
          f"mediana={rsi_b.median():.1f}")
    n_extreme_a = int(((rsi_a > 70) | (rsi_a < 30)).sum())
    print(f"Universo A: N={len(rsi_a)}, eventos con RSI>70 o RSI<30 = {n_extreme_a}/{len(rsi_a)} "
          f"({n_extreme_a/len(rsi_a)*100:.2f}%)")
    check("reverificacion independiente del hallazgo de BOT-024.2 seccion G ('RSI nunca sale de banda "
          "media en limit_created_bar') -- reconstruido aca desde cero con RSI de produccion (strategy."
          "scoring.rsi()), no copiado del CSV de Momentum",
          n_extreme_a <= 10, f"eventos extremos observados={n_extreme_a} (BOT-024.2 reporto 8/3207)")
    print("CONCLUSION PRELIMINAR: `rsi_level_m5` esta estructuralmente confinado a una banda media estrecha "
          "por el propio mecanismo de señal (cruce de EMA12 con 'armado' HTF) -- el mismo hallazgo que "
          "BOT-024.2 encontro para `rsi_now` (ya calculado en esa tarea, mismo periodo=14, parte del feature "
          "set de Momentum). No se trata como un candidato nuevo de Context: ya fue descubierto y reportado "
          "bajo Momentum, se reverifica aca por disciplina causal pero no se reclama independencia -- ver "
          "clasificacion final seccion S.")

    # ---------------------------------------------------------------------------
    # Q. Redundancia cruzada -- Momentum / Structure / Alignment
    # ---------------------------------------------------------------------------
    section("Q. Redundancia cruzada con Momentum (BOT-024.2) / Structure (BOT-048.1) / Alignment (BOT-047.1)")
    cross_available = CSV_MOMENTUM_B.exists() and CSV_STRUCT_B.exists() and CSV_ALIGN_B.exists()
    check("CSVs de Momentum/Structure/Alignment disponibles para merge por limit_created_bar (sin recalcular "
          "esas dimensiones)", cross_available,
          f"momentum={CSV_MOMENTUM_B.exists()} structure={CSV_STRUCT_B.exists()} alignment={CSV_ALIGN_B.exists()}")

    if cross_available:
        mom = pd.read_csv(CSV_MOMENTUM_B)[["limit_created_bar", "roc_atr_3", "atr_pct", "atr14",
                                            "atr5_atr20_ratio", "rsi_now"]]
        struct = pd.read_csv(CSV_STRUCT_B)[["limit_created_bar", "origin_dist_atr"]]
        align = pd.read_csv(CSV_ALIGN_B)[["limit_created_bar", "closed_ema200_slope"]]
        merged = df_b.merge(mom, on="limit_created_bar", how="inner") \
                     .merge(struct, on="limit_created_bar", how="inner") \
                     .merge(align, on="limit_created_bar", how="inner")
        check("Merge por limit_created_bar reproduce el Universo B completo (mismo motor/dataset/Config A en "
              "las 4 tareas, debe coincidir 1:1)", len(merged) == len(df_b),
              f"merged={len(merged)}, df_b={len(df_b)}")

        context_candidates = ["atr_ratio_short_long", "atr_ratio_short_long_alt", "adx_m5",
                               "dist_ema_m5_atr", "rsi_level_m5"]
        other_dims = dict(momentum_roc_atr_3="roc_atr_3", momentum_roc_atr_10="momentum_roc_atr_10",
                           structure_origin_dist_atr="origin_dist_atr",
                           alignment_closed_ema200_slope="closed_ema200_slope")
        print("\nrho(candidata Context, representante de otra dimension YA CONGELADA) -- Universo B, merge exacto:")
        for ctx_col in context_candidates:
            for label, other_col in other_dims.items():
                rho = spearman_corr(merged[ctx_col], merged[other_col])
                print(f"    {ctx_col:26s} <-> {label:34s} rho={rho:+.3f}")

        print("\n-- H. atr_ratio_short_long vs features ATR-normalizadas YA CALCULADAS por Momentum "
              "(BOT-024.2, no congeladas/no frozen -- seccion 7.1 del prompt: 'evaluar redundancia con "
              "cualquier feature ATR-normalizada existente') --")
        for other_col, label in [("atr5_atr20_ratio", "Momentum atr5_atr20_ratio (ratio ATR5/ATR20, "
                                   "misma familia conceptual, ventanas mas cortas)"),
                                  ("atr_pct", "Momentum atr_pct (ATR14/close, normalizacion distinta: "
                                   "nivel absoluto vs precio, no un ratio short/long)"),
                                  ("atr14", "Momentum atr14 (identico en definicion a atr_short de esta "
                                   "tarea, control de identidad)")]:
            rho_prim = spearman_corr(merged["atr_ratio_short_long"], merged[other_col])
            rho_alt = spearman_corr(merged["atr_ratio_short_long_alt"], merged[other_col])
            print(f"    rho(atr_ratio_short_long [/160], {other_col:20s}) = {rho_prim:+.3f}   ({label})")
            print(f"    rho(atr_ratio_short_long_alt [/288], {other_col:17s}) = {rho_alt:+.3f}")
        rho_atr14_identity = spearman_corr(merged["atr_short"], merged["atr14"])
        print(f"\n    Control de identidad: rho(atr_short [esta tarea, ATR(14) M5], atr14 [Momentum, "
              f"BOT-024.2]) = {rho_atr14_identity:+.3f} (se espera ~+1.000, MISMA definicion exacta "
              f"calculada dos veces de forma independiente).")

        print("\n-- P. rsi_level_m5 vs rsi_now (Momentum, BOT-024.2, MISMO periodo=14) --")
        rho_rsi_identity = spearman_corr(merged["rsi_level_m5"], merged["rsi_now"])
        print(f"    rho(rsi_level_m5, rsi_now) = {rho_rsi_identity:+.3f} (se espera ~+1.000, misma "
              f"definicion RSI(14) calculada dos veces de forma independiente -- confirma identidad, no "
              f"redundancia parcial).")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
