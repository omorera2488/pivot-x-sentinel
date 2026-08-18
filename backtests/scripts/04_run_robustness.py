"""Prueba de robustez — docs/spec-backtest.md #5.

Parte la muestra en 3 sub-periodos contiguos (por indice, ~mismo numero de
velas cada uno) y corre la(s) combinacion(es) indicadas por separado en cada
uno, SIN continuidad de estado entre sub-periodos (cada uno recalcula su
propio bloque HTF desde cero, con su propio periodo de calentamiento).

Uso:
    python scripts/04_run_robustness.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engine import StrategyParams, run_backtest
from src.costs import BrokerCosts
from src.sweep import summarize

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
SYMBOL = "XAUUSDm"
FIXED_LOT = 0.01

# Combinaciones a validar: la ganadora del barrido + un par de vecinas top
# (ver results/sweep_top20.csv)
CANDIDATES = [
    dict(ema_periods=14, periodos_htf_min=800, buf_bp=2.7, rr=3.0, max_concurrent_por_direccion=1),
    dict(ema_periods=14, periodos_htf_min=800, buf_bp=1.2, rr=3.0, max_concurrent_por_direccion=3),
    dict(ema_periods=14, periodos_htf_min=800, buf_bp=1.2, rr=3.0, max_concurrent_por_direccion=1),
]


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
    path = DATA_DIR / f"{SYMBOL}_M5_latest.parquet"
    df = pd.read_parquet(path)
    n = len(df)
    third = n // 3
    splits = [
        ("sub1", df.iloc[0:third]),
        ("sub2", df.iloc[third:2 * third]),
        ("sub3", df.iloc[2 * third:n]),
    ]

    costs = get_live_costs(SYMBOL)

    rows = []
    for label, chunk in splits:
        t0 = pd.to_datetime(chunk["time_utc"].iloc[0], unit="s")
        t1 = pd.to_datetime(chunk["time_utc"].iloc[-1], unit="s")
        bars = {
            "time_utc": chunk["time_utc"].to_numpy(),
            "time_server": chunk["time_server"].to_numpy(),
            "open": chunk["open"].to_numpy(dtype=float),
            "high": chunk["high"].to_numpy(dtype=float),
            "low": chunk["low"].to_numpy(dtype=float),
            "close": chunk["close"].to_numpy(dtype=float),
            "spread_pts": chunk["spread"].to_numpy(dtype=float),
        }
        for cand in CANDIDATES:
            params = StrategyParams(fixed_lot=FIXED_LOT, valid_bars=10, orden_viva=True,
                                     max_bars_trade=500, **cand)
            res = run_backtest(bars["time_utc"], bars["time_server"], bars["open"], bars["high"],
                                bars["low"], bars["close"], bars["spread_pts"], params, costs)
            row = summarize(params, res)
            row["sub_periodo"] = label
            row["desde"] = str(t0)
            row["hasta"] = str(t1)
            row["n_velas"] = len(chunk)
            rows.append(row)

    out = pd.DataFrame(rows)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "robustness_subperiods.csv"
    out.to_csv(out_path, index=False)

    cols = ["sub_periodo", "desde", "hasta", "n_velas", "ema_periods", "periodos_htf_min",
            "buf_bp", "rr", "max_concurrent_por_direccion", "n_trades", "win_rate",
            "expectancy_r", "expectancy_usd", "max_drawdown_r"]
    print(out[cols].to_string(index=False))
    print(f"\nGuardado: {out_path}")

    print("\n== resumen por combinacion: positiva en los 3 sub-periodos? ==")
    for cand in CANDIDATES:
        mask = np.all([out[k] == v for k, v in cand.items()], axis=0)
        sub = out[mask]
        all_positive = bool((sub["expectancy_r"] > 0).all())
        print(f"{cand} -> expectancy_r por sub-periodo: {sub['expectancy_r'].tolist()} "
              f"-> {'CUMPLE (positiva en los 3)' if all_positive else 'NO CUMPLE'}")


if __name__ == "__main__":
    main()
