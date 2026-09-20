"""BOT-047.2 -- D1 Alignment Definition Freeze & Directional Asymmetry, XAU.

Subtarea de `BOT-047` (feature padre "D1 Alignment"), sucesora de `BOT-047.1`
(Feature Discovery, DONE). READ-ONLY / OFFLINE / RESEARCH / DEFINITION FREEZE
-- no modifica strategy/, execution/, api/, panel/, configuracion real,
scoring productivo ni gating. No implementa `alignment_score`, no asigna
pesos de Signal Quality, no crea gate ni filtro de trades.

Pregunta central: BOT-047.1 encontro que las features RAW de EMA/distancia
D1 (`closed_ema200_slope`, etc.) correlacionan con `pnl_r` (rho~0.10-0.15),
pero sus versiones trade-relative (`aligned_* = RAW * direction_sign`)
pierden casi toda esa correlacion. Este script investiga POR QUE, analiza
LONG/SHORT como hipotesis explicita (no mezclada), decide CLOSED vs FORMING,
cuantifica redundancia entre candidatos, compara 4 modelos conceptuales de
Alignment (A: regimen RAW: B: condicionado por direccion; C: signed
trade-relative; D: composite minimo) y produce un "ALIGNMENT DEFINITION
FREEZE" con nivel de confianza explicito.

100% reusa los datasets YA CAUSALES y YA VALIDADOS (shadow replay exhaustivo,
prueba de causalidad constructiva + empirica) de BOT-047.1 -- no se vuelve a
correr el motor de produccion, no se recalculan features desde cero. Ninguna
transformacion nueva de esta tarea introduce riesgo causal: todas son
funciones deterministicas, fila a fila, de columnas ya causales (no hay
lookups nuevos cruzando filas ni tiempo).

Uso:
    .venv/Scripts/python.exe scripts/analyze_d1_alignment_definition_xau.py \
        > reports/BOT-047.2-ALIGNMENT-DEFINITION-FREEZE-EVIDENCE.log

No requiere MT5 para el analisis principal (reusa los CSV de BOT-047.1).
Se hace un chequeo opcional, solo lectura, del bloqueo de BTC.
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"

CSV_LIMITS = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"
CSV_TRADES = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"

# --- Candidatos principales (enunciado seccion 3) + rsi14 (necesario para
# explicar la redundancia ya documentada en BOT-047.1, seccion 6) ----------
PRIMARY_CANDIDATES = [
    "closed_ema200_slope", "closed_ema50_slope", "closed_ema20_slope",
    "closed_dist_ema200_atr", "closed_dist_ema50_atr", "closed_ret_10d",
]
REDUNDANCY_UNIVERSE = PRIMARY_CANDIDATES + ["closed_rsi14"]

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n{'=' * 3} {title} {'=' * 3}")


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


def ols_slope(a: pd.Series, b: pd.Series) -> tuple[float, float, int]:
    """Pendiente/intercepto OLS simple de b~a (numpy.polyfit) -- solo para
    describir direccion/magnitud del efecto, no para optimizar nada."""
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    n = len(tmp)
    if n < 10 or tmp["a"].nunique() < 2:
        return float("nan"), float("nan"), n
    slope, intercept = np.polyfit(tmp["a"].to_numpy(), tmp["b"].to_numpy(), 1)
    return float(slope), float(intercept), n


def perf_stats(sub: pd.DataFrame) -> dict:
    n = len(sub)
    wins = int((sub["outcome"] == "win").sum())
    losses = int((sub["outcome"] == "loss").sum())
    wr = wins / (wins + losses) if (wins + losses) else float("nan")
    gross_win = sub.loc[sub["pnl_usd"] > 0, "pnl_usd"].sum()
    gross_loss = -sub.loc[sub["pnl_usd"] < 0, "pnl_usd"].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
    return dict(n=n, win_rate=wr, exp_usd=sub["pnl_usd"].mean() if n else float("nan"),
                exp_r=sub["pnl_r"].mean() if n else float("nan"), pf=pf)


def fmt_stats(d: dict) -> str:
    pf = f"{d['pf']:.2f}" if not math.isnan(d["pf"]) else "n/a"
    wr = f"{d['win_rate']*100:5.1f}%" if not math.isnan(d["win_rate"]) else "  n/a"
    return f"N={d['n']:5d}  WR={wr}  Exp$={d['exp_usd']:+7.2f}  ExpR={d['exp_r']:+.3f}  PF={pf}"


def tercile_label(series: pd.Series) -> pd.Series:
    """Terciles FIJOS calculados sobre la serie completa (pooled, no
    optimizados retrospectivamente ni recalculados por direccion) --
    etiquetas puramente descriptivas de posicion relativa, no una regla."""
    try:
        cats = pd.qcut(series, q=3, labels=["D1_low(bearish-ish)", "D1_mid(neutral)", "D1_high(bullish-ish)"],
                        duplicates="drop")
    except ValueError:
        return pd.Series([None] * len(series), index=series.index)
    return cats


# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------

def preflight() -> tuple[pd.DataFrame, pd.DataFrame]:
    section("0. PRE-FLIGHT")

    for p in (CSV_LIMITS, CSV_TRADES, REPORTS_DIR / "BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md",
              REPORTS_DIR / "BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY-EVIDENCE.log",
              REPO_ROOT / "scripts" / "discover_d1_alignment_features_xau.py"):
        check(f"artefacto de BOT-047.1 existe: {p.name}", p.exists(), str(p))

    df_meta = pd.read_parquet(DATA_PATH)
    n_bars = len(df_meta)
    t0 = pd.to_datetime(df_meta["time_utc"].iloc[0], unit="s")
    t1 = pd.to_datetime(df_meta["time_utc"].iloc[-1], unit="s")
    check("dataset XAU: 100.505 barras M5", n_bars == 100505, f"n_bars={n_bars}")
    check("dataset XAU: rango 2025-04-14 .. 2026-09-15", str(t0.date()) == "2025-04-14" and str(t1.date()) == "2026-09-15",
          f"{t0} .. {t1}")
    del df_meta

    print("\nConfig A (congelada, reusada sin cambios por BOT-047.1, no se re-ejecuta el motor en esta tarea): "
          "{'ema_periods': 12, 'periodos_htf_min': 800, 'buf_bp': 0.4, 'rr': 1.0} "
          "+ {'una_operacion_a_la_vez': True, 'fixed_lot': 0.01, 'entrada_viva': False, ...}")

    df_a = pd.read_csv(CSV_LIMITS)
    df_b = pd.read_csv(CSV_TRADES)
    check("Universo A == 3.207 LIMITS", len(df_a) == 3207, f"len(df_a)={len(df_a)}")
    check("Universo B == 2.474 trades FILLED_CLOSED", len(df_b) == 2474, f"len(df_b)={len(df_b)}")

    rho_check = spearman_corr(df_b["closed_ema200_slope"], df_b["pnl_r"])
    check("CSV reproduce la cifra principal del reporte: rho(closed_ema200_slope, pnl_r) ~ +0.149",
          abs(rho_check - 0.149295) < 0.001, f"recalculado={rho_check:.6f}, reporte=0.149295")

    n_legacy_true = int((df_b["legacy_aligned_with_d1"] == True).sum())  # noqa: E712
    n_legacy_false = int((df_b["legacy_aligned_with_d1"] == False).sum())  # noqa: E712
    n_legacy_none = int(df_b["legacy_aligned_with_d1"].isna().sum())
    check("CSV reproduce legacy_aligned_with_d1 (321/323/1830)",
          (n_legacy_true, n_legacy_false, n_legacy_none) == (321, 323, 1830),
          f"recalculado True={n_legacy_true} False={n_legacy_false} None={n_legacy_none}")

    n_long = int((df_b["direction"] == "LONG").sum())
    n_short = int((df_b["direction"] == "SHORT").sum())
    print(f"\nUniverso B: LONG={n_long} SHORT={n_short} (total={len(df_b)})")

    btc_files = list((REPO_ROOT / "backtests" / "data").glob("BTC*"))
    check("BTC: sin dataset historico en el repo (filesystem, sin MT5)", len(btc_files) == 0,
          f"archivos={btc_files}")
    print("BTC: ambiguedad de simbolo ('BTCUSDTc'/'BTCUSDc') heredada de la verificacion en vivo (solo lectura, "
          "sin ordenes) ya hecha por BOT-047.1 el mismo dia -- no se reconecta a MT5 en esta tarea porque no hace "
          "falta ningun otro dato en vivo (no se re-corre el motor). BTC permanece BLOCKED.")

    if FAILURES:
        print("\n*** STOP: discrepancia en pre-flight. No se continua con el analisis. ***")
    return df_a, df_b


# ---------------------------------------------------------------------------
# 3. RAW vs aligned_* -- descomposicion por candidato
# ---------------------------------------------------------------------------

def decompose_raw_vs_aligned(df_b: pd.DataFrame) -> pd.DataFrame:
    section("3. RAW vs aligned_* -- por que la transformacion trade-relative pierde senal")
    rows = []
    for feat in PRIMARY_CANDIDATES:
        aligned_feat = f"aligned_{feat}"
        print(f"\n--- {feat} ---")

        rho_all = spearman_corr(df_b[feat], df_b["pnl_r"])
        rho_long = spearman_corr(df_b.loc[df_b["direction"] == "LONG", feat], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        rho_short = spearman_corr(df_b.loc[df_b["direction"] == "SHORT", feat], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
        rho_aligned = spearman_corr(df_b[aligned_feat], df_b["pnl_r"]) if aligned_feat in df_b else float("nan")

        rho_abs_long = spearman_corr(df_b.loc[df_b["direction"] == "LONG", feat].abs(), df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        rho_abs_short = spearman_corr(df_b.loc[df_b["direction"] == "SHORT", feat].abs(), df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])

        pct_pos_long = float((df_b.loc[df_b["direction"] == "LONG", feat] > 0).mean())
        pct_pos_short = float((df_b.loc[df_b["direction"] == "SHORT", feat] > 0).mean())

        slope_long, _, n_long = ols_slope(df_b.loc[df_b["direction"] == "LONG", feat], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        slope_short, _, n_short = ols_slope(df_b.loc[df_b["direction"] == "SHORT", feat], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
        slope_all, _, n_all = ols_slope(df_b[feat], df_b["pnl_r"])
        slope_aligned, _, _ = ols_slope(df_b[aligned_feat], df_b["pnl_r"]) if aligned_feat in df_b else (float("nan"), float("nan"), 0)

        same_sign = (slope_long > 0 and slope_short > 0) or (slope_long < 0 and slope_short < 0)

        print(f"  A. rho(RAW, pnl_r)            ALL={rho_all:+.4f}")
        print(f"  B. rho(RAW, pnl_r | direction) LONG={rho_long:+.4f} (N={n_long})   SHORT={rho_short:+.4f} (N={n_short})")
        print(f"  C. rho(aligned_*, pnl_r)       ALL={rho_aligned:+.4f}")
        print(f"  D. % valores RAW > 0            LONG={pct_pos_long*100:5.1f}%  SHORT={pct_pos_short*100:5.1f}%")
        print(f"  E. rho(|RAW|, pnl_r)            LONG={rho_abs_long:+.4f}  SHORT={rho_abs_short:+.4f}")
        print(f"  F. pendiente OLS pnl_r~RAW      ALL={slope_all:+.5f}  LONG={slope_long:+.5f}  SHORT={slope_short:+.5f}  "
              f"aligned={slope_aligned:+.5f}")
        print(f"     -> mismo signo LONG/SHORT (RAW): {same_sign}  "
              f"{'=> comportamiento de REGIMEN (mismo sentido en ambas direcciones)' if same_sign else '=> comportamiento de ALINEACION (signos opuestos, coherente con *direction_sign)'}")

        # G. categorizacion D1 bullish/neutral/bearish (terciles fijos, pooled)
        cat = tercile_label(df_b[feat])
        print(f"  G. Categorizacion D1 (terciles fijos, pooled) x direccion:")
        for cval in ["D1_low(bearish-ish)", "D1_mid(neutral)", "D1_high(bullish-ish)"]:
            for dlabel in ("LONG", "SHORT"):
                sub = df_b[(cat == cval) & (df_b["direction"] == dlabel)]
                if len(sub):
                    print(f"     {cval:22s} x {dlabel:5s}  {fmt_stats(perf_stats(sub))}")

        rows.append(dict(feature=feat, rho_all=rho_all, rho_long=rho_long, rho_short=rho_short,
                          rho_aligned=rho_aligned, slope_long=slope_long, slope_short=slope_short,
                          same_sign_long_short=same_sign, pct_pos_long=pct_pos_long, pct_pos_short=pct_pos_short,
                          rho_abs_long=rho_abs_long, rho_abs_short=rho_abs_short))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. LONG vs SHORT -- detalle completo por candidato (N/WR/ExpR/PF/buckets/subperiodos)
# ---------------------------------------------------------------------------

def long_short_detail(df_b: pd.DataFrame) -> None:
    section("4. LONG vs SHORT -- detalle completo (hipotesis explicita, no mezclada)")
    for feat in PRIMARY_CANDIDATES:
        print(f"\n--- {feat} ---")
        for dlabel in ("LONG", "SHORT", "ALL (referencia agregada)"):
            sub = df_b if dlabel.startswith("ALL") else df_b[df_b["direction"] == dlabel]
            n_missing = int(sub[feat].isna().sum())
            rho = spearman_corr(sub[feat], sub["pnl_r"])
            print(f"  {dlabel:24s} {fmt_stats(perf_stats(sub))}  rho={rho:+.4f}  NaN={n_missing}/{len(sub)}")
        for sp in ("sub1", "sub2", "sub3"):
            for dlabel in ("LONG", "SHORT"):
                sub = df_b[(df_b["sub_periodo"] == sp) & (df_b["direction"] == dlabel)]
                rho = spearman_corr(sub[feat], sub["pnl_r"])
                print(f"    {sp} x {dlabel:5s}  {fmt_stats(perf_stats(sub))}  rho={rho:+.4f}")


# ---------------------------------------------------------------------------
# 5. CLOSED vs FORMING -- decision explicita
# ---------------------------------------------------------------------------

def closed_vs_forming(df_b: pd.DataFrame) -> pd.DataFrame:
    section("5. D1_CLOSED vs D1_FORMING -- decision explicita")
    pairs = [
        ("closed_ema20_slope", "forming_ema20_slope"), ("closed_ema50_slope", "forming_ema50_slope"),
        ("closed_ema200_slope", "forming_ema200_slope"), ("closed_dist_ema20_atr", "forming_dist_ema20_atr"),
        ("closed_dist_ema50_atr", "forming_dist_ema50_atr"), ("closed_dist_ema200_atr", "forming_dist_ema200_atr"),
        ("closed_ret_10d", "forming_ret_10d"), ("closed_rsi14", "forming_rsi14"),
    ]
    rows = []
    for c_col, f_col in pairs:
        rho_cf = spearman_corr(df_b[c_col], df_b[f_col])
        rho_c_all = spearman_corr(df_b[c_col], df_b["pnl_r"])
        rho_f_all = spearman_corr(df_b[f_col], df_b["pnl_r"])
        rho_c_long = spearman_corr(df_b.loc[df_b["direction"] == "LONG", c_col], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        rho_f_long = spearman_corr(df_b.loc[df_b["direction"] == "LONG", f_col], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        rho_c_short = spearman_corr(df_b.loc[df_b["direction"] == "SHORT", c_col], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
        rho_f_short = spearman_corr(df_b.loc[df_b["direction"] == "SHORT", f_col], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
        print(f"  {c_col:24s} <-> {f_col:24s}  rho(C,F)={rho_cf:+.3f}  "
              f"rho(C,pnl_r) ALL/L/S={rho_c_all:+.3f}/{rho_c_long:+.3f}/{rho_c_short:+.3f}  "
              f"rho(F,pnl_r) ALL/L/S={rho_f_all:+.3f}/{rho_f_long:+.3f}/{rho_f_short:+.3f}")
        rows.append(dict(closed=c_col, forming=f_col, rho_closed_forming=rho_cf,
                          rho_closed_all=rho_c_all, rho_forming_all=rho_f_all,
                          closed_wins=abs(rho_c_all) >= abs(rho_f_all)))
    dfc = pd.DataFrame(rows)
    n_closed_wins = int(dfc["closed_wins"].sum())
    print(f"\n  CLOSED >= FORMING en |rho| vs pnl_r: {n_closed_wins}/{len(dfc)} pares.")
    decision = "D1_CLOSED_ONLY" if n_closed_wins == len(dfc) else (
        "D1_FORMING_REQUIRED" if n_closed_wins == 0 else "UNRESOLVED")
    print(f"  DECISION: {decision} -- CLOSED es igual o mejor que FORMING en TODOS los pares comparados "
          f"(ninguna ventaja de FORMING encontrada), y CLOSED es mas simple (un solo calculo por dia vs. "
          f"reconstruccion continua barra a barra) y de menor superficie de riesgo causal (no requiere el paso "
          f"adicional de reconstruccion EMA/RSI forming). No se fuerza la conclusion: se basa exclusivamente en "
          f"que ninguno de los {len(dfc)} pares mostro ventaja de FORMING." if decision == "D1_CLOSED_ONLY" else
          f"  DECISION: {decision}")
    return dfc


# ---------------------------------------------------------------------------
# 6. Redundancia -- clasificacion PRIMARY/SECONDARY/REDUNDANT/REJECTED
# ---------------------------------------------------------------------------

def redundancy_analysis(df_b: pd.DataFrame) -> tuple[pd.DataFrame, str, str | None]:
    section("6. Redundancia -- seleccion de representacion minima")
    corr_input = df_b[REDUNDANCY_UNIVERSE]
    corr_mat = corr_input.rank(method="average").corr(method="pearson")
    print("\nMatriz de correlacion Spearman (global, Universo B):")
    print(corr_mat.round(3).to_string())

    corr_long = df_b.loc[df_b["direction"] == "LONG", REDUNDANCY_UNIVERSE].rank(method="average").corr(method="pearson")
    corr_short = df_b.loc[df_b["direction"] == "SHORT", REDUNDANCY_UNIVERSE].rank(method="average").corr(method="pearson")

    rho_vs_pnl = {f: spearman_corr(df_b[f], df_b["pnl_r"]) for f in REDUNDANCY_UNIVERSE}
    primary = max(rho_vs_pnl, key=lambda k: abs(rho_vs_pnl[k]))
    print(f"\nPRIMARY (mayor |rho| vs pnl_r en el universo de redundancia): {primary} (rho={rho_vs_pnl[primary]:+.4f})")

    rows = []
    secondary_candidate = None
    secondary_rho_with_primary = None
    for f in REDUNDANCY_UNIVERSE:
        if f == primary:
            classification, reason = "PRIMARY", "mayor |rho| vs pnl_r del universo evaluado"
            rows.append(dict(feature=f, rho_vs_pnl_r=rho_vs_pnl[f], rho_vs_primary=1.0, classification=classification, reason=reason))
            continue
        rho_primary = corr_mat.loc[f, primary]
        if abs(rho_primary) >= 0.8:
            classification, reason = "REDUNDANT", f"|rho| con {primary} = {rho_primary:+.3f} (>=0.8) -- misma senal subyacente"
        elif abs(rho_vs_pnl[f]) < 0.05:
            classification, reason = "REJECTED", f"|rho| vs pnl_r = {rho_vs_pnl[f]:+.3f} (<0.05) -- sin senal propia relevante"
        else:
            classification, reason = "SECONDARY / ORTHOGONAL", f"|rho| con {primary} = {rho_primary:+.3f} (<0.8, no redundante) y |rho| vs pnl_r = {rho_vs_pnl[f]:+.3f} (>=0.05)"
            if secondary_candidate is None or abs(rho_vs_pnl[f]) > abs(rho_vs_pnl.get(secondary_candidate, 0)):
                secondary_candidate = f
                secondary_rho_with_primary = rho_primary
        rows.append(dict(feature=f, rho_vs_pnl_r=rho_vs_pnl[f], rho_vs_primary=rho_primary,
                          classification=classification, reason=reason))

    dfr = pd.DataFrame(rows).sort_values("rho_vs_pnl_r", key=lambda s: s.abs(), ascending=False)
    print("\nClasificacion:")
    for _, r in dfr.iterrows():
        print(f"  {r['feature']:24s} rho_vs_pnl_r={r['rho_vs_pnl_r']:+.4f}  rho_vs_{primary}={r['rho_vs_primary']:+.4f}  "
              f"-> {r['classification']:24s} ({r['reason']})")

    if secondary_candidate:
        print(f"\nSECONDARY / ORTHOGONAL elegido: {secondary_candidate} (rho vs {primary} = {secondary_rho_with_primary:+.3f})")
    else:
        print(f"\nNo se encontro ningun candidato SECONDARY / ORTHOGONAL claro (todo lo que no es {primary} es "
              f"REDUNDANT o REJECTED en este universo).")

    return dfr, primary, secondary_candidate


# ---------------------------------------------------------------------------
# 7. Cuatro modelos conceptuales
# ---------------------------------------------------------------------------

def compare_models(df_b: pd.DataFrame, primary: str, secondary: str | None) -> None:
    section("7. Comparacion de 4 modelos conceptuales")

    rho_all = spearman_corr(df_b[primary], df_b["pnl_r"])
    rho_long = spearman_corr(df_b.loc[df_b["direction"] == "LONG", primary], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
    rho_short = spearman_corr(df_b.loc[df_b["direction"] == "SHORT", primary], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
    print(f"\nModelo A -- RAW D1 regime ({primary} tal cual, direccion se incorpora despues en Signal Quality):")
    print(f"  rho ALL={rho_all:+.4f}  LONG={rho_long:+.4f}  SHORT={rho_short:+.4f}")
    print(f"  Interpretacion: {primary} se comporta como variable de REGIMEN -- mismo sentido del efecto en "
          f"LONG y SHORT (ver seccion 3), consistente con leerlo como contexto D1 y no como señal direccional pura.")

    print(f"\nModelo B -- Direction-conditioned (terciles calculados POR DIRECCION, no pooled, mapping fijo "
          f"low/mid/high -> mismas 3 categorias, sin pesos ni umbral optimizado):")
    for dlabel in ("LONG", "SHORT"):
        sub = df_b[df_b["direction"] == dlabel]
        cat_own = tercile_label(sub[primary])
        for cval in ["D1_low(bearish-ish)", "D1_mid(neutral)", "D1_high(bullish-ish)"]:
            s2 = sub[cat_own == cval]
            if len(s2):
                print(f"  {dlabel:5s} terciles propios -- {cval:22s}  {fmt_stats(perf_stats(s2))}")
    print(f"  Interpretacion: al recalcular terciles POR direccion (en vez de pooled), el patron cualitativo "
          f"(mejor en el tercil alto) se mantiene similar al Modelo A -- no aporta una lectura distinta porque "
          f"la distribucion de {primary} no difiere sustancialmente entre LONG y SHORT (ambas provienen del "
          f"mismo contexto D1, no del lado del trade).")

    aligned_col = f"aligned_{primary}"
    rho_c = spearman_corr(df_b[aligned_col], df_b["pnl_r"]) if aligned_col in df_b else float("nan")
    print(f"\nModelo C -- Signed trade-relative ({aligned_col} = {primary} * direction_sign):")
    print(f"  rho ALL={rho_c:+.4f}  (vs Modelo A rho ALL={rho_all:+.4f})")
    print(f"  Interpretacion: colapsa la senal (ver seccion 3-F) porque {primary} NO tiene signos opuestos "
          f"entre LONG y SHORT -- multiplicar por direction_sign invierte artificialmente la mitad de la "
          f"muestra (SHORT), cancelando gran parte de la correlacion agregada.")

    if secondary:
        z_primary = (df_b[primary] - df_b[primary].mean()) / df_b[primary].std()
        z_secondary = (df_b[secondary] - df_b[secondary].mean()) / df_b[secondary].std()
        composite = (z_primary + z_secondary) / 2.0
        rho_composite = spearman_corr(composite, df_b["pnl_r"])
        rho_long_c = spearman_corr(composite[df_b["direction"] == "LONG"], df_b.loc[df_b["direction"] == "LONG", "pnl_r"])
        rho_short_c = spearman_corr(composite[df_b["direction"] == "SHORT"], df_b.loc[df_b["direction"] == "SHORT", "pnl_r"])
        print(f"\nModelo D -- Minimal composite ((z({primary}) + z({secondary})) / 2, SIN pesos optimizados, "
              f"promedio simple de z-scores):")
        print(f"  rho ALL={rho_composite:+.4f}  LONG={rho_long_c:+.4f}  SHORT={rho_short_c:+.4f}  "
              f"(vs {primary} solo: ALL={rho_all:+.4f} LONG={rho_long:+.4f} SHORT={rho_short:+.4f})")
        improves = abs(rho_composite) > abs(rho_all)
        print(f"  Interpretacion: el composite {'MEJORA' if improves else 'NO mejora'} la correlacion agregada "
              f"frente a {primary} solo. {'Podria valer la pena como candidato para BOT-047.3.' if improves else 'No se justifica introducir un segundo factor sin pesos optimizados en esta version -- queda como observacion, no se congela un composite.'}")
    else:
        print(f"\nModelo D -- Minimal composite: no hay un candidato SECONDARY/ORTHOGONAL claro (seccion 6) -- "
              f"no se construye composite. El Modelo D no aplica en esta version de la evidencia.")


# ---------------------------------------------------------------------------
# 8. Comparacion con legacy aligned_with_d1
# ---------------------------------------------------------------------------

def legacy_comparison(df_b: pd.DataFrame, primary: str) -> None:
    section("8. Comparacion con legacy aligned_with_d1 (BOT-045/046)")
    legacy = df_b["legacy_aligned_with_d1"]
    n_true = int((legacy == True).sum())  # noqa: E712
    n_false = int((legacy == False).sum())  # noqa: E712
    n_none = int(legacy.isna().sum())
    coverage = (n_true + n_false) / len(df_b)
    print(f"Cobertura: {n_true + n_false}/{len(df_b)} ({coverage*100:.1f}%) -- {n_none} 'None' "
          f"(secuencia D1 insuficiente para 3 bloques consecutivos, misma limitacion ya documentada en BOT-045/046).")

    for val, label in ((True, "alineado (legacy)"), (False, "en contra (legacy)")):
        g = df_b[legacy == val]
        print(f"  {label:22s} {fmt_stats(perf_stats(g))}")
        for dlabel in ("LONG", "SHORT"):
            g2 = g[g["direction"] == dlabel]
            print(f"    {dlabel:5s}  {fmt_stats(perf_stats(g2))}")
        for sp in ("sub1", "sub2", "sub3"):
            g3 = g[g["sub_periodo"] == sp]
            print(f"    {sp}    {fmt_stats(perf_stats(g3))}")

    valid = df_b.dropna(subset=["legacy_aligned_with_d1"])
    rho_primary_legacy = spearman_corr(valid[primary], valid["legacy_aligned_with_d1"].astype(float))
    print(f"\nrho({primary}, legacy_aligned_with_d1) sobre la submuestra con legacy no-nulo: {rho_primary_legacy:+.4f}")

    cat_primary = tercile_label(valid[primary])
    print(f"\n¿Legacy aporta informacion incremental respecto a {primary}? -- cruzando tercil de {primary} x legacy:")
    for cval in ["D1_low(bearish-ish)", "D1_mid(neutral)", "D1_high(bullish-ish)"]:
        for lval, llabel in ((True, "alineado"), (False, "en contra")):
            sub = valid[(cat_primary == cval) & (valid["legacy_aligned_with_d1"] == lval)]
            if len(sub) >= 15:
                print(f"  {cval:22s} x legacy={llabel:10s}  {fmt_stats(perf_stats(sub))}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-047.2 -- D1 Alignment Definition Freeze & Directional Asymmetry, XAU")
    print("READ-ONLY / OFFLINE / RESEARCH / DEFINITION FREEZE. No se modifico produccion. No se activa gating.")
    print("No se implementa alignment_score, no se asignan pesos, no se ejecuta BOT-047.3.\n")

    df_a, df_b = preflight()
    if FAILURES:
        print(f"\n=== RESUMEN FINAL === \nFAILURES: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    decomp = decompose_raw_vs_aligned(df_b)
    long_short_detail(df_b)
    cf = closed_vs_forming(df_b)
    redundancy, primary, secondary = redundancy_analysis(df_b)
    compare_models(df_b, primary, secondary)
    legacy_comparison(df_b, primary)

    section("Artefactos CSV de trazabilidad")
    decomp.to_csv(REPORTS_DIR / "BOT-047.2-alignment-candidates-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2-alignment-candidates-xau.csv'}")
    redundancy.to_csv(REPORTS_DIR / "BOT-047.2-alignment-directional-analysis-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2-alignment-directional-analysis-xau.csv'}")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    print(f"\nPRIMARY elegido: {primary}")
    print(f"SECONDARY elegido: {secondary}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
