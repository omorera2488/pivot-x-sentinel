"""BOT-045 -- construccion del dataset enriquecido de operaciones (analisis de
regimen de mercado / calidad de entradas). Ver BACKLOG.md (BOT-045) y
docs/reports/BOT-045_market_regime_analysis.md para el informe completo.

100% offline y diagnostico: NO modifica /strategy, /execution, la API, el
panel, ni ningun parametro de produccion. Corre `strategy.engine.run_backtest`
sin tocarlo, UNA sola vez sobre todo el dataset (ver nota de metodologia mas
abajo), y calcula variables de regimen adicionales (RSI/ADX/ATR/EMA-distancia/
sesion/hora/dia/D1/caracteristicas del bloque HTF/los 4 factores de scoring de
BOT-023) para cada operacion resuelta, respetando causalidad estricta (ninguna
variable usa informacion posterior a la barra de entrada de esa operacion).

Config congelada (baseline, "Config A" -- la misma que BOT-042/BOT-043
trataron como "la configuracion real del bot" para el motor de costos ya
corregido): EMA=12, HTF=800min, Buffer=0.4bp, RR=1.0.

Nota de metodologia (diferencia deliberada frente a 04_run_robustness.py /
05_run_rr_isolation.py): esos scripts cortan el dataset en 3 sub-periodos y
corren el motor POR SEPARADO en cada uno (sin continuidad de EMA/HTF entre
sub-periodos, cada uno recalienta desde cero). Para el dataset POR OPERACION
de BOT-045 se corre el motor UNA SOLA VEZ, continuo, sobre las 100.505 velas
completas -- mas representativo de como el bot corre en la practica (nunca se
reinicia en medio de una serie historica) -- y luego cada operacion se etiqueta
sub1/sub2/sub3 segun en que tercio de indice cae su `entry_bar` (los mismos 3
cortes de indice que usan esos scripts). Por eso los conteos de trades por
sub-periodo de este dataset pueden diferir levemente (unas pocas operaciones
cerca de cada borde) de los de `robustness_subperiods_M5.csv` /
`rr_subperiods_post_BOT-043_M5.csv" -- se documenta explicitamente en el
informe, no es un error.

Uso:
    python backtests/scripts/07_bot045_regime_dataset.py [M5]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import strategy"

from strategy.engine import StrategyParams, run_backtest, ema, bucket_levels
from strategy.costs import BrokerCosts
from strategy.htf_session import bucket_start_utc_seconds
from strategy import scoring as sc
from execution.src.mt5_utils import resolve_symbol

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# --- Config A congelada (BOT-042/BOT-043) -----------------------------------
CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)

# --- Variables de regimen: ventanas ------------------------------------------
TREND_WINDOWS_MIN = sc.TREND_WINDOWS_MIN["5m"]     # (30, 240) -- factor "Tendencia" de BOT-023
TREND_LOOKBACK = sc.TREND_LOOKBACK_BLOCKS          # 3 bloques cerrados
D1_WINDOW_MIN = 1440                               # "dia de sesion" (misma ancla 22:00 UTC que HTF)
ATR_PERIOD = 14
ADX_PERIOD = 14

# --- Sesiones (UTC, sin ajuste de horario de verano -- ver limitacion en el
# informe): particion NO solapada por hora-del-dia UTC, convencion documentada
# explicitamente (no es la unica posible, pero es fija y trazable).
SESSION_BOUNDS_UTC = [
    (0, 7, "Asia"),
    (7, 8, "Asia/Londres (overlap)"),
    (8, 12, "Londres"),
    (12, 16, "Londres/NY (overlap)"),
    (16, 21, "Nueva York"),
    (21, 24, "Post-NY / transicion"),
]


def session_of_hour(hour_utc: int) -> str:
    for lo, hi, label in SESSION_BOUNDS_UTC:
        if lo <= hour_utc < hi:
            return label
    return "desconocida"


# --- Indicadores causales nuevos (ATR/ADX Wilder) ----------------------------
# No existen en strategy/ -- se agregan aca, exclusivamente para diagnostico
# offline de BOT-045. Formula estandar de Wilder (misma familia de suavizado
# que ya usa strategy.scoring.rsi()).

def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = ATR_PERIOD) -> np.ndarray:
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


# --- Precomputos causales para los factores de scoring (BOT-023), reescritos
# para performance (una sola pasada sobre todo el dataset en vez de recorrer
# el historial completo por cada una de las ~2.5k operaciones). Logica
# identica a strategy/scoring.py -- se reusan directamente las funciones
# privadas de ese modulo donde es seguro (ya filtran por current_bar/rango) y
# se replican, con el mismo algoritmo, las que dependen de la LONGITUD del
# array pasado (trend_score/node_score truncan implicitamente via el llamador
# en vivo, no internamente).

def precompute_closed_blocks(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, window_min: int):
    """Lista de bloques CERRADOS (closing_bar, high_final, low_final), mismo
    criterio que strategy.scoring._closed_blocks pero calculado UNA vez sobre
    todo el dataset. closing_bar=i significa 'este bloque totalmente conocido
    desde la barra i+1 en adelante' -- exactamente igual semantica que la
    version original."""
    resistencia, soporte = bucket_levels(time_utc, high, low, window_min)
    bucket_len_s = window_min * 60
    bucket_id = time_utc // bucket_len_s
    n = len(time_utc)
    closing_bars = []
    block_high = []
    block_low = []
    for i in range(n - 1):
        if bucket_id[i] != bucket_id[i + 1]:
            closing_bars.append(i)
            block_high.append(resistencia[i])
            block_low.append(soporte[i])
    return np.array(closing_bars), np.array(block_high), np.array(block_low)


def trend_at(closing_bars: np.ndarray, block_high: np.ndarray, block_low: np.ndarray,
             current_bar: int, lookback: int = TREND_LOOKBACK):
    """Replica exacta de strategy.scoring._classify_sequence, alimentada con
    los bloques precomputados filtrados a 'cerrados antes de current_bar'
    (mismo corte causal que _closed_blocks + slicing a [0:current_bar+1])."""
    idx = np.searchsorted(closing_bars, current_bar, side="left")  # closing_bars[:idx] < current_bar
    if idx < lookback:
        return None
    highs = block_high[idx - lookback:idx].tolist()
    lows = block_low[idx - lookback:idx].tolist()
    blocks = list(zip(range(lookback), highs, lows))
    return sc._classify_sequence(blocks, lookback)


def build_htf_bucket_start(time_utc: np.ndarray, periodos_min: int) -> np.ndarray:
    return bucket_start_utc_seconds(time_utc, periodos_min)  # vectorizado (solo +,-,//,%)


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


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"

    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    SYMBOL = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(SYMBOL)
    print(f"Costos en vivo ({SYMBOL}): point={costs.point} tick_value={costs.tick_value} "
          f"tick_size={costs.tick_size} swap_long={costs.swap_long_points} "
          f"swap_short={costs.swap_short_points} commission_per_lot={costs.commission_per_lot}")

    path = DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet"
    df = pd.read_parquet(path)
    n = len(df)
    print(f"Dataset: {path.name} -- {n} velas, "
          f"{pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. {pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    time_utc = df["time_utc"].to_numpy()
    time_server = df["time_server"].to_numpy()
    open_ = df["open"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    spread_pts = df["spread"].to_numpy(dtype=float)
    volume = df["tick_volume"].to_numpy(dtype=float)

    # --- 1. Motor real, UNA sola corrida continua sobre todo el dataset -----
    params = StrategyParams(**CONFIG_A, **SHARED)
    ema_line = ema(close, params.ema_periods)
    resistencia, soporte = bucket_levels(time_utc, high, low, params.periodos_htf_min)
    res = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts, params, costs,
                        ema_line=ema_line, resistencia=resistencia, soporte=soporte)
    trades = res.resolved_trades()
    print(f"Config A (continua, todo el periodo): n_trades={len(trades)} "
          f"win_rate={res.win_rate():.4f} expectancy_r={res.expectancy_r():.4f}")

    # --- 2. Indicadores causales de regimen, precomputados UNA vez ----------
    print("Precomputando RSI/ADX/ATR/bloques de tendencia/pivotes de divergencia...")
    rsi_values = sc.rsi(close, sc.RSI_PERIOD)
    atr_values = atr_wilder(high, low, close, ATR_PERIOD)
    adx_values = adx_wilder(high, low, close, ADX_PERIOD)
    pivots_high, pivots_low = sc.find_confirmed_pivots(rsi_values, sc.DIVERGENCE_LB_LEFT, sc.DIVERGENCE_LB_RIGHT)

    w1, w2 = TREND_WINDOWS_MIN
    blocks_w1 = precompute_closed_blocks(time_utc, high, low, w1)
    blocks_w2 = precompute_closed_blocks(time_utc, high, low, w2)
    blocks_d1 = precompute_closed_blocks(time_utc, high, low, D1_WINDOW_MIN)
    htf_bucket_start = build_htf_bucket_start(time_utc, params.periodos_htf_min)

    # --- 3. sub1/sub2/sub3 por indice (mismos cortes que 04_/05_) -----------
    n_sub = 3
    chunk = n // n_sub

    def sub_periodo_of(bar_idx: int) -> str:
        if bar_idx < chunk:
            return "sub1"
        if bar_idx < 2 * chunk:
            return "sub2"
        return "sub3"

    # --- 4. CVP causal: win-rate acumulado de operaciones YA CERRADAS antes
    # de la entrada de esta operacion (aproximacion -- ver limitacion abajo).
    trades_sorted_by_exit = sorted(
        [t for t in trades if t.exit_bar is not None and t.outcome in ("win", "loss")],
        key=lambda t: t.exit_bar,
    )
    exit_bars_sorted = np.array([t.exit_bar for t in trades_sorted_by_exit])
    win_flags_sorted = np.array([1 if t.outcome == "win" else 0 for t in trades_sorted_by_exit])
    cum_wins = np.cumsum(win_flags_sorted)
    CVP_MIN_SAMPLE = sc.CVP_MIN_SAMPLE

    def aciertos_pct_causal(entry_bar: int):
        idx = np.searchsorted(exit_bars_sorted, entry_bar, side="left")  # cerradas ANTES de esta entrada
        if idx < CVP_MIN_SAMPLE:
            return None, idx
        return float(cum_wins[idx - 1]) / idx * 100.0, idx

    # --- 5. armar el dataset por operacion ------------------------------------
    rows = []
    for t in trades:
        eb = t.entry_bar if t.entry_bar is not None else t.signal_bar
        d = t.direction
        dir_label = "LONG" if d > 0 else "SHORT"

        dt = datetime.fromtimestamp(int(time_utc[eb]), tz=timezone.utc)
        hour_utc = dt.hour
        weekday_num = dt.weekday()  # 0=lunes
        weekday_name = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][weekday_num]

        atr_e = atr_values[eb]
        rsi_e = rsi_values[eb]
        adx_e = adx_values[eb]
        ema_e = ema_line[eb]
        close_e = close[eb]
        dist_ema = close_e - ema_e
        dist_ema_atr = abs(dist_ema) / atr_e if atr_e and not np.isnan(atr_e) and atr_e > 0 else np.nan

        htf_res_e = resistencia[eb]
        htf_sop_e = soporte[eb]
        htf_width = htf_res_e - htf_sop_e
        htf_width_atr = htf_width / atr_e if atr_e and not np.isnan(atr_e) and atr_e > 0 else np.nan
        htf_pos = (close_e - htf_sop_e) / htf_width if htf_width > 0 else np.nan
        block_start = htf_bucket_start[eb]
        bars_since_block_start = int(np.searchsorted(htf_bucket_start, block_start, side="left"))
        htf_age_bars = eb - bars_since_block_start

        d1_dir = trend_at(*blocks_d1, current_bar=eb, lookback=TREND_LOOKBACK)
        aligned_d1 = (d1_dir == d) if d1_dir not in (None, 0) else None

        # --- Divergencia (BOT-023), causal, pivotes precomputados ------------
        latest_low = sc._most_recent_fresh(pivots_low, eb, sc.DIVERGENCE_FRESH_BARS)
        div_score, div_reason = 0, "sin divergencia vigente"
        if latest_low is not None:
            prior_low = sc._prior_in_range(pivots_low, latest_low, sc.DIVERGENCE_RANGE_MIN, sc.DIVERGENCE_RANGE_MAX)
            if prior_low is not None and close[latest_low.bar] < close[prior_low.bar] and latest_low.value > prior_low.value:
                div_score, div_reason = sc._signed(d, 1, "divergencia alcista RSI vigente")
        if div_score == 0:
            latest_high = sc._most_recent_fresh(pivots_high, eb, sc.DIVERGENCE_FRESH_BARS)
            if latest_high is not None:
                prior_high = sc._prior_in_range(pivots_high, latest_high, sc.DIVERGENCE_RANGE_MIN, sc.DIVERGENCE_RANGE_MAX)
                if prior_high is not None and close[latest_high.bar] > close[prior_high.bar] and latest_high.value < prior_high.value:
                    div_score, div_reason = sc._signed(d, -1, "divergencia bajista RSI vigente")

        # --- Tendencia (BOT-023), causal, bloques precomputados --------------
        t1 = trend_at(*blocks_w1, current_bar=eb, lookback=TREND_LOOKBACK)
        t2 = trend_at(*blocks_w2, current_bar=eb, lookback=TREND_LOOKBACK)
        if t1 is None or t2 is None or t1 == 0 or t2 == 0 or t1 != t2:
            tend_score, tend_reason = 0, "sin momentum claro / historial insuficiente"
        else:
            tend_score, tend_reason = sc._signed(d, t1, "tendencia con momentum en ambas ventanas")

        # --- CVP (aproximado, ver limitacion en el informe) -------------------
        acc_pct, n_closed_before = aciertos_pct_causal(eb)
        spread_price_e = costs.spread_price(spread_pts[eb])
        cvp_s, cvp_reason, cvp_margin = sc.cvp_score(
            d, t.entry_price, t.stop, t.target, spread_price_e,
            commission_usd=costs.commission_usd(params.fixed_lot), fixed_lot=params.fixed_lot,
            contract_size=costs.contract_size, aciertos_pct=acc_pct,
        )

        # --- Nodo (perfil de volumen), causal: solo barras del bloque HTF
        # actual hasta la barra de entrada (inclusive) --------------------------
        idx_block = np.arange(bars_since_block_start, eb + 1)
        nodo_s, nodo_reason = 0, "historial insuficiente para el perfil de volumen del bloque actual"
        if len(idx_block) >= sc.NODE_MIN_BARS:
            profile = sc._volume_profile(high, low, volume, idx_block, sc.NODE_BINS)
            if profile is not None:
                edges, vol = profile
                va = sc._value_area(edges, vol, sc.NODE_VALUE_AREA_PCT)
                if va is not None:
                    poc_price, va_low, va_high = va
                    path_lo, path_hi = min(t.entry_price, t.target), max(t.entry_price, t.target)
                    overlap = not (va_high < path_lo or va_low > path_hi)
                    nodo_reason = f"POC~{poc_price:.3f}, zona {va_low:.3f}-{va_high:.3f}"
                    if overlap:
                        nodo_s, nodo_reason = -1, nodo_reason + " -- nodo en el camino a la salida"
                    else:
                        nodo_reason = nodo_reason + " -- sin nodo en el camino"
                else:
                    nodo_reason = "sin volumen en el bloque actual"
            else:
                nodo_reason = "sin rango de precio valido para el perfil de volumen"

        rows.append({
            "signal_bar": t.signal_bar, "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
            "entry_time_utc": dt.isoformat(),
            "direction": dir_label,
            "entry_price": t.entry_price, "stop": t.stop, "target": t.target, "exit_price": t.exit_price,
            "outcome": t.outcome, "pnl_r": t.pnl_r, "pnl_usd": t.pnl_usd, "nights_held": t.nights_held,
            "sub_periodo": sub_periodo_of(eb),
            "session_utc": session_of_hour(hour_utc), "hour_utc": hour_utc,
            "weekday": weekday_name, "weekday_num": weekday_num,
            "rsi_entry": rsi_e, "adx_entry": adx_e,
            "atr_entry": atr_e, "atr_pct_entry": (atr_e / close_e * 100.0) if close_e else np.nan,
            "ema_entry": ema_e, "close_entry": close_e,
            "dist_ema": dist_ema, "dist_ema_abs": abs(dist_ema), "dist_ema_atr": dist_ema_atr,
            "htf_resistencia": htf_res_e, "htf_soporte": htf_sop_e,
            "htf_width": htf_width, "htf_width_atr": htf_width_atr,
            "htf_pos_in_block": htf_pos, "htf_age_bars": htf_age_bars,
            "d1_trend": {1: "alcista", -1: "bajista", 0: "sin_secuencia", None: "insuficiente"}[d1_dir],
            "aligned_with_d1": aligned_d1,
            "divergencia_score": div_score, "divergencia_reason": div_reason,
            "tendencia_score": tend_score, "tendencia_reason": tend_reason,
            "cvp_score": cvp_s, "cvp_reason": cvp_reason, "cvp_margin": cvp_margin,
            "cvp_n_closed_before": int(n_closed_before), "cvp_aciertos_pct_causal": acc_pct,
            "nodo_score": nodo_s, "nodo_reason": nodo_reason,
        })

    out = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(RESULTS_DIR / f"BOT-045_trades_enriched_{tf}.csv", index=False)
    out.to_parquet(RESULTS_DIR / f"BOT-045_trades_enriched_{tf}.parquet", index=False)
    print(f"Dataset enriquecido guardado: {len(out)} operaciones, "
          f"{RESULTS_DIR / f'BOT-045_trades_enriched_{tf}.csv'}")

    # --- 6. baseline: completo + sub1/sub2/sub3 -------------------------------
    def summarize_baseline(sub_df: pd.DataFrame, label: str) -> dict:
        n_t = len(sub_df)
        wins = int((sub_df["outcome"] == "win").sum())
        losses = int((sub_df["outcome"] == "loss").sum())
        wr = wins / (wins + losses) if (wins + losses) else float("nan")
        rs = sub_df["pnl_r"].dropna().to_numpy()
        gross_win = rs[rs > 0].sum()
        gross_loss = -rs[rs < 0].sum()
        pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
        expectancy_r = rs.mean() if len(rs) else float("nan")
        net_r = rs.sum() if len(rs) else float("nan")
        net_usd = sub_df["pnl_usd"].dropna().sum()
        avg_win = sub_df.loc[sub_df["outcome"] == "win", "pnl_r"].mean()
        avg_loss = sub_df.loc[sub_df["outcome"] == "loss", "pnl_r"].mean()
        if len(rs):
            equity = np.cumsum(rs)
            peak = np.maximum.accumulate(equity)
            max_dd = float((peak - equity).max())
        else:
            max_dd = float("nan")
        return {
            "periodo": label, "n_trades": n_t, "wins": wins, "losses": losses,
            "win_rate": wr, "profit_factor": pf, "expectancy_r": expectancy_r,
            "net_r": net_r, "net_usd": net_usd, "avg_winner_r": avg_win, "avg_loser_r": avg_loss,
            "max_drawdown_r": max_dd,
        }

    baseline_rows = [summarize_baseline(out, "completo")]
    for sp in ("sub1", "sub2", "sub3"):
        baseline_rows.append(summarize_baseline(out[out["sub_periodo"] == sp], sp))
    baseline_df = pd.DataFrame(baseline_rows)
    baseline_df.to_csv(RESULTS_DIR / f"BOT-045_baseline_{tf}.csv", index=False)
    print("\n== Baseline (completo / sub1 / sub2 / sub3) ==")
    print(baseline_df.to_string(index=False))
    print(f"\nGuardado: {RESULTS_DIR / f'BOT-045_baseline_{tf}.csv'}")


if __name__ == "__main__":
    main()
