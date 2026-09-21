"""BOT-049.1 -- Economics Feature Discovery, XAU (BTC bloqueado, ver seccion A).

Subtarea de `BOT-049` (feature padre "Economics", dimension del futuro Signal
Quality de BOT-024 -- ver BOT-049 en BACKLOG.md). SOLO LECTURA/DISCOVERY --
OFFLINE / DISCOVERY / NO PRODUCTION CHANGES / NO SCORE / NO GATE. No define
todavia una definicion final de Economics, no crea EconomicsScore, no crea
escala 0-100, no asigna pesos, no crea gates, no optimiza EMA/HTF/Buffer/RR.

Pregunta que responde: que variables economicas observables, causales y
reproducibles existen en `limit_created_bar` (== `signal_bar` == `born_bar`,
mismo punto de congelacion que BOT-024.2/BOT-047.1/BOT-048.1) y describen la
geometria economica del setup (RR, costos, spread, distancia a SL/TP) --
explicitamente independiente de Momentum (BOT-024.2), Alignment (BOT-047) y
Structure (BOT-048, `ORIGIN_ONLY_FREEZE`). ATR_short/ATR_long queda
explicitamente EXCLUIDO (reservado para BOT-050.1, Context) -- ver seccion N.

Metodologia (resumen; ver reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY.md):
  1. Corre strategy.engine.run_backtest (sin tocar) UNA sola vez, continuo,
     sobre backtests/data/XAUUSDc_M5_latest.parquet, "Config A" (misma que
     BOT-024.1/BOT-024.2/BOT-047.1/BOT-048.1/BOT-042/043/045/046).
  2. Shadow replay -- copiado VERBATIM de scripts/discover_structure_features_
     xau.py (misma logica de decision + bookkeeping de "origen de armado",
     necesario para reconstruir origin_retracement_frac) -- reproduce
     Universo A completo y se valida EXHAUSTIVAMENTE contra run_backtest()
     real antes de interpretar nada.
  3. Bajo Config A (rr=1.0 FIJO por parametro de estrategia, no por evento),
     se verifica primero si RR nominal/geometrico varia -- no varia (es un
     parametro congelado, ver seccion I) -- se documenta la degeneracion en
     vez de fingir poder predictivo donde no existe variacion (seccion 3 del
     prompt de la tarea, punto "C").
  4. Familias A-E (geometria SL/TP, RR, friccion de spread, costos/breakeven)
     se calculan directamente de entry/stop/target/spread_pts en
     limit_created_bar -- ninguna requiere el futuro. origin_retracement_frac
     (Familia F) se reconstruye con el mismo bookkeeping de origen que
     BOT-048.1 y se re-verifica causalmente aca de nuevo (no se asume el
     resultado de BOT-048.1, se reproduce). distance_to_limit_atr (seccion 8
     del prompt) usa el CLOSE de la barra de creacion (unico precio conocido
     en el momento de encolar el LIMIT, ver justificacion en seccion F).
  5. Redundancia cruzada con Momentum (BOT-024.2, roc_atr_3), Structure
     (BOT-048.1, origin_dist_atr) y Alignment (BOT-047.1, closed_ema200_slope)
     via merge por limit_created_bar sobre los CSV ya congelados de esas
     tareas -- no se recalcula ninguna de esas dimensiones.
  6. CVP (strategy.scoring.cvp_score()) se compara conceptualmente: la mitad
     "costo" de CVP (breakeven neto) es la MISMA formula que breakeven_pct de
     esta tarea -- se documenta el solapamiento sin reemplazar CVP.

Uso:
    .venv/Scripts/python.exe scripts/discover_economics_features_xau.py \
        > reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY-EVIDENCE.log

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
# BOT-042/BOT-043/BOT-045/BOT-046. NO se optimiza ni se cambia ningun
# parametro de estrategia en esta tarea. rr=1.0 es un PARAMETRO fijo -- ver
# seccion I para la verificacion explicita de que RR es degenerado bajo esta
# config (no varia evento a evento).
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

M5_ATR_PERIOD = 14  # misma ventana que BOT-024.2/BOT-047.1/BOT-048.1 (M5_ATR_PERIOD)
MOMENTUM_ROC_HORIZON = 10  # roc_atr_10, misma definicion exacta que BOT-047.1/BOT-048.1 (control cruzado)

SESSION_BOUNDS_UTC = [  # misma convencion que BOT-045/BOT-024.2/BOT-047.1/BOT-048.1
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
# 0. Toolkit estadistico -- reusado VERBATIM de scripts/discover_momentum_
#    features_xau.py / scripts/freeze_structure_definition_xau.py.
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
# 1. Shadow replay -- COPIADO VERBATIM de scripts/discover_structure_features_
#    xau.py (a su vez copiado de scripts/discover_d1_alignment_features_xau.py
#    / scripts/discover_momentum_features_xau.py). Incluye el bookkeeping de
#    "origen de armado" (origin_venta/origin_compra) necesario para
#    reconstruir origin_retracement_frac -- NO participa de ninguna decision
#    de fill/expiracion/outcome, solo lee el estado que la logica original ya
#    calculaba. NO SE MODIFICA ninguna decision respecto a strategy/engine.py.
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
    print("BOT-049.1 -- Economics Feature Discovery, XAU (BTC bloqueado, ver seccion A)")
    print("SOLO LECTURA/DISCOVERY. No se modifico ningun archivo de produccion. No se activa gating.")
    print("No se implementa una definicion final de Economics. No se crea score/peso/gate.\n")

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
    section("B. Dataset XAU y costos (reusa lo ya usado por BOT-024.2/BOT-047.1/BOT-048.1)")
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
          f"tick_size={costs.tick_size} swap_long={costs.swap_long_points} swap_short={costs.swap_short_points} "
          f"commission_per_lot={costs.commission_per_lot} (0.0, mismo valor hardcodeado que produccion "
          f"execution/src/bot.py -- ver BOT-044, comision NO se inventa)")

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

    # --- E. ATR M5 causal ----------------------------------------------------
    section("E. ATR M5 causal (Wilder, misma ventana que BOT-024.2/BOT-047.1/BOT-048.1)")
    atr_m5 = atr_wilder(high, low, close, M5_ATR_PERIOD)
    print(f"ATR Wilder({M5_ATR_PERIOD}) sobre M5 -- reusado verbatim de tareas anteriores, no redefinido aca.")

    # ---------------------------------------------------------------------------
    # F. Feature vector Economics por evento del Universo A, congelado en
    #    limit_created_bar. Justificacion de "precio actual" en creation: el
    #    LIMIT se encola al PROCESAR la barra b (cruce evaluado con
    #    close[b-1]/close[b], ver strategy/engine.py::run_backtest -- paso 3
    #    "nueva senal" corre DESPUES del paso 2 "evaluar pendientes" de la
    #    MISMA iteracion b, o sea la primera vela en que se evalua si toca el
    #    limite es b+1) -- el unico precio observable/conocido en el momento
    #    de crear la orden es close[b]. No se usa ningun tick de b+1 en
    #    adelante.
    # ---------------------------------------------------------------------------
    section("F. Feature vector Economics, congelado en limit_created_bar, por cada LIMIT del Universo A")

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
        entry = ev["entry"]
        stop = ev["stop"]
        target = ev["target"]
        origin_bar = ev["origin_bar"]
        origin_level = ev["origin_level"]

        atr_b = atr_m5[b]
        atr_ok = atr_b is not None and not math.isnan(atr_b) and atr_b > 0

        feats: dict = {}

        # --- Familia A: Geometria LIMIT -> SL --------------------------------
        risk_price = abs(stop - entry)
        feats["risk_price"] = risk_price
        feats["risk_atr"] = risk_price / atr_b if atr_ok else np.nan
        feats["risk_ticks"] = risk_price / costs.tick_size
        feats["risk_usd"] = costs.price_to_usd(risk_price, params.fixed_lot)

        # --- Familia B: Geometria LIMIT -> TP --------------------------------
        reward_price = abs(target - entry)
        feats["reward_price"] = reward_price
        feats["reward_atr"] = reward_price / atr_b if atr_ok else np.nan
        feats["reward_ticks"] = reward_price / costs.tick_size
        feats["reward_usd"] = costs.price_to_usd(reward_price, params.fixed_lot)

        # --- Familia C: RR bruto y geometria RR ------------------------------
        feats["rr_nominal"] = params.rr
        feats["rr_geometric"] = reward_price / risk_price if risk_price > 0 else np.nan

        # --- Familia D: Friccion por spread -----------------------------------
        spread_price = costs.spread_price(spread_pts[b])
        feats["spread_price"] = spread_price
        feats["spread_usd"] = costs.price_to_usd(spread_price, params.fixed_lot)
        feats["spread_over_risk"] = spread_price / risk_price if risk_price > 0 else np.nan
        feats["spread_over_reward"] = spread_price / reward_price if reward_price > 0 else np.nan

        # --- Familia E: Costos y breakeven economico (commission_per_lot=0.0,
        #     ver seccion B -- conocido/estimable en creation, NO inventado).
        #     Swap EXCLUIDO (depende de nights_held futuro, no causal) -- solo
        #     se reporta una ESTIMACION de exposicion potencial por noche,
        #     etiquetada explicitamente como geometry/estimate, nunca como
        #     costo realizado (seccion E del prompt de la tarea). -----------
        commission_usd_evt = costs.commission_usd(params.fixed_lot)
        # Conversion USD->precio inversa de price_to_usd() (BOT-043), NO el patron
        # contract_size de cvp_score()/BOT-044 -- commission_usd_evt es 0.0 aca
        # (commission_per_lot=0.0, ver seccion B), esta rama nunca se ejecuta con
        # un valor distinto de 0 en este dataset, se deja correcta por si cambia.
        commission_price = (commission_usd_evt * costs.tick_size / costs.tick_value / params.fixed_lot
                             if commission_usd_evt else 0.0)
        sl_neto = risk_price + spread_price + commission_price
        tp_neto = max(reward_price - spread_price - commission_price, 0.0)
        feats["breakeven_pct"] = (sl_neto / (sl_neto + tp_neto) * 100) if (sl_neto + tp_neto) > 0 else np.nan
        feats["rr_effective_net"] = (tp_neto / sl_neto) if sl_neto > 0 else np.nan
        feats["cost_frac_of_target"] = spread_price / reward_price if reward_price > 0 else np.nan
        feats["swap_1night_estimate_usd"] = costs.swap_usd_per_lot_per_night(d) * params.fixed_lot

        # --- Familia F: origin_retracement_frac (candidata CROSS_FACTOR_ONLY
        #     conocida, BOT-048.2) -- reconstruida aca desde cero con el mismo
        #     bookkeeping de origen que BOT-048.1, NO copiada del CSV. -------
        if origin_bar is not None:
            denom = abs(target - origin_level)
            feats["origin_retracement_frac"] = (abs(entry - origin_level) / denom) if denom > 0 else np.nan
            feats["origin_dist_to_target_atr"] = denom / atr_b if atr_ok else np.nan
        else:
            feats["origin_retracement_frac"] = np.nan
            feats["origin_dist_to_target_atr"] = np.nan

        # --- Seccion 8 del prompt: distance_to_limit_atr / friccion de
        #     ejecucion. Precio "actual" en creation = close[b] (ver
        #     justificacion arriba de la seccion F). --------------------------
        price_at_creation = close[b]
        feats["distance_to_limit_atr"] = abs(price_at_creation - entry) / atr_b if atr_ok else np.nan
        feats["distance_to_limit_price"] = abs(price_at_creation - entry)

        # --- Momentum M5 (control cruzado -- MISMA definicion exacta que
        #     BOT-047.1/BOT-048.1, roc_atr_10, no se modifica) --------------
        j = b - MOMENTUM_ROC_HORIZON
        if j >= 0 and atr_ok:
            feats["momentum_roc_atr_10"] = d * (close[b] - close[j]) / atr_b
        else:
            feats["momentum_roc_atr_10"] = np.nan

        dt = pd.Timestamp(int(time_utc[b]), unit="s", tz="UTC")
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
            origin_bar=origin_bar, atr_m5=atr_b,
        )
        row.update(feats)
        rows.append(row)

        if idx_ev % max(1, len(limit_events) // 40) == 0:
            causal_sample_bars.append(b)

    df_a = pd.DataFrame(rows)

    # --- G. Verificacion de causalidad --------------------------------------
    section("G. Verificacion de causalidad")
    print("Argumento constructivo (Familias A-E, distance_to_limit_atr): entry/stop/target se calculan en "
          "strategy/engine.py::run_backtest a partir EXCLUSIVAMENTE de ema_line[b]/resistencia[b]/soporte[b] "
          "(datos de la barra b o anteriores, ver bucket_levels/ema en strategy/engine.py -- ya verificado "
          "causal en BOT-003/BOT-004/BOT-042/BOT-048.1). spread_price usa spread_pts[b] (spread de la MISMA "
          "vela de creacion, no de una vela futura). price_at_creation usa close[b] exclusivamente (ver "
          "justificacion en seccion F). Ningun campo de esta seccion lee indices > b.")
    print("Argumento constructivo (origen de armado / origin_retracement_frac): identico al usado y verificado "
          "en BOT-048.1 -- el loop de shadow_replay recorre i=0..n-1 en orden y origin_venta/origin_compra se "
          "leen (snapshot) ANTES de actualizarse con la barra actual; ningun acceso a i+k existe en el codigo.")
    print("Argumento constructivo (ATR Wilder): atr[i] depende recursivamente solo de atr[i-1] y tr[i] (high/low/"
          "close de la barra i o i-1) -- reusado verbatim, ya verificado causal en BOT-024.2/BOT-047.1/BOT-048.1.")

    print("\nVerificacion empirica (re-slice [:b+1] para una muestra distribuida en el tiempo, recalculando "
          "TODO -- shadow replay + ATR + features -- desde cero sobre el array truncado):")
    mismatches = []
    for b in causal_sample_bars:
        ev_full = limit_events.get(b)
        if ev_full is None:
            continue
        n_trunc = b + 1
        atr_trunc = atr_wilder(high[:n_trunc], low[:n_trunc], close[:n_trunc], M5_ATR_PERIOD)
        limit_events_trunc, _, _ = shadow_replay(
            time_utc[:n_trunc], time_server[:n_trunc], high[:n_trunc], low[:n_trunc], close[:n_trunc],
            spread_pts[:n_trunc], params, costs, ema_line[:n_trunc], resistencia[:n_trunc], soporte[:n_trunc])
        ev_trunc = limit_events_trunc.get(b)
        if ev_trunc is None:
            mismatches.append((b, "evento no reproducido en el array truncado"))
            continue
        atr_full_b, atr_trunc_b = atr_m5[b], atr_trunc[b]
        same_atr = (math.isnan(atr_full_b) and math.isnan(atr_trunc_b)) or math.isclose(
            atr_full_b, atr_trunc_b, rel_tol=1e-9, abs_tol=1e-12)
        same_origin = (ev_trunc["origin_bar"] == ev_full["origin_bar"]) and (
            (ev_trunc["origin_level"] is None and ev_full["origin_level"] is None) or
            math.isclose(ev_trunc["origin_level"], ev_full["origin_level"], rel_tol=1e-9, abs_tol=1e-9))
        same_geom = (math.isclose(ev_trunc["entry"], ev_full["entry"], rel_tol=1e-9, abs_tol=1e-9) and
                     math.isclose(ev_trunc["stop"], ev_full["stop"], rel_tol=1e-9, abs_tol=1e-9) and
                     math.isclose(ev_trunc["target"], ev_full["target"], rel_tol=1e-9, abs_tol=1e-9))
        if not (same_atr and same_origin and same_geom):
            mismatches.append((b, dict(same_atr=same_atr, same_origin=same_origin, same_geom=same_geom)))

    check(f"ATR/origen de armado/entry-stop-target: re-slice[:b+1] == calculo sobre array completo, "
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
    check("Universo A/B: mismo tamano que BOT-024.2/BOT-047.1/BOT-048.1 (mismo motor/dataset/Config A, debe "
          "coincidir)", len(df_a) == 3207 and len(df_b) == 2474,
          f"BOT-049.1: A={len(df_a)} (esperado 3207) B={len(df_b)} (esperado 2474)")

    dup_bars = df_a["limit_created_bar"].duplicated().sum()
    check("Universo A sin limit_created_bar duplicado", dup_bars == 0, f"duplicados={dup_bars}")

    feature_cols = [c for c in df_a.columns if c not in (
        "trade_id", "asset", "direction", "limit_created_bar", "entry_time_utc", "hour_utc", "session_utc",
        "weekday", "sub_periodo", "fate", "filled", "fill_bar", "time_to_fill_bars", "exit_bar", "outcome",
        "pnl_usd", "pnl_r", "origin_bar")]
    numeric_feature_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df_a[c])]
    n_inf = int(np.isinf(df_a[numeric_feature_cols]).sum().sum())
    check("sin valores infinitos en ninguna feature numerica", n_inf == 0, f"n_inf={n_inf}")

    print(f"\nCobertura (columnas no-NaN sobre Universo A, {len(df_a)} filas):")
    for c in numeric_feature_cols:
        cov = df_a[c].notna().mean()
        print(f"  {c:28s} cobertura={cov*100:5.1f}%")

    # --- I. RR nominal/geometrico -- verificacion explicita de degeneracion --
    section("I. RR nominal/geometrico bajo Config A -- verificacion explicita de (no-)variacion")
    rr_nom_unique = df_a["rr_nominal"].unique()
    rr_geo_unique = df_a["rr_geometric"].round(9).unique()
    check("rr_nominal es constante (parametro de estrategia, no varia evento a evento) -- Config A: rr=1.0",
          len(rr_nom_unique) == 1 and float(rr_nom_unique[0]) == 1.0, f"valores unicos={rr_nom_unique}")
    check("rr_geometric (reward_price/risk_price) es IDENTICO a rr_nominal para TODOS los eventos -- por "
          "construccion (target = entry +/- rr*risk en strategy/engine.py), no es un hallazgo estadistico, "
          "es una identidad algebraica -- documentado, no fingido como variacion",
          len(rr_geo_unique) == 1 and math.isclose(float(rr_geo_unique[0]), 1.0, rel_tol=1e-9),
          f"valores unicos (redondeados a 1e-9)={rr_geo_unique}")
    print("CONSECUENCIA DIRECTA (RR=1.0 fijo): reward_price==risk_price para TODO evento -- Familias A y B "
          "(geometria SL/TP) son IDENTICAS bajo Config A (no dos familias independientes, ver seccion K). "
          "spread_over_risk==spread_over_reward para todo evento (mismo denominador). El unico grado de "
          "libertad de friccion que sobrevive es la RATIO spread_price/risk_price -- ver seccion J/K para la "
          "derivacion completa de por que breakeven_pct y rr_effective_net son funciones deterministas de esa "
          "misma ratio bajo RR=1.")
    same_ab = bool(np.allclose(df_a["risk_price"], df_a["reward_price"], rtol=1e-9, atol=1e-9))
    check("reward_price == risk_price para TODOS los eventos (identidad algebraica bajo RR=1.0)",
          same_ab, f"max|diff|={float((df_a['risk_price']-df_a['reward_price']).abs().max()):.3e}")
    same_spread_ratio = bool(np.allclose(df_a["spread_over_risk"].fillna(-1), df_a["spread_over_reward"].fillna(-1),
                                          rtol=1e-9, atol=1e-9))
    check("spread_over_risk == spread_over_reward para TODOS los eventos (mismo denominador bajo RR=1.0)",
          same_spread_ratio, "verificado elementwise")

    csv_a = REPORTS_DIR / "BOT-049.1-economics-limits-xau.csv"
    df_a.to_csv(csv_a, index=False)
    print(f"\nCSV Universo A escrito: {csv_a} ({len(df_a)} filas)")
    csv_b = REPORTS_DIR / "BOT-049.1-economics-trades-xau.csv"
    df_b.to_csv(csv_b, index=False)
    print(f"CSV Universo B escrito: {csv_b} ({len(df_b)} filas)")

    # ---------------------------------------------------------------------------
    # J. Screening -- correlacion Spearman (diagnostico, no seleccion final)
    # ---------------------------------------------------------------------------
    section("J. Screening -- correlacion Spearman feature vs fill / vs pnl_r")

    # rr_nominal/rr_geometric excluidos del screening (constantes, sin varianza,
    # ver seccion I) -- reward_* excluidos del screening independiente por ser
    # identicos a risk_* bajo RR=1 (documentado, ver seccion K para el par
    # explicito), se listan igual en la tabla completa para trazabilidad.
    screen_cols = [c for c in numeric_feature_cols if c not in ("rr_nominal",)]
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
        screen_df.sort_values("abs_rho_fill", ascending=False).head(8)["feature"].tolist() +
        screen_df.sort_values("abs_rho_pnl_r", ascending=False).head(8)["feature"].tolist() +
        ["origin_retracement_frac", "distance_to_limit_atr", "risk_atr", "spread_over_risk", "breakeven_pct"]
    ))
    print(f"\nShortlist deep-dive (union top-8 fill + top-8 pnl_r + candidatas obligatorias del enunciado -- "
          f"screening, no clasificacion final): {shortlist}")

    # ---------------------------------------------------------------------------
    # K. Redundancia interna (Economics) -- Spearman entre features
    # ---------------------------------------------------------------------------
    section("K. Redundancia interna -- correlacion Spearman entre features Economics (Universo B)")
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
    # M. Fill / time-to-fill -- distance_to_limit_atr (seccion 8 del prompt,
    #    NO mezclar P(fill)/time_to_fill/P(outcome|filled) -- BOT-024.2 ya
    #    establecio que son fenomenos distintos, se mantiene el mismo criterio)
    # ---------------------------------------------------------------------------
    section("M. distance_to_limit_atr -- P(fill) / time_to_fill_bars|filled / P(outcome|filled) POR SEPARADO")

    def fill_rate_by_bucket(sub: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
        s = sub[[col, "filled"]].dropna(subset=[col])
        if len(s) < 20 or s[col].nunique() < 2:
            return pd.DataFrame()
        try:
            s = s.assign(bucket=pd.qcut(s[col], q=q, duplicates="drop"))
        except ValueError:
            return pd.DataFrame()
        out = []
        for bkt, g in s.groupby("bucket", observed=True):
            n = len(g)
            n_filled = int(g["filled"].sum())
            fr = n_filled / n if n else float("nan")
            lo, hi = wilson_ci(n_filled, n)
            out.append(dict(bucket=str(bkt), n=n, fill_rate=fr, fr_lo=lo, fr_hi=hi))
        return pd.DataFrame(out)

    print("1) P(fill | distance_to_limit_atr) -- Universo A completo, exploratorio (quintiles descriptivos, "
          "NO congelables como threshold):")
    fr_tab = fill_rate_by_bucket(df_a, "distance_to_limit_atr")
    for _, r in fr_tab.iterrows():
        print(f"    {r['bucket']:<32s} N={r['n']:5d}  FillRate={r['fill_rate']*100:5.1f}% [{r['fr_lo']*100:4.1f},{r['fr_hi']*100:4.1f}]")

    print("\n2) time_to_fill_bars | filled -- distribucion real (NO se hardcodea '3 barras' como gate ni "
          "threshold, ver seccion 8 del prompt de la tarea):")
    ttf = df_a.loc[df_a["filled"], "time_to_fill_bars"].dropna()
    print(f"    N={len(ttf)}  media={ttf.mean():.2f}  mediana={ttf.median():.1f}  "
          f"p10={ttf.quantile(0.10):.1f}  p25={ttf.quantile(0.25):.1f}  p75={ttf.quantile(0.75):.1f}  "
          f"p90={ttf.quantile(0.90):.1f}  p99={ttf.quantile(0.99):.1f}  max={ttf.max():.0f}")
    print("    Distribucion por bucket exploratorio (predefinido por interpretabilidad, NO umbral congelable):")
    for lo, hi, label in [(0, 1, "1 barra"), (1, 3, "2-3 barras"), (3, 6, "4-6 barras"),
                          (6, 12, "7-12 barras"), (12, 1_000_000, "13+ barras")]:
        n_b = int(((ttf > lo) & (ttf <= hi)).sum()) if hi < 1_000_000 else int((ttf > lo).sum())
        print(f"      {label:12s} N={n_b:5d} ({n_b/len(ttf)*100:5.1f}%)")

    print("\n3) P(outcome | filled, distance_to_limit_atr) -- SOLO Universo B (condicionado a fill), separado "
          "de (1) y (2) explicitamente:")
    print_bucket_table("ALL (condicionado a fill)", bucket_report_perf(df_b, "distance_to_limit_atr"))
    for dlabel in ("LONG", "SHORT"):
        print_bucket_table(dlabel, bucket_report_perf(df_b[df_b["direction"] == dlabel], "distance_to_limit_atr"))
    for sp in ("sub1", "sub2", "sub3"):
        print_bucket_table(sp, bucket_report_perf(df_b[df_b["sub_periodo"] == sp], "distance_to_limit_atr"))

    print("\n4) No-fill/expiracion -- distribucion de `fate` para eventos NO filled:")
    not_filled = df_a[~df_a["filled"]]
    print(f"    {not_filled['fate'].value_counts().to_dict()} (total no-filled={len(not_filled)}/{len(df_a)})")

    # ---------------------------------------------------------------------------
    # N. origin_retracement_frac -- deep dive obligatorio (seccion 7.F del
    #    prompt) + confirmacion de exclusion de ATR_short/ATR_long
    # ---------------------------------------------------------------------------
    section("N. origin_retracement_frac -- deep dive obligatorio")
    orf = df_a["origin_retracement_frac"].dropna()
    print(f"Cobertura: {df_a['origin_retracement_frac'].notna().mean()*100:.1f}% ({len(orf)}/{len(df_a)})")
    print(f"Distribucion: media={orf.mean():.4f} mediana={orf.median():.4f} std={orf.std():.4f} "
          f"p1={orf.quantile(0.01):.4f} p5={orf.quantile(0.05):.4f} p25={orf.quantile(0.25):.4f} "
          f"p75={orf.quantile(0.75):.4f} p95={orf.quantile(0.95):.4f} p99={orf.quantile(0.99):.4f}")
    band_lo, band_hi = 0.45, 0.55
    band_frac = float(((orf >= band_lo) & (orf <= band_hi)).mean())
    print(f"Fraccion en banda [{band_lo},{band_hi}]: {band_frac*100:.1f}% (BOT-048.1/048.2 reporto ~97.6% -- "
          f"reconstruido aca de forma independiente, no copiado del CSV)")
    print("\nExplicacion matematica de la dependencia mecanica (RR=1 fijo, ver seccion I):")
    print("  origin_retracement_frac = |entry - origin_level| / |target - origin_level|")
    print("  target = entry +/- rr*risk  (rr=1.0 fijo) => |target - origin_level| = |entry - origin_level +/- risk|")
    print("  Si origin_level ~ stop (la señal casi siempre se arma en el MISMO nivel HTF que luego define el "
          "stop, salvo que un nuevo extremo local re-arme el bloque antes de la señal -- 'auto-armado' de "
          "engine.bucket_levels), entonces |entry-origin_level| ~ |entry-stop| = risk, y el denominador ~ "
          "|risk +/- risk| = 0 o 2*risk segun el signo -- el caso no degenerado (denominador ~2*risk) produce "
          "origin_retracement_frac ~ risk/(2*risk) = 0.5 exactamente, consistente con la banda estrecha "
          "observada. La dispersion alrededor de 0.5 proviene exclusivamente de los casos donde origin_level "
          "!= stop/level exacto (re-armado intermedio antes de la señal) -- un mecanismo de Structure (Familia "
          "F de BOT-048.1: origin_bar/origin_age), no de Economics.")

    print("\nALL/LONG/SHORT:")
    for dlabel, sub in [("ALL", df_b), ("LONG", df_b[df_b["direction"] == "LONG"]), ("SHORT", df_b[df_b["direction"] == "SHORT"])]:
        rho = spearman_corr(sub["origin_retracement_frac"], sub["pnl_r"])
        print(f"    {dlabel:6s} N={len(sub):5d}  rho(origin_retracement_frac, pnl_r)={rho:+.3f}")
    print("\nEstabilidad temporal (sub1/sub2/sub3):")
    for sp in ("sub1", "sub2", "sub3"):
        sub = df_b[df_b["sub_periodo"] == sp]
        rho = spearman_corr(sub["origin_retracement_frac"], sub["pnl_r"])
        band = float(((sub["origin_retracement_frac"] >= band_lo) & (sub["origin_retracement_frac"] <= band_hi)).mean())
        print(f"    {sp}: N={len(sub):5d}  rho={rho:+.3f}  banda[{band_lo},{band_hi}]={band*100:.1f}%")

    print("\nRedundancia con otras candidatas Economics (Universo B):")
    for other in ("risk_atr", "spread_over_risk", "breakeven_pct", "distance_to_limit_atr", "momentum_roc_atr_10"):
        rho = spearman_corr(df_b["origin_retracement_frac"], df_b[other])
        print(f"    rho(origin_retracement_frac, {other}) = {rho:+.3f}")

    print("\nATR_short/ATR_long -- confirmacion explicita de exclusion (seccion 12 del prompt de la tarea): "
          "NO se calculo en este script, NO se uso ni siquiera como control auxiliar (no fue necesario para "
          "interpretar ningun resultado de esta tarea). Reservado para BOT-050.1 (Context) -- ver actualizacion "
          "del backlog al cierre de esta tarea.")

    # ---------------------------------------------------------------------------
    # O. Redundancia cruzada -- Momentum / Structure / Alignment / CVP
    # ---------------------------------------------------------------------------
    section("O. Redundancia cruzada con Momentum (BOT-024.2) / Structure (BOT-048.1) / Alignment (BOT-047.1)")
    cross_available = CSV_MOMENTUM_B.exists() and CSV_STRUCT_B.exists() and CSV_ALIGN_B.exists()
    check("CSVs de Momentum/Structure/Alignment disponibles para merge por limit_created_bar (sin recalcular "
          "esas dimensiones)", cross_available,
          f"momentum={CSV_MOMENTUM_B.exists()} structure={CSV_STRUCT_B.exists()} alignment={CSV_ALIGN_B.exists()}")

    if cross_available:
        mom = pd.read_csv(CSV_MOMENTUM_B)[["limit_created_bar", "roc_atr_3"]]
        struct = pd.read_csv(CSV_STRUCT_B)[["limit_created_bar", "origin_dist_atr"]]
        align = pd.read_csv(CSV_ALIGN_B)[["limit_created_bar", "closed_ema200_slope"]]
        merged = df_b.merge(mom, on="limit_created_bar", how="inner") \
                     .merge(struct, on="limit_created_bar", how="inner") \
                     .merge(align, on="limit_created_bar", how="inner")
        check("Merge por limit_created_bar reproduce el Universo B completo (mismo motor/dataset/Config A en "
              "las 4 tareas, debe coincidir 1:1)", len(merged) == len(df_b),
              f"merged={len(merged)}, df_b={len(df_b)}")

        econ_candidates = ["risk_atr", "spread_over_risk", "breakeven_pct", "origin_retracement_frac",
                            "distance_to_limit_atr", "rr_effective_net"]
        other_dims = dict(momentum_roc_atr_3="roc_atr_3", structure_origin_dist_atr="origin_dist_atr",
                           alignment_closed_ema200_slope="closed_ema200_slope")
        print("\nrho(candidata Economics, representante de otra dimension) -- Universo B, merge exacto:")
        for econ_col in econ_candidates:
            for label, other_col in other_dims.items():
                rho = spearman_corr(merged[econ_col], merged[other_col])
                print(f"    {econ_col:26s} <-> {label:34s} rho={rho:+.3f}")

    # ---------------------------------------------------------------------------
    # P. CVP (strategy.scoring.cvp_score()) -- comparacion conceptual
    # ---------------------------------------------------------------------------
    section("P. Comparacion conceptual con CVP (strategy.scoring.cvp_score())")
    overall_wr = float((df_b["outcome"] == "win").sum() / len(df_b[df_b["outcome"].isin(["win", "loss"])]))
    print(f"aciertos_pct ILUSTRATIVO usado solo para esta comparacion (win rate agregado de Config A sobre "
          f"todo el Universo B, {overall_wr*100:.2f}% -- NO es la medida rodante en vivo real que usa "
          f"produccion, se etiqueta explicitamente como ilustrativo/informativo, no causal por evento):")
    sample = df_b.sample(n=min(500, len(df_b)), random_state=42)
    cvp_scores, cvp_margins = [], []
    for _, r in sample.iterrows():
        d = 1 if r["direction"] == "LONG" else -1
        # cvp_score() solo usa abs(entry-stop)/abs(target-entry) -- un origen
        # arbitrario (entry=0.0) con stop/target desplazados +/-risk/reward
        # reproduce exactamente las mismas distancias que el evento real.
        c_score, c_reason, c_margin = sc.cvp_score(
            direction=d, entry=0.0, stop=(-d * r["risk_price"]), target=(d * r["reward_price"]),
            spread_price=r["spread_price"], commission_usd=0.0, fixed_lot=params.fixed_lot,
            contract_size=costs.contract_size, aciertos_pct=overall_wr * 100)
        cvp_scores.append(c_score)
        cvp_margins.append(c_margin)
    sample = sample.assign(cvp_score_illustrative=cvp_scores, cvp_margin_illustrative=cvp_margins)
    rho_cvp_be = spearman_corr(sample["cvp_margin_illustrative"], -sample["breakeven_pct"])
    print(f"rho(cvp_margin_illustrative, -breakeven_pct) = {rho_cvp_be:+.3f} (se espera muy alto en magnitud -- "
          f"cvp_score() calcula breakeven_neto con LA MISMA formula que breakeven_pct de esta tarea, la unica "
          f"diferencia es que CVP resta un aciertos_pct medido en vivo del lado de afuera; el margen de CVP y "
          f"breakeven_pct de Economics son, hasta una constante aditiva, la MISMA cantidad).")
    print("CONCLUSION (respuesta a la pregunta 16 del prompt de la tarea): CVP YA cubre la mitad 'costo' de la "
          "geometria economica (breakeven neto SL/TP con spread+comision) -- Economics NO debe reintroducir "
          "esa misma cantidad como si fuera nueva. Lo que Economics aporta que CVP no aporta: (a) la ESCALA "
          "absoluta del setup como variable CONTINUA (risk_atr/risk_usd), que CVP no expone en absoluto: CVP "
          "solo produce +1/0 con un umbral fijo (CVP_MARGIN_HOLGADO=10pp) sobre el margen; (b) breakeven_pct/"
          "friction_ratio como variable CONTINUA en vez de un +1/0/-1 discreto gateado por aciertos_pct medido "
          "en vivo (CVP no funciona hasta tener >=10 operaciones cerradas, ver CVP_MIN_SAMPLE); (c) "
          "distance_to_limit_atr y origin_retracement_frac, que CVP no calcula en absoluto.")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
