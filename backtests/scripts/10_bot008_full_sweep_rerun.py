"""BOT-008 -- re-run completo del barrido de 3.780 combinaciones con el motor
de backtest corregido por BOT-043 (signo de swap + escala precio->USD).

Reutiliza EXACTAMENTE el mismo espacio de parametros que el barrido original
(`backtests/src/sweep.py::grid_5m()`, sin tocar), la misma logica de
entrada/HTF/EMA actual (`strategy.engine.run_backtest`, sin modificar) y el
mismo dataset (`backtests/data/XAUUSDc_M5_latest.parquet`). NO agrega
indicadores nuevos, NO filtra por D1/RSI/ADX/sesion (eso queda congelado en
BOT-045/BOT-046 para una futura Prueba controlada, fuera de alcance acá).

A diferencia de `03_run_sweep.py` (que sobreescribiria `sweep_full_M5.csv`
contaminado), este script escribe a archivos NUEVOS, con sufijo
`_post_BOT-043`, para no pisar los resultados historicos invalidos -- esos
quedan intactos como evidencia historica.

Guarda resultados de las 3.780 combinaciones completas (no solo las
mejores), con metricas extendidas por combinacion: N trades, wins, losses,
win rate, PF, expectancy R/trade, Net R, Net USD, avg winner R, avg loser R,
max drawdown R, max drawdown USD, longest losing streak, costos totales USD,
swap total USD, n_long, n_short.

Uso:
    python backtests/scripts/10_bot008_full_sweep_rerun.py [M5]
Default: M5.
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import strategy"

from strategy.engine import StrategyParams, run_backtest
from strategy.costs import BrokerCosts
from src.sweep import grid_5m, iter_param_combos
from execution.src.mt5_utils import resolve_symbol

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
FIXED_LOT = 0.01


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


def loss_streak_max(outcomes: list[str]) -> int:
    best = cur = 0
    for o in outcomes:
        if o == "loss":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize_full(cfg_id: str, params: StrategyParams, res, costs: BrokerCosts) -> dict:
    trades = res.resolved_trades()
    n_trades = len(trades)
    rs = [t.pnl_r for t in trades if t.pnl_r is not None]
    usds = [t.pnl_usd for t in trades if t.pnl_usd is not None]
    n_win = sum(1 for t in trades if t.outcome == "win")
    n_loss = sum(1 for t in trades if t.outcome == "loss")
    win_rate = (n_win / (n_win + n_loss)) if (n_win + n_loss) else float("nan")
    net_r = sum(rs) if rs else float("nan")
    net_usd = sum(usds) if usds else float("nan")
    expectancy_r = net_r / n_trades if n_trades else float("nan")
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = -sum(r for r in rs if r < 0)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    if rs:
        eq_r = np.cumsum(rs)
        peak_r = np.maximum.accumulate(eq_r)
        max_dd_r = float((peak_r - eq_r).max())
    else:
        max_dd_r = float("nan")
    if usds:
        eq_usd = np.cumsum(usds)
        peak_usd = np.maximum.accumulate(eq_usd)
        max_dd_usd = float((peak_usd - eq_usd).max())
    else:
        max_dd_usd = float("nan")
    winner_rs = [t.pnl_r for t in trades if t.outcome == "win" and t.pnl_r is not None]
    loser_rs = [t.pnl_r for t in trades if t.outcome == "loss" and t.pnl_r is not None]
    avg_winner_r = float(np.mean(winner_rs)) if winner_rs else float("nan")
    avg_loser_r = float(np.mean(loser_rs)) if loser_rs else float("nan")
    outcomes = [t.outcome if t.outcome in ("win", "loss") else ("win" if (t.pnl_r or 0) > 0 else "loss")
                for t in trades]
    max_loss_streak = loss_streak_max(outcomes)
    n_long = sum(1 for t in trades if t.direction > 0)
    n_short = sum(1 for t in trades if t.direction < 0)

    swap_total_usd = 0.0
    for t in trades:
        if t.pnl_usd is None or t.entry_price is None or t.exit_price is None:
            continue
        adj_diff = (t.entry_price_adj - t.exit_price_adj) if t.direction < 0 else (t.exit_price_adj - t.entry_price_adj)
        adj_usd = costs.price_to_usd(adj_diff, params.fixed_lot)
        commission = costs.commission_usd(params.fixed_lot)
        swap_total_usd += t.pnl_usd - adj_usd + commission
    commission_total_usd = costs.commission_usd(params.fixed_lot) * n_trades
    gross_pnl_usd = sum(
        costs.price_to_usd((t.entry_price - t.exit_price) if t.direction < 0 else (t.exit_price - t.entry_price),
                            params.fixed_lot)
        for t in trades if t.entry_price is not None and t.exit_price is not None
    )
    total_costs_usd = gross_pnl_usd - net_usd if (gross_pnl_usd == gross_pnl_usd and net_usd == net_usd) else float("nan")

    return {
        "cfg_id": cfg_id,
        "ema_periods": params.ema_periods, "periodos_htf_min": params.periodos_htf_min,
        "buf_bp": params.buf_bp, "rr": params.rr,
        "max_concurrent_por_direccion": params.max_concurrent_por_direccion,
        "n_trades": n_trades, "n_win": n_win, "n_loss": n_loss, "win_rate": win_rate,
        "profit_factor": profit_factor, "expectancy_r": expectancy_r, "net_r": net_r, "net_usd": net_usd,
        "avg_winner_r": avg_winner_r, "avg_loser_r": avg_loser_r,
        "max_drawdown_r": max_dd_r, "max_drawdown_usd": max_dd_usd,
        "longest_losing_streak": max_loss_streak,
        "total_costs_usd": total_costs_usd, "swap_total_usd": swap_total_usd,
        "commission_total_usd": commission_total_usd,
        "n_long": n_long, "n_short": n_short,
    }


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    if tf != "M5":
        print("Este re-run solo cubre el perfil M5 (el que corrio originalmente BOT-008).")
        sys.exit(1)

    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    SYMBOL = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(SYMBOL)
    print(f"Costos en vivo ({SYMBOL}): point={costs.point} contract_size={costs.contract_size} "
          f"tick_value={costs.tick_value} tick_size={costs.tick_size} "
          f"swap_long={costs.swap_long_points} swap_short={costs.swap_short_points} "
          f"commission_per_lot={costs.commission_per_lot}")

    path = DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet"
    df = pd.read_parquet(path)
    print(f"Dataset: {path.name} -- {len(df)} velas, "
          f"{pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. {pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    bars = {
        "time_utc": df["time_utc"].to_numpy(), "time_server": df["time_server"].to_numpy(),
        "open": df["open"].to_numpy(dtype=float), "high": df["high"].to_numpy(dtype=float),
        "low": df["low"].to_numpy(dtype=float), "close": df["close"].to_numpy(dtype=float),
        "spread_pts": df["spread"].to_numpy(dtype=float),
    }

    grid = grid_5m()
    total = 1
    for v in grid.values():
        total *= len(v)
    print(f"Malla ({tf}): {total} combinaciones -- ema_periods={grid['ema_periods']} "
          f"periodos_htf_min={grid['periodos_htf_min']} buf_bp={grid['buf_bp']} rr={grid['rr']} "
          f"max_concurrent_por_direccion={grid['max_concurrent_por_direccion']}")
    assert total == 3780, f"el espacio de parametros no da 3780 combinaciones, da {total} -- DETENER"

    combos = list(iter_param_combos(grid, FIXED_LOT, valid_bars=10, orden_viva=True, max_bars_trade=500))
    assert len(combos) == 3780

    rows = []
    t0 = time.time()
    for i, params in enumerate(tqdm(combos)):
        res = run_backtest(bars["time_utc"], bars["time_server"], bars["open"], bars["high"],
                            bars["low"], bars["close"], bars["spread_pts"], params, costs)
        cfg_id = f"cfg_{i:04d}"
        rows.append(summarize_full(cfg_id, params, res, costs))
    t1 = time.time()
    print(f"Barrido completo (3.780 combinaciones) en {t1 - t0:.1f}s")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out_path = RESULTS_DIR / f"sweep_full_{tf}_post_BOT-043.csv"
    out.to_csv(out_path, index=False)
    print(f"Guardado: {out_path} ({len(out)} filas -- TODAS las combinaciones, no solo las mejores)")

    print("\n== Q1-Q3 (respuesta rapida, detalle completo en el reporte) ==")
    n_exp_pos = int((out["expectancy_r"] > 0).sum())
    n_pf_pos = int((out["profit_factor"] > 1).sum())
    n_both = int(((out["expectancy_r"] > 0) & (out["profit_factor"] > 1)).sum())
    print(f"Q1 expectancy>0: {n_exp_pos}/3780")
    print(f"Q2 PF>1: {n_pf_pos}/3780")
    print(f"Q3 ambas: {n_both}/3780")


if __name__ == "__main__":
    main()
