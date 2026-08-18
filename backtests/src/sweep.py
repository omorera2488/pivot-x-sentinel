"""Barrido de parametros — docs/spec-backtest.md #4."""
from __future__ import annotations

from dataclasses import asdict
from itertools import product

from .engine import StrategyParams, run_backtest
from .costs import BrokerCosts


def linspace_count(start: float, step: float, count: int) -> list[float]:
    return [round(start + step * i, 6) for i in range(count)]


def default_grid() -> dict:
    """Malla acordada en docs/spec-backtest.md #4 (3.780 combinaciones)."""
    return {
        "ema_periods": [int(v) for v in linspace_count(8, 3, 6)],
        "periodos_htf_min": [int(v) for v in linspace_count(200, 150, 5)],
        "buf_bp": linspace_count(0.2, 0.5, 7),
        "rr": linspace_count(0.5, 0.5, 6),
        "max_concurrent_por_direccion": [int(v) for v in linspace_count(1, 1, 3)],
    }


def iter_param_combos(grid: dict, fixed_lot: float, valid_bars: int, orden_viva: bool, max_bars_trade: int):
    keys = ["ema_periods", "periodos_htf_min", "buf_bp", "rr", "max_concurrent_por_direccion"]
    for combo in product(*(grid[k] for k in keys)):
        kwargs = dict(zip(keys, combo))
        yield StrategyParams(
            fixed_lot=fixed_lot, valid_bars=valid_bars, orden_viva=orden_viva,
            max_bars_trade=max_bars_trade, **kwargs,
        )


def summarize(params: StrategyParams, res) -> dict:
    d = asdict(params)
    d.update({
        "n_sig": res.counters.n_sig,
        "n_fill": res.counters.n_fill,
        "n_win": res.counters.n_win,
        "n_loss": res.counters.n_loss,
        "n_none": res.counters.n_none,
        "n_open_timeout": res.counters.n_open_timeout,
        "n_skip_stop": res.counters.n_skip_stop,
        "n_skip_concurrency": res.counters.n_skip_concurrency,
        "n_trades": res.n_trades(),
        "win_rate": res.win_rate(),
        "expectancy_r": res.expectancy_r(),
        "expectancy_usd": res.expectancy_usd(),
        "max_drawdown_r": res.max_drawdown_r(),
    })
    return d


def run_sweep(bars: dict, grid: dict, costs: BrokerCosts, fixed_lot: float,
              valid_bars: int = 10, orden_viva: bool = True, max_bars_trade: int = 500,
              progress=None):
    rows = []
    combos = list(iter_param_combos(grid, fixed_lot, valid_bars, orden_viva, max_bars_trade))
    iterator = combos if progress is None else progress(combos)
    for params in iterator:
        res = run_backtest(
            bars["time_utc"], bars["time_server"], bars["open"], bars["high"],
            bars["low"], bars["close"], bars["spread_pts"], params, costs,
        )
        rows.append(summarize(params, res))
    return rows
