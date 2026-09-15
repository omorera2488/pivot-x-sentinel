"""BOT-008 -- etapa 2: robustez temporal de un conjunto amplio de candidatos
superiores del barrido de 3.780 combinaciones (10_bot008_full_sweep_rerun.py).

Criterios de seleccion de candidatos, PRE-DEFINIDOS antes de mirar el
resultado del sweep completo (para evitar "elegir el que mejor da" a
posteriori):
  1. Muestra minima: n_trades >= 100 en el periodo completo (mas exigente
     que el umbral n_trades>=30 del barrido original -- con 3 sub-periodos,
     100 trades totales da ~33/sub-periodo en promedio, similar al piso
     original por tramo).
  2. Conjunto amplio, no "Top 1": union de top 25 por expectancy_r, top 25
     por profit_factor, y top 25 por recovery factor (net_r/max_drawdown_r),
     todos sobre el subconjunto que cumple (1). Se espera bastante
     superposicion entre los tres rankings -- el conjunto final tipicamente
     queda muy por debajo de 75 candidatos unicos.

Para cada candidato (y Config A como referencia) corre el motor sobre los
mismos 3 sub-periodos por indice que usa `04_run_robustness.py`/
`05_run_rr_isolation.py`, calcula N/WR/expectancy/PF/Net R/Max DD por
sub-periodo, `positive_subperiods` (cuantos de los 3 tienen expectancy>0),
y una senal de dependencia de sub2 (que porcion del Net R total del periodo
completo viene de sub2 en particular).

Uso:
    python backtests/scripts/11_bot008_robustness_candidates.py [M5]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategy.engine import StrategyParams, run_backtest
from strategy.costs import BrokerCosts
from execution.src.mt5_utils import resolve_symbol

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
FIXED_LOT = 0.01
N_MIN_TRADES = 100
TOP_N_PER_METRIC = 25

CONFIG_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4, rr=1.0, max_concurrent_por_direccion=1)


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


def metrics_for(res) -> dict:
    trades = res.resolved_trades()
    n = len(trades)
    rs = [t.pnl_r for t in trades if t.pnl_r is not None]
    n_win = sum(1 for t in trades if t.outcome == "win")
    n_loss = sum(1 for t in trades if t.outcome == "loss")
    net_r = sum(rs) if rs else float("nan")
    exp_r = net_r / n if n else float("nan")
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = -sum(r for r in rs if r < 0)
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    if rs:
        eq = np.cumsum(rs)
        peak = np.maximum.accumulate(eq)
        max_dd = float((peak - eq).max())
    else:
        max_dd = float("nan")
    wr = (n_win / (n_win + n_loss)) if (n_win + n_loss) else float("nan")
    return {"n_trades": n, "win_rate": wr, "net_r": net_r, "expectancy_r": exp_r,
            "profit_factor": pf, "max_drawdown_r": max_dd}


def main():
    tf = "M5"
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")
    SYMBOL = resolve_symbol("XAUUSD")
    mt5.shutdown()
    costs = get_live_costs(SYMBOL)

    sweep_path = RESULTS_DIR / f"sweep_full_{tf}_post_BOT-043.csv"
    sweep = pd.read_csv(sweep_path)
    print(f"Barrido cargado: {sweep_path.name} ({len(sweep)} filas)")

    pool = sweep[sweep["n_trades"] >= N_MIN_TRADES].copy()
    print(f"Con n_trades>={N_MIN_TRADES}: {len(pool)}/{len(sweep)} configuraciones")

    top_exp = pool.sort_values("expectancy_r", ascending=False).head(TOP_N_PER_METRIC)
    top_pf = pool.sort_values("profit_factor", ascending=False).head(TOP_N_PER_METRIC)
    pool_finite_recovery = pool[pool["max_drawdown_r"] > 0].copy()
    pool_finite_recovery["recovery_factor"] = pool_finite_recovery["net_r"] / pool_finite_recovery["max_drawdown_r"]
    top_recovery = pool_finite_recovery.sort_values("recovery_factor", ascending=False).head(TOP_N_PER_METRIC)

    candidate_ids = sorted(set(top_exp["cfg_id"]) | set(top_pf["cfg_id"]) | set(top_recovery["cfg_id"]))
    print(f"Candidatos unicos (union top {TOP_N_PER_METRIC} expectancy / PF / recovery): {len(candidate_ids)}")

    candidates = sweep[sweep["cfg_id"].isin(candidate_ids)][
        ["cfg_id", "ema_periods", "periodos_htf_min", "buf_bp", "rr", "max_concurrent_por_direccion",
         "n_trades", "win_rate", "profit_factor", "expectancy_r", "net_r", "max_drawdown_r"]
    ].to_dict("records")

    df = pd.read_parquet(DATA_DIR / f"{SYMBOL}_{tf}_latest.parquet")
    n = len(df)
    n_sub = 3
    chunk = n // n_sub
    splits = [(f"sub{i+1}", df.iloc[i * chunk: n if i == n_sub - 1 else (i + 1) * chunk]) for i in range(n_sub)]
    full_bars = bars_of(df)

    all_configs = [("ConfigA_referencia", CONFIG_A)] + [
        (c["cfg_id"], dict(ema_periods=int(c["ema_periods"]), periodos_htf_min=int(c["periodos_htf_min"]),
                            buf_bp=c["buf_bp"], rr=c["rr"],
                            max_concurrent_por_direccion=int(c["max_concurrent_por_direccion"])))
        for c in candidates
    ]

    rows = []
    for label, cfg in all_configs:
        params = StrategyParams(fixed_lot=FIXED_LOT, valid_bars=10, orden_viva=True, max_bars_trade=500, **cfg)
        res_full = run_backtest(full_bars["time_utc"], full_bars["time_server"], full_bars["open"], full_bars["high"],
                                 full_bars["low"], full_bars["close"], full_bars["spread_pts"], params, costs)
        m_full = metrics_for(res_full)

        sub_metrics = {}
        for label_sub, chunk_df in splits:
            cbars = bars_of(chunk_df)
            res_s = run_backtest(cbars["time_utc"], cbars["time_server"], cbars["open"], cbars["high"],
                                  cbars["low"], cbars["close"], cbars["spread_pts"], params, costs)
            sub_metrics[label_sub] = metrics_for(res_s)

        positive_subperiods = sum(1 for s in sub_metrics.values() if s["expectancy_r"] > 0)
        net_r_total = m_full["net_r"]
        net_r_sub2 = sub_metrics["sub2"]["net_r"]
        # cuota de sub2 sobre el Net R total -- solo tiene sentido si el total es positivo y finito
        sub2_share_of_net_r = (net_r_sub2 / net_r_total) if (net_r_total and net_r_total > 0) else float("nan")
        sub2_dependent = bool(
            sub_metrics["sub2"]["expectancy_r"] > 0
            and sub_metrics["sub1"]["expectancy_r"] <= 0
            and sub_metrics["sub3"]["expectancy_r"] <= 0
        )

        row = {"cfg_id": label, **cfg,
               "full_n_trades": m_full["n_trades"], "full_win_rate": m_full["win_rate"],
               "full_net_r": m_full["net_r"], "full_expectancy_r": m_full["expectancy_r"],
               "full_pf": m_full["profit_factor"], "full_max_dd_r": m_full["max_drawdown_r"],
               "positive_subperiods": positive_subperiods,
               "sub2_only_positive": sub2_dependent,
               "sub2_share_of_net_r": sub2_share_of_net_r}
        for s in ("sub1", "sub2", "sub3"):
            for k in ("n_trades", "win_rate", "net_r", "expectancy_r", "profit_factor", "max_drawdown_r"):
                row[f"{s}_{k}"] = sub_metrics[s][k]
        rows.append(row)
        print(f"{label}: full n={m_full['n_trades']} expR={m_full['expectancy_r']:.4f} PF={m_full['profit_factor']:.3f} "
              f"| positive_subperiods={positive_subperiods} sub2_only={sub2_dependent}")

    out = pd.DataFrame(rows)
    out_path = RESULTS_DIR / f"bot008_robustness_candidates_post_BOT-043_{tf}.csv"
    out.to_csv(out_path, index=False)
    print(f"\nGuardado: {out_path} ({len(out)} filas: Config A + {len(candidates)} candidatos)")


if __name__ == "__main__":
    main()
