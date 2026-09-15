"""Experimento A/B -- HTF en formacion (control, produccion real) vs HTF
anterior cerrado (variante experimental) -- a pedido del usuario, tras la
auditoria de auto-armado del 2026-09-15 (docs/reports/AUDIT-HTF_autoarmado_2026-09-15.md).

SOLO DIAGNOSTICO. No modifica strategy/engine.py, strategy/live_signal.py ni
/execution. Reutiliza el motor real `strategy.engine.run_backtest` SIN
TOCARLO: ese motor ya acepta `resistencia`/`soporte` como hook de testeo
("si se pasan, se usan tal cual" -- ver docstring de run_backtest) -- por
eso A y B comparten literalmente la misma funcion de EMA/entrada/salida/
costos/concurrencia, y la UNICA variable que cambia entre A y B es el array
resistencia/soporte que se le pasa. Esto garantiza la "regla fundamental"
del experimento (cambiar una sola variable) por construccion, no por
disciplina manual.

Variante A -- CONTROL (= produccion real):
    resistencia[i]/soporte[i] = strategy.engine.bucket_levels(...) sin tocar,
    igual que si resistencia=None (el motor lo calcula asi por default) --
    se valida explicitamente que ambos caminos coinciden bar a bar.

Variante B -- EXPERIMENTAL (HTF anterior cerrado):
    bucket_levels_previous_closed() (definida en este script, NO en
    strategy/engine.py) -- resistencia[i]/soporte[i] = high/low FINAL del
    bloque HTF N-1 (ya cerrado), constante durante todo el bloque N. Usa el
    mismo bucket_start_utc_seconds() que la produccion para los limites de
    bloque. Bloque 0 del dataset (sin bloque anterior): NaN -- sin nivel
    valido, no se inventa (el motor ya maneja NaN nativamente: ver
    `if not math.isnan(r_i) and high[i] >= r_i` en engine.py, asi que un
    bloque con NaN simplemente no puede armar nada).

Uso:
    python backtests/scripts/06_htf_ab_experiment.py [M5]

Salidas en backtests/results/ (prefijo htf_ab_):
    htf_ab_signals_<TF>.csv       -- 1 fila por señal (A y B), con match_status
    htf_ab_trades_<TF>.csv        -- 1 fila por trade resuelto (A y B)
    htf_ab_monthly_<TF>.csv       -- 1 fila por (config, mes)
    htf_ab_subperiods_<TF>.csv    -- 1 fila por (config, mitad)
    htf_ab_summary_<TF>.json      -- resumen completo, todas las metricas
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root

from strategy.engine import StrategyParams, run_backtest, ema, bucket_levels
from strategy.htf_session import bucket_start_utc_seconds
from strategy.costs import BrokerCosts
from strategy.profiles import get_profile
from execution.src.mt5_utils import resolve_symbol

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"


# ---------------------------------------------------------------------------
# Variante B -- funcion experimental aislada, NO vive en strategy/engine.py
# ---------------------------------------------------------------------------
def bucket_levels_previous_closed(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray,
                                   periodos_min: int):
    """resistencia[i]/soporte[i] = high/low del bloque HTF ANTERIOR ya
    cerrado (constante durante todo el bloque actual). Comparte
    bucket_start_utc_seconds() con la produccion real para los limites de
    bloque -- la UNICA diferencia con bucket_levels() (produccion) es que
    NO incluye la vela/bloque actual en el nivel, usa el bloque previo
    completo y congelado.

    Primer bloque del dataset (sin bloque anterior): NaN -- ver docstring
    del modulo."""
    n = len(time_utc)
    resistencia = np.full(n, np.nan)
    soporte = np.full(n, np.nan)

    bucket_id = np.array([bucket_start_utc_seconds(int(t), periodos_min) for t in time_utc])
    is_new_block = np.empty(n, dtype=bool)
    is_new_block[0] = True
    is_new_block[1:] = bucket_id[1:] != bucket_id[:-1]

    prev_high, prev_low = np.nan, np.nan   # bloque anterior cerrado -- aun no existe
    cur_high = cur_low = None              # bloque actual en formacion (para saber cuando cierra)

    for i in range(n):
        if is_new_block[i]:
            if cur_high is not None:       # habia un bloque anterior completo -> se cierra ahora
                prev_high, prev_low = cur_high, cur_low
            cur_high, cur_low = high[i], low[i]
        else:
            cur_high = max(cur_high, high[i])
            cur_low = min(cur_low, low[i])
        resistencia[i] = prev_high
        soporte[i] = prev_low

    return resistencia, soporte, bucket_id, is_new_block


# ---------------------------------------------------------------------------
# Conteo de armados -- run_backtest no expone armado por barra (solo señales
# resueltas), asi que se replica aca la MISMA maquina de estados de 6 lineas
# que usa engine.py (lineas ~267-292), puramente para diagnostico -- no
# participa del backtest real (eso lo sigue haciendo run_backtest sin tocar).
# ---------------------------------------------------------------------------
def count_armados(high, low, close, ema_line, resistencia, soporte):
    n = len(close)
    armado_venta = armado_compra = False
    n_act_venta = n_act_compra = 0
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
            if not armado_venta:
                n_act_venta += 1
            armado_venta = True
        if not math.isnan(s_i) and low[i] <= s_i:
            if not armado_compra:
                n_act_compra += 1
            armado_compra = True
    return n_act_venta, n_act_compra


# ---------------------------------------------------------------------------
# Costos reales -- identico mecanismo que backtests/scripts/05_run_rr_isolation.py
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


def bars_of(d: pd.DataFrame) -> dict:
    return {
        "time_utc": d["time_utc"].to_numpy("int64"), "time_server": d["time_server"].to_numpy("int64"),
        "open": d["open"].to_numpy("float64"), "high": d["high"].to_numpy("float64"),
        "low": d["low"].to_numpy("float64"), "close": d["close"].to_numpy("float64"),
        "spread_pts": d["spread"].to_numpy("float64"),
    }


def loss_streak_lengths(outcomes: list[str]) -> list[int]:
    lengths, cur = [], 0
    for o in outcomes:
        if o == "loss":
            cur += 1
        else:
            if cur > 0:
                lengths.append(cur)
            cur = 0
    if cur > 0:
        lengths.append(cur)
    return lengths


def win_streak_max(outcomes: list[str]) -> int:
    best = cur = 0
    for o in outcomes:
        cur = cur + 1 if o == "win" else 0
        best = max(best, cur)
    return best


def summarize_trades(trades, label: str) -> dict:
    trades = sorted(trades, key=lambda t: t.entry_bar if t.entry_bar is not None else t.signal_bar)
    n_trades = len(trades)
    rs = [t.pnl_r for t in trades if t.pnl_r is not None]
    us = [t.pnl_usd for t in trades if t.pnl_usd is not None]
    n_win = sum(1 for t in trades if t.outcome == "win")
    n_loss = sum(1 for t in trades if t.outcome == "loss")
    n_timeout = sum(1 for t in trades if t.outcome == "timeout")
    win_rate = (n_win / (n_win + n_loss)) if (n_win + n_loss) else float("nan")

    net_r = sum(rs) if rs else float("nan")
    expectancy_r = net_r / n_trades if n_trades else float("nan")
    gross_win_r = sum(r for r in rs if r > 0)
    gross_loss_r = -sum(r for r in rs if r < 0)
    pf_r = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else float("inf")

    net_usd = sum(us) if us else float("nan")
    expectancy_usd = net_usd / n_trades if n_trades else float("nan")
    gross_win_usd = sum(u for u in us if u > 0)
    gross_loss_usd = -sum(u for u in us if u < 0)
    pf_usd = (gross_win_usd / gross_loss_usd) if gross_loss_usd > 0 else float("inf")

    if rs:
        equity_r = np.cumsum(rs)
        peak_r = np.maximum.accumulate(equity_r)
        max_dd_r = float((peak_r - equity_r).max())
    else:
        max_dd_r = float("nan")
    if us:
        equity_usd = np.cumsum(us)
        peak_usd = np.maximum.accumulate(equity_usd)
        max_dd_usd = float((peak_usd - equity_usd).max())
    else:
        max_dd_usd = float("nan")
    recovery_r = (net_r / max_dd_r) if max_dd_r else float("nan")

    outcomes = [t.outcome for t in trades]
    streak_lengths = loss_streak_lengths(outcomes)
    max_loss_streak = max(streak_lengths) if streak_lengths else 0
    max_win_streak = win_streak_max(outcomes)

    winner_rs = np.array([t.pnl_r for t in trades if t.outcome == "win" and t.pnl_r is not None])
    loser_rs = np.array([t.pnl_r for t in trades if t.outcome == "loss" and t.pnl_r is not None])
    winner_usd = np.array([t.pnl_usd for t in trades if t.outcome == "win" and t.pnl_usd is not None])
    loser_usd = np.array([t.pnl_usd for t in trades if t.outcome == "loss" and t.pnl_usd is not None])

    return {
        "label": label, "n_trades": n_trades, "n_win": n_win, "n_loss": n_loss, "n_timeout": n_timeout,
        "win_rate": win_rate,
        "net_r": net_r, "expectancy_r": expectancy_r, "gross_win_r": gross_win_r, "gross_loss_r": gross_loss_r,
        "profit_factor_r": pf_r, "max_drawdown_r": max_dd_r, "recovery_factor_r": recovery_r,
        "net_usd": net_usd, "expectancy_usd": expectancy_usd,
        "gross_win_usd": gross_win_usd, "gross_loss_usd": gross_loss_usd,
        "profit_factor_usd": pf_usd, "max_drawdown_usd": max_dd_usd,
        "avg_winner_r": float(winner_rs.mean()) if len(winner_rs) else float("nan"),
        "avg_loser_r": float(loser_rs.mean()) if len(loser_rs) else float("nan"),
        "avg_winner_usd": float(winner_usd.mean()) if len(winner_usd) else float("nan"),
        "avg_loser_usd": float(loser_usd.mean()) if len(loser_usd) else float("nan"),
        "max_loss_streak": max_loss_streak, "max_win_streak": max_win_streak,
    }


def run_variant(bars: dict, params: StrategyParams, costs: BrokerCosts,
                 resistencia: np.ndarray | None, soporte: np.ndarray | None, label: str):
    signal_log: list = []
    res = run_backtest(bars["time_utc"], bars["time_server"], bars["open"], bars["high"], bars["low"],
                        bars["close"], bars["spread_pts"], params, costs,
                        resistencia=resistencia, soporte=soporte, signal_log=signal_log)
    return res, signal_log


def month_key(ts: int) -> str:
    return pd.to_datetime(int(ts), unit="s", utc=True).strftime("%Y-%m")


def monthly_breakdown(trades, bars_time_utc, label: str) -> list[dict]:
    rows = []
    by_month: dict[str, list] = {}
    for t in trades:
        bar = t.entry_bar if t.entry_bar is not None else t.signal_bar
        m = month_key(bars_time_utc[bar])
        by_month.setdefault(m, []).append(t)
    for m in sorted(by_month):
        ts = by_month[m]
        n = len(ts)
        nw = sum(1 for t in ts if t.outcome == "win")
        nl = sum(1 for t in ts if t.outcome == "loss")
        wr = nw / (nw + nl) if (nw + nl) else float("nan")
        net_usd = sum(t.pnl_usd for t in ts if t.pnl_usd is not None)
        rs = [t.pnl_r for t in ts if t.pnl_r is not None]
        gross_win = sum(r for r in rs if r > 0)
        gross_loss = -sum(r for r in rs if r < 0)
        pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
        rows.append({"config": label, "mes": m, "n_trades": n, "win_rate": wr,
                      "net_usd": net_usd, "net_r": sum(rs), "profit_factor_r": pf})
    return rows


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"

    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    SYMBOL = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(SYMBOL)
    print(f"Costos en vivo ({SYMBOL}): point={costs.point} contract_size={costs.contract_size} "
          f"tick_value={costs.tick_value} tick_size={costs.tick_size} "
          f"swap_long={costs.swap_long_points} swap_short={costs.swap_short_points} "
          f"spread_fallback_points={costs.spread_fallback_points}")

    path = DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet"
    df = pd.read_parquet(path).sort_values("time_utc").reset_index(drop=True)
    n = len(df)
    print(f"Dataset: {path.name} -- {n} velas, "
          f"{pd.to_datetime(int(df['time_utc'].iloc[0]), unit='s', utc=True)} .. "
          f"{pd.to_datetime(int(df['time_utc'].iloc[-1]), unit='s', utc=True)}")

    params = get_profile("5m")   # perfil 5m real, SIN overrides -- "no inventar parametros"
    print(f"Parametros efectivos (strategy.profiles.get_profile('5m'), sin overrides): {params}")

    bars = bars_of(df)
    time_utc, high, low, close = bars["time_utc"], bars["high"], bars["low"], bars["close"]

    # =========================================================================
    # 1. VALIDAR EL CONTROL (Variante A == produccion real)
    # =========================================================================
    print("\n=== 1. Validacion del CONTROL (Variante A) ===")
    resistencia_A, soporte_A = bucket_levels(time_utc, high, low, params.periodos_htf_min)
    res_A_default, log_A_default = run_variant(bars, params, costs, None, None, "A_default")
    res_A_explicit, log_A_explicit = run_variant(bars, params, costs, resistencia_A, soporte_A, "A_explicit")

    assert len(log_A_default) == len(log_A_explicit), "A explicito vs A default: distinta cantidad de señales"
    for a, b in zip(log_A_default, log_A_explicit):
        assert a == b, f"A explicito vs A default difieren: {a} vs {b}"
    print(f"Variante A (resistencia=None por default) vs A (resistencia=bucket_levels() explicito): "
          f"IDENTICAS bar-a-bar ({len(log_A_default)} señales) -- confirma que el hook de testeo "
          f"reproduce exactamente el camino de produccion.")

    n_sig_A = len(log_A_explicit)
    n_buy_A = sum(1 for s in log_A_explicit if s["dir"] == 1)
    n_sell_A = sum(1 for s in log_A_explicit if s["dir"] == -1)
    n_trades_A = len(res_A_explicit.resolved_trades())
    print(f"Variante A: señales={n_sig_A} (BUY={n_buy_A} SELL={n_sell_A}) trades resueltos={n_trades_A}")
    print(f"Referencia de la auditoria previa (2026-09-15): 6.409 señales -- "
          f"{'COINCIDE' if n_sig_A == 6409 else 'NO COINCIDE, DETENER Y EXPLICAR'}")
    if n_sig_A != 6409:
        print("*** DISCREPANCIA CON EL BASELINE DE LA AUDITORIA -- revisar antes de continuar ***")

    # =========================================================================
    # 2/3. VARIANTE B -- construccion aislada + validacion
    # =========================================================================
    print("\n=== 2/3. Variante B (HTF anterior cerrado) -- construccion y validacion ===")
    resistencia_B, soporte_B, bucket_id, is_new_block = bucket_levels_previous_closed(
        time_utc, high, low, params.periodos_htf_min)

    n_nan_B = int(np.isnan(resistencia_B).sum())
    first_block_end = int(np.argmax(is_new_block[1:]) + 1) if is_new_block[1:].any() else n
    print(f"Barras sin nivel valido (primer bloque, sin HTF anterior): {n_nan_B} "
          f"(deberian ser exactamente las barras del primer bloque, 0..{first_block_end - 1})")
    assert n_nan_B == first_block_end, \
        f"el NaN de B deberia cubrir exactamente el primer bloque ({first_block_end} barras), da {n_nan_B}"

    # reconstruccion independiente del high/low de cada bloque cerrado, para validar B por fuera de B
    recon_block_high, recon_block_low = {}, {}
    cur_h = cur_l = None
    cur_id = None
    for i in range(n):
        if cur_id != bucket_id[i]:
            if cur_id is not None:
                recon_block_high[cur_id] = cur_h
                recon_block_low[cur_id] = cur_l
            cur_id, cur_h, cur_l = bucket_id[i], high[i], low[i]
        else:
            cur_h = max(cur_h, high[i])
            cur_l = min(cur_l, low[i])
    recon_block_high[cur_id] = cur_h
    recon_block_low[cur_id] = cur_l

    # cada barra con bloque anterior definido: resistencia_B debe ser exactamente el high FINAL
    # del bloque cuyo id es el inmediatamente anterior al bloque de esa barra
    unique_ids = sorted(set(bucket_id.tolist()))
    id_index = {bid: k for k, bid in enumerate(unique_ids)}
    n_checked = 0
    for i in range(n):
        if not np.isnan(resistencia_B[i]):
            k = id_index[bucket_id[i]]
            prev_id = unique_ids[k - 1]
            assert np.isclose(resistencia_B[i], recon_block_high[prev_id]), \
                f"bar {i}: resistencia_B={resistencia_B[i]} != high final bloque anterior={recon_block_high[prev_id]}"
            assert np.isclose(soporte_B[i], recon_block_low[prev_id]), \
                f"bar {i}: soporte_B={soporte_B[i]} != low final bloque anterior={recon_block_low[prev_id]}"
            n_checked += 1
    print(f"Assert 'resistencia_B == high del bloque anterior cerrado' (y soporte_B == low): "
          f"OK en {n_checked}/{n - n_nan_B} barras con bloque anterior definido.")

    # constancia dentro del bloque: resistencia_B/soporte_B no cambian dentro de un mismo bloque
    changes_within_block = 0
    for i in range(1, n):
        if bucket_id[i] == bucket_id[i - 1]:
            if not (np.isclose(resistencia_B[i], resistencia_B[i - 1], equal_nan=True) and
                    np.isclose(soporte_B[i], soporte_B[i - 1], equal_nan=True)):
                changes_within_block += 1
    print(f"Barras donde resistencia_B/soporte_B cambiaron DENTRO del mismo bloque (deberia ser 0): "
          f"{changes_within_block}")
    assert changes_within_block == 0, "B esta actualizando niveles dentro del bloque -- BUG en la variante experimental"

    # demostracion explicita: una vela que hace nuevo maximo/minimo del bloque EN CURSO no mueve B
    demo_rows = []
    for i in range(1, n):
        if bucket_id[i] == bucket_id[i - 1] and not np.isnan(resistencia_B[i]):
            # esta vela hace nuevo maximo del bloque actual (respecto a lo visto en el bloque)?
            block_start = i
            while block_start > 0 and bucket_id[block_start - 1] == bucket_id[i]:
                block_start -= 1
            running_max_before_i = high[block_start:i].max() if i > block_start else -np.inf
            if high[i] > running_max_before_i:
                demo_rows.append(i)
        if len(demo_rows) >= 3:
            break
    print(f"Ejemplo -- barras que hacen nuevo maximo de SU bloque en curso pero NO mueven resistencia_B "
          f"(primeras {len(demo_rows)} encontradas):")
    for i in demo_rows:
        ts = pd.to_datetime(int(time_utc[i]), unit="s", utc=True)
        print(f"  bar {i} {ts}: high={high[i]:.3f} (nuevo max del bloque en curso) "
              f"resistencia_B={resistencia_B[i]:.3f} (SIN CAMBIAR, = high del bloque N-1) "
              f"resistencia_A(en formacion)={resistencia_A[i]:.3f} (SI se actualizo)")

    print(f"\nTabla de muestra -- primeras 2 transiciones de bloque completas, HTF={params.periodos_htf_min}min:")
    hdr = (f"{'bar':>6}{'timestamp_utc':>22}{'bucket_id':>12}{'nuevo_blk':>10}"
           f"{'high':>10}{'low':>10}{'res_B':>10}{'sop_B':>10}{'res_A':>10}{'sop_A':>10}")
    print(hdr); print("-" * len(hdr))
    shown_blocks = 0
    last_id = None
    for i in range(n):
        if bucket_id[i] != last_id:
            shown_blocks += 1
            last_id = bucket_id[i]
            if shown_blocks > 3:
                break
        if shown_blocks == 0:
            continue
        ts = pd.to_datetime(int(time_utc[i]), unit="s", utc=True)
        rb = f"{resistencia_B[i]:.3f}" if not np.isnan(resistencia_B[i]) else "NaN"
        sb = f"{soporte_B[i]:.3f}" if not np.isnan(soporte_B[i]) else "NaN"
        print(f"{i:>6}{str(ts):>22}{bucket_id[i]:>12}{str(bool(is_new_block[i])):>10}"
              f"{high[i]:>10.3f}{low[i]:>10.3f}{rb:>10}{sb:>10}{resistencia_A[i]:>10.3f}{soporte_A[i]:>10.3f}")
        if i > 30 and shown_blocks >= 2:
            # mostrar solo el arranque de cada bloque + un par de barras, no todo
            pass

    # =========================================================================
    # Correr B completo
    # =========================================================================
    res_B, log_B = run_variant(bars, params, costs, resistencia_B, soporte_B, "B")
    n_sig_B = len(log_B)
    n_buy_B = sum(1 for s in log_B if s["dir"] == 1)
    n_sell_B = sum(1 for s in log_B if s["dir"] == -1)
    n_trades_B = len(res_B.resolved_trades())
    print(f"\nVariante B: señales={n_sig_B} (BUY={n_buy_B} SELL={n_sell_B}) trades resueltos={n_trades_B}")

    ema_line = ema(close, params.ema_periods)
    armado_venta_A, armado_compra_A = count_armados(high, low, close, ema_line, resistencia_A, soporte_A)
    armado_venta_B, armado_compra_B = count_armados(high, low, close, ema_line, resistencia_B, soporte_B)
    print(f"Armados (activaciones False->True) -- A: venta={armado_venta_A} compra={armado_compra_A}  "
          f"B: venta={armado_venta_B} compra={armado_compra_B}")

    # =========================================================================
    # 4. Comparacion de señales A vs B (por timestamp + direccion)
    # =========================================================================
    print("\n=== 4. Comparacion de señales A vs B ===")
    set_A = {(int(time_utc[s["bar"]]), s["dir"]): s for s in log_A_explicit}
    set_B = {(int(time_utc[s["bar"]]), s["dir"]): s for s in log_B}
    keys_A, keys_B = set(set_A), set(set_B)
    same_signals = keys_A & keys_B
    a_only = keys_A - keys_B
    b_only = keys_B - keys_A
    n_valid_A = sum(1 for s in log_A_explicit if s["valido"])
    n_valid_B = sum(1 for s in log_B if s["valido"])
    print(f"Señales totales:      A={n_sig_A}  B={n_sig_B}")
    print(f"Señales validas:      A={n_valid_A} ({100*n_valid_A/max(n_sig_A,1):.1f}%)  "
          f"B={n_valid_B} ({100*n_valid_B/max(n_sig_B,1):.1f}%)")
    print(f"Coincidentes (mismo timestamp+dir): {len(same_signals)}")
    print(f"Solo en A (desaparecen en B):       {len(a_only)} ({100*len(a_only)/max(n_sig_A,1):.1f}% de A)")
    print(f"Solo en B (nuevas, no estan en A):  {len(b_only)} ({100*len(b_only)/max(n_sig_B,1):.1f}% de B)")

    # =========================================================================
    # 5/6. Comparacion de trading (R y USD) + normalizado
    # =========================================================================
    print("\n=== 5/6. Comparacion de performance (trades resueltos) ===")
    m_A = summarize_trades(res_A_explicit.resolved_trades(), "A")
    m_B = summarize_trades(res_B.resolved_trades(), "B")

    def months_span(trades):
        if not trades:
            return float("nan")
        bars_idx = [t.entry_bar if t.entry_bar is not None else t.signal_bar for t in trades]
        t0 = pd.to_datetime(int(time_utc[min(bars_idx)]), unit="s", utc=True)
        t1 = pd.to_datetime(int(time_utc[max(bars_idx)]), unit="s", utc=True)
        return max((t1 - t0).days / 30.4375, 1e-9)

    months_A = months_span(res_A_explicit.resolved_trades())
    months_B = months_span(res_B.resolved_trades())
    m_A["trades_per_month"] = m_A["n_trades"] / months_A if months_A else float("nan")
    m_B["trades_per_month"] = m_B["n_trades"] / months_B if months_B else float("nan")
    m_A["usd_per_month"] = m_A["net_usd"] / months_A if months_A else float("nan")
    m_B["usd_per_month"] = m_B["net_usd"] / months_B if months_B else float("nan")
    m_A["usd_per_100_trades"] = (m_A["net_usd"] / m_A["n_trades"] * 100) if m_A["n_trades"] else float("nan")
    m_B["usd_per_100_trades"] = (m_B["net_usd"] / m_B["n_trades"] * 100) if m_B["n_trades"] else float("nan")
    m_A["return_over_dd_usd"] = (m_A["net_usd"] / m_A["max_drawdown_usd"]) if m_A["max_drawdown_usd"] else float("nan")
    m_B["return_over_dd_usd"] = (m_B["net_usd"] / m_B["max_drawdown_usd"]) if m_B["max_drawdown_usd"] else float("nan")

    for label, m in (("A", m_A), ("B", m_B)):
        print(f"{label}: n_trades={m['n_trades']} WR={m['win_rate']:.4f} netUSD={m['net_usd']:.2f} "
              f"netR={m['net_r']:.2f} PF_usd={m['profit_factor_usd']:.3f} PF_r={m['profit_factor_r']:.3f} "
              f"expR={m['expectancy_r']:.4f} maxDD_usd={m['max_drawdown_usd']:.2f} "
              f"maxLossStreak={m['max_loss_streak']} trades/mes={m['trades_per_month']:.2f}")

    print("\nNOTA sobre max drawdown %: el motor opera con lote fijo (fixed_lot=0.01), no con "
          "equity compuesto sobre un balance de cuenta -- no hay una base de capital definida en el "
          "motor para expresar el drawdown como porcentaje sin inventar un balance inicial arbitrario. "
          "Se reporta max drawdown en USD y en R (múltiplos de riesgo), que si son nativos del motor.")

    # =========================================================================
    # 7. Mensual
    # =========================================================================
    monthly_A = monthly_breakdown(res_A_explicit.resolved_trades(), time_utc, "A")
    monthly_B = monthly_breakdown(res_B.resolved_trades(), time_utc, "B")

    # =========================================================================
    # 8. Primer 50% vs segundo 50% (sin warmup cruzado, mismo criterio que
    #    04_run_robustness.py / 05_run_rr_isolation.py para sub-periodos)
    # =========================================================================
    print("\n=== 8. Estabilidad -- primer 50% vs segundo 50% (sin optimizar nada) ===")
    mid = n // 2
    halves = [("H1_2025", df.iloc[:mid]), ("H2_2026", df.iloc[mid:])]
    subperiod_rows = []
    for half_label, half_df in halves:
        hb = bars_of(half_df)
        h_time, h_high, h_low = hb["time_utc"], hb["high"], hb["low"]
        h_res_A, h_sop_A = bucket_levels(h_time, h_high, h_low, params.periodos_htf_min)
        h_res_B, h_sop_B, _, _ = bucket_levels_previous_closed(h_time, h_high, h_low, params.periodos_htf_min)
        t0 = pd.to_datetime(int(half_df["time_utc"].iloc[0]), unit="s", utc=True)
        t1 = pd.to_datetime(int(half_df["time_utc"].iloc[-1]), unit="s", utc=True)
        for variant_label, r_arr, s_arr in (("A", h_res_A, h_sop_A), ("B", h_res_B, h_sop_B)):
            res_h, log_h = run_variant(hb, params, costs, r_arr, s_arr, f"{variant_label}_{half_label}")
            m_h = summarize_trades(res_h.resolved_trades(), f"{variant_label}_{half_label}")
            subperiod_rows.append({
                "config": variant_label, "mitad": half_label, "desde": str(t0), "hasta": str(t1),
                "n_velas": len(half_df), "n_señales": len(log_h), "n_trades": m_h["n_trades"],
                "win_rate": m_h["win_rate"], "net_usd": m_h["net_usd"], "net_r": m_h["net_r"],
                "profit_factor_usd": m_h["profit_factor_usd"], "max_drawdown_usd": m_h["max_drawdown_usd"],
                "max_loss_streak": m_h["max_loss_streak"],
            })
            print(f"  {variant_label} {half_label} ({t0.date()}..{t1.date()}): n_trades={m_h['n_trades']} "
                  f"WR={m_h['win_rate']:.4f} netUSD={m_h['net_usd']:.2f} PF_usd={m_h['profit_factor_usd']:.3f}")

    # =========================================================================
    # 9. Señales A-only / B-only -- que resultado tuvieron (si llegaron a trade)
    # =========================================================================
    print("\n=== 9. Señales A-only / B-only -- resultado original ===")
    trades_by_key_A = {(t.direction, t.born_bar): t for t in res_A_explicit.resolved_trades()}
    trades_by_key_B = {(t.direction, t.born_bar): t for t in res_B.resolved_trades()}

    def classify_group(keys, set_map, trades_by_key, bar_of_key_fn):
        resolved, no_trade = [], 0
        for k in keys:
            s = set_map[k]
            bar = s["bar"]
            t = trades_by_key.get((s["dir"], bar))
            if t is not None:
                resolved.append(t)
            else:
                no_trade += 1
        return resolved, no_trade

    a_only_trades, a_only_no_trade = classify_group(a_only, set_A, trades_by_key_A, None)
    b_only_trades, b_only_no_trade = classify_group(b_only, set_B, trades_by_key_B, None)

    def group_stats(trades, no_trade_n, total_n, label):
        nw = sum(1 for t in trades if t.outcome == "win")
        nl = sum(1 for t in trades if t.outcome == "loss")
        nt = sum(1 for t in trades if t.outcome == "timeout")
        wr = nw / (nw + nl) if (nw + nl) else float("nan")
        net_usd = sum(t.pnl_usd for t in trades if t.pnl_usd is not None)
        net_r = sum(t.pnl_r for t in trades if t.pnl_r is not None)
        print(f"{label}: {total_n} señales -- {len(trades)} llegaron a trade resuelto "
              f"({nw} win / {nl} loss / {nt} timeout, WR={wr:.4f}, netUSD={net_usd:.2f}, netR={net_r:.2f}); "
              f"{no_trade_n} no llegaron a trade resuelto (invalidas / expiradas / bloqueadas por concurrencia)")
        return {"label": label, "total_señales": total_n, "n_resueltos": len(trades), "n_win": nw, "n_loss": nl,
                "n_timeout": nt, "win_rate": wr, "net_usd": net_usd, "net_r": net_r, "no_trade": no_trade_n}

    stats_a_only = group_stats(a_only_trades, a_only_no_trade, len(a_only), "A-only (desaparecen en B)")
    stats_b_only = group_stats(b_only_trades, b_only_no_trade, len(b_only), "B-only (nuevas en B)")

    # =========================================================================
    # 11/12. Tabla final + clasificacion
    # =========================================================================
    diff_net_usd = m_B["net_usd"] - m_A["net_usd"]
    diff_pf = m_B["profit_factor_usd"] - m_A["profit_factor_usd"] if math.isfinite(m_A["profit_factor_usd"]) else float("nan")
    print("\n=== 11. Tabla final A/B ===")
    print(f"{'Metrica':<20}{'A (formacion)':>18}{'B (cerrado)':>18}{'Diferencia (B-A)':>20}")
    rows_final = [
        ("Señales", n_sig_A, n_sig_B), ("Trades", m_A["n_trades"], m_B["n_trades"]),
        ("Winners", m_A["n_win"], m_B["n_win"]), ("Losers", m_A["n_loss"], m_B["n_loss"]),
        ("Win Rate", m_A["win_rate"], m_B["win_rate"]),
        ("Net Profit (USD)", m_A["net_usd"], m_B["net_usd"]),
        ("Profit Factor (USD)", m_A["profit_factor_usd"], m_B["profit_factor_usd"]),
        ("Expectancy (R)", m_A["expectancy_r"], m_B["expectancy_r"]),
        ("Avg Winner (USD)", m_A["avg_winner_usd"], m_B["avg_winner_usd"]),
        ("Avg Loser (USD)", m_A["avg_loser_usd"], m_B["avg_loser_usd"]),
        ("Max Drawdown (USD)", m_A["max_drawdown_usd"], m_B["max_drawdown_usd"]),
        ("Trades/mes", m_A["trades_per_month"], m_B["trades_per_month"]),
        ("Profit/mes (USD)", m_A["usd_per_month"], m_B["usd_per_month"]),
        ("Return/DD (USD)", m_A["return_over_dd_usd"], m_B["return_over_dd_usd"]),
    ]
    for name, va, vb in rows_final:
        diff = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else float("nan")
        print(f"{name:<20}{va!s:>18}{vb!s:>18}{diff!s:>20}")

    # =========================================================================
    # Guardar resultados
    # =========================================================================
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    signal_rows = []
    for s in log_A_explicit:
        k = (int(time_utc[s["bar"]]), s["dir"])
        signal_rows.append({"config": "A", "bar": s["bar"], "timestamp_utc": time_utc[s["bar"]],
                             "dir": s["dir"], "valido": s["valido"],
                             "match_status": "same" if k in same_signals else "A_only"})
    for s in log_B:
        k = (int(time_utc[s["bar"]]), s["dir"])
        signal_rows.append({"config": "B", "bar": s["bar"], "timestamp_utc": time_utc[s["bar"]],
                             "dir": s["dir"], "valido": s["valido"],
                             "match_status": "same" if k in same_signals else "B_only"})
    pd.DataFrame(signal_rows).to_csv(RESULTS_DIR / f"htf_ab_signals_{tf}.csv", index=False)

    trade_rows = []
    for label, res in (("A", res_A_explicit), ("B", res_B)):
        for t in res.resolved_trades():
            trade_rows.append({
                "config": label, "born_bar": t.born_bar, "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                "direction": t.direction, "outcome": t.outcome, "pnl_usd": t.pnl_usd, "pnl_r": t.pnl_r,
                "entry_timestamp": time_utc[t.entry_bar] if t.entry_bar is not None else None,
            })
    pd.DataFrame(trade_rows).to_csv(RESULTS_DIR / f"htf_ab_trades_{tf}.csv", index=False)

    pd.DataFrame(monthly_A + monthly_B).to_csv(RESULTS_DIR / f"htf_ab_monthly_{tf}.csv", index=False)
    pd.DataFrame(subperiod_rows).to_csv(RESULTS_DIR / f"htf_ab_subperiods_{tf}.csv", index=False)

    summary = {
        "symbol": SYMBOL, "n_velas": n, "params": str(params),
        "costs": {"point": costs.point, "contract_size": costs.contract_size, "tick_value": costs.tick_value,
                  "tick_size": costs.tick_size, "swap_long_points": costs.swap_long_points,
                  "swap_short_points": costs.swap_short_points},
        "control_validation": {"n_sig_A_default": len(log_A_default), "n_sig_A_explicit": len(log_A_explicit),
                                "matches_audit_baseline_6409": n_sig_A == 6409},
        "A": m_A, "B": m_B,
        "señales": {"n_A": n_sig_A, "n_B": n_sig_B, "n_valid_A": n_valid_A, "n_valid_B": n_valid_B,
                    "n_same": len(same_signals), "n_a_only": len(a_only), "n_b_only": len(b_only)},
        "armados": {"venta_A": armado_venta_A, "compra_A": armado_compra_A,
                    "venta_B": armado_venta_B, "compra_B": armado_compra_B},
        "a_only_analysis": stats_a_only, "b_only_analysis": stats_b_only,
        "diff_net_usd_B_minus_A": diff_net_usd,
    }
    with open(RESULTS_DIR / f"htf_ab_summary_{tf}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nGuardado en {RESULTS_DIR}: htf_ab_signals_{tf}.csv, htf_ab_trades_{tf}.csv, "
          f"htf_ab_monthly_{tf}.csv, htf_ab_subperiods_{tf}.csv, htf_ab_summary_{tf}.json")


if __name__ == "__main__":
    main()
