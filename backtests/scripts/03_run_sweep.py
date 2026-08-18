"""Corre el barrido completo de parametros (docs/spec-backtest.md #4) sobre
el historial descargado y guarda los resultados en /backtests/results.

Cada timeframe base tiene su propio perfil de malla, centrado en los
defaults del Pine original de ese timeframe (src/sweep.py grid_1m/grid_5m) —
ver docs/spec-backtest.md #4.1.

Uso:
    python scripts/03_run_sweep.py [M1|M5] [ruta_parquet]
Default: M5, data/XAUUSDm_M5_latest.parquet
"""
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import strategy"

from strategy.costs import BrokerCosts
from src.sweep import grid_1m, grid_5m, run_sweep

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

SYMBOL = "XAUUSDm"
FIXED_LOT = 0.01

GRID_BY_TF = {"M1": grid_1m, "M5": grid_5m}


def load_bars(path: Path) -> dict:
    df = pd.read_parquet(path)
    return {
        "time_utc": df["time_utc"].to_numpy(),
        "time_server": df["time_server"].to_numpy(),
        "open": df["open"].to_numpy(dtype=float),
        "high": df["high"].to_numpy(dtype=float),
        "low": df["low"].to_numpy(dtype=float),
        "close": df["close"].to_numpy(dtype=float),
        "spread_pts": df["spread"].to_numpy(dtype=float),
    }, df


def get_live_costs(symbol: str) -> BrokerCosts:
    """Lee spread/contrato/swap EN VIVO de symbol_info — nada hardcodeado.
    Comision y dia de swap triple son supuestos, ver docs/spec-backtest.md #3.2/#3.3."""
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar {symbol!r}: {mt5.last_error()}")
    si = mt5.symbol_info(symbol)
    mt5.shutdown()
    return BrokerCosts(
        point=si.point,
        contract_size=si.trade_contract_size,
        tick_value=si.trade_tick_value,
        swap_long_points=si.swap_long,
        swap_short_points=si.swap_short,
        commission_per_lot=0.0,          # SUPUESTO: cuenta Standard, spread-only (pendiente de confirmar)
        triple_swap_weekday=2,           # SUPUESTO: miercoles (pendiente de confirmar), 0=lunes
        spread_fallback_points=si.spread,  # solo por si alguna vela no trae 'spread' propio
    )


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    if tf not in GRID_BY_TF:
        print(f"Timeframe no soportado: {tf!r} (opciones: {list(GRID_BY_TF)})")
        sys.exit(1)
    path = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet"

    bars, df = load_bars(path)
    print(f"Perfil: {tf}")
    print(f"Datos: {len(df)} velas, {pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. {pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    costs = get_live_costs(SYMBOL)
    print(f"Costos (en vivo, {SYMBOL}): point={costs.point} contract_size={costs.contract_size} "
          f"tick_value={costs.tick_value} swap_long_pts={costs.swap_long_points} swap_short_pts={costs.swap_short_points} "
          f"commission_per_lot={costs.commission_per_lot} (SUPUESTO) triple_swap_weekday={costs.triple_swap_weekday} (SUPUESTO)")

    grid = GRID_BY_TF[tf]()
    total = 1
    for v in grid.values():
        total *= len(v)
    print(f"Malla ({tf}): {total} combinaciones -- ema_periods={grid['ema_periods']} periodos_htf_min={grid['periodos_htf_min']}")

    t0 = time.time()
    rows = run_sweep(bars, grid, costs, fixed_lot=FIXED_LOT, progress=tqdm)
    t1 = time.time()
    print(f"Barrido completo en {t1-t0:.1f}s")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out_path = RESULTS_DIR / f"sweep_full_{tf}.csv"
    out.to_csv(out_path, index=False)
    print(f"Guardado: {out_path} ({len(out)} filas)")

    # top combinaciones con muestra minimamente relevante
    relevant = out[out["n_trades"] >= 30].copy()
    relevant = relevant.sort_values("expectancy_r", ascending=False)
    top_path = RESULTS_DIR / f"sweep_top20_{tf}.csv"
    relevant.head(20).to_csv(top_path, index=False)
    print(f"Top 20 (n_trades>=30) guardado en: {top_path}")
    print(relevant.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
