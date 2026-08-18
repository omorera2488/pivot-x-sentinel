"""Prueba de robustez — docs/spec-backtest.md #5.

Parte la muestra en sub-periodos contiguos (por indice, ~mismo numero de
velas cada uno) y corre las combinaciones top del barrido por separado en
cada uno, SIN continuidad de estado entre sub-periodos (cada uno recalcula
su propio bloque HTF desde cero, con su propio periodo de calentamiento).

Toma las combinaciones a validar directamente de results/sweep_top20_<TF>.csv
(las N mejores por expectancy_r), asi no hay que hardcodear numeros a mano.

Uso:
    python scripts/04_run_robustness.py [M1|M5] [n_subperiodos] [n_candidatos]
Default: M5, 3 sub-periodos, 3 candidatos
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import strategy"

from strategy.engine import StrategyParams, run_backtest
from strategy.costs import BrokerCosts
from src.sweep import summarize

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
SYMBOL = "XAUUSDm"
FIXED_LOT = 0.01
PARAM_COLS = ["ema_periods", "periodos_htf_min", "buf_bp", "rr", "max_concurrent_por_direccion"]


def get_live_costs(symbol: str) -> BrokerCosts:
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar {symbol!r}: {mt5.last_error()}")
    si = mt5.symbol_info(symbol)
    mt5.shutdown()
    return BrokerCosts(
        point=si.point, contract_size=si.trade_contract_size, tick_value=si.trade_tick_value,
        swap_long_points=si.swap_long, swap_short_points=si.swap_short,
        commission_per_lot=0.0, triple_swap_weekday=2, spread_fallback_points=si.spread,
    )


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    n_sub = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    n_cand = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    top_path = RESULTS_DIR / f"sweep_top20_{tf}.csv"
    top = pd.read_csv(top_path)
    if top.empty:
        print(f"{top_path} esta vacio (ninguna combinacion con n_trades>=30) -- nada que validar.")
        sys.exit(0)
    candidates = top.head(n_cand)[PARAM_COLS].to_dict("records")
    for c in candidates:
        c["ema_periods"] = int(c["ema_periods"])
        c["periodos_htf_min"] = int(c["periodos_htf_min"])
        c["max_concurrent_por_direccion"] = int(c["max_concurrent_por_direccion"])

    path = DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet"
    df = pd.read_parquet(path)
    n = len(df)
    chunk = n // n_sub
    splits = [(f"sub{i+1}", df.iloc[i * chunk: n if i == n_sub - 1 else (i + 1) * chunk]) for i in range(n_sub)]

    print(f"Perfil {tf}: {n} velas totales, {n_sub} sub-periodos de ~{chunk} velas cada uno "
          f"({'MUESTRA CHICA, robustez indicativa nomas' if n < 50000 else 'muestra razonable'})")

    costs = get_live_costs(SYMBOL)

    rows = []
    for label, chunk_df in splits:
        t0 = pd.to_datetime(chunk_df["time_utc"].iloc[0], unit="s")
        t1 = pd.to_datetime(chunk_df["time_utc"].iloc[-1], unit="s")
        bars = {
            "time_utc": chunk_df["time_utc"].to_numpy(),
            "time_server": chunk_df["time_server"].to_numpy(),
            "open": chunk_df["open"].to_numpy(dtype=float),
            "high": chunk_df["high"].to_numpy(dtype=float),
            "low": chunk_df["low"].to_numpy(dtype=float),
            "close": chunk_df["close"].to_numpy(dtype=float),
            "spread_pts": chunk_df["spread"].to_numpy(dtype=float),
        }
        for cand in candidates:
            params = StrategyParams(fixed_lot=FIXED_LOT, valid_bars=10, orden_viva=True,
                                     max_bars_trade=500, **cand)
            res = run_backtest(bars["time_utc"], bars["time_server"], bars["open"], bars["high"],
                                bars["low"], bars["close"], bars["spread_pts"], params, costs)
            row = summarize(params, res)
            row["sub_periodo"] = label
            row["desde"] = str(t0)
            row["hasta"] = str(t1)
            row["n_velas"] = len(chunk_df)
            rows.append(row)

    out = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"robustness_subperiods_{tf}.csv"
    out.to_csv(out_path, index=False)

    cols = ["sub_periodo", "desde", "hasta", "n_velas"] + PARAM_COLS + \
           ["n_trades", "win_rate", "expectancy_r", "expectancy_usd", "max_drawdown_r"]
    print(out[cols].to_string(index=False))
    print(f"\nGuardado: {out_path}")

    print("\n== resumen por combinacion: positiva en TODOS los sub-periodos? ==")
    for cand in candidates:
        mask = np.all([out[k] == v for k, v in cand.items()], axis=0)
        sub = out[mask]
        all_positive = bool((sub["expectancy_r"] > 0).all())
        print(f"{cand} -> expectancy_r por sub-periodo: {sub['expectancy_r'].round(4).tolist()} "
              f"-> {'CUMPLE' if all_positive else 'NO CUMPLE'}")


if __name__ == "__main__":
    main()
