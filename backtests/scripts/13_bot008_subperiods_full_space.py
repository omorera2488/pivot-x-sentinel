"""BOT-008 -- cobertura exhaustiva de sub-periodos sobre el espacio UNICO de
1.260 combinaciones (las 3.780 filas de `sweep_full_M5_post_BOT-043.csv` son
en realidad 1.260 configuraciones de comportamiento unicas, repetidas 3 veces
cada una porque `max_concurrent_por_direccion` no tiene ningun efecto
mientras `una_operacion_a_la_vez=True` -- ver reporte).

A diferencia de `11_bot008_robustness_candidates.py` (que solo evalua un
conjunto preseleccionado de candidatos superiores en sub-periodos), este
script corre sub1/sub2/sub3 sobre las 1.260 combinaciones unicas COMPLETAS,
para responder de forma exhaustiva (no muestreada) cuantas configuraciones
del espacio total son positivas en 1/2/3 de los sub-periodos.

Uso:
    python backtests/scripts/13_bot008_subperiods_full_space.py [M5]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategy.engine import StrategyParams, run_backtest
from strategy.costs import BrokerCosts
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


def bars_of(d: pd.DataFrame) -> dict:
    return {
        "time_utc": d["time_utc"].to_numpy(), "time_server": d["time_server"].to_numpy(),
        "open": d["open"].to_numpy(dtype=float), "high": d["high"].to_numpy(dtype=float),
        "low": d["low"].to_numpy(dtype=float), "close": d["close"].to_numpy(dtype=float),
        "spread_pts": d["spread"].to_numpy(dtype=float),
    }


def expectancy_of(res) -> tuple[float, int]:
    trades = res.resolved_trades()
    n = len(trades)
    rs = [t.pnl_r for t in trades if t.pnl_r is not None]
    return (sum(rs) / n if n else float("nan")), n


def main():
    tf = "M5"
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    SYMBOL = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(SYMBOL)

    sweep = pd.read_csv(RESULTS_DIR / f"sweep_full_{tf}_post_BOT-043.csv")
    unique = sweep.drop_duplicates(subset=["ema_periods", "periodos_htf_min", "buf_bp", "rr"]).copy()
    print(f"Espacio unico: {len(unique)} configuraciones (de {len(sweep)} filas totales)")

    df = pd.read_parquet(DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet")
    n = len(df)
    n_sub = 3
    chunk = n // n_sub
    splits = [(f"sub{i+1}", df.iloc[i * chunk: n if i == n_sub - 1 else (i + 1) * chunk]) for i in range(n_sub)]
    sub_bars = [(label, bars_of(cdf)) for label, cdf in splits]

    rows = []
    t0 = time.time()
    for _, r in tqdm(unique.iterrows(), total=len(unique)):
        params = StrategyParams(
            ema_periods=int(r["ema_periods"]), periodos_htf_min=int(r["periodos_htf_min"]),
            buf_bp=r["buf_bp"], rr=r["rr"], max_concurrent_por_direccion=1,
            fixed_lot=FIXED_LOT, valid_bars=10, orden_viva=True, max_bars_trade=500,
        )
        exp_by_sub = {}
        n_by_sub = {}
        for label, cbars in sub_bars:
            res = run_backtest(cbars["time_utc"], cbars["time_server"], cbars["open"], cbars["high"],
                                cbars["low"], cbars["close"], cbars["spread_pts"], params, costs)
            exp_by_sub[label], n_by_sub[label] = expectancy_of(res)
        positive_subperiods = sum(1 for v in exp_by_sub.values() if v > 0)
        rows.append({
            "cfg_id": r["cfg_id"], "ema_periods": r["ema_periods"], "periodos_htf_min": r["periodos_htf_min"],
            "buf_bp": r["buf_bp"], "rr": r["rr"],
            "full_expectancy_r": r["expectancy_r"], "full_n_trades": r["n_trades"],
            "sub1_expectancy_r": exp_by_sub["sub1"], "sub1_n_trades": n_by_sub["sub1"],
            "sub2_expectancy_r": exp_by_sub["sub2"], "sub2_n_trades": n_by_sub["sub2"],
            "sub3_expectancy_r": exp_by_sub["sub3"], "sub3_n_trades": n_by_sub["sub3"],
            "positive_subperiods": positive_subperiods,
        })
    t1 = time.time()
    print(f"Sub-periodos sobre el espacio unico completo en {t1 - t0:.1f}s")

    out = pd.DataFrame(rows)
    out_path = RESULTS_DIR / f"bot008_subperiods_full_space_post_BOT-043_{tf}.csv"
    out.to_csv(out_path, index=False)
    print(f"Guardado: {out_path} ({len(out)} filas)")

    print("\n== Q4-Q6 (espacio unico completo, 1.260 configuraciones) ==")
    dist = out["positive_subperiods"].value_counts().sort_index()
    print("Distribucion de positive_subperiods (0,1,2,3):")
    print(dist.to_string())
    n_3of3 = int((out["positive_subperiods"] == 3).sum())
    n_2plus = int((out["positive_subperiods"] >= 2).sum())
    print(f"Q4 positivas en sub1,sub2,sub3 simultaneamente: {n_3of3}/{len(out)}")
    print(f"Q5 positivas en al menos 2 de 3: {n_2plus}/{len(out)}")
    best_by_sub = {s: out.sort_values(f"{s}_expectancy_r", ascending=False).iloc[0][f"{s}_expectancy_r"] for s in ("sub1", "sub2", "sub3")}
    print(f"Mejor expectancy por sub-periodo (cualquier config): {best_by_sub}")


if __name__ == "__main__":
    main()
