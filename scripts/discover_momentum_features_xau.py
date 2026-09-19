"""BOT-024.2 -- Momentum Feature Discovery, XAU (BTC bloqueado, ver seccion A).

Subtarea de BOT-024 (Signal Quality / Scoring 0-100). SOLO LECTURA /
DISCOVERY -- no construye MomentumScore, no asigna pesos, no activa gating,
no integra D1, no modifica strategy/, execution/, api/ ni panel/.

Pregunta que responde: de las propiedades observables del movimiento de
precio disponibles CAUSALMENTE en `limit_created_bar` (== `signal_bar` ==
`born_bar`, mismo hallazgo de BOT-024.1), ¿cuales muestran evidencia de
capturar Momentum predictivo en XAUUSD -- para probabilidad de fill (Universo
A, TODOS los LIMITS creados) y para desempeno de los trades cerrados
(Universo B, LIMITS que hicieron fill)?

BTC: bloqueado en esta ejecucion. Verificado en vivo (solo lectura, symbol
info, sin ordenes) contra la cuenta conectada: `resolve_symbol("BTCUSD")` es
AMBIGUO en este broker (BTCUSDc y BTCUSDTc matchean la base "BTCUSD" por
igual -- ver execution/src/mt5_utils.py:KNOWN_BASES/resolve_symbol). Ademas
no existe ningun dataset historico BTC en backtests/data/ ni una corrida
BOT-042/043/045-equivalente que haya validado alguna vez una configuracion
de estrategia (ema_periods/periodos_htf_min/buf_bp/rr) para BTC. Regla del
enunciado (#13): no inventar parametros BTC -- se documenta el bloqueo
explicitamente (seccion A) y se continua XAU normalmente, que es el activo
prioritario.

Metodologia (resumen; ver reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY.md):
  1. Corre strategy.engine.run_backtest (sin tocar) UNA sola vez, continuo,
     sobre backtests/data/XAUUSDc_M5_latest.parquet, "Config A" (misma que
     BOT-024.1/BOT-042/043/045).
  2. run_backtest() de produccion NO retiene un registro por cada LIMIT que
     nunca hizo fill (solo los CUENTA, Counters.n_none/n_skip_*) -- pero el
     Universo A de esta tarea (todos los LIMITS creados, para medir relacion
     con probabilidad de fill) necesita ese detalle. Se reimplementa aca un
     "shadow replay" que reproduce LINEA POR LINEA la misma logica causal de
     pending/open_pos/counters de run_backtest() (copiada de
     strategy/engine.py, no reinventada), y ADEMAS registra un evento por
     cada LIMIT (fate: PENDING_RESIDUAL/EXPIRED/FILLED_CLOSED/
     FILLED_OPEN_RESIDUAL).
  3. Se valida de forma EXHAUSTIVA (no muestral) que el shadow replay
     produce EXACTAMENTE los mismos Counters y las mismas N trades cerradas
     (mismos campos: entry/stop/target/exit/outcome/pnl_usd/pnl_r/nights)
     que run_backtest() REAL. Si hay una sola discrepancia, se detiene la
     ejecucion antes de interpretar nada (misma regla que
     scripts/evaluate_rsi_divergence_predictive.py).
  4. Features de Momentum (ROC/velocidad, EMA slope, persistencia/
     eficiencia, aceleracion, RSI extendido, volatilidad ATR) se calculan
     causalmente en `limit_created_bar` para CADA evento del Universo A.
     Reusa sin modificar: strategy.engine.ema(), strategy.scoring.rsi(),
     find_confirmed_pivots()/resolve_divergence()/divergence_detail().
     ATR (Wilder) no existe en produccion -- se reusa VERBATIM la
     implementacion ya usada en
     backtests/scripts/07_bot045_regime_dataset.py::atr_wilder (no se
     reinventa una formula nueva).
  5. Divergencia RSI (variante A=close, baseline ya validado en BOT-024.1)
     se recalcula con el mismo indice rapido (bisect) de
     scripts/audit_rsi_price_source.py, validado EXHAUSTIVAMENTE contra
     divergence_detail() real de produccion para cada evento.
  6. El resultado del trade (fill/no-fill, win/loss/timeout, pnl) se usa
     UNICAMENTE como label posterior -- nunca como insumo de una feature.

Uso:
    .venv/Scripts/python.exe scripts/discover_momentum_features_xau.py \
        > reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY-EVIDENCE.log

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

# rsi_gt80/rsi_lt20 son columnas constantes (todo False) en Universo B en este
# dataset (ver seccion J del reporte -- RSI nunca llega a esos extremos en
# limit_created_bar) -- corr() sobre una columna constante da 0/0, warning
# esperado y sin impacto (el resultado NaN se maneja explicitamente).
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/, para importar audit_rsi_price_source

import MetaTrader5 as mt5

from execution.src.mt5_utils import KNOWN_BASES, find_symbols, resolve_symbol
from strategy.costs import BrokerCosts
from strategy.engine import StrategyParams, _server_date, bucket_levels, ema, run_backtest
from strategy import scoring as sc
from audit_rsi_price_source import PivotIndex, _candidate_fast

DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
REPORTS_DIR = REPO_ROOT / "reports"

# Config A congelada -- misma que BOT-024.1/BOT-042/BOT-043/BOT-045. NO se
# optimiza ni se cambia ningun parametro de estrategia en esta tarea.
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

# --- Ventanas de features (predefinidas ANTES de mirar resultados) ---------
ROC_HORIZONS = [3, 5, 10, 20, 40, 60]
EMA_SLOPE_WINDOWS = [3, 5, 10, 20]
PERSIST_WINDOWS = [5, 10, 20]
ACCEL_PAIRS = [(3, 20), (5, 20), (10, 40)]  # ROC_rate(corto) - ROC_rate(largo); documentado en el reporte
RSI_DELTA_WINDOWS = [3, 5, 10, 20]
RSI_MAXMIN_WINDOW = 20
ATR_PERIOD_SHORT = 5
ATR_PERIOD_BASE = 14
ATR_PERIOD_LONG = 20
STREAK_SAFETY_CAP = 60  # tope de seguridad para current_streak, no una ventana con significado propio

SESSION_BOUNDS_UTC = [  # misma convencion ya usada en BOT-045 (07_bot045_regime_dataset.py)
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
# 0. ATR Wilder -- reusado VERBATIM de backtests/scripts/07_bot045_regime_dataset.py
#    (no existe en produccion; no se reinventa una formula nueva).
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
# 1. Shadow replay -- reproduce LINEA POR LINEA strategy/engine.py:run_backtest()
#    (pending/open_pos/counters), agregando el registro por-LIMIT que
#    produccion no retiene. Ver docstring del modulo.
# ---------------------------------------------------------------------------

def shadow_replay(time_utc, time_server, high, low, close, spread_pts, params: StrategyParams,
                   costs: BrokerCosts, ema_line, resistencia, soporte):
    n = len(close)
    buf = params.buf_bp / 10000.0

    armado_venta = False
    armado_compra = False
    pending: list[dict] = []
    open_pos: list[dict] = []

    limit_events: dict[int, dict] = {}   # born_bar -> evento (Universo A)
    shadow_closed: list[dict] = []       # trades cerrados (para paridad con produccion)

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

        # --- 1. resolver ABIERTAS ---
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

        # --- 2. evaluar PENDIENTES ---
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

        # --- 3. nueva señal -> encolar orden ---
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
# 2. estadisticas por cohorte (mismos utilitarios que BOT-024.1)
# ---------------------------------------------------------------------------

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
    """Spearman = Pearson sobre los rangos -- evita depender de scipy (no
    instalado en este entorno), sin cambiar el resultado matematico."""
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


def spearman_matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(method="average").corr(method="pearson")


def fmt_pct(x):
    return f"{x*100:5.1f}%" if not (x is None or (isinstance(x, float) and math.isnan(x))) else "  n/a"


def bucket_report_fill(df: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
    """Universo A: N / fill_rate / IC Wilson por bucket de cuantiles de `col`."""
    sub = df[[col, "filled"]].dropna(subset=[col])
    if len(sub) < 20 or sub[col].nunique() < 2:
        return pd.DataFrame()
    try:
        sub = sub.assign(bucket=pd.qcut(sub[col], q=q, duplicates="drop"))
    except ValueError:
        return pd.DataFrame()
    rows = []
    for b, g in sub.groupby("bucket", observed=True):
        n = len(g)
        wins = int(g["filled"].sum())
        lo, hi = wilson_ci(wins, n)
        rows.append(dict(bucket=str(b), n=n, fill_rate=wins / n, ci_lo=lo, ci_hi=hi))
    return pd.DataFrame(rows)


def bucket_report_perf(df: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
    """Universo B (cerrados win/loss/timeout): N / WR / Exp$ / ExpR / PF por bucket."""
    sub = df[[col, "outcome", "pnl_usd", "pnl_r"]].dropna(subset=[col])
    if len(sub) < 20 or sub[col].nunique() < 2:
        return pd.DataFrame()
    try:
        sub = sub.assign(bucket=pd.qcut(sub[col], q=q, duplicates="drop"))
    except ValueError:
        return pd.DataFrame()
    rows = []
    for b, g in sub.groupby("bucket", observed=True):
        n = len(g)
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        wr = wins / (wins + losses) if (wins + losses) else float("nan")
        gross_win = g.loc[g["pnl_usd"] > 0, "pnl_usd"].sum()
        gross_loss = -g.loc[g["pnl_usd"] < 0, "pnl_usd"].sum()
        pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
        rows.append(dict(bucket=str(b), n=n, win_rate=wr, exp_usd=g["pnl_usd"].mean(),
                          exp_r=g["pnl_r"].mean(), pf=pf))
    return pd.DataFrame(rows)


def print_bucket_table(title: str, dfb: pd.DataFrame, kind: str) -> None:
    print(f"\n  {title}")
    if dfb.empty:
        print("    (sin datos suficientes para bucketizar)")
        return
    if kind == "fill":
        for _, r in dfb.iterrows():
            print(f"    {r['bucket']:<28s} N={r['n']:5d}  fill_rate={fmt_pct(r['fill_rate'])} "
                  f"[{fmt_pct(r['ci_lo'])}-{fmt_pct(r['ci_hi'])}]")
    else:
        for _, r in dfb.iterrows():
            pf = f"{r['pf']:.2f}" if not math.isnan(r["pf"]) else "n/a"
            print(f"    {r['bucket']:<28s} N={r['n']:5d}  WR={fmt_pct(r['win_rate'])}  "
                  f"Exp$={r['exp_usd']:+7.2f}  ExpR={r['exp_r']:+.3f}  PF={pf}")


# ---------------------------------------------------------------------------
# 3. main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-024.2 -- Momentum Feature Discovery, XAU (BTC bloqueado, ver seccion A)")
    print("SOLO LECTURA/DISCOVERY. No se modifico ningun archivo de produccion. No se activa gating.")
    print("No se implementa MomentumScore. No se integra D1.\n")

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
          f"candidatos={btc_candidates} (se necesita EXACTAMENTE 1 para resolve_symbol sin ambiguedad), "
          f"archivos_dataset={[p.name for p in btc_data_files]}")
    print("CONCLUSION: la parte predictiva de BTC de BOT-024.2 queda BLOQUEADA y documentada -- "
          "no se descarga ni inventa ningun dataset/config BTC en esta tarea. XAU continua normalmente "
          "(activo prioritario, regla #1 del enunciado).")

    # --- B. Dataset XAU + costos --------------------------------------------
    section("B. Dataset XAU y costos (reusa lo ya usado por BOT-024.1/BOT-045)")
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
            ("entry_price", math.isclose(s["entry_price"], t.entry_price, rel_tol=1e-9, abs_tol=1e-9)),
            ("entry_price_adj", math.isclose(s["entry_price_adj"], t.entry_price_adj, rel_tol=1e-9, abs_tol=1e-9)),
            ("stop", math.isclose(s["stop"], t.stop, rel_tol=1e-9, abs_tol=1e-9)),
            ("target", math.isclose(s["target"], t.target, rel_tol=1e-9, abs_tol=1e-9)),
            ("exit_price", math.isclose(s["exit_price"], t.exit_price, rel_tol=1e-9, abs_tol=1e-9)),
            ("outcome", s["outcome"] == t.outcome),
            ("pnl_usd", math.isclose(s["pnl_usd"], t.pnl_usd, rel_tol=1e-9, abs_tol=1e-9)),
            ("pnl_r", (math.isnan(s["pnl_r"]) and math.isnan(t.pnl_r)) or math.isclose(s["pnl_r"], t.pnl_r, rel_tol=1e-9, abs_tol=1e-9)),
            ("nights_held", s["nights_held"] == t.nights_held),
        ]
        bad = [name for name, ok in checks if not ok]
        if bad:
            field_mismatches.append((t.signal_bar, bad))

    check(f"TODOS los {len(prod_trades)} trades cerrados: shadow replay == produccion en TODOS los campos "
          f"(entry/stop/target/exit/outcome/pnl_usd/pnl_r/nights_held) -- verificacion EXHAUSTIVA, no muestral",
          len(field_mismatches) == 0,
          f"comparaciones={len(prod_trades)}, discrepancias={len(field_mismatches)}"
          + (f", ejemplos={field_mismatches[:3]}" if field_mismatches else ""))

    if FAILURES:
        print("\n*** DETENIENDO: el shadow replay no reproduce exactamente la produccion. "
              "No se interpreta ningun resultado hasta resolver esto. ***")
        return 1

    print(f"\nParidad EXHAUSTIVA confirmada: {len(prod_trades)}/{len(prod_trades)} trades, "
          f"8/8 campos de counters -- el shadow replay es una reproduccion fiel de produccion.")
    print(f"Universo A (LIMITS creados en total): {len(limit_events)}")
    fate_counts = pd.Series([e["fate"] for e in limit_events.values()]).value_counts()
    print(f"Distribucion de fate: {fate_counts.to_dict()}")

    # --- E. Indicadores causales precomputados UNA vez ----------------------
    section("E. Indicadores causales precomputados (RSI/ATR/pivotes de divergencia)")
    rsi_values = sc.rsi(close, sc.RSI_PERIOD)
    print("RSI(14, close, Wilder) -- reusado de strategy.scoring.rsi(), sin modificar.")
    atr5 = atr_wilder(high, low, close, ATR_PERIOD_SHORT)
    atr14 = atr_wilder(high, low, close, ATR_PERIOD_BASE)
    atr20 = atr_wilder(high, low, close, ATR_PERIOD_LONG)
    print(f"ATR Wilder periodos {ATR_PERIOD_SHORT}/{ATR_PERIOD_BASE}/{ATR_PERIOD_LONG} -- reusado VERBATIM de "
          f"backtests/scripts/07_bot045_regime_dataset.py::atr_wilder (no existe en produccion, no se reinventa).")
    highs_full, lows_full = sc.find_confirmed_pivots(rsi_values, sc.DIVERGENCE_LB_LEFT, sc.DIVERGENCE_LB_RIGHT)
    lows_idx = PivotIndex(lows_full)
    highs_idx = PivotIndex(highs_full)
    print(f"Pivotes RSI (sin cambios respecto a produccion): {len(lows_full)} lows, {len(highs_full)} highs.")

    def cand(kind, price, idx, decision_bar):
        return _candidate_fast(kind, price, idx, decision_bar, sc.DIVERGENCE_RANGE_MIN, sc.DIVERGENCE_RANGE_MAX,
                                sc.DIVERGENCE_FRESH_BARS)

    def alignment_of(detail):
        if detail.resolved_state == sc.DIVERGENCE_STATE_NONE:
            return "NONE"
        if detail.resolved_state == sc.DIVERGENCE_STATE_CONFLICT:
            return "CONFLICT"
        return "ALIGNED" if detail.score == 1 else "OPPOSED"

    def active_cand(detail):
        if detail.resolved_state == sc.DIVERGENCE_STATE_BULLISH:
            return detail.bullish
        if detail.resolved_state == sc.DIVERGENCE_STATE_BEARISH:
            return detail.bearish
        return None

    PARITY_LOOKBACK = 300  # misma tecnica y misma justificacion que evaluate_rsi_divergence_predictive.py

    # --- F. Feature vector por evento del Universo A ------------------------
    section("F. Feature vector de Momentum, congelado en limit_created_bar, por cada LIMIT del Universo A")

    chunk = n_bars // 3

    def sub_periodo_of(bar_idx: int) -> str:
        if bar_idx < chunk:
            return "sub1"
        if bar_idx < 2 * chunk:
            return "sub2"
        return "sub3"

    rows = []
    parity_mismatches = []
    events_sorted = sorted(limit_events.values(), key=lambda e: e["born_bar"])
    for idx_ev, ev in enumerate(events_sorted):
        b = ev["born_bar"]
        d = ev["direction"]
        atr_i = atr14[b]

        feats = {}

        for h in ROC_HORIZONS:
            j = b - h
            if j >= 0 and atr_i and not math.isnan(atr_i) and atr_i > 0:
                feats[f"roc_atr_{h}"] = d * (close[b] - close[j]) / atr_i
            else:
                feats[f"roc_atr_{h}"] = np.nan

        for w in EMA_SLOPE_WINDOWS:
            j = b - w
            if j >= 0 and atr_i and not math.isnan(atr_i) and atr_i > 0:
                feats[f"ema_slope_atr_{w}"] = d * (ema_line[b] - ema_line[j]) / atr_i
            else:
                feats[f"ema_slope_atr_{w}"] = np.nan

        for w in PERSIST_WINDOWS:
            start = b - w + 1
            if start >= 1:
                deltas = close[start:b + 1] - close[start - 1:b]
                pct_fav = float(np.mean((deltas * d) > 0))
                gross = float(np.sum(np.abs(deltas)))
                net = close[b] - close[start - 1]
                feats[f"pct_favorable_{w}"] = pct_fav
                feats[f"efficiency_{w}"] = abs(net) / gross if gross > 0 else np.nan
                feats[f"efficiency_signed_{w}"] = d * net / gross if gross > 0 else np.nan
            else:
                feats[f"pct_favorable_{w}"] = np.nan
                feats[f"efficiency_{w}"] = np.nan
                feats[f"efficiency_signed_{w}"] = np.nan

        streak = 0
        k = b
        while k >= 1 and (close[k] - close[k - 1]) * d > 0 and streak < STREAK_SAFETY_CAP:
            streak += 1
            k -= 1
        feats["current_streak"] = streak

        for (sh, lo_h) in ACCEL_PAIRS:
            rs, rl = feats.get(f"roc_atr_{sh}"), feats.get(f"roc_atr_{lo_h}")
            if rs is not None and rl is not None and not math.isnan(rs) and not math.isnan(rl):
                feats[f"accel_{sh}_{lo_h}"] = rs / sh - rl / lo_h
            else:
                feats[f"accel_{sh}_{lo_h}"] = np.nan

        rsi_now = rsi_values[b]
        feats["rsi_now"] = rsi_now
        for w in RSI_DELTA_WINDOWS:
            j = b - w
            if j >= 0 and not math.isnan(rsi_values[j]) and not math.isnan(rsi_now):
                feats[f"rsi_delta_{w}"] = d * (rsi_now - rsi_values[j])
            else:
                feats[f"rsi_delta_{w}"] = np.nan
        feats["rsi_gt70"] = (rsi_now > 70) if not math.isnan(rsi_now) else np.nan
        feats["rsi_gt80"] = (rsi_now > 80) if not math.isnan(rsi_now) else np.nan
        feats["rsi_lt30"] = (rsi_now < 30) if not math.isnan(rsi_now) else np.nan
        feats["rsi_lt20"] = (rsi_now < 20) if not math.isnan(rsi_now) else np.nan

        ext_streak = 0
        if not math.isnan(rsi_now) and (rsi_now > 70 or rsi_now < 30):
            above = rsi_now > 70
            k = b
            while k >= 0 and not math.isnan(rsi_values[k]) and ((rsi_values[k] > 70) if above else (rsi_values[k] < 30)) \
                    and ext_streak < 200:
                ext_streak += 1
                k -= 1
        feats["rsi_extreme_streak"] = ext_streak

        lo_win = max(0, b - RSI_MAXMIN_WINDOW + 1)
        w_rsi = rsi_values[lo_win:b + 1]
        w_rsi = w_rsi[~np.isnan(w_rsi)]
        feats["rsi_max_20"] = float(w_rsi.max()) if len(w_rsi) else np.nan
        feats["rsi_min_20"] = float(w_rsi.min()) if len(w_rsi) else np.nan

        feats["atr14"] = atr_i
        feats["atr_pct"] = (atr_i / close[b] * 100.0) if atr_i and not math.isnan(atr_i) and close[b] else np.nan
        a5, a20 = atr5[b], atr20[b]
        feats["atr5_atr20_ratio"] = (a5 / a20) if a20 and not math.isnan(a20) and a20 > 0 and not math.isnan(a5) else np.nan

        # --- Divergencia (variante A=close, baseline BOT-024.1) + paridad exhaustiva ---
        bullish_A = cand("bullish", close, lows_idx, b)
        bearish_A = cand("bearish", close, highs_idx, b)
        detail_A = sc.resolve_divergence(d, bullish_A, bearish_A)

        w_start = max(0, b - PARITY_LOOKBACK)
        rsi_window = rsi_values[w_start:b + 1]
        close_window = close[w_start:b + 1]
        current_bar_window = b - w_start
        prod_detail = sc.divergence_detail(d, close_window, rsi_window, current_bar_window)
        if (prod_detail.resolved_state, prod_detail.resolution, prod_detail.score) != \
           (detail_A.resolved_state, detail_A.resolution, detail_A.score):
            parity_mismatches.append((b, prod_detail, detail_A))

        act_A = active_cand(detail_A)
        feats["div_alignment"] = alignment_of(detail_A)
        feats["div_age"] = act_A.age if act_A else np.nan

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

    check(f"Divergencia A congelada en limit_created_bar == divergence_detail() REAL de produccion en TODOS "
          f"los {len(events_sorted)} eventos del Universo A (verificacion EXHAUSTIVA, no muestral)",
          len(parity_mismatches) == 0,
          f"comparaciones={len(events_sorted)}, discrepancias={len(parity_mismatches)}"
          + (f", ejemplos={parity_mismatches[:3]}" if parity_mismatches else ""))
    if parity_mismatches:
        print("\n*** DETENIENDO INTERPRETACION: discrepancias de paridad en Divergencia. ***")
        return 1

    df_a = pd.DataFrame(rows)
    csv_a = REPORTS_DIR / "BOT-024.2-momentum-limits-xau.csv"
    df_a.to_csv(csv_a, index=False)
    print(f"\nCSV Universo A escrito: {csv_a} ({len(df_a)} filas)")

    df_b = df_a[df_a["fate"] == "FILLED_CLOSED"].copy()
    csv_b = REPORTS_DIR / "BOT-024.2-momentum-trades-xau.csv"
    df_b.to_csv(csv_b, index=False)
    print(f"CSV Universo B escrito: {csv_b} ({len(df_b)} filas)")

    n_dangling_pending = int((df_a["fate"] == "PENDING_RESIDUAL").sum())
    n_dangling_open = int((df_a["fate"] == "FILLED_OPEN_RESIDUAL").sum())
    print(f"\nFunnel: LIMITS creados={len(df_a)}  FILLED_CLOSED={len(df_b)}  EXPIRED={int((df_a['fate']=='EXPIRED').sum())} "
          f" PENDING_RESIDUAL={n_dangling_pending}  FILLED_OPEN_RESIDUAL={n_dangling_open}")

    feature_cols = [c for c in df_a.columns if c not in (
        "trade_id", "asset", "direction", "limit_created_bar", "entry_time_utc", "hour_utc", "session_utc",
        "weekday", "sub_periodo", "fate", "filled", "fill_bar", "exit_bar", "outcome", "pnl_usd", "pnl_r",
        "div_alignment")]

    # --- G. Screening: correlacion (Spearman) feature vs fill / vs pnl_r ----
    section("G. Screening -- correlacion Spearman (diagnostico, NO es el criterio final de seleccion)")
    print("Universo A: feature vs `filled` (0/1). Universo B: feature vs `pnl_r` (continuo, solo cerrados).")
    screen_rows = []
    for c in feature_cols:
        col_a = df_a[c].astype(float) if df_a[c].dtype == bool else df_a[c]
        rho_fill = spearman_corr(col_a, df_a["filled"].astype(float)) if col_a.notna().sum() > 30 else np.nan

        col_b = df_b[c].astype(float) if df_b[c].dtype == bool else df_b[c]
        rho_pnl = spearman_corr(col_b, df_b["pnl_r"]) if col_b.notna().sum() > 30 else np.nan
        screen_rows.append(dict(feature=c, rho_fill=rho_fill, rho_pnl_r=rho_pnl))
    screen_df = pd.DataFrame(screen_rows)
    screen_df["abs_rho_fill"] = screen_df["rho_fill"].abs()
    screen_df["abs_rho_pnl_r"] = screen_df["rho_pnl_r"].abs()

    print("\n-- Top 12 por |rho| vs fill (Universo A) --")
    print(screen_df.sort_values("abs_rho_fill", ascending=False).head(12)
          [["feature", "rho_fill"]].to_string(index=False))
    print("\n-- Top 12 por |rho| vs pnl_r (Universo B) --")
    print(screen_df.sort_values("abs_rho_pnl_r", ascending=False).head(12)
          [["feature", "rho_pnl_r"]].to_string(index=False))
    print("\n-- Tabla completa de screening (todas las features) --")
    print(screen_df[["feature", "rho_fill", "rho_pnl_r"]].to_string(index=False))

    shortlist = sorted(set(
        screen_df.sort_values("abs_rho_fill", ascending=False).head(8)["feature"].tolist() +
        screen_df.sort_values("abs_rho_pnl_r", ascending=False).head(8)["feature"].tolist()
    ))
    print(f"\nShortlist para deep-dive (union top-8 fill + top-8 pnl_r, por MAGNITUD de correlacion -- "
          f"screening, no clasificacion final): {shortlist}")

    # --- H. Deep dive: buckets, LONG/SHORT, temporal, bootstrap -------------
    section("H. Deep dive de la shortlist -- buckets, LONG/SHORT, estabilidad temporal, bootstrap")
    bootstrap_summary = []
    for feat in shortlist:
        print(f"\n--- {feat} ---")
        print_bucket_table("Universo A -- fill rate por quintil (agregado XAU)", bucket_report_fill(df_a, feat), "fill")
        print_bucket_table("Universo B -- desempeno por quintil (agregado XAU)", bucket_report_perf(df_b, feat), "perf")

        for dlabel in ("LONG", "SHORT"):
            sub_b = df_b[df_b["direction"] == dlabel]
            print_bucket_table(f"Universo B -- {dlabel}", bucket_report_perf(sub_b, feat), "perf")

        for sp in ("sub1", "sub2", "sub3"):
            sub_b = df_b[df_b["sub_periodo"] == sp]
            print_bucket_table(f"Universo B -- {sp}", bucket_report_perf(sub_b, feat), "perf")

        valid = df_b[[feat, "pnl_usd"]].dropna()
        if len(valid) >= 40 and valid[feat].nunique() >= 5:
            try:
                q = pd.qcut(valid[feat], q=5, duplicates="drop")
                labels = sorted(q.unique(), key=lambda iv: iv.left)
                top_label, bot_label = labels[-1], labels[0]
                top_vals = valid.loc[q == top_label, "pnl_usd"]
                bot_vals = valid.loc[q == bot_label, "pnl_usd"]
                lo_t, hi_t = bootstrap_mean_ci(top_vals.tolist())
                lo_b, hi_b = bootstrap_mean_ci(bot_vals.tolist())
                diff_boot = bootstrap_mean_ci((top_vals.reset_index(drop=True) -
                                                bot_vals.sample(n=len(top_vals), replace=True, random_state=42).reset_index(drop=True)).tolist()) \
                    if len(top_vals) and len(bot_vals) else (float("nan"), float("nan"))
                print(f"  Bootstrap 95% Exp$ quintil TOP (N={len(top_vals)}): [{lo_t:+.2f},{hi_t:+.2f}] "
                      f"mean={top_vals.mean():+.2f}")
                print(f"  Bootstrap 95% Exp$ quintil BOTTOM (N={len(bot_vals)}): [{lo_b:+.2f},{hi_b:+.2f}] "
                      f"mean={bot_vals.mean():+.2f}")
                bootstrap_summary.append(dict(feature=feat, n_top=len(top_vals), n_bot=len(bot_vals),
                                               top_mean=top_vals.mean(), top_ci=(lo_t, hi_t),
                                               bot_mean=bot_vals.mean(), bot_ci=(lo_b, hi_b)))
            except (ValueError, IndexError) as e:
                print(f"  (bootstrap no aplicable: {e})")

    # --- I. Redundancia -------------------------------------------------------
    section("I. Redundancia -- correlacion Spearman entre features (Universo B)")
    corr_mat = spearman_matrix(df_b[feature_cols].apply(lambda s: s.astype(float) if s.dtype == bool else s))
    pairs = []
    for i, a in enumerate(feature_cols):
        for bcol in feature_cols[i + 1:]:
            r = corr_mat.loc[a, bcol]
            if not math.isnan(r) and abs(r) >= 0.8:
                pairs.append((a, bcol, r))
    pairs.sort(key=lambda p: -abs(p[2]))
    print(f"Pares con |rho|>=0.8 (redundancia fuerte): {len(pairs)}")
    for a, bcol, r in pairs[:40]:
        print(f"  {a:24s} <-> {bcol:24s}  rho={r:+.3f}")

    named_pairs = [
        ("roc_atr_10", "ema_slope_atr_10"), ("roc_atr_20", "ema_slope_atr_20"),
        ("roc_atr_10", "rsi_delta_10"), ("roc_atr_20", "rsi_delta_20"),
        ("pct_favorable_10", "efficiency_10"), ("pct_favorable_20", "efficiency_20"),
        ("roc_atr_5", "roc_atr_10"), ("roc_atr_10", "roc_atr_20"), ("roc_atr_20", "roc_atr_40"),
        ("ema_slope_atr_5", "ema_slope_atr_10"), ("ema_slope_atr_10", "ema_slope_atr_20"),
    ]
    print("\nComparaciones nombradas explicitamente en el enunciado (duplicados conceptuales candidatos):")
    for a, bcol in named_pairs:
        if a in corr_mat.index and bcol in corr_mat.columns:
            print(f"  {a:24s} <-> {bcol:24s}  rho={corr_mat.loc[a, bcol]:+.3f}")

    # --- J. RSI extremo -- continuacion vs agotamiento (XAU) -----------------
    section("J. RSI extremo -- continuacion vs agotamiento (solo XAU; BTC bloqueado, ver A)")
    gt80 = df_b["rsi_gt80"] == True  # noqa: E712 -- NaN == True es False, evita el warning de fillna+astype en object dtype
    gt70 = df_b["rsi_gt70"] == True  # noqa: E712
    lt20 = df_b["rsi_lt20"] == True  # noqa: E712
    lt30 = df_b["rsi_lt30"] == True  # noqa: E712
    df_b["rsi_extreme_state"] = np.select(
        [gt80, gt70 & ~gt80, lt20, lt30 & ~lt20],
        ["gt80", "gt70_le80", "lt20", "lt30_ge20"], default="neutral")
    for state, g in df_b.groupby("rsi_extreme_state"):
        n = len(g)
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        wr = wins / (wins + losses) if (wins + losses) else float("nan")
        print(f"  rsi_state={state:12s} N={n:5d} WR={fmt_pct(wr)} Exp$={g['pnl_usd'].mean():+7.2f} "
              f"ExpR={g['pnl_r'].mean():+.3f}")
    print_bucket_table("rsi_extreme_streak (todos los eventos, no solo extremos) -- Universo B",
                        bucket_report_perf(df_b, "rsi_extreme_streak", q=4), "perf")

    # --- K. Interaccion Divergencia OPPOSED x Momentum fuerte/debil -----------
    section("K. Interaccion Divergencia (OPPOSED) x Momentum (roc_atr_10) -- agotamiento/contradiccion")
    opp = df_b[df_b["div_alignment"] == "OPPOSED"].copy()
    if len(opp) >= 20:
        med = df_b["roc_atr_10"].median()
        opp["momentum_bucket"] = np.where(opp["roc_atr_10"] >= med, "fuerte(>=mediana_global)", "debil(<mediana_global)")
        for mb, g in opp.groupby("momentum_bucket"):
            n = len(g)
            wins = int((g["outcome"] == "win").sum())
            losses = int((g["outcome"] == "loss").sum())
            wr = wins / (wins + losses) if (wins + losses) else float("nan")
            print(f"  OPPOSED x {mb:26s} N={n:4d} WR={fmt_pct(wr)} Exp$={g['pnl_usd'].mean():+7.2f}")
    else:
        print(f"  N insuficiente en OPPOSED (N={len(opp)}) para esta interaccion.")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
