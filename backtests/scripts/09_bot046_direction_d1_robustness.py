"""BOT-046 -- validacion controlada de Direccion (LONG/SHORT) y Alineacion D1
+ robustez temporal, a partir de las hipotesis H1/H2/H3 generadas por BOT-045.

100% offline y diagnostico: NO modifica /strategy, /execution, la API, el
panel, ni ningun parametro de produccion (Config A queda exactamente igual a
BOT-045). NO recalcula indicadores -- reutiliza directamente el dataset
enriquecido de BOT-045 (backtests/results/BOT-045_trades_enriched_M5.csv).

Hipotesis (congeladas ANTES de mirar el holdout, ver docs/reports/
BOT-045_market_regime_analysis.md):
    H1 -- asimetria direccional: SHORT > LONG en expectancy, de forma robusta.
    H2 -- alineacion D1: alineado > contra, de forma robusta.
    H3 -- interaccion Direccion x D1: LONG sigue siendo malo aun alineado con
          D1? SHORT conserva su ventaja aun en contra de D1?

Uso:
    python backtests/scripts/09_bot046_direction_d1_robustness.py [M5]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CHARTS_DIR = RESULTS_DIR / "BOT-046_charts"

BLOCK_LEN_HEURISTIC = None  # se fija en main() como round(sqrt(N)), documentado
N_BOOTSTRAP = 10_000
MIN_SAMPLE_FLAG = 20  # bajo este N, se marca "muestra_insuficiente" (no se oculta el numero)

# --- valores reportados en BOT-045_market_regime_analysis.md, para el sanity
# check de reproduccion (ticket BOT-046 SS6) -- NO se recalculan, solo se
# comparan contra lo que da el CSV reusado.
BOT045_REPORTED = {
    ("direction", "LONG"): dict(n=1189, expectancy_r=-0.100),
    ("direction", "SHORT"): dict(n=1285, expectancy_r=0.004),
    ("d1", "aligned"): dict(n=321, expectancy_r=0.067),
    ("d1", "against"): dict(n=325, expectancy_r=-0.183),
    ("d1", "neutral"): dict(n=1828, expectancy_r=-0.042),
}


# ------------------------------------------------------------------
# Metricas por grupo -- N, %, wins, losses, WR, PF, expectancy, Net R,
# Net USD, avg winner/loser R, max DD R, max DD USD, longest losing streak.
# ------------------------------------------------------------------
def group_metrics(sub: pd.DataFrame, n_period_total: int) -> dict:
    n = len(sub)
    if n == 0:
        return {"n_trades": 0, "pct_of_period": 0.0, "wins": 0, "losses": 0,
                "win_rate": np.nan, "profit_factor": np.nan, "expectancy_r": np.nan,
                "net_r": np.nan, "net_usd": np.nan, "avg_winner_r": np.nan,
                "avg_loser_r": np.nan, "max_dd_r": np.nan, "max_dd_usd": np.nan,
                "max_losing_streak": 0, "muestra_insuficiente": True}

    sub_sorted = sub.sort_values("entry_bar")
    wins = int((sub_sorted["outcome"] == "win").sum())
    losses = int((sub_sorted["outcome"] == "loss").sum())
    wr = wins / (wins + losses) if (wins + losses) else float("nan")
    rs = sub_sorted["pnl_r"].dropna().to_numpy()
    gross_win = rs[rs > 0].sum() if len(rs) else 0.0
    gross_loss = -rs[rs < 0].sum() if len(rs) else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else float("nan"))
    expectancy_r = rs.mean() if len(rs) else float("nan")
    net_r = rs.sum() if len(rs) else float("nan")
    net_usd = sub_sorted["pnl_usd"].dropna().sum() if n else float("nan")
    avg_win = sub_sorted.loc[sub_sorted["outcome"] == "win", "pnl_r"].mean()
    avg_loss = sub_sorted.loc[sub_sorted["outcome"] == "loss", "pnl_r"].mean()

    if len(rs):
        eq_r = np.cumsum(rs)
        peak_r = np.maximum.accumulate(eq_r)
        max_dd_r = float((peak_r - eq_r).max())
    else:
        max_dd_r = float("nan")

    usd = sub_sorted["pnl_usd"].dropna().to_numpy()
    if len(usd):
        eq_u = np.cumsum(usd)
        peak_u = np.maximum.accumulate(eq_u)
        max_dd_usd = float((peak_u - eq_u).max())
    else:
        max_dd_usd = float("nan")

    outcomes = sub_sorted["outcome"].tolist()
    cur = best = 0
    for o in outcomes:
        if o == "loss":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0

    return {
        "n_trades": n, "pct_of_period": (n / n_period_total * 100.0) if n_period_total else float("nan"),
        "wins": wins, "losses": losses, "win_rate": wr, "profit_factor": pf,
        "expectancy_r": expectancy_r, "net_r": net_r, "net_usd": net_usd,
        "avg_winner_r": avg_win, "avg_loser_r": avg_loss,
        "max_dd_r": max_dd_r, "max_dd_usd": max_dd_usd,
        "max_losing_streak": best, "muestra_insuficiente": n < MIN_SAMPLE_FLAG,
    }


def d1_condition(row) -> str:
    v = row["aligned_with_d1"]
    if pd.isna(v):
        return "neutral"
    return "aligned" if bool(v) else "against"


def build_periods(df: pd.DataFrame, n_bars: int) -> dict:
    """Devuelve {nombre_periodo: mascara_booleana} para completo/sub1-3/T1-6/
    development/holdout. Todos los cortes son por indice de barra (entry_bar),
    exactamente el mismo criterio que ya usa sub_periodo en BOT-045 (no una
    metodologia nueva)."""
    periods = {"completo": pd.Series(True, index=df.index)}
    for sp in ("sub1", "sub2", "sub3"):
        periods[sp] = df["sub_periodo"] == sp

    n_sex = 6
    chunk = n_bars // n_sex
    for k in range(n_sex):
        lo = k * chunk
        hi = n_bars if k == n_sex - 1 else (k + 1) * chunk
        periods[f"T{k+1}"] = (df["entry_bar"] >= lo) & (df["entry_bar"] < hi)

    cutoff = int(round(n_bars * 0.7))
    periods["development"] = df["entry_bar"] < cutoff
    periods["holdout"] = df["entry_bar"] >= cutoff
    return periods, cutoff


def moving_block_bootstrap_indices(n: int, block_len: int, rng: np.random.Generator) -> np.ndarray:
    """Bloques circulares (wrap-around) de largo block_len, muestreados con
    reemplazo hasta cubrir >= n posiciones, truncado a n."""
    n_blocks_needed = int(np.ceil(n / block_len))
    starts = rng.integers(0, n, size=n_blocks_needed)
    idx = np.concatenate([np.arange(s, s + block_len) % n for s in starts])
    return idx[:n]


def bootstrap_deltas(sub: pd.DataFrame, block_len: int, n_boot: int, rng: np.random.Generator):
    """Block bootstrap sobre la secuencia cronologica de trades de `sub`
    (ordenada por entry_bar). Devuelve arrays de delta_direction y delta_d1
    (NaN cuando algun grupo queda vacio en ese resample)."""
    s = sub.sort_values("entry_bar").reset_index(drop=True)
    n = len(s)
    direction = s["direction"].to_numpy()
    d1c = s.apply(d1_condition, axis=1).to_numpy()
    pnl_r = s["pnl_r"].to_numpy()

    deltas_dir = np.full(n_boot, np.nan)
    deltas_d1 = np.full(n_boot, np.nan)
    for b in range(n_boot):
        idx = moving_block_bootstrap_indices(n, block_len, rng)
        d = direction[idx]
        c = d1c[idx]
        r = pnl_r[idx]
        short_r = r[d == "SHORT"]
        long_r = r[d == "LONG"]
        if len(short_r) and len(long_r):
            deltas_dir[b] = short_r.mean() - long_r.mean()
        aligned_r = r[c == "aligned"]
        against_r = r[c == "against"]
        if len(aligned_r) and len(against_r):
            deltas_d1[b] = aligned_r.mean() - against_r.mean()
    return deltas_dir, deltas_d1


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    global BLOCK_LEN_HEURISTIC

    # --- 0. dataset base: reusar BOT-045 tal cual, sin recalcular nada ------
    parquet_path = DATA_DIR / f"XAUUSDc_{tf}_latest.parquet"
    n_bars = len(pd.read_parquet(parquet_path, columns=["time_utc"]))
    df = pd.read_csv(RESULTS_DIR / f"BOT-045_trades_enriched_{tf}.csv")
    df["entry_time_utc"] = pd.to_datetime(df["entry_time_utc"], utc=True)
    df["d1_condition"] = df.apply(d1_condition, axis=1)
    n_total = len(df)
    print(f"Dataset reusado de BOT-045: {n_total} operaciones, {n_bars} velas totales "
          f"({parquet_path.name})")

    # --- 1. sanity check: reproducir BOT-045 --------------------------------
    print("\n== Sanity check -- reproduccion de BOT-045 ==")
    ok_all = True
    for (kind, cat), expected in BOT045_REPORTED.items():
        if kind == "direction":
            sub = df[df["direction"] == cat]
        else:
            sub = df[df["d1_condition"] == cat]
        n = len(sub)
        exp_r = sub["pnl_r"].mean()
        n_ok = n == expected["n"]
        exp_ok = abs(exp_r - expected["expectancy_r"]) < 0.001
        ok_all = ok_all and n_ok and exp_ok
        print(f"  {kind}={cat}: N={n} (esperado {expected['n']}, {'OK' if n_ok else 'DIFIERE'}) "
              f"expectancy_r={exp_r:.4f} (esperado {expected['expectancy_r']:.4f}, "
              f"{'OK' if exp_ok else 'DIFIERE'})")
    if not ok_all:
        print("ADVERTENCIA: alguna reproduccion no coincide exactamente -- revisar antes de continuar.")
    else:
        print("Reproduccion de BOT-045 OK -- se continua con el experimento.")

    # --- 2. periodos (sub1-3, T1-6, dev/holdout) -----------------------------
    periods, cutoff_bar = build_periods(df, n_bars)
    cutoff_time = df.loc[df["entry_bar"] >= cutoff_bar, "entry_time_utc"].min()
    print(f"\nCorte development/holdout: entry_bar < {cutoff_bar} (70% de {n_bars} velas) "
          f"-- holdout arranca ~{cutoff_time}")
    for name, mask in periods.items():
        t0 = df.loc[mask, "entry_time_utc"].min()
        t1 = df.loc[mask, "entry_time_utc"].max()
        print(f"  {name}: n={mask.sum():4d}  {t0} .. {t1}")

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    # --- 3. BOT-046_direction_M5.csv / _d1_M5.csv / _interaction_M5.csv -----
    direction_rows, d1_rows, inter_rows = [], [], []
    GROUPS_INTER = {
        "G1_LONG_alineado": lambda d: (d["direction"] == "LONG") & (d["d1_condition"] == "aligned"),
        "G2_LONG_contra": lambda d: (d["direction"] == "LONG") & (d["d1_condition"] == "against"),
        "G3_LONG_neutral": lambda d: (d["direction"] == "LONG") & (d["d1_condition"] == "neutral"),
        "G4_SHORT_alineado": lambda d: (d["direction"] == "SHORT") & (d["d1_condition"] == "aligned"),
        "G5_SHORT_contra": lambda d: (d["direction"] == "SHORT") & (d["d1_condition"] == "against"),
        "G6_SHORT_neutral": lambda d: (d["direction"] == "SHORT") & (d["d1_condition"] == "neutral"),
    }

    for period_name, pmask in periods.items():
        pdf = df[pmask]
        n_period = len(pdf)

        m_base = group_metrics(pdf, n_period)
        direction_rows.append({"period": period_name, "group": "A_baseline", **m_base})
        d1_rows.append({"period": period_name, "group": "A_baseline", **m_base})

        for lab in ("LONG", "SHORT"):
            m = group_metrics(pdf[pdf["direction"] == lab], n_period)
            direction_rows.append({"period": period_name, "group": lab, **m})

        for lab, key in (("aligned", "D_aligned"), ("against", "E_against"), ("neutral", "F_neutral")):
            m = group_metrics(pdf[pdf["d1_condition"] == lab], n_period)
            d1_rows.append({"period": period_name, "group": key, **m})

        for gname, gfn in GROUPS_INTER.items():
            m = group_metrics(pdf[gfn(pdf)], n_period)
            inter_rows.append({"period": period_name, "group": gname, **m})

    pd.DataFrame(direction_rows).to_csv(RESULTS_DIR / f"BOT-046_direction_{tf}.csv", index=False)
    pd.DataFrame(d1_rows).to_csv(RESULTS_DIR / f"BOT-046_d1_{tf}.csv", index=False)
    pd.DataFrame(inter_rows).to_csv(RESULTS_DIR / f"BOT-046_direction_d1_interaction_{tf}.csv", index=False)
    print(f"\nGuardado: BOT-046_direction_{tf}.csv, BOT-046_d1_{tf}.csv, "
          f"BOT-046_direction_d1_interaction_{tf}.csv")

    # --- 4. BOT-046_sextiles_M5.csv (resumen ancho, T1..T6) ------------------
    sex_rows = []
    for t in [f"T{k}" for k in range(1, 7)]:
        pdf = df[periods[t]]
        n_period = len(pdf)
        t0 = pdf["entry_time_utc"].min()
        t1 = pdf["entry_time_utc"].max()
        m_base = group_metrics(pdf, n_period)
        m_long = group_metrics(pdf[pdf["direction"] == "LONG"], n_period)
        m_short = group_metrics(pdf[pdf["direction"] == "SHORT"], n_period)
        m_al = group_metrics(pdf[pdf["d1_condition"] == "aligned"], n_period)
        m_ag = group_metrics(pdf[pdf["d1_condition"] == "against"], n_period)
        m_ne = group_metrics(pdf[pdf["d1_condition"] == "neutral"], n_period)
        sex_rows.append({
            "sextil": t, "desde": t0, "hasta": t1, "n_total": n_period,
            "expectancy_baseline": m_base["expectancy_r"], "pf_baseline": m_base["profit_factor"],
            "n_long": m_long["n_trades"], "expectancy_long": m_long["expectancy_r"],
            "n_short": m_short["n_trades"], "expectancy_short": m_short["expectancy_r"],
            "delta_direction_short_minus_long": m_short["expectancy_r"] - m_long["expectancy_r"],
            "n_aligned": m_al["n_trades"], "expectancy_aligned": m_al["expectancy_r"],
            "n_against": m_ag["n_trades"], "expectancy_against": m_ag["expectancy_r"],
            "delta_d1_aligned_minus_against": m_al["expectancy_r"] - m_ag["expectancy_r"],
            "n_neutral": m_ne["n_trades"], "expectancy_neutral": m_ne["expectancy_r"],
        })
    sextiles_df = pd.DataFrame(sex_rows)
    sextiles_df.to_csv(RESULTS_DIR / f"BOT-046_sextiles_{tf}.csv", index=False)
    print(f"Guardado: BOT-046_sextiles_{tf}.csv")
    print(sextiles_df[["sextil", "n_total", "expectancy_baseline", "delta_direction_short_minus_long",
                        "delta_d1_aligned_minus_against"]].round(4).to_string(index=False))

    # --- 5. Rolling windows (3 meses, avance 1 mes, por entry_time_utc) -----
    t_start = df["entry_time_utc"].min().normalize()
    t_end = df["entry_time_utc"].max()
    rolling_rows = []
    w_start = t_start
    while w_start < t_end:
        w_end = min(w_start + pd.DateOffset(months=3), t_end + pd.Timedelta(seconds=1))
        wmask = (df["entry_time_utc"] >= w_start) & (df["entry_time_utc"] < w_end)
        wdf = df[wmask]
        n_period = len(wdf)
        m_base = group_metrics(wdf, n_period)
        m_long = group_metrics(wdf[wdf["direction"] == "LONG"], n_period)
        m_short = group_metrics(wdf[wdf["direction"] == "SHORT"], n_period)
        m_al = group_metrics(wdf[wdf["d1_condition"] == "aligned"], n_period)
        m_ag = group_metrics(wdf[wdf["d1_condition"] == "against"], n_period)
        row = {
            "window_start": w_start, "window_end": w_end, "n_total": n_period,
            "expectancy_baseline": m_base["expectancy_r"], "pf_baseline": m_base["profit_factor"],
            "net_r_baseline": m_base["net_r"],
            "n_long": m_long["n_trades"], "expectancy_long": m_long["expectancy_r"], "net_r_long": m_long["net_r"],
            "n_short": m_short["n_trades"], "expectancy_short": m_short["expectancy_r"], "net_r_short": m_short["net_r"],
            "delta_direction_short_minus_long": m_short["expectancy_r"] - m_long["expectancy_r"],
            "n_aligned": m_al["n_trades"], "expectancy_aligned": m_al["expectancy_r"], "net_r_aligned": m_al["net_r"],
            "n_against": m_ag["n_trades"], "expectancy_against": m_ag["expectancy_r"], "net_r_against": m_ag["net_r"],
            "delta_d1_aligned_minus_against": m_al["expectancy_r"] - m_ag["expectancy_r"],
            "muestra_direction_insuficiente": (m_long["n_trades"] < MIN_SAMPLE_FLAG or m_short["n_trades"] < MIN_SAMPLE_FLAG),
            "muestra_d1_insuficiente": (m_al["n_trades"] < MIN_SAMPLE_FLAG or m_ag["n_trades"] < MIN_SAMPLE_FLAG),
        }
        for gname, gfn in GROUPS_INTER.items():
            m = group_metrics(wdf[gfn(wdf)], n_period)
            row[f"n_{gname}"] = m["n_trades"]
            row[f"expectancy_{gname}"] = m["expectancy_r"]
        rolling_rows.append(row)
        w_start = w_start + pd.DateOffset(months=1)

    rolling_df = pd.DataFrame(rolling_rows)
    rolling_df.to_csv(RESULTS_DIR / f"BOT-046_rolling_{tf}.csv", index=False)
    print(f"\nGuardado: BOT-046_rolling_{tf}.csv ({len(rolling_df)} ventanas de 3 meses, avance mensual)")

    # --- 6. Development 70% vs Holdout 30% -----------------------------------
    dh_rows = []
    for scope in ("development", "holdout"):
        pdf = df[periods[scope]]
        n_period = len(pdf)
        m_base = group_metrics(pdf, n_period)
        dh_rows.append({"scope": scope, "group": "A_baseline", **m_base})
        for lab in ("LONG", "SHORT"):
            m = group_metrics(pdf[pdf["direction"] == lab], n_period)
            dh_rows.append({"scope": scope, "group": lab, **m})
        for lab, key in (("aligned", "D_aligned"), ("against", "E_against"), ("neutral", "F_neutral")):
            m = group_metrics(pdf[pdf["d1_condition"] == lab], n_period)
            dh_rows.append({"scope": scope, "group": key, **m})
        for gname, gfn in GROUPS_INTER.items():
            m = group_metrics(pdf[gfn(pdf)], n_period)
            dh_rows.append({"scope": scope, "group": gname, **m})
    dh_df = pd.DataFrame(dh_rows)
    dh_df.to_csv(RESULTS_DIR / f"BOT-046_dev_holdout_{tf}.csv", index=False)
    print(f"Guardado: BOT-046_dev_holdout_{tf}.csv")

    # --- 7. Bootstrap (block bootstrap, block_len=round(sqrt(N))) -----------
    rng = np.random.default_rng(20260915)  # semilla fija, documentada, no ajustada por resultado
    bootstrap_rows = []
    for scope in ("completo", "sub1", "sub2", "sub3", "development", "holdout"):
        pdf = df[periods[scope]].sort_values("entry_bar")
        n = len(pdf)
        block_len = max(5, round(np.sqrt(n)))
        if scope == "completo":
            BLOCK_LEN_HEURISTIC = block_len
        deltas_dir, deltas_d1 = bootstrap_deltas(pdf, block_len, N_BOOTSTRAP, rng)
        for name, deltas in (("delta_direction_short_minus_long", deltas_dir),
                              ("delta_d1_aligned_minus_against", deltas_d1)):
            valid = deltas[~np.isnan(deltas)]
            point = (pdf.loc[pdf["direction"] == "SHORT", "pnl_r"].mean()
                     - pdf.loc[pdf["direction"] == "LONG", "pnl_r"].mean()) if "direction" in name else np.nan
            if "d1" in name:
                point = (pdf.loc[pdf["d1_condition"] == "aligned", "pnl_r"].mean()
                          - pdf.loc[pdf["d1_condition"] == "against", "pnl_r"].mean())
            bootstrap_rows.append({
                "scope": scope, "n_trades": n, "block_len": block_len, "n_resamples_validos": len(valid),
                "delta": name, "point_estimate": point,
                "boot_mean": float(np.mean(valid)) if len(valid) else np.nan,
                "ci_lo_2.5": float(np.percentile(valid, 2.5)) if len(valid) else np.nan,
                "ci_hi_97.5": float(np.percentile(valid, 97.5)) if len(valid) else np.nan,
                "excludes_zero": bool(len(valid) and (np.percentile(valid, 2.5) > 0 or np.percentile(valid, 97.5) < 0)),
            })
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(RESULTS_DIR / f"BOT-046_bootstrap_{tf}.csv", index=False)
    print(f"\nGuardado: BOT-046_bootstrap_{tf}.csv (block_len completo={BLOCK_LEN_HEURISTIC}, "
          f"{N_BOOTSTRAP} resamples)")
    print(bootstrap_df[["scope", "delta", "n_trades", "point_estimate", "ci_lo_2.5", "ci_hi_97.5", "excludes_zero"]]
          .round(4).to_string(index=False))

    # ------------------------------------------------------------------
    # 8. Graficos
    # ------------------------------------------------------------------
    plt.rcParams.update({"figure.dpi": 110, "font.size": 9})

    def savefig(name):
        plt.tight_layout()
        plt.savefig(CHARTS_DIR / name)
        plt.close()

    direction_df = pd.DataFrame(direction_rows)
    d1_df = pd.DataFrame(d1_rows)
    sextil_order = [f"T{k}" for k in range(1, 7)]

    # 1. expectancy LONG vs SHORT por T1..T6
    piv = direction_df[direction_df["period"].isin(sextil_order) & direction_df["group"].isin(["LONG", "SHORT"])]
    piv = piv.pivot(index="period", columns="group", values="expectancy_r").reindex(sextil_order)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(piv))
    ax.bar(x - 0.2, piv["LONG"], width=0.4, label="LONG", color="#DD8452")
    ax.bar(x + 0.2, piv["SHORT"], width=0.4, label="SHORT", color="#4C72B0")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(piv.index)
    ax.set_title("Expectancy (R) LONG vs SHORT por sextil")
    ax.legend()
    savefig("01_expectancy_long_short_sextiles.png")

    # 2. delta expectancy SHORT-LONG por periodo (sub1-3, T1-6, dev/holdout)
    order2 = ["sub1", "sub2", "sub3"] + sextil_order + ["development", "holdout"]
    delta_dir = (piv["SHORT"] - piv["LONG"]).reindex(sextil_order)
    full_delta = direction_df[direction_df["period"].isin(order2) & direction_df["group"].isin(["LONG", "SHORT"])]
    full_piv = full_delta.pivot(index="period", columns="group", values="expectancy_r").reindex(order2)
    delta_all = (full_piv["SHORT"] - full_piv["LONG"])
    fig, ax = plt.subplots(figsize=(10, 3.8))
    colors = np.where(delta_all >= 0, "#55A868", "#C44E52")
    ax.bar(range(len(delta_all)), delta_all.values, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(delta_all))); ax.set_xticklabels(delta_all.index, rotation=45, ha="right")
    ax.set_title("Delta expectancy SHORT - LONG por periodo")
    savefig("02_delta_direction_por_periodo.png")

    # 3. expectancy D1 aligned vs against por T1..T6
    piv_d1 = d1_df[d1_df["period"].isin(sextil_order) & d1_df["group"].isin(["D_aligned", "E_against"])]
    piv_d1 = piv_d1.pivot(index="period", columns="group", values="expectancy_r").reindex(sextil_order)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    x = np.arange(len(piv_d1))
    ax.bar(x - 0.2, piv_d1["D_aligned"], width=0.4, label="alineado", color="#55A868")
    ax.bar(x + 0.2, piv_d1["E_against"], width=0.4, label="contra", color="#C44E52")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(piv_d1.index)
    ax.set_title("Expectancy (R) D1 alineado vs contra por sextil")
    ax.legend()
    savefig("03_expectancy_d1_sextiles.png")

    # 4. delta expectancy aligned-against por periodo
    full_d1 = d1_df[d1_df["period"].isin(order2) & d1_df["group"].isin(["D_aligned", "E_against"])]
    full_piv_d1 = full_d1.pivot(index="period", columns="group", values="expectancy_r").reindex(order2)
    delta_d1_all = (full_piv_d1["D_aligned"] - full_piv_d1["E_against"])
    fig, ax = plt.subplots(figsize=(10, 3.8))
    colors = np.where(delta_d1_all >= 0, "#55A868", "#C44E52")
    ax.bar(range(len(delta_d1_all)), delta_d1_all.values, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(len(delta_d1_all))); ax.set_xticklabels(delta_d1_all.index, rotation=45, ha="right")
    ax.set_title("Delta expectancy D1 alineado - contra por periodo")
    savefig("04_delta_d1_por_periodo.png")

    # 5. matriz Direccion x D1 (completo)
    inter_full = pd.DataFrame(inter_rows)
    inter_full = inter_full[inter_full["period"] == "completo"].set_index("group")
    mat = np.array([
        [inter_full.loc["G1_LONG_alineado", "expectancy_r"], inter_full.loc["G2_LONG_contra", "expectancy_r"], inter_full.loc["G3_LONG_neutral", "expectancy_r"]],
        [inter_full.loc["G4_SHORT_alineado", "expectancy_r"], inter_full.loc["G5_SHORT_contra", "expectancy_r"], inter_full.loc["G6_SHORT_neutral", "expectancy_r"]],
    ])
    fig, ax = plt.subplots(figsize=(6, 3.5))
    im = ax.imshow(mat, cmap="RdYlGn", vmin=-0.25, vmax=0.25)
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["alineado", "contra", "neutral"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["LONG", "SHORT"])
    for i in range(2):
        for j in range(3):
            ax.text(j, i, f"{mat[i,j]:.3f}", ha="center", va="center")
    ax.set_title("Matriz Direccion x D1 -- expectancy (R), completo")
    fig.colorbar(im, ax=ax)
    savefig("05_matriz_direccion_d1.png")

    # 6. rolling expectancy LONG/SHORT
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(rolling_df["window_start"], rolling_df["expectancy_long"], marker="o", label="LONG", color="#DD8452")
    ax.plot(rolling_df["window_start"], rolling_df["expectancy_short"], marker="o", label="SHORT", color="#4C72B0")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Rolling expectancy (R) -- ventanas de 3 meses, avance mensual")
    ax.legend()
    plt.xticks(rotation=30, ha="right")
    savefig("06_rolling_long_short.png")

    # 7. rolling expectancy aligned/against
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(rolling_df["window_start"], rolling_df["expectancy_aligned"], marker="o", label="alineado", color="#55A868")
    ax.plot(rolling_df["window_start"], rolling_df["expectancy_against"], marker="o", label="contra", color="#C44E52")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Rolling expectancy (R) D1 -- ventanas de 3 meses, avance mensual")
    ax.legend()
    plt.xticks(rotation=30, ha="right")
    savefig("07_rolling_d1.png")

    # 8. Development vs Holdout
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    dev = dh_df[dh_df["scope"] == "development"].set_index("group")
    hold = dh_df[dh_df["scope"] == "holdout"].set_index("group")
    delta_dev_dir = dev.loc["SHORT", "expectancy_r"] - dev.loc["LONG", "expectancy_r"]
    delta_hold_dir = hold.loc["SHORT", "expectancy_r"] - hold.loc["LONG", "expectancy_r"]
    delta_dev_d1 = dev.loc["D_aligned", "expectancy_r"] - dev.loc["E_against", "expectancy_r"]
    delta_hold_d1 = hold.loc["D_aligned", "expectancy_r"] - hold.loc["E_against", "expectancy_r"]
    axes[0].bar(["development", "holdout"], [delta_dev_dir, delta_hold_dir], color=["#4C72B0", "#DD8452"])
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("Delta SHORT-LONG: dev vs holdout")
    axes[1].bar(["development", "holdout"], [delta_dev_d1, delta_hold_d1], color=["#55A868", "#C44E52"])
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("Delta D1 alineado-contra: dev vs holdout")
    savefig("08_development_vs_holdout.png")

    # 9. bootstrap CI
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, delta_name, title in [(axes[0], "delta_direction_short_minus_long", "Delta SHORT-LONG"),
                                   (axes[1], "delta_d1_aligned_minus_against", "Delta D1 alineado-contra")]:
        sub = bootstrap_df[bootstrap_df["delta"] == delta_name]
        y = np.arange(len(sub))
        ax.errorbar(sub["point_estimate"], y,
                    xerr=[sub["point_estimate"] - sub["ci_lo_2.5"], sub["ci_hi_97.5"] - sub["point_estimate"]],
                    fmt="o", capsize=3)
        ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_yticks(y); ax.set_yticklabels(sub["scope"])
        ax.set_title(f"{title} -- IC 95% (block bootstrap)")
    savefig("09_bootstrap_ci.png")

    print(f"\nGraficos guardados en {CHARTS_DIR}")


if __name__ == "__main__":
    main()
