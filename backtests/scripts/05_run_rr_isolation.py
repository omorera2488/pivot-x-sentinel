"""Aislamiento del efecto de RR sobre una configuracion fija -- BOT-042
(re-ejecutado post BOT-043, motor de costos corregido).

Mantiene EMA/HTF/Buffer fijos (por defecto los de Config A: 12/800/0.4) y
corre el motor real (`strategy.engine.run_backtest`, costos reales via
`symbol_info`) UNA vez por cada valor de RR de la lista, sobre el mismo
dataset y con los mismos 3 sub-periodos por indice que usa
`04_run_robustness.py`. No es un barrido combinatorio (`03_run_sweep.py`):
una sola dimension (RR) variando, todo lo demas fijo.

Para cada RR calcula: metricas agregadas (trades, WR, Net R, expectancy, PF,
max DD, recovery, rachas de ganadores/perdedores, R promedio de ganadores/
perdedores, trades/mes, % overnight), resultados por sub-periodo,
distribucion completa de rachas de perdidas, desglose de costos (spread,
comision, swap, bruto vs neto) y percentiles de R realizado (ganadores y
perdedores por separado). Opcionalmente corre una config de referencia
adicional (ej. B) una sola vez, sin barrerla.

Uso:
    python scripts/05_run_rr_isolation.py [M5] [rr1,rr2,...]
Default: M5, RR = 1,2,3,4,5,7 sobre Config A (EMA=12,HTF=800,Buffer=0.4).

Salidas en results/ (sufijo "post_BOT-043" para no pisar nada contaminado):
    rr_summary_post_BOT-043_<TF>.csv       -- 1 fila por RR (+ referencia opcional), agregado
    rr_subperiods_post_BOT-043_<TF>.csv    -- 1 fila por RR x sub-periodo
    rr_loss_streaks_post_BOT-043_<TF>.csv  -- 1 fila por RR, distribucion de rachas de perdidas
    rr_cost_and_r_dist_post_BOT-043_<TF>.csv -- 1 fila por RR, costos + percentiles de R
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import strategy"

from strategy.engine import StrategyParams, run_backtest, _server_date
from strategy.costs import BrokerCosts
from execution.src.mt5_utils import resolve_symbol

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

FIXED_A = dict(ema_periods=12, periodos_htf_min=800, buf_bp=0.4)
CONFIG_B_REF = dict(ema_periods=17, periodos_htf_min=800, buf_bp=2.2, rr=3.0)
SHARED = dict(max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
              max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
              una_operacion_a_la_vez=True)
BREAKEVEN_WR = {1: 50.00, 2: 33.33, 3: 25.00, 4: 20.00, 5: 16.67, 7: 12.50}


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


def pct(arr, q):
    return float(np.percentile(arr, q)) if len(arr) else float("nan")


def summarize_trades(trades, bars_time_utc, costs: BrokerCosts, fixed_lot: float, label: str) -> dict:
    trades = sorted(trades, key=lambda t: t.entry_bar if t.entry_bar is not None else t.signal_bar)
    n_trades = len(trades)
    rs = [t.pnl_r for t in trades if t.pnl_r is not None]
    n_win = sum(1 for t in trades if t.outcome == "win")
    n_loss = sum(1 for t in trades if t.outcome == "loss")
    win_rate = (n_win / (n_win + n_loss)) if (n_win + n_loss) else float("nan")
    net_r = sum(rs)
    expectancy_r = net_r / n_trades if n_trades else float("nan")
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = -sum(r for r in rs if r < 0)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")
    if rs:
        equity = np.cumsum(rs)
        peak = np.maximum.accumulate(equity)
        max_dd_r = float((peak - equity).max())
    else:
        max_dd_r = float("nan")
    recovery_factor = (net_r / max_dd_r) if max_dd_r else float("nan")

    outcomes = [t.outcome if t.outcome in ("win", "loss") else ("win" if (t.pnl_r or 0) > 0 else "loss")
                for t in trades]
    streak_lengths = loss_streak_lengths(outcomes)
    max_loss_streak = max(streak_lengths) if streak_lengths else 0
    max_win_streak = win_streak_max(outcomes)

    winner_rs = np.array([t.pnl_r for t in trades if t.outcome == "win" and t.pnl_r is not None])
    loser_rs = np.array([t.pnl_r for t in trades if t.outcome == "loss" and t.pnl_r is not None])
    avg_winner_r = float(winner_rs.mean()) if len(winner_rs) else float("nan")
    avg_loser_r = float(loser_rs.mean()) if len(loser_rs) else float("nan")

    n_overnight = sum(1 for t in trades if t.nights_held and t.nights_held > 0)
    pct_overnight = n_overnight / n_trades if n_trades else float("nan")

    times = [bars_time_utc[t.entry_bar if t.entry_bar is not None else t.signal_bar] for t in trades]
    if times:
        t0 = pd.to_datetime(min(times), unit="s")
        t1 = pd.to_datetime(max(times), unit="s")
        months = max((t1 - t0).days / 30.4375, 1e-9)
        trades_per_month = n_trades / months
    else:
        trades_per_month = float("nan")

    # --- costos: bruto (sin spread/swap/comision) vs neto ---
    gross_list, spread_cost_list, swap_list, commission_list = [], [], [], []
    for t in trades:
        if t.entry_price is None or t.exit_price is None:
            continue
        raw_diff = (t.entry_price - t.exit_price) if t.direction < 0 else (t.exit_price - t.entry_price)
        gross_usd = costs.price_to_usd(raw_diff, fixed_lot)
        adj_diff = (t.entry_price_adj - t.exit_price_adj) if t.direction < 0 else (t.exit_price_adj - t.entry_price_adj)
        adj_usd = costs.price_to_usd(adj_diff, fixed_lot)
        spread_cost = gross_usd - adj_usd  # >=0 en general, costo de cruzar el spread
        commission = costs.commission_usd(fixed_lot)
        swap = t.pnl_usd - adj_usd + commission  # despeja swap de la ecuacion del motor
        gross_list.append(gross_usd)
        spread_cost_list.append(spread_cost)
        swap_list.append(swap)
        commission_list.append(commission)

    gross_pnl_usd = float(sum(gross_list))
    net_pnl_usd = float(sum(t.pnl_usd for t in trades if t.pnl_usd is not None))
    swap_total_usd = float(sum(swap_list))
    swap_overnight_vals = [s for s, t in zip(swap_list, trades) if t.nights_held and t.nights_held > 0]
    swap_avg_per_overnight = float(np.mean(swap_overnight_vals)) if swap_overnight_vals else 0.0
    commission_total_usd = float(sum(commission_list))
    spread_total_usd = float(sum(spread_cost_list))
    total_costs_usd = gross_pnl_usd - net_pnl_usd  # incluye spread + comision - swap(con su signo)

    rs_arr = np.array(rs) if rs else np.array([])
    r_dist = {
        "r_min": float(rs_arr.min()) if len(rs_arr) else float("nan"),
        "r_max": float(rs_arr.max()) if len(rs_arr) else float("nan"),
        "r_p1": pct(rs_arr, 1), "r_p5": pct(rs_arr, 5), "r_p50": pct(rs_arr, 50),
        "r_p95": pct(rs_arr, 95), "r_p99": pct(rs_arr, 99),
        "winner_r_mean": avg_winner_r, "winner_r_median": pct(winner_rs, 50),
        "winner_r_p10": pct(winner_rs, 10), "winner_r_p90": pct(winner_rs, 90),
        "loser_r_mean": avg_loser_r, "loser_r_median": pct(loser_rs, 50),
        "loser_r_p10": pct(loser_rs, 10), "loser_r_p90": pct(loser_rs, 90),
    }

    return {
        "label": label, "n_trades": n_trades, "n_win": n_win, "n_loss": n_loss,
        "win_rate": win_rate, "net_r": net_r, "expectancy_r": expectancy_r,
        "profit_factor": profit_factor, "max_drawdown_r": max_dd_r, "recovery_factor": recovery_factor,
        "max_loss_streak": max_loss_streak, "max_win_streak": max_win_streak,
        "avg_winner_r": avg_winner_r, "avg_loser_r": avg_loser_r,
        "trades_per_month": trades_per_month, "pct_overnight": pct_overnight,
        "n_overnight": n_overnight,
        "streak_lengths": streak_lengths,
        "streak_ge3": sum(1 for L in streak_lengths if L >= 3),
        "streak_ge5": sum(1 for L in streak_lengths if L >= 5),
        "streak_ge7": sum(1 for L in streak_lengths if L >= 7),
        "streak_ge10": sum(1 for L in streak_lengths if L >= 10),
        "streak_ge15": sum(1 for L in streak_lengths if L >= 15),
        "streak_ge20": sum(1 for L in streak_lengths if L >= 20),
        "n_loss_streaks_total": len(streak_lengths),
        "gross_pnl_usd": gross_pnl_usd, "net_pnl_usd": net_pnl_usd,
        "swap_total_usd": swap_total_usd, "swap_avg_per_overnight_usd": swap_avg_per_overnight,
        "commission_total_usd": commission_total_usd, "spread_total_usd": spread_total_usd,
        "total_costs_usd": total_costs_usd,
        **r_dist,
    }


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    rr_arg = sys.argv[2] if len(sys.argv) > 2 else "1,2,3,4,5,7"
    rr_values = [float(x) for x in rr_arg.split(",")]

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
    n = len(df)
    print(f"Dataset: {path.name} -- {n} velas, "
          f"{pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. {pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    bars = bars_of(df)

    n_sub = 3
    chunk = n // n_sub
    splits = [(f"sub{i+1}", df.iloc[i * chunk: n if i == n_sub - 1 else (i + 1) * chunk]) for i in range(n_sub)]

    configs = [(f"A_RR{int(rr) if rr == int(rr) else rr}", dict(**FIXED_A, rr=rr), rr) for rr in rr_values]
    configs.append(("B_referencia_motor_corregido", CONFIG_B_REF, CONFIG_B_REF["rr"]))

    summary_rows, subperiod_rows, streak_rows, costdist_rows = [], [], [], []
    all_full = {}

    for label, cfg, rr in configs:
        params = StrategyParams(**cfg, **SHARED)
        res = run_backtest(bars["time_utc"], bars["time_server"], bars["open"], bars["high"],
                            bars["low"], bars["close"], bars["spread_pts"], params, costs)
        m = summarize_trades(res.resolved_trades(), bars["time_utc"], costs, params.fixed_lot, label)
        all_full[label] = m
        summary_rows.append({
            "config": label, "rr": rr, **{k: v for k, v in m.items()
                                           if k not in ("streak_lengths",) and not k.startswith("r_") and not k.endswith("_r_mean")
                                           and not k.endswith("_r_median") and not k.endswith("_r_p10") and not k.endswith("_r_p90")}
        })
        streak_rows.append({
            "config": label, "rr": rr, "max_loss_streak": m["max_loss_streak"],
            "streak_ge3": m["streak_ge3"], "streak_ge5": m["streak_ge5"], "streak_ge7": m["streak_ge7"],
            "streak_ge10": m["streak_ge10"], "streak_ge15": m["streak_ge15"], "streak_ge20": m["streak_ge20"],
            "n_loss_streaks_total": m["n_loss_streaks_total"],
        })
        costdist_rows.append({
            "config": label, "rr": rr,
            "pct_overnight": m["pct_overnight"], "n_overnight": m["n_overnight"],
            "swap_total_usd": m["swap_total_usd"], "swap_avg_per_overnight_usd": m["swap_avg_per_overnight_usd"],
            "commission_total_usd": m["commission_total_usd"], "spread_total_usd": m["spread_total_usd"],
            "total_costs_usd": m["total_costs_usd"], "gross_pnl_usd": m["gross_pnl_usd"], "net_pnl_usd": m["net_pnl_usd"],
            "r_min": m["r_min"], "r_max": m["r_max"], "r_p1": m["r_p1"], "r_p5": m["r_p5"], "r_p50": m["r_p50"],
            "r_p95": m["r_p95"], "r_p99": m["r_p99"],
            "winner_r_mean": m["winner_r_mean"], "winner_r_median": m["winner_r_median"],
            "winner_r_p10": m["winner_r_p10"], "winner_r_p90": m["winner_r_p90"],
            "loser_r_mean": m["loser_r_mean"], "loser_r_median": m["loser_r_median"],
            "loser_r_p10": m["loser_r_p10"], "loser_r_p90": m["loser_r_p90"],
        })

        for sub_label, chunk_df in splits:
            t0 = pd.to_datetime(chunk_df["time_utc"].iloc[0], unit="s")
            t1 = pd.to_datetime(chunk_df["time_utc"].iloc[-1], unit="s")
            cbars = bars_of(chunk_df)
            res_s = run_backtest(cbars["time_utc"], cbars["time_server"], cbars["open"], cbars["high"],
                                  cbars["low"], cbars["close"], cbars["spread_pts"], params, costs)
            m_s = summarize_trades(res_s.resolved_trades(), cbars["time_utc"], costs, params.fixed_lot,
                                    f"{label}-{sub_label}")
            subperiod_rows.append({
                "config": label, "rr": rr, "sub_periodo": sub_label, "desde": str(t0), "hasta": str(t1),
                "n_velas": len(chunk_df), "n_trades": m_s["n_trades"], "win_rate": m_s["win_rate"],
                "net_r": m_s["net_r"], "expectancy_r": m_s["expectancy_r"], "profit_factor": m_s["profit_factor"],
                "max_drawdown_r": m_s["max_drawdown_r"], "max_loss_streak": m_s["max_loss_streak"],
            })

        print(f"{label} (rr={rr}): n_trades={m['n_trades']} WR={m['win_rate']:.4f} "
              f"netR={m['net_r']:.2f} expR={m['expectancy_r']:.4f} PF={m['profit_factor']:.3f} "
              f"maxDD={m['max_drawdown_r']:.2f} pct_overnight={m['pct_overnight']:.3f}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"post_BOT-043_{tf}"
    pd.DataFrame(summary_rows).to_csv(RESULTS_DIR / f"rr_summary_{suffix}.csv", index=False)
    pd.DataFrame(subperiod_rows).to_csv(RESULTS_DIR / f"rr_subperiods_{suffix}.csv", index=False)
    pd.DataFrame(streak_rows).to_csv(RESULTS_DIR / f"rr_loss_streaks_{suffix}.csv", index=False)
    pd.DataFrame(costdist_rows).to_csv(RESULTS_DIR / f"rr_cost_and_r_dist_{suffix}.csv", index=False)

    # dump JSON completo (incluye streak_lengths crudos) para trazabilidad total
    json_out = {"symbol": SYMBOL, "n_velas": n, "costs": {
        "point": costs.point, "contract_size": costs.contract_size, "tick_value": costs.tick_value,
        "tick_size": costs.tick_size, "swap_long_points": costs.swap_long_points,
        "swap_short_points": costs.swap_short_points, "commission_per_lot": costs.commission_per_lot,
    }, "full_period": all_full, "subperiods": subperiod_rows}
    with open(RESULTS_DIR / f"rr_isolation_{suffix}.json", "w", encoding="utf-8") as f:
        json.dump(json_out, f, indent=2, default=str)

    print(f"\nGuardado en {RESULTS_DIR}:")
    for fn in (f"rr_summary_{suffix}.csv", f"rr_subperiods_{suffix}.csv",
               f"rr_loss_streaks_{suffix}.csv", f"rr_cost_and_r_dist_{suffix}.csv",
               f"rr_isolation_{suffix}.json"):
        print(f"  {fn}")


if __name__ == "__main__":
    main()
