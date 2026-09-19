"""BOT-024.1 -- Evaluacion predictiva A/B de Divergencia RSI (subtarea de
BOT-024, Signal Quality / Scoring 0-100). SOLO LECTURA sobre produccion: no
modifica strategy/scoring.py, strategy/engine.py, strategy/live_signal.py,
execution/, la API ni el panel. No elige A o B. No implementa Momentum ni
integra D1. No activa ningun gate de entrada.

Pregunta que responde: dado el universo real de trades que el motor de
estrategia (strategy.engine.run_backtest, sin tocar) genero sobre el
dataset historico ya existente, ¿la Divergencia RSI disponible
CAUSALMENTE en la barra exacta en que se crea el LIMIT (`signal_bar` ==
`born_bar` en este motor -- ver seccion "Definiciones" mas abajo) dice algo
sobre el resultado posterior del trade?

Metodologia (resumen; ver reports/BOT-024.1-RSI-DIVERGENCE-PREDICTIVE.md
para el detalle completo):
  1. Corre strategy.engine.run_backtest UNA sola vez, continuo, sobre las
     100505 velas de backtests/data/XAUUSDc_M5_latest.parquet, con "Config A"
     (EMA=12, HTF=800min, buf=0.4bp, RR=1.0) -- la misma configuracion que
     BOT-042/043/045 ya tratan como "la configuracion real del bot" para
     analisis de backtest (ver backtests/scripts/07_bot045_regime_dataset.py).
  2. Para cada trade CERRADO (ver funnel), congela Divergencia A (close) y
     Divergencia B (low/high) en decision_bar = t.signal_bar, usando
     EXCLUSIVAMENTE datos disponibles hasta esa barra (misma tecnica de
     indice con bisect ya validada en scripts/audit_rsi_price_source.py).
  3. Valida de forma EXHAUSTIVA (no muestral) que la Variante A calculada
     aca coincide con divergence_detail() REAL de strategy/scoring.py para
     cada uno de los trades evaluables.
  4. El resultado del trade (win/loss/timeout, pnl_usd, pnl_r) se usa
     UNICAMENTE como label posterior -- nunca como insumo de la feature.

Uso:
    .venv/Scripts/python.exe scripts/evaluate_rsi_divergence_predictive.py \
        > reports/BOT-024.1-RSI-DIVERGENCE-PREDICTIVE-EVIDENCE.log

Requiere MT5 corriendo (solo lectura, mismo patron que
backtests/scripts/07_bot045_regime_dataset.py::get_live_costs -- no coloca
ni cancela ninguna orden) para los costos reales de swap/comision/spread
usados en el calculo de PnL neto.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/, para importar audit_rsi_price_source

import MetaTrader5 as mt5

from execution.src.mt5_utils import resolve_symbol
from strategy.costs import BrokerCosts
from strategy.engine import StrategyParams, run_backtest
from strategy.scoring import (
    DIVERGENCE_FRESH_BARS, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT, DIVERGENCE_RANGE_MAX,
    DIVERGENCE_RANGE_MIN, DIVERGENCE_STATE_BEARISH, DIVERGENCE_STATE_BULLISH,
    DIVERGENCE_STATE_CONFLICT, DIVERGENCE_STATE_NONE, RSI_PERIOD,
    divergence_detail as prod_divergence_detail, find_confirmed_pivots, resolve_divergence, rsi,
)
# Reusa (sin duplicar) el indice rapido validado en la auditoria previa (BOT-024,
# reports/AUDIT-RSI-PRICE-SOURCE.md seccion 3: 0 discrepancias contra el calculo
# identico a produccion).
from audit_rsi_price_source import PivotIndex, _candidate_fast

DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
REPORTS_DIR = REPO_ROOT / "reports"

# Config A congelada -- misma que BOT-042/BOT-043/BOT-045 (ver
# backtests/scripts/07_bot045_regime_dataset.py). NO se optimiza ni se
# cambia ningun parametro de estrategia en esta tarea.
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

AGE_BUCKETS = [(0, 2), (3, 5), (6, 8), (9, 10)]  # predefinidos ANTES de mirar resultados (0..10 inclusive, vigencia real)


# ---------------------------------------------------------------------------
# utilidades de reporte
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# 1. costos reales (mismo patron que backtests/scripts/07_bot045_regime_dataset.py)
# ---------------------------------------------------------------------------

def get_live_costs(symbol: str) -> BrokerCosts:
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar {symbol!r}: {mt5.last_error()}")
    si = mt5.symbol_info(symbol)
    mt5.shutdown()
    return BrokerCosts(
        point=si.point, contract_size=si.trade_contract_size, tick_value=si.trade_tick_value,
        tick_size=si.trade_tick_size, swap_long_points=si.swap_long, swap_short_points=si.swap_short,
        commission_per_lot=0.0, triple_swap_weekday=2, spread_fallback_points=si.spread,
    )


# ---------------------------------------------------------------------------
# 2. estadisticas por cohorte
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(center - half, 0.0), min(center + half, 1.0))


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def cluster_bootstrap_ci(event_ids: list, values: list[float], n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    """Bootstrap por EVENTO de divergencia (no por trade) -- ver seccion 7:
    varios trades pueden compartir el mismo pivote/evento, esto evita tratar
    esas observaciones como independientes."""
    groups: dict = {}
    for e, v in zip(event_ids, values):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        groups.setdefault(e, []).append(v)
    keys = list(groups.keys())
    if not keys:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for b in range(n_boot):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        pooled = []
        for k in sampled:
            pooled.extend(groups[k])
        means[b] = np.mean(pooled) if pooled else np.nan
    lo, hi = np.nanpercentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def cohort_stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return dict(n=0, pct=0.0, wins=0, losses=0, win_rate=float("nan"),
                    pnl_total_usd=0.0, pnl_avg_usd=float("nan"), expectancy_r=float("nan"),
                    pnl_total_r=0.0, profit_factor=float("nan"),
                    wilson_lo=float("nan"), wilson_hi=float("nan"))
    wins = sum(1 for r in rows if r["outcome"] == "win")
    losses = sum(1 for r in rows if r["outcome"] == "loss")
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else float("nan")
    wlo, whi = wilson_ci(wins, wins + losses) if (wins + losses) > 0 else (float("nan"), float("nan"))
    pnl_usd = [r["pnl_usd"] for r in rows if r["pnl_usd"] is not None]
    pnl_r = [r["pnl_r"] for r in rows if r["pnl_r"] is not None and not math.isnan(r["pnl_r"])]
    pnl_total_usd = sum(pnl_usd) if pnl_usd else 0.0
    pnl_avg_usd = pnl_total_usd / len(pnl_usd) if pnl_usd else float("nan")
    expectancy_r = sum(pnl_r) / len(pnl_r) if pnl_r else float("nan")
    pnl_total_r = sum(pnl_r) if pnl_r else 0.0
    gross_profit = sum(p for p in pnl_usd if p > 0)
    gross_loss = -sum(p for p in pnl_usd if p < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("nan")
    return dict(n=n, wins=wins, losses=losses, win_rate=win_rate,
                wilson_lo=wlo, wilson_hi=whi,
                pnl_total_usd=pnl_total_usd, pnl_avg_usd=pnl_avg_usd,
                expectancy_r=expectancy_r, pnl_total_r=pnl_total_r, profit_factor=profit_factor)


def fmt_stats(label: str, s: dict, total_n: int) -> str:
    pct = 100.0 * s["n"] / total_n if total_n else 0.0
    return (f"{label:22s} N={s['n']:5d} ({pct:5.1f}%)  WR={s['win_rate']*100:5.1f}% "
            f"[{s['wilson_lo']*100:5.1f}-{s['wilson_hi']*100:5.1f}]  "
            f"PnL=${s['pnl_total_usd']:+10.2f}  Exp/trade=${s['pnl_avg_usd']:+7.2f}  "
            f"ExpR={s['expectancy_r']:+.3f}  PF={s['profit_factor']:.2f}" if s["n"] > 0 else
            f"{label:22s} N=0")


# ---------------------------------------------------------------------------
# 3. main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-024.1 -- Evaluacion predictiva A/B de Divergencia RSI")
    print("SOLO LECTURA. No se modifico ningun archivo de produccion. No se activa gating. No se elige A/B.\n")

    # --- 1. Inspeccion / definiciones -------------------------------------------------
    section("A. Definiciones (signal_bar / limit_created_bar / fill_bar / exit_bar)")
    print("strategy/engine.py:Trade -- campos reales:")
    print("  signal_bar: barra donde se genera la señal (cruce EMA con armado ya activo)")
    print("  born_bar:   barra en la que la orden LIMIT se encola en `pending` (run_backtest linea ~395)")
    print("  entry_bar:  barra en la que el LIMIT hace fill (precio toca `entry`)")
    print("  exit_bar:   barra en la que el trade cierra (SL/TP/timeout)")
    print("run_backtest() asigna signal_bar=born_bar=i EN LA MISMA ITERACION donde nace la señal")
    print("(ver strategy/engine.py: 'trades.append(Trade(..., signal_bar=pos[\"born_bar\"], born_bar=pos[\"born_bar\"], ...))').")
    print("En produccion (execution/src/bot.py:process_closed_bar), el LIMIT se coloca SINCRONICAMENTE")
    print("en la misma barra que la señal (sin barra de demora) -- misma semantica.")
    print("CONCLUSION: limit_created_bar == signal_bar == born_bar en esta arquitectura (se demuestra")
    print("empiricamente mas abajo con una assertion sobre TODOS los trades). fill_bar = entry_bar")
    print("(puede ser >= signal_bar; ver funnel). exit_bar es el cierre.")
    print("\nNOTA IMPORTANTE: backtests/scripts/07_bot045_regime_dataset.py (BOT-045, otro proposito --")
    print("regimen de mercado) congela sus features EN entry_bar (fill), no en signal_bar. Esta tarea")
    print("(BOT-024.1) usa DELIBERADAMENTE signal_bar/limit_created_bar, tal como pide el enunciado --")
    print("los datasets NO son intercambiables, tienen anclas causales distintas.")

    # --- 2. dataset + costos -----------------------------------------------------------
    section("B. Dataset y costos")
    print(f"Dataset reusado (no se descargo ni invento nada nuevo): {DATA_PATH}")
    df = pd.read_parquet(DATA_PATH)
    print(f"  {len(df)} barras M5, {pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. "
          f"{pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    symbol = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(symbol)
    print(f"Costos en vivo ({symbol}): point={costs.point} tick_value={costs.tick_value} "
          f"tick_size={costs.tick_size} contract_size={costs.contract_size} "
          f"swap_long={costs.swap_long_points} swap_short={costs.swap_short_points} "
          f"commission_per_lot={costs.commission_per_lot}")

    time_utc = df["time_utc"].to_numpy(dtype=np.int64)
    time_server = df["time_server"].to_numpy(dtype=np.int64)  # timestamp de servidor SIN corregir (swap rollover)
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    spread_pts = df["spread"].to_numpy(dtype=float)
    n_bars = len(close)

    params = StrategyParams(**CONFIG_A, **SHARED)
    print(f"\nConfig A (congelada, BOT-042/043/045): {CONFIG_A}")
    print(f"Params compartidos: {SHARED}")

    # --- 3. correr el motor UNA vez, continuo (sin tocar strategy/engine.py) -----------
    result = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts, params, costs)
    trades = result.trades
    counters = result.counters
    print(f"\nrun_backtest() completo: {len(trades)} trades cerrados en la lista `trades` "
          f"(counters={counters})")

    # --- 4. Funnel -----------------------------------------------------------------
    section("C. Funnel (señales -> LIMITS -> fills -> cerrados/evaluables)")
    n_signals = counters.n_sig
    n_discard_stop = counters.n_skip_stop
    n_discard_conc = counters.n_skip_concurrency
    n_limits_created = n_signals - n_discard_stop - n_discard_conc
    n_fill = counters.n_fill
    n_expired_unfilled = counters.n_none
    n_dangling_pending = n_limits_created - n_fill - n_expired_unfilled
    n_closed = len(trades)
    n_dangling_open = n_fill - n_closed

    print(f"señales generadas (armado+cruce EMA):           {n_signals}")
    print(f"  descartadas -- stop del lado incorrecto:      -{n_discard_stop}")
    print(f"  descartadas -- limite de concurrencia:        -{n_discard_conc}")
    print(f"LIMITS creados (encolados en `pending`):         {n_limits_created}")
    print(f"  ejecutados (fill):                              {n_fill}")
    print(f"  expirados sin fill (tpAntes/muerto/caduca):    -{n_expired_unfilled}")
    print(f"  aun pendientes al final del dataset (residual): {n_dangling_pending}  <- efecto de borde, no se evaluan")
    print(f"Trades ejecutados (fill):                         {n_fill}")
    print(f"  cerrados (win/loss/timeout):                    {n_closed}")
    print(f"  aun abiertos al final del dataset (residual):   {n_dangling_open}  <- efecto de borde, no se evaluan")
    print(f"TRADES CERRADOS/EVALUABLES (universo de este analisis): {n_closed}")

    check("no hay attrition oculta: LIMITS creados = fill + expirados + pendientes residuales",
          n_limits_created == n_fill + n_expired_unfilled + n_dangling_pending,
          f"{n_limits_created} == {n_fill}+{n_expired_unfilled}+{n_dangling_pending}")
    check("no hay attrition oculta: fills = cerrados + abiertos residuales",
          n_fill == n_closed + n_dangling_open,
          f"{n_fill} == {n_closed}+{n_dangling_open}")
    check("todos los trades cerrados tienen signal_bar == born_bar (limit_created_bar bien definido)",
          all(t.signal_bar == t.born_bar for t in trades),
          f"verificado sobre los {len(trades)} trades")
    check("todos los trades cerrados tienen entry_bar (fill) no-None -- 'trades' solo contiene fills",
          all(t.entry_bar is not None for t in trades), f"verificado sobre {len(trades)} trades")
    check("todos los trades cerrados tienen outcome win/loss/timeout (resueltos)",
          all(t.outcome in ("win", "loss", "timeout") for t in trades), f"verificado sobre {len(trades)} trades")

    # --- 5. Divergencia causal por trade (A y B) + verificacion de paridad exhaustiva ---
    section("D. Divergencia A/B congelada en limit_created_bar + verificacion de paridad")

    rsi_values = rsi(close, RSI_PERIOD)
    highs_full, lows_full = find_confirmed_pivots(rsi_values, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
    lows_idx = PivotIndex(lows_full)
    highs_idx = PivotIndex(highs_full)
    print(f"Pivotes RSI globales (sin cambios respecto a produccion): {len(lows_full)} lows, {len(highs_full)} highs")

    def cand(kind, price, idx, decision_bar):
        return _candidate_fast(kind, price, idx, decision_bar, DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX, DIVERGENCE_FRESH_BARS)

    # Ventana local para el llamado EXACTO a produccion (divergence_detail real):
    # find_confirmed_pivots() es puramente local (un pivote en bar i depende solo
    # de rsi_values[i-lbL:i+lbR+1]), y _most_recent_fresh()/_prior_in_range() nunca
    # miran mas atras que range_max+fresh_bars+lbR desde decision_bar (~75 barras
    # con los defaults). divergence_detail() de produccion internamente hace
    # rsi_values[:current_bar+1] -- SIN acotar por afuera, ese slice reescanea
    # desde el bar 0 en cada llamado (costo O(decision_bar), impracticable llamado
    # ~2500 veces sobre un dataset de 100k barras). Se le pasa una VENTANA de los
    # MISMOS rsi_values ya calculados globalmente (no se recalcula RSI -- eso si
    # cambiaria el valor, RSI es recursivo/no local) recortada a las ultimas
    # `PARITY_LOOKBACK` barras antes de decision_bar: resultado matematicamente
    # identico (ya validado en reports/AUDIT-RSI-PRICE-SOURCE.md seccion 3 que el
    # indice rapido, que SI usa el array completo de pivotes, coincide exactamente
    # con el calculo lento), solo evita el rescan O(n) innecesario mas alla de lo
    # que el algoritmo puede llegar a usar.
    PARITY_LOOKBACK = 300

    parity_mismatches = []
    rows: list[dict] = []
    for i, t in enumerate(trades):
        decision_bar = t.signal_bar
        direction = t.direction

        bullish_A = cand("bullish", close, lows_idx, decision_bar)
        bearish_A = cand("bearish", close, highs_idx, decision_bar)
        detail_A = resolve_divergence(direction, bullish_A, bearish_A)

        # paridad EXHAUSTIVA contra produccion real (no muestral: los ~2-3k trades
        # se comparan TODOS, no una muestra) -- ver nota de PARITY_LOOKBACK arriba.
        w_start = max(0, decision_bar - PARITY_LOOKBACK)
        rsi_window = rsi_values[w_start:decision_bar + 1]
        close_window = close[w_start:decision_bar + 1]
        current_bar_window = decision_bar - w_start
        prod_detail = prod_divergence_detail(direction, close_window, rsi_window, current_bar_window)
        if (prod_detail.resolved_state, prod_detail.resolution, prod_detail.score, prod_detail.reason) != \
           (detail_A.resolved_state, detail_A.resolution, detail_A.score, detail_A.reason):
            parity_mismatches.append((i, decision_bar, prod_detail, detail_A))

        bullish_B = cand("bullish", low, lows_idx, decision_bar)
        bearish_B = cand("bearish", high, highs_idx, decision_bar)
        detail_B = resolve_divergence(direction, bullish_B, bearish_B)

        def alignment_of(detail):
            if detail.resolved_state == DIVERGENCE_STATE_NONE:
                return "NONE"
            if detail.resolved_state == DIVERGENCE_STATE_CONFLICT:
                return "CONFLICT"
            return "ALIGNED" if detail.score == 1 else "OPPOSED"

        def active_cand(detail):
            if detail.resolved_state == DIVERGENCE_STATE_BULLISH:
                return detail.bullish
            if detail.resolved_state == DIVERGENCE_STATE_BEARISH:
                return detail.bearish
            return None

        act_A = active_cand(detail_A)
        act_B = active_cand(detail_B)

        def event_id(kind_detail, act):
            if act is None:
                return None
            return f"{act.kind}|{act.pivot_bar}|{act.prior_pivot_bar}|{act.confirmation_bar}"

        rows.append({
            "trade_id": f"T{i:05d}",
            "direction": "LONG" if direction > 0 else "SHORT",
            "signal_bar": t.signal_bar, "limit_created_bar": t.signal_bar,
            "fill_bar": t.entry_bar, "exit_bar": t.exit_bar,
            "entry_time_utc": datetime.fromtimestamp(int(time_utc[t.signal_bar]), tz=timezone.utc).isoformat(),
            "entry": t.entry_price, "stop": t.stop, "target": t.target, "exit_price": t.exit_price,
            "outcome": t.outcome, "pnl_usd": t.pnl_usd, "pnl_r": t.pnl_r, "nights_held": t.nights_held,
            "A_state": detail_A.resolved_state, "A_resolution": detail_A.resolution,
            "A_alignment": alignment_of(detail_A),
            "A_pivot_bar": act_A.pivot_bar if act_A else None,
            "A_confirmation_bar": act_A.confirmation_bar if act_A else None,
            "A_prior_pivot_bar": act_A.prior_pivot_bar if act_A else None,
            "A_age": act_A.age if act_A else None,
            "A_bullish_active": bullish_A is not None, "A_bearish_active": bearish_A is not None,
            "A_event_id": event_id("A", act_A),
            "B_state": detail_B.resolved_state, "B_resolution": detail_B.resolution,
            "B_alignment": alignment_of(detail_B),
            "B_pivot_bar": act_B.pivot_bar if act_B else None,
            "B_confirmation_bar": act_B.confirmation_bar if act_B else None,
            "B_prior_pivot_bar": act_B.prior_pivot_bar if act_B else None,
            "B_age": act_B.age if act_B else None,
            "B_bullish_active": bullish_B is not None, "B_bearish_active": bearish_B is not None,
            "B_event_id": event_id("B", act_B),
        })

        # tercio cronologico por INDICE de decision_bar (mismo criterio de "cortes oficiales"
        # que backtests/scripts/04_run_robustness.py/05_run_rr_isolation.py/07_bot045..., pero
        # anclado a decision_bar en vez de entry_bar -- documentado explicitamente).
        chunk = n_bars // 3
        if decision_bar < chunk:
            rows[-1]["sub_periodo"] = "sub1"
        elif decision_bar < 2 * chunk:
            rows[-1]["sub_periodo"] = "sub2"
        else:
            rows[-1]["sub_periodo"] = "sub3"

    check(f"Variante A (indice rapido) == divergence_detail() REAL de produccion en TODOS los "
          f"{len(trades)} trades evaluables (verificacion EXHAUSTIVA, no muestral)",
          len(parity_mismatches) == 0,
          f"comparaciones={len(trades)}, discrepancias={len(parity_mismatches)}"
          + (f", ejemplos={parity_mismatches[:3]}" if parity_mismatches else ""))
    if parity_mismatches:
        print("\n*** DETENIENDO INTERPRETACION PREDICTIVA: hay discrepancias de paridad en Variante A ***")
        return 1

    df_trades = pd.DataFrame(rows)
    csv_path = REPORTS_DIR / "BOT-024.1-RSI-DIVERGENCE-PREDICTIVE.csv"
    df_trades.to_csv(csv_path, index=False)
    print(f"\nCSV escrito: {csv_path} ({len(df_trades)} filas)")

    # --- 6. Baseline -----------------------------------------------------------------
    section("E. Baseline (todos los trades evaluables)")
    baseline = cohort_stats(rows)
    print(fmt_stats("BASELINE (todos)", baseline, len(rows)))

    # --- 7. Cohortes A y B -------------------------------------------------------------
    def cohorts_by(col: str) -> dict:
        out = {}
        for state in ("ALIGNED", "OPPOSED", "NONE", "CONFLICT"):
            out[state] = cohort_stats([r for r in rows if r[col] == state])
        return out

    section("F. Variante A (close) -- cohortes ALIGNED/OPPOSED/NONE/CONFLICT")
    cohorts_A = cohorts_by("A_alignment")
    for k, s in cohorts_A.items():
        print(fmt_stats(f"A={k}", s, len(rows)))

    section("G. Variante B (low/high) -- cohortes ALIGNED/OPPOSED/NONE/CONFLICT")
    cohorts_B = cohorts_by("B_alignment")
    for k, s in cohorts_B.items():
        print(fmt_stats(f"B={k}", s, len(rows)))

    # --- 8. Matriz A x B ---------------------------------------------------------------
    section("H. Matriz A x B")
    states = ["ALIGNED", "OPPOSED", "NONE", "CONFLICT"]
    matrix_cells = {}
    header = "A\\B".ljust(10) + "".join(s.rjust(12) for s in states)
    print(header)
    for sa in states:
        counts_row = []
        for sb in states:
            cell_rows = [r for r in rows if r["A_alignment"] == sa and r["B_alignment"] == sb]
            s = cohort_stats(cell_rows)
            matrix_cells[(sa, sb)] = s
            counts_row.append(s["n"])
        print(sa.ljust(10) + "".join(str(c).rjust(12) for c in counts_row))

    print("\nDetalle de celdas con N>0 (N / WR% / Exp$ / PF):")
    for sa in states:
        for sb in states:
            s = matrix_cells[(sa, sb)]
            if s["n"] > 0:
                wr = f"{s['win_rate']*100:.1f}%" if not math.isnan(s["win_rate"]) else "n/a"
                pf = f"{s['profit_factor']:.2f}" if not math.isnan(s["profit_factor"]) else "n/a"
                print(f"  A={sa:9s} B={sb:9s}  N={s['n']:4d}  WR={wr:>6s}  Exp/trade=${s['pnl_avg_usd']:+7.2f}  PF={pf}")

    check("suma de la matriz A x B == total de trades evaluables",
          sum(c["n"] for c in matrix_cells.values()) == len(rows),
          f"suma={sum(c['n'] for c in matrix_cells.values())}, total={len(rows)}")

    # --- 9. Dependencia por evento (clustering) ---------------------------------------
    section("I. Dependencia por evento de divergencia (evitar pseudorreplicacion)")

    def event_clustering(col_event: str, col_alignment: str):
        active_rows = [r for r in rows if r[col_alignment] in ("ALIGNED", "OPPOSED") and r[col_event] is not None]
        events: dict = {}
        for r in active_rows:
            events.setdefault(r[col_event], []).append(r["trade_id"])
        counts = [len(v) for v in events.values()]
        return {
            "n_trades": len(active_rows),
            "n_events": len(events),
            "max_trades_por_evento": max(counts) if counts else 0,
            "mediana_trades_por_evento": float(np.median(counts)) if counts else 0.0,
        }

    clus_A = event_clustering("A_event_id", "A_alignment")
    clus_B = event_clustering("B_event_id", "B_alignment")
    print(f"Variante A: {clus_A}")
    print(f"Variante B: {clus_B}")
    check("clustering reportado explicitamente (N trades vs N eventos unicos)",
          clus_A["n_events"] <= clus_A["n_trades"] and clus_B["n_events"] <= clus_B["n_trades"],
          f"A: {clus_A['n_events']} eventos / {clus_A['n_trades']} trades; "
          f"B: {clus_B['n_events']} eventos / {clus_B['n_trades']} trades")

    # --- 10. Edad de la divergencia -----------------------------------------------------
    section("J. Edad de la divergencia (buckets predefinidos: 0-2, 3-5, 6-8, 9-10)")

    def age_bucket(age):
        if age is None:
            return None
        for lo, hi in AGE_BUCKETS:
            if lo <= age <= hi:
                return f"{lo}-{hi}"
        return "fuera_de_rango"

    for variant, alignment_col, age_col in (("A", "A_alignment", "A_age"), ("B", "B_alignment", "B_age")):
        print(f"\nVariante {variant}:")
        for align in ("ALIGNED", "OPPOSED"):
            for lo, hi in AGE_BUCKETS:
                bucket_rows = [r for r in rows if r[alignment_col] == align and r[age_col] is not None and lo <= r[age_col] <= hi]
                s = cohort_stats(bucket_rows)
                print(fmt_stats(f"  {align} age {lo}-{hi}", s, len(rows)))

    # --- 11. LONG vs SHORT ---------------------------------------------------------------
    section("K. LONG vs SHORT")
    for direction_label in ("LONG", "SHORT"):
        print(f"\n{direction_label}:")
        dir_rows = [r for r in rows if r["direction"] == direction_label]
        print(fmt_stats("  baseline", cohort_stats(dir_rows), len(rows)))
        for variant, col in (("A", "A_alignment"), ("B", "B_alignment")):
            for align in ("ALIGNED", "OPPOSED"):
                sub = [r for r in dir_rows if r[col] == align]
                print(fmt_stats(f"  {variant}={align}", cohort_stats(sub), len(rows)))

    # --- 12. Estabilidad temporal --------------------------------------------------------
    section("L. Estabilidad temporal (terciles por indice de decision_bar)")
    for sp in ("sub1", "sub2", "sub3"):
        sp_rows = [r for r in rows if r["sub_periodo"] == sp]
        print(f"\n{sp} (N total={len(sp_rows)}):")
        print(fmt_stats("  baseline", cohort_stats(sp_rows), len(rows)))
        print(fmt_stats("  A=ALIGNED", cohort_stats([r for r in sp_rows if r["A_alignment"] == "ALIGNED"]), len(rows)))
        print(fmt_stats("  A=OPPOSED", cohort_stats([r for r in sp_rows if r["A_alignment"] == "OPPOSED"]), len(rows)))
        print(fmt_stats("  B=ALIGNED", cohort_stats([r for r in sp_rows if r["B_alignment"] == "ALIGNED"]), len(rows)))
        print(fmt_stats("  B=OPPOSED", cohort_stats([r for r in sp_rows if r["B_alignment"] == "OPPOSED"]), len(rows)))
        both_aligned = [r for r in sp_rows if r["A_alignment"] == "ALIGNED" and r["B_alignment"] == "ALIGNED"]
        print(fmt_stats("  A+B=ALIGNED", cohort_stats(both_aligned), len(rows)))

    # --- 13. Incertidumbre (bootstrap) ----------------------------------------------------
    section("M. Incertidumbre estadistica (bootstrap 95%, por trade y por evento)")
    for variant, align_col, event_col in (("A", "A_alignment", "A_event_id"), ("B", "B_alignment", "B_event_id")):
        for align in ("ALIGNED", "OPPOSED"):
            sub = [r for r in rows if r[align_col] == align]
            if not sub:
                continue
            pnl_vals = [r["pnl_usd"] for r in sub]
            evs = [r[event_col] for r in sub]
            lo_t, hi_t = bootstrap_ci(pnl_vals)
            lo_e, hi_e = cluster_bootstrap_ci(evs, pnl_vals)
            print(f"{variant}={align:8s} N={len(sub):4d}  bootstrap por-trade Exp$ 95% CI=[{lo_t:+.2f}, {hi_t:+.2f}]  "
                  f"bootstrap por-evento Exp$ 95% CI=[{lo_e:+.2f}, {hi_e:+.2f}]")

    print("\nDesglose LONG/SHORT (el agregado ALIGNED puede esconder un efecto direccional asimetrico -- ver seccion K):")
    for variant, align_col, event_col in (("A", "A_alignment", "A_event_id"), ("B", "B_alignment", "B_event_id")):
        for direction_label in ("LONG", "SHORT"):
            for align in ("ALIGNED", "OPPOSED"):
                sub = [r for r in rows if r[align_col] == align and r["direction"] == direction_label]
                if not sub:
                    continue
                pnl_vals = [r["pnl_usd"] for r in sub]
                evs = [r[event_col] for r in sub]
                lo_t, hi_t = bootstrap_ci(pnl_vals)
                lo_e, hi_e = cluster_bootstrap_ci(evs, pnl_vals)
                print(f"{variant}={align:8s} {direction_label:5s} N={len(sub):4d}  bootstrap por-trade Exp$ 95% CI=[{lo_t:+.2f}, {hi_t:+.2f}]  "
                      f"bootstrap por-evento Exp$ 95% CI=[{lo_e:+.2f}, {hi_e:+.2f}]")

    print("\nEventos unicos especificamente dentro de ALIGNED y OPPOSED (no solo combinados, ver seccion I):")
    for variant, align_col, event_col in (("A", "A_alignment", "A_event_id"), ("B", "B_alignment", "B_event_id")):
        for align in ("ALIGNED", "OPPOSED"):
            sub = [r for r in rows if r[align_col] == align]
            evs = [r[event_col] for r in sub if r[event_col] is not None]
            uniq = len(set(evs))
            from collections import Counter
            counts = list(Counter(evs).values())
            print(f"{variant}={align:8s} N_trades={len(sub):4d}  N_eventos_unicos={uniq:4d}  "
                  f"max_trades_por_evento={max(counts) if counts else 0}  mediana={float(np.median(counts)) if counts else 0.0}")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
