"""BOT-045 -- analisis univariado, comparacion sub1/sub2/sub3, winners vs
losers, interacciones seleccionadas y graficos, a partir del dataset
enriquecido que genera 07_bot045_regime_dataset.py.

100% offline, solo lectura de los CSV/parquet ya generados -- no corre el
motor de la estrategia, no toca /strategy ni produccion.

Uso:
    python backtests/scripts/08_bot045_analysis.py [M5]
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
CHARTS_DIR = RESULTS_DIR / "BOT-045_charts"


def metrics_for(sub: pd.DataFrame, n_total: int) -> dict:
    n = len(sub)
    wins = int((sub["outcome"] == "win").sum())
    losses = int((sub["outcome"] == "loss").sum())
    wr = wins / (wins + losses) if (wins + losses) else float("nan")
    rs = sub["pnl_r"].dropna().to_numpy()
    gross_win = rs[rs > 0].sum() if len(rs) else 0.0
    gross_loss = -rs[rs < 0].sum() if len(rs) else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else float("nan")
    expectancy_r = rs.mean() if len(rs) else float("nan")
    net_r = rs.sum() if len(rs) else float("nan")
    net_usd = sub["pnl_usd"].dropna().sum() if n else float("nan")
    pct_sub = {}
    for sp in ("sub1", "sub2", "sub3"):
        pct_sub[f"pct_{sp}"] = (sub["sub_periodo"] == sp).mean() * 100.0 if n else float("nan")
    return {
        "n_trades": n, "pct_sample": (n / n_total * 100.0) if n_total else float("nan"),
        "win_rate": wr, "profit_factor": pf, "expectancy_r": expectancy_r,
        "avg_r": expectancy_r, "net_r": net_r, "net_usd": net_usd,
        **pct_sub,
    }


def add_rows(rows: list, df: pd.DataFrame, variable: str, bucket_col: pd.Series, n_total: int):
    for bucket in sorted(bucket_col.dropna().unique().tolist(), key=lambda x: str(x)):
        sub = df[bucket_col == bucket]
        m = metrics_for(sub, n_total)
        rows.append({"variable": variable, "bucket": str(bucket), **m})
    n_na = bucket_col.isna().sum()
    if n_na:
        sub = df[bucket_col.isna()]
        m = metrics_for(sub, n_total)
        rows.append({"variable": variable, "bucket": "sin_dato", **m})


def bucket_rsi(v):
    if pd.isna(v):
        return np.nan
    if v < 30:
        return "1) <30"
    if v < 40:
        return "2) 30-40"
    if v < 50:
        return "3) 40-50"
    if v < 60:
        return "4) 50-60"
    if v < 70:
        return "5) 60-70"
    return "6) >70"


def bucket_adx(v):
    if pd.isna(v):
        return np.nan
    if v < 20:
        return "1) <20 (debil/no-tendencial)"
    if v < 25:
        return "2) 20-25 (transicion)"
    if v < 40:
        return "3) 25-40 (tendencia)"
    return "4) >40 (tendencia fuerte)"


def bucket_htf_pos(v):
    if pd.isna(v):
        return np.nan
    if v < 0.33:
        return "1) cerca soporte (<0.33)"
    if v < 0.67:
        return "2) medio (0.33-0.67)"
    return "3) cerca resistencia (>0.67)"


def qcut_labeled(series: pd.Series, q: int, prefix: str, labels_ext: list[str]) -> pd.Series:
    try:
        cats = pd.qcut(series, q, duplicates="drop")
    except ValueError:
        return pd.Series([np.nan] * len(series), index=series.index)
    ordered = sorted(cats.cat.categories, key=lambda iv: iv.left)
    mapping = {}
    for i, iv in enumerate(ordered):
        lab = labels_ext[i] if i < len(labels_ext) else f"Q{i+1}"
        mapping[iv] = f"{i+1}) {lab} [{iv.left:.3f}-{iv.right:.3f}]"
    return cats.map(mapping)


def main():
    tf = sys.argv[1].upper() if len(sys.argv) > 1 else "M5"
    df = pd.read_csv(RESULTS_DIR / f"BOT-045_trades_enriched_{tf}.csv")
    n_total = len(df)
    print(f"Dataset: {n_total} operaciones")
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. UNIVARIADO
    # ------------------------------------------------------------------
    rows = []

    add_rows(rows, df, "rsi_entry", df["rsi_entry"].apply(bucket_rsi), n_total)
    add_rows(rows, df, "adx_entry", df["adx_entry"].apply(bucket_adx), n_total)
    add_rows(rows, df, "atr_pct_entry (volatilidad relativa, cuartiles del dataset)",
              qcut_labeled(df["atr_pct_entry"], 4, "atr", ["muy baja", "baja", "alta", "muy alta"]), n_total)
    add_rows(rows, df, "dist_ema_atr (distancia a EMA / ATR, cuartiles del dataset)",
              qcut_labeled(df["dist_ema_atr"], 4, "dist", ["muy cerca", "cerca", "lejos", "muy lejos"]), n_total)
    add_rows(rows, df, "htf_width_atr (ancho bloque HTF / ATR, cuartiles del dataset)",
              qcut_labeled(df["htf_width_atr"], 4, "width", ["angosto", "normal-", "normal+", "muy ancho"]), n_total)
    add_rows(rows, df, "htf_pos_in_block", df["htf_pos_in_block"].apply(bucket_htf_pos), n_total)
    add_rows(rows, df, "htf_age_bars (antiguedad dentro del bloque, cuartiles)",
              qcut_labeled(df["htf_age_bars"], 4, "age", ["temprano", "medio-temprano", "medio-tardio", "tardio"]), n_total)
    add_rows(rows, df, "session_utc", df["session_utc"], n_total)
    add_rows(rows, df, "hour_utc", df["hour_utc"].apply(lambda h: f"{int(h):02d}h"), n_total)
    add_rows(rows, df, "weekday", df["weekday"], n_total)
    add_rows(rows, df, "direction", df["direction"], n_total)
    add_rows(rows, df, "d1_trend", df["d1_trend"], n_total)
    add_rows(rows, df, "aligned_with_d1", df["aligned_with_d1"], n_total)
    add_rows(rows, df, "divergencia_score", df["divergencia_score"], n_total)
    add_rows(rows, df, "tendencia_score", df["tendencia_score"], n_total)
    add_rows(rows, df, "cvp_score", df["cvp_score"], n_total)
    add_rows(rows, df, "nodo_score", df["nodo_score"], n_total)
    add_rows(rows, df, "sub_periodo", df["sub_periodo"], n_total)

    univariate = pd.DataFrame(rows)
    univariate.to_csv(RESULTS_DIR / f"BOT-045_univariate_{tf}.csv", index=False)
    print(f"Univariado: {len(univariate)} filas -> BOT-045_univariate_{tf}.csv")

    # ------------------------------------------------------------------
    # 2. sub1 vs sub2 vs sub3 -- variables continuas (medias/medianas) y
    #    categoricas (proporciones)
    # ------------------------------------------------------------------
    cont_vars = ["rsi_entry", "adx_entry", "atr_pct_entry", "dist_ema_atr",
                 "htf_width_atr", "htf_pos_in_block", "htf_age_bars", "pnl_r"]
    cat_vars = ["direction", "session_utc", "weekday", "d1_trend", "aligned_with_d1",
                "divergencia_score", "tendencia_score", "nodo_score"]

    cont_rows = []
    for v in cont_vars:
        for sp in ("sub1", "sub2", "sub3"):
            s = df.loc[df["sub_periodo"] == sp, v].dropna()
            cont_rows.append({
                "variable": v, "sub_periodo": sp, "n": len(s),
                "mean": s.mean() if len(s) else np.nan, "median": s.median() if len(s) else np.nan,
                "std": s.std() if len(s) else np.nan, "p25": s.quantile(.25) if len(s) else np.nan,
                "p75": s.quantile(.75) if len(s) else np.nan,
            })
    pd.DataFrame(cont_rows).to_csv(RESULTS_DIR / f"BOT-045_subperiod_continuous_{tf}.csv", index=False)

    cat_rows = []
    for v in cat_vars:
        for sp in ("sub1", "sub2", "sub3"):
            s = df.loc[df["sub_periodo"] == sp, v]
            vc = s.value_counts(normalize=True, dropna=False) * 100.0
            for cat, pct in vc.items():
                cat_rows.append({"variable": v, "sub_periodo": sp, "categoria": str(cat), "pct": pct,
                                  "n": int((s == cat).sum()) if not pd.isna(cat) else int(s.isna().sum())})
    pd.DataFrame(cat_rows).to_csv(RESULTS_DIR / f"BOT-045_subperiod_categorical_{tf}.csv", index=False)
    print(f"Comparacion sub1/sub2/sub3 -> BOT-045_subperiod_continuous_{tf}.csv / _categorical_{tf}.csv")

    # ------------------------------------------------------------------
    # 3. winners vs losers -- global y dentro de cada sub-periodo
    # ------------------------------------------------------------------
    wl_cont_rows = []
    for scope_label, scope_df in [("global", df)] + [(sp, df[df["sub_periodo"] == sp]) for sp in ("sub1", "sub2", "sub3")]:
        for v in cont_vars:
            if v == "pnl_r":
                continue
            w = scope_df.loc[scope_df["outcome"] == "win", v].dropna()
            l = scope_df.loc[scope_df["outcome"] == "loss", v].dropna()
            wl_cont_rows.append({
                "scope": scope_label, "variable": v,
                "n_winners": len(w), "n_losers": len(l),
                "mean_winners": w.mean() if len(w) else np.nan, "mean_losers": l.mean() if len(l) else np.nan,
                "median_winners": w.median() if len(w) else np.nan, "median_losers": l.median() if len(l) else np.nan,
                "diff_mean": (w.mean() - l.mean()) if len(w) and len(l) else np.nan,
            })
    pd.DataFrame(wl_cont_rows).to_csv(RESULTS_DIR / f"BOT-045_winners_losers_continuous_{tf}.csv", index=False)

    wl_cat_rows = []
    for scope_label, scope_df in [("global", df)] + [(sp, df[df["sub_periodo"] == sp]) for sp in ("sub1", "sub2", "sub3")]:
        for v in cat_vars:
            w = scope_df.loc[scope_df["outcome"] == "win", v]
            l = scope_df.loc[scope_df["outcome"] == "loss", v]
            w_vc = w.value_counts(normalize=True, dropna=False) * 100.0
            l_vc = l.value_counts(normalize=True, dropna=False) * 100.0
            cats = set(w_vc.index) | set(l_vc.index)
            for cat in cats:
                wl_cat_rows.append({
                    "scope": scope_label, "variable": v, "categoria": str(cat),
                    "pct_winners": w_vc.get(cat, 0.0), "pct_losers": l_vc.get(cat, 0.0),
                    "n_winners": int((w == cat).sum()) if not (isinstance(cat, float) and pd.isna(cat)) else int(w.isna().sum()),
                    "n_losers": int((l == cat).sum()) if not (isinstance(cat, float) and pd.isna(cat)) else int(l.isna().sum()),
                })
    pd.DataFrame(wl_cat_rows).to_csv(RESULTS_DIR / f"BOT-045_winners_losers_categorical_{tf}.csv", index=False)
    print(f"Winners vs losers -> BOT-045_winners_losers_continuous_{tf}.csv / _categorical_{tf}.csv")

    # ------------------------------------------------------------------
    # 4. Interacciones seleccionadas (solo variables con alguna senal
    #    previa en el univariado: ADX, sesion, direccion, distancia EMA,
    #    tendencia/divergencia del scoring, alineacion con D1)
    # ------------------------------------------------------------------
    inter_rows = []

    def add_interaction(name: str, mask: pd.Series):
        sub = df[mask]
        m = metrics_for(sub, n_total)
        by_sub = {sp: round(float((sub["sub_periodo"] == sp).mean() * 100), 1) for sp in ("sub1", "sub2", "sub3")}
        inter_rows.append({"combinacion": name, **m, "dist_sub_pct": str(by_sub)})

    adx_high = df["adx_entry"] >= 25
    adx_low = df["adx_entry"] < 20
    d1_aligned = df["aligned_with_d1"] == True  # noqa: E712
    d1_against = df["aligned_with_d1"] == False  # noqa: E712
    short_mask = df["direction"] == "SHORT"
    long_mask = df["direction"] == "LONG"
    ny_lon_overlap = df["session_utc"] == "Londres/NY (overlap)"
    asia = df["session_utc"] == "Asia"
    dist_far = df["dist_ema_atr"] >= df["dist_ema_atr"].quantile(.75)
    dist_near = df["dist_ema_atr"] <= df["dist_ema_atr"].quantile(.25)
    tend_against = df["tendencia_score"] == -1
    div_favor = df["divergencia_score"] == 1

    add_interaction("ADX alto (>=25) + alineado con D1", adx_high & d1_aligned)
    add_interaction("ADX alto (>=25) + en contra de D1", adx_high & d1_against)
    add_interaction("ADX bajo (<20) + Londres/NY overlap", adx_low & ny_lon_overlap)
    add_interaction("SHORT + tendencia en contra (scoring)", short_mask & tend_against)
    add_interaction("LONG + tendencia en contra (scoring)", long_mask & tend_against)
    add_interaction("Distancia a EMA lejos (Q4) + ADX alto", dist_far & adx_high)
    add_interaction("Distancia a EMA cerca (Q1) + ADX alto", dist_near & adx_high)
    add_interaction("Divergencia a favor + ADX alto", div_favor & adx_high)
    add_interaction("Asia + ADX bajo (<20)", asia & adx_low)
    add_interaction("Londres/NY overlap + ADX alto (>=25)", ny_lon_overlap & adx_high)

    interactions = pd.DataFrame(inter_rows)
    interactions.to_csv(RESULTS_DIR / f"BOT-045_interactions_{tf}.csv", index=False)
    print(f"Interacciones -> BOT-045_interactions_{tf}.csv")

    # ------------------------------------------------------------------
    # 5. Graficos
    # ------------------------------------------------------------------
    plt.rcParams.update({"figure.dpi": 110, "font.size": 9})

    def savefig(name):
        plt.tight_layout()
        plt.savefig(CHARTS_DIR / name)
        plt.close()

    # expectancy y PF por sub-periodo
    baseline = pd.read_csv(RESULTS_DIR / f"BOT-045_baseline_{tf}.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    order = ["completo", "sub1", "sub2", "sub3"]
    b2 = baseline.set_index("periodo").loc[order]
    axes[0].bar(order, b2["expectancy_r"], color=["#888"] + ["#4C72B0"] * 3)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("Expectancy (R) por periodo")
    axes[1].bar(order, b2["profit_factor"].clip(upper=2), color=["#888"] + ["#55A868"] * 3)
    axes[1].axhline(1, color="black", linewidth=0.8, linestyle="--")
    axes[1].set_title("Profit Factor por periodo (clip 2.0)")
    savefig("01_expectancy_pf_por_periodo.png")

    # RSI winners vs losers
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(df.loc[df["outcome"] == "win", "rsi_entry"].dropna(), bins=30, alpha=0.55, label="winners", color="#55A868")
    ax.hist(df.loc[df["outcome"] == "loss", "rsi_entry"].dropna(), bins=30, alpha=0.55, label="losers", color="#C44E52")
    ax.set_title("RSI en la entrada -- winners vs losers")
    ax.legend()
    savefig("02_rsi_winners_vs_losers.png")

    # ADX distribution winners vs losers
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(df.loc[df["outcome"] == "win", "adx_entry"].dropna(), bins=30, alpha=0.55, label="winners", color="#55A868")
    ax.hist(df.loc[df["outcome"] == "loss", "adx_entry"].dropna(), bins=30, alpha=0.55, label="losers", color="#C44E52")
    ax.set_title("ADX en la entrada -- winners vs losers")
    ax.legend()
    savefig("03_adx_winners_vs_losers.png")

    # ATR% distribution
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(df.loc[df["outcome"] == "win", "atr_pct_entry"].dropna(), bins=30, alpha=0.55, label="winners", color="#55A868")
    ax.hist(df.loc[df["outcome"] == "loss", "atr_pct_entry"].dropna(), bins=30, alpha=0.55, label="losers", color="#C44E52")
    ax.set_title("ATR% (volatilidad relativa) -- winners vs losers")
    ax.legend()
    savefig("04_atr_pct_winners_vs_losers.png")

    # rendimiento por sesion
    sess = univariate[univariate["variable"] == "session_utc"].sort_values("expectancy_r")
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.barh(sess["bucket"], sess["expectancy_r"], color=np.where(sess["expectancy_r"] >= 0, "#55A868", "#C44E52"))
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Expectancy (R) por sesion UTC")
    savefig("05_expectancy_por_sesion.png")

    # rendimiento por hora
    hourly = univariate[univariate["variable"] == "hour_utc"].copy()
    hourly["h"] = hourly["bucket"].str.replace("h", "").astype(int)
    hourly = hourly.sort_values("h")
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar(hourly["h"], hourly["expectancy_r"], color=np.where(hourly["expectancy_r"] >= 0, "#55A868", "#C44E52"))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(0, 24, 2))
    ax.set_title("Expectancy (R) por hora UTC de entrada")
    savefig("06_expectancy_por_hora.png")

    # LONG vs SHORT
    dirv = univariate[univariate["variable"] == "direction"]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5))
    axes[0].bar(dirv["bucket"], dirv["win_rate"] * 100, color=["#4C72B0", "#DD8452"])
    axes[0].set_title("Win rate %% por direccion")
    axes[1].bar(dirv["bucket"], dirv["expectancy_r"], color=["#4C72B0", "#DD8452"])
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("Expectancy (R) por direccion")
    savefig("07_long_vs_short.png")

    # distancia a EMA / ATR
    dist_v = univariate[univariate["variable"].str.startswith("dist_ema_atr")]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(dist_v["bucket"], dist_v["expectancy_r"], color=np.where(dist_v["expectancy_r"] >= 0, "#55A868", "#C44E52"))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Expectancy (R) por distancia EMA/ATR (cuartiles)")
    plt.xticks(rotation=20, ha="right")
    savefig("08_distancia_ema_atr.png")

    # sub1/sub2/sub3 comparacion ADX y ATR%
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for sp, color in zip(("sub1", "sub2", "sub3"), ("#4C72B0", "#55A868", "#C44E52")):
        axes[0].hist(df.loc[df["sub_periodo"] == sp, "adx_entry"].dropna(), bins=25, alpha=0.5, label=sp, color=color)
        axes[1].hist(df.loc[df["sub_periodo"] == sp, "atr_pct_entry"].dropna(), bins=25, alpha=0.5, label=sp, color=color)
    axes[0].set_title("ADX por sub-periodo")
    axes[1].set_title("ATR%% por sub-periodo")
    axes[0].legend()
    axes[1].legend()
    savefig("09_sub_periodos_adx_atr.png")

    # heatmap ADX bucket x sesion (interaccion justificada: ambas mostraron variacion univariada)
    pivot = df.copy()
    pivot["adx_b"] = pivot["adx_entry"].apply(bucket_adx)
    heat = pivot.groupby(["adx_b", "session_utc"])["pnl_r"].mean().unstack()
    heat = heat.reindex(sorted(heat.index.dropna()))
    fig, ax = plt.subplots(figsize=(8, 4))
    im = ax.imshow(heat.to_numpy(), cmap="RdYlGn", vmin=-0.3, vmax=0.3, aspect="auto")
    ax.set_xticks(range(len(heat.columns)))
    ax.set_xticklabels(heat.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(heat.index)))
    ax.set_yticklabels(heat.index)
    ax.set_title("Expectancy media (R) -- ADX bucket x sesion")
    fig.colorbar(im, ax=ax, label="R promedio")
    savefig("10_heatmap_adx_sesion.png")

    print(f"\nGraficos guardados en {CHARTS_DIR}")


if __name__ == "__main__":
    main()
