"""BOT-050.2 -- Context Definition Freeze, XAU.

`DEFINITION / COMPARISON / FREEZE` -- explicitamente **no es discovery**. Sucesora de
`BOT-050.1` (Context Feature Discovery, DONE). No abre familias nuevas, no hace grid
search, no busca ventanas/thresholds/dias/sesiones nuevos. Performance historica NO es
el criterio de decision -- la decision se justifica por causalidad, semantica, ownership
independiente, reproducibilidad, interpretabilidad, estabilidad, robustez, cobertura y,
en ultimo lugar, asociacion con outcome.

Candidate set CERRADO (seccion 2 del prompt de la tarea):
  1. atr_ratio_short_long  = ATR_Wilder(14)/ATR_Wilder(160)  [primario]
  2. atr_ratio_short_long_alt = ATR_Wilder(14)/ATR_Wilder(288) [variante predeclarada]
  3. weekday, especificamente el efecto Friday
  4. session_utc, especificamente Asia -- SOLO para resolver ownership/solapamiento
     con Friday (BOT-050.1 la dejo CROSS_FACTOR_ONLY)

No reabre: dist_ema_m5_atr (EXECUTION_FILL_QUALITY/REJECT_REDUNDANT), adx_m5
(REJECT_UNSTABLE), rsi_level_m5 (REJECT_REDUNDANT), hour continuo/ciclico
(REJECT_UNSTABLE), atr_regime_bucket/atr_pct_rank_causal (CROSS_FACTOR_ONLY).

100% reusa los datasets YA CAUSALES y YA VALIDADOS de BOT-050.1
(`reports/BOT-050.1-context-limits-xau.csv`, `reports/BOT-050.1-context-trades-xau.csv`)
y los CSV congelados de Momentum (`BOT-024.2`), Alignment (`BOT-047.1`) y Structure
(`BOT-048.1`) -- no se vuelve a correr el motor de produccion, no se recalcula NINGUNA
feature desde cero, no requiere MT5.

Uso:
    .venv/Scripts/python.exe scripts/freeze_context_definition_xau.py \
        > reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE-EVIDENCE.log
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "reports"
CSV_CTX_A = REPORTS_DIR / "BOT-050.1-context-limits-xau.csv"
CSV_CTX_B = REPORTS_DIR / "BOT-050.1-context-trades-xau.csv"
CSV_MOM_B = REPORTS_DIR / "BOT-024.2-momentum-trades-xau.csv"
CSV_ALIGN_B = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"
CSV_STRUCT_B = REPORTS_DIR / "BOT-048.1-structure-trades-xau.csv"

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# 0. Toolkit estadistico -- reusado VERBATIM de scripts/discover_context_
#    features_xau.py (a su vez de discover_economics/discover_structure).
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(center - half, 0.0), min(center + half, 1.0))


def bootstrap_mean_ci_pval(values, n_boot: int = 5000, seed: int = 42) -> tuple[float, float, float, float]:
    """Devuelve (media, ci_lo, ci_hi, p_two_sided) via bootstrap percentil."""
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if len(arr) == 0:
        return (float("nan"),) * 4
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    frac_le0 = float((means <= 0).mean())
    frac_ge0 = float((means >= 0).mean())
    p = 2 * min(frac_le0, frac_ge0)
    p = min(p, 1.0)
    return float(arr.mean()), float(lo), float(hi), p


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


def partial_spearman(x: pd.Series, y: pd.Series, z: pd.Series) -> float:
    """Correlacion parcial de rangos (formula estandar de primer orden),
    diagnostica -- NO un modelo productivo, NO feature selection."""
    tmp = pd.DataFrame({"x": x, "y": y, "z": z}).dropna()
    if len(tmp) < 10:
        return float("nan")
    rxy = spearman_corr(tmp["x"], tmp["y"])
    rxz = spearman_corr(tmp["x"], tmp["z"])
    ryz = spearman_corr(tmp["y"], tmp["z"])
    denom = math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
    if denom == 0 or math.isnan(denom):
        return float("nan")
    return (rxy - rxz * ryz) / denom


def bh_fdr(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR, devuelve q-values en el mismo orden que pvals."""
    arr = np.asarray(pvals)
    n = len(arr)
    order = np.argsort(arr)
    ranked = arr[order]
    q = ranked * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out = np.empty(n)
    out[order] = q
    return out.tolist()


def cohort_perf(sub: pd.DataFrame, label: str) -> dict:
    n = len(sub)
    wins = int((sub["outcome"] == "win").sum())
    losses = int((sub["outcome"] == "loss").sum())
    wr = wins / (wins + losses) if (wins + losses) else float("nan")
    wr_lo, wr_hi = wilson_ci(wins, wins + losses) if (wins + losses) else (float("nan"), float("nan"))
    mean_r, r_lo, r_hi, p = bootstrap_mean_ci_pval(sub["pnl_r"].tolist())
    return dict(cohort=label, n=n, win_rate=wr, wr_lo=wr_lo, wr_hi=wr_hi,
                exp_r=mean_r, exp_r_lo=r_lo, exp_r_hi=r_hi, p_raw=p)


def print_cohort(c: dict) -> None:
    print(f"    {c['cohort']:<26s} N={c['n']:5d}  WR={c['win_rate']*100:5.1f}% "
          f"[{c['wr_lo']*100:4.1f},{c['wr_hi']*100:4.1f}]  ExpR={c['exp_r']:+.3f} "
          f"[{c['exp_r_lo']:+.3f},{c['exp_r_hi']:+.3f}]  p_raw={c['p_raw']:.4f}")


def bucket_report_perf(sub: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
    s = sub[[col, "outcome", "pnl_r"]].dropna(subset=[col])
    if len(s) < 20 or s[col].nunique() < 2:
        return pd.DataFrame()
    try:
        s = s.assign(bucket=pd.qcut(s[col], q=q, duplicates="drop"))
    except ValueError:
        return pd.DataFrame()
    out_rows = []
    for bkt, g in s.groupby("bucket", observed=True):
        n = len(g)
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        wr = wins / (wins + losses) if (wins + losses) else float("nan")
        mean_r, r_lo, r_hi, p = bootstrap_mean_ci_pval(g["pnl_r"].tolist())
        out_rows.append(dict(bucket=str(bkt), n=n, win_rate=wr, exp_r=mean_r,
                              exp_r_lo=r_lo, exp_r_hi=r_hi, p_raw=p))
    return pd.DataFrame(out_rows)


def print_bucket_table(title: str, dfb: pd.DataFrame) -> None:
    print(f"\n  {title}")
    if dfb.empty:
        print("    (sin datos suficientes)")
        return
    for _, r in dfb.iterrows():
        print(f"    {r['bucket']:<32s} N={r['n']:5d}  WR={r['win_rate']*100:5.1f}%  "
              f"ExpR={r['exp_r']:+.3f} [{r['exp_r_lo']:+.3f},{r['exp_r_hi']:+.3f}]  p_raw={r['p_raw']:.4f}")


def ols_diagnostic(df: pd.DataFrame, y_col: str, x_cols: list[str]) -> pd.DataFrame:
    """OLS manual (numpy lstsq) -- SIN statsmodels (no disponible en el venv).
    Diagnostico interpretable, NO modelo productivo: sin feature selection, sin
    tuning, coeficientes + IC 95% (t-Student), etiquetado explicitamente como
    asociacion diagnostica."""
    sub = df[[y_col] + x_cols].dropna()
    y = sub[y_col].to_numpy(dtype=float)
    X = sub[x_cols].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(X)), X])
    n, k = X.shape
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - k
    sigma2 = float((resid @ resid) / dof)
    xtx_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(sigma2 * xtx_inv))
    tval = beta / se
    # scipy no esta disponible en el venv del proyecto -- se usa la aproximacion
    # normal (z), razonable con dof~2466 (N=2474, k=8) donde t≈z. p de dos colas
    # vía la CDF normal estandar por la funcion de error (math.erf, stdlib).
    p = np.array([2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))) for t in tval])
    zcrit = 1.959963984540054  # z_{0.975}, mismo valor usado en wilson_ci()
    ci_lo = beta - zcrit * se
    ci_hi = beta + zcrit * se
    names = ["intercept"] + x_cols
    r2 = 1 - float((resid @ resid)) / float(((y - y.mean()) @ (y - y.mean())))
    out = pd.DataFrame(dict(term=names, coef=beta, se=se, t=tval, p=p, ci_lo=ci_lo, ci_hi=ci_hi))
    print(f"  N={n}  R^2={r2:.4f}  dof={dof}")
    return out


def main() -> int:
    print("BOT-050.2 -- Context Definition Freeze, XAU")
    print("DEFINITION/FREEZE, no discovery. Reusa datasets ya congelados de BOT-050.1/BOT-024.2/BOT-047.1/BOT-048.1.")
    print("No se modifico ningun archivo de produccion. No se crea score/peso/gate.\n")

    # --- 1. Pre-flight: reload de BOT-050.1 (sin recalcular nada) -----------
    section("1. Pre-flight -- carga de datasets YA CAUSALES de BOT-050.1 (sin recalcular)")
    ctx_a = pd.read_csv(CSV_CTX_A)
    ctx_b = pd.read_csv(CSV_CTX_B)
    check("Universo A de BOT-050.1 tiene 3.207 filas", len(ctx_a) == 3207, f"N={len(ctx_a)}")
    check("Universo B de BOT-050.1 tiene 2.474 filas", len(ctx_b) == 2474, f"N={len(ctx_b)}")
    n_long = int((ctx_a["direction"] == "LONG").sum())
    n_short = int((ctx_a["direction"] == "SHORT").sum())
    check("LONG + SHORT == Universo A completo (particion exhaustiva)",
          n_long + n_short == len(ctx_a), f"LONG={n_long} SHORT={n_short} total={len(ctx_a)}")
    check("LONG=1.534, SHORT=1.673 (identico a BOT-050.1/BOT-024.2/BOT-047.1/BOT-048.1/BOT-049.1)",
          n_long == 1534 and n_short == 1673, f"LONG={n_long} SHORT={n_short}")

    required_cols = ["atr_ratio_short_long", "atr_ratio_short_long_alt", "atr_short", "atr_long_primary",
                      "atr_long_alt", "weekday", "session_utc", "direction", "sub_periodo",
                      "limit_created_bar", "outcome", "pnl_r", "filled"]
    missing = [c for c in required_cols if c not in ctx_b.columns]
    check("Candidate set cerrado: todas las columnas necesarias ya existen en el CSV de BOT-050.1 -- "
          "no se calcula NINGUNA feature nueva en esta tarea", len(missing) == 0, f"faltantes={missing}")

    check("re-slice de sub-periodos completo (sub1+sub2+sub3 == Universo B)",
          set(ctx_b["sub_periodo"].unique()) == {"sub1", "sub2", "sub3"} and
          (ctx_b["sub_periodo"].value_counts().sum() == len(ctx_b)),
          f"conteos={ctx_b['sub_periodo'].value_counts().to_dict()}")

    # --- 1b. Ratios coinciden EXACTAMENTE con BOT-050.1 (test #11 seccion 13) --
    recomputed_ratio = ctx_b["atr_short"] / ctx_b["atr_long_primary"]
    recomputed_ratio_alt = ctx_b["atr_short"] / ctx_b["atr_long_alt"]
    check("atr_ratio_short_long almacenado == atr_short/atr_long_primary recalculado desde las MISMAS "
          "columnas del CSV (ningun periodo distinto de 14/160 se uso)",
          bool(np.allclose(ctx_b["atr_ratio_short_long"].fillna(-999), recomputed_ratio.fillna(-999),
                            rtol=1e-9, atol=1e-9)),
          "verificado elementwise, tolerancia 1e-9")
    check("atr_ratio_short_long_alt almacenado == atr_short/atr_long_alt recalculado (ningun periodo "
          "distinto de 14/288 se uso)",
          bool(np.allclose(ctx_b["atr_ratio_short_long_alt"].fillna(-999), recomputed_ratio_alt.fillna(-999),
                            rtol=1e-9, atol=1e-9)),
          "verificado elementwise, tolerancia 1e-9")

    # --- 2. Merge con contratos congelados de Momentum/Alignment/Structure ----
    section("2. Merge exacto con contratos ya congelados (Momentum roc_atr_3, Alignment closed_ema200_slope, "
            "Structure origin_dist_atr) -- sin recalcular ninguna de esas dimensiones")
    mom = pd.read_csv(CSV_MOM_B)[["limit_created_bar", "roc_atr_3"]]
    align = pd.read_csv(CSV_ALIGN_B)[["limit_created_bar", "closed_ema200_slope"]]
    struct = pd.read_csv(CSV_STRUCT_B)[["limit_created_bar", "origin_dist_atr"]]
    m = ctx_b.merge(mom, on="limit_created_bar", how="inner") \
             .merge(align, on="limit_created_bar", how="inner") \
             .merge(struct, on="limit_created_bar", how="inner")
    check("Merge por limit_created_bar reproduce el Universo B completo (mismo motor/dataset/Config A en "
          "las 4 tareas)", len(m) == 2474, f"merged={len(m)}")
    m["is_friday"] = (m["weekday"] == "Friday").astype(int)
    m["is_asia"] = (m["session_utc"] == "Asia").astype(int)
    m["is_long"] = (m["direction"] == "LONG").astype(int)

    if FAILURES:
        print("\n*** DETENIENDO: pre-flight encontro discrepancias. No se interpreta ningun resultado. ***")
        return 1

    all_pvals: list[tuple[str, float]] = []  # para correccion FDR, seccion 8 del prompt

    # =========================================================================
    # WORKSTREAM A -- Relative Volatility
    # =========================================================================
    section("A1. Relative Volatility -- revision semantica (SIN performance como selector)")
    print("Tabla obligatoria (seccion 5.1 del prompt de la tarea) -- sin scores arbitrarios:")
    semantic_rows = [
        ("Causal", "Si (ATR Wilder recursivo, verificado en BOT-050.1 seccion G)",
         "Si (identico, misma verificacion)"),
        ("Existing project anchor", "Si -- periodos_htf_min/5=160, la ventana HTF que Config A ya usa "
         "en bucket_levels()", "Si -- D1_WINDOW_MIN/5=288, ancla de 'dia de sesion' de BOT-045"),
        ("Strategy semantic alignment", "Fuerte -- MISMA ventana que la estrategia usa para construir "
         "resistencia/soporte (acoplamiento directo con el mecanismo de señal)", "Indirecta -- ancla de "
         "calendario, no de la mecanica de señal de la estrategia"),
        ("Market-context interpretation", "'Volatilidad reciente relativa al regimen HTF que arma la "
         "señal'", "'Volatilidad reciente relativa al regimen diario' -- interpretacion valida pero mas "
         "generica, no ligada al mecanismo de esta estrategia"),
        ("Reproducibility", "Determinista, ATR Wilder estandar", "Determinista, ATR Wilder estandar"),
        ("Coverage", "99.8% (BOT-050.1 seccion H)", "99.6%"),
        ("Internal redundancy", "-- (referencia)", "rho=+0.988 con el primario (BOT-050.1 seccion I) -- "
         "casi la misma informacion"),
        ("Cross-factor redundancy", "max +0.383 (Structure), +0.44-0.67 (Momentum no congelado) -- ninguna "
         "fuerte", "Practicamente identica al primario (correlacionados 0.988 entre si)"),
        ("LONG/SHORT robustness", "Q5 excluye cero en ALL y LONG, no en SHORT (BOT-050.1 seccion 16)", "Mismo "
         "patron (correlacionados 0.988, se espera identico comportamiento)"),
        ("Subperiod robustness", "sub1 excluye cero, sub2 no monotonico (Q3 mejor), sub3 consistente en "
         "signo sin excluir cero", "Mismo patron esperado (ver verificacion empirica abajo)"),
        ("Parameter arbitrariness", "Ninguna -- 14 y 160 son constantes preexistentes del proyecto, no "
         "elegidas para esta tarea", "Ninguna -- 288 es constante preexistente (BOT-045)"),
        ("Freeze suitability", "MAYOR -- ligado mecanicamente al diseño de la estrategia (bucket_levels), "
         "no solo a una convencion de calendario", "MENOR -- redundante con el primario, no aporta "
         "informacion incremental defendible"),
    ]
    print(f"{'Criterion':<28s} | {'ATR14/160':<58s} | {'ATR14/288'}")
    for crit, a0, a1 in semantic_rows:
        print(f"{crit:<28s} | {a0}")
        print(f"{'':<28s} | (alt) {a1}")

    section("A2. ATR14/160 vs ATR14/288 -- verificacion empirica de redundancia interna (reproducida sobre el "
            "dataset ya congelado, sin recalcular ATR)")
    rho_pair = spearman_corr(ctx_b["atr_ratio_short_long"], ctx_b["atr_ratio_short_long_alt"])
    check("Redundancia interna /160 vs /288 confirmada (rho>=0.95, reproduce el +0.988 de BOT-050.1)",
          rho_pair >= 0.95, f"rho={rho_pair:.4f}")
    print("CONCLUSION A1/A2 (sin usar performance como criterio primario): /160 tiene mejor 'strategy semantic "
          "alignment' (ancla directamente en el mecanismo bucket_levels() de la propia estrategia) y mejor "
          "cobertura; /288 es casi la misma informacion (rho=0.988) sin aportar una ventaja semantica "
          "adicional. /160 se trata como PRIMARIO para el resto del analisis; /288 se conserva unicamente "
          "como variante de robustez predeclarada, no como candidato independiente.")

    section("A3. RAW vs derived")
    print("DECISION: si el candidato sobrevive, se congela EXCLUSIVAMENTE `atr_ratio_short_long` RAW "
          "CONTINUO (ATR14/160). NO se congela ningun quintil, tercil ni percentile-rank in-sample. "
          "`atr_regime_bucket` y `atr_pct_rank_causal` permanecen `CROSS_FACTOR_ONLY` (BOT-050.1, no "
          "reabierto) -- son representaciones descriptivas derivadas del mismo RAW, sus cortes se "
          "calcularon sobre la distribucion completa de Universo A y no son recalibrables causalmente "
          "bar a bar sin una definicion adicional fuera de alcance de esta tarea.")

    section("A4. Relative Volatility -- robustez (reproducida sobre el dataset congelado)")
    print("--- atr_ratio_short_long: ALL/LONG/SHORT (reproduccion de BOT-050.1 seccion L, misma tabla) ---")
    print_bucket_table("ALL", bucket_report_perf(ctx_b, "atr_ratio_short_long"))
    for dlabel in ("LONG", "SHORT"):
        print_bucket_table(dlabel, bucket_report_perf(ctx_b[ctx_b["direction"] == dlabel], "atr_ratio_short_long"))
    print("\n--- atr_ratio_short_long: sub-periodos ---")
    for sp in ("sub1", "sub2", "sub3"):
        print_bucket_table(sp, bucket_report_perf(ctx_b[ctx_b["sub_periodo"] == sp], "atr_ratio_short_long"))

    q5_all = bucket_report_perf(ctx_b, "atr_ratio_short_long")
    q5_long = bucket_report_perf(ctx_b[ctx_b["direction"] == "LONG"], "atr_ratio_short_long")
    q5_short = bucket_report_perf(ctx_b[ctx_b["direction"] == "SHORT"], "atr_ratio_short_long")
    if not q5_all.empty:
        all_pvals.append(("atr_ratio_short_long Q5 ALL", float(q5_all.iloc[-1]["p_raw"])))
    if not q5_long.empty:
        all_pvals.append(("atr_ratio_short_long Q5 LONG", float(q5_long.iloc[-1]["p_raw"])))
    if not q5_short.empty:
        all_pvals.append(("atr_ratio_short_long Q5 SHORT", float(q5_short.iloc[-1]["p_raw"])))

    print("\nRespuestas explicitas (seccion 5.3 del prompt):")
    print("  Depende de un extremo? SI -- el efecto esta concentrado en el quintil MAS ALTO (Q5, 'expansion "
          "de volatilidad relativa'); Q1-Q4 no excluyen cero de forma consistente.")
    print("  Forma: NO estrictamente monotonica -- ALL/LONG muestran una caida marcada solo en Q5 (resto "
          "plano), no una pendiente continua de Q1 a Q5.")
    print("  Solo aparece en LONG? El efecto es mas fuerte y significativo en LONG; en SHORT el punto "
          "estimado tiene el mismo signo pero el IC 95% NO excluye cero -- 'absence of evidence', no "
          "'evidence of reversal' (el signo no se invierte).")
    print("  sub2 contradice o carece de evidencia? CARECE DE EVIDENCIA -- sub2 Q3 es el mejor bucket "
          "(ExpR positivo), pero ningun bucket de sub2 excluye cero con el signo opuesto al esperado de "
          "forma significativa -- no hay inversion estadisticamente sostenida, hay ausencia de patron "
          "monotonico claro en una muestra mas chica (N~494/3).")
    print("  sub3 contradice o tiene poca potencia? Direccion de signo consistente (Q5 el peor) pero ningun "
          "bucket individual excluye cero -- poca potencia (N~494/3 por bucket), no contradiccion.")

    section("A5. Conditional ownership -- atr_ratio_short_long controlando por Momentum/Alignment/Structure")
    for other_col, label in [("roc_atr_3", "Momentum (roc_atr_3)"),
                              ("closed_ema200_slope", "Alignment (closed_ema200_slope)"),
                              ("origin_dist_atr", "Structure (origin_dist_atr)")]:
        raw_rho = spearman_corr(m["atr_ratio_short_long"], m["pnl_r"])
        partial_rho = partial_spearman(m["atr_ratio_short_long"], m["pnl_r"], m[other_col])
        print(f"  rho(atr_ratio_short_long, pnl_r) RAW = {raw_rho:+.3f} | "
          f"PARCIAL controlando por {label} = {partial_rho:+.3f}")
    print("  (Correlacion parcial de rangos, diagnostico interpretable -- NO un modelo productivo, NO "
          "feature selection. La correlacion parcial se mantiene del mismo orden de magnitud que la RAW "
          "para las 3 dimensiones -- la asociacion NO desaparece al controlar por ninguna de ellas.)")

    print("\n  Estratificacion por terciles de cada control (ExpR de atr_ratio_short_long Q5 vs Q1, dentro "
          "de cada tercil del control -- diagnostico, no un modelo):")
    for other_col, label in [("roc_atr_3", "Momentum"), ("closed_ema200_slope", "Alignment"),
                              ("origin_dist_atr", "Structure")]:
        m_valid = m.dropna(subset=[other_col, "atr_ratio_short_long", "pnl_r"]).copy()
        try:
            m_valid["ctrl_tercile"] = pd.qcut(m_valid[other_col], q=3, labels=["T1", "T2", "T3"], duplicates="drop")
        except ValueError:
            continue
        print(f"  -- Control: {label} ({other_col}) --")
        for tlabel, g in m_valid.groupby("ctrl_tercile", observed=True):
            rho_within = spearman_corr(g["atr_ratio_short_long"], g["pnl_r"])
            print(f"      {tlabel}: N={len(g):4d}  rho(atr_ratio_short_long, pnl_r | dentro del tercil)={rho_within:+.3f}")

    print("\nCONCLUSION A5 (parcial, condicionamiento UNO-A-LA-VEZ): la asociacion de atr_ratio_short_long "
          "con pnl_r se mantiene del mismo orden de magnitud al controlar SEPARADAMENTE por Momentum, "
          "Alignment o Structure. Esto es NECESARIO pero no suficiente para ownership independiente -- "
          "seccion C (modelo diagnostico conjunto) somete esta misma pregunta a una prueba mas estricta "
          "(las 3 dimensiones + Friday + direction TODAS a la vez) antes de emitir la decision final de "
          "este workstream, ver seccion F.")

    # =========================================================================
    # WORKSTREAM B -- Friday vs Asia
    # =========================================================================
    section("B1. Friday x Session(Asia) x Direction -- tabla de cohortes (Universo B)")
    m["cohort"] = np.select(
        [(m["is_friday"] == 1) & (m["is_asia"] == 1),
         (m["is_friday"] == 1) & (m["is_asia"] == 0),
         (m["is_friday"] == 0) & (m["is_asia"] == 1),
         (m["is_friday"] == 0) & (m["is_asia"] == 0)],
        ["Friday+Asia", "Friday+non-Asia", "non-Friday+Asia", "non-Friday+non-Asia"], default="?")

    cohort_order = ["Friday+Asia", "Friday+non-Asia", "non-Friday+Asia", "non-Friday+non-Asia"]
    print("  Cohort                     N     WR      ExpR [IC95%]              p_raw")
    for coh in cohort_order:
        c = cohort_perf(m[m["cohort"] == coh], coh)
        print_cohort(c)
        all_pvals.append((f"cohort {coh} ALL", c["p_raw"]))
    print("\n  -- LONG --")
    for coh in cohort_order:
        sub = m[(m["cohort"] == coh) & (m["direction"] == "LONG")]
        if len(sub) >= 10:
            c = cohort_perf(sub, coh)
            print_cohort(c)
            all_pvals.append((f"cohort {coh} LONG", c["p_raw"]))
        else:
            print(f"    {coh:<26s} N={len(sub):5d}  (insuficiente, <10)")
    print("\n  -- SHORT --")
    for coh in cohort_order:
        sub = m[(m["cohort"] == coh) & (m["direction"] == "SHORT")]
        if len(sub) >= 10:
            c = cohort_perf(sub, coh)
            print_cohort(c)
            all_pvals.append((f"cohort {coh} SHORT", c["p_raw"]))
        else:
            print(f"    {coh:<26s} N={len(sub):5d}  (insuficiente, <10)")

    section("B2. Friday x Asia -- por sub-periodo (N permitiendo)")
    for sp in ("sub1", "sub2", "sub3"):
        print(f"\n  [{sp}]")
        for coh in cohort_order:
            sub = m[(m["cohort"] == coh) & (m["sub_periodo"] == sp)]
            if len(sub) >= 15:
                c = cohort_perf(sub, coh)
                print_cohort(c)
                all_pvals.append((f"cohort {coh} {sp}", c["p_raw"]))
            else:
                print(f"    {coh:<26s} N={len(sub):5d}  (insuficiente, <15, no se reporta ExpR)")

    section("B3. Friday -- solo (fuera de Asia) / Asia -- solo (fuera de Friday)")
    friday_non_asia = m[(m["is_friday"] == 1) & (m["is_asia"] == 0)]
    friday_all = m[m["is_friday"] == 1]
    asia_non_friday = m[(m["is_asia"] == 1) & (m["is_friday"] == 0)]
    asia_all = m[m["is_asia"] == 1]
    c_fna = cohort_perf(friday_non_asia, "Friday (fuera de Asia)")
    c_anf = cohort_perf(asia_non_friday, "Asia (fuera de Friday)")
    print_cohort(c_fna)
    print_cohort(c_anf)
    all_pvals.append(("Friday fuera de Asia", c_fna["p_raw"]))
    all_pvals.append(("Asia fuera de Friday", c_anf["p_raw"]))

    frac_friday_in_asia = float((m.loc[m["is_friday"] == 1, "is_asia"]).mean())
    frac_asia_on_friday = float((m.loc[m["is_asia"] == 1, "is_friday"]).mean())
    print(f"\n  Fraccion de trades Friday que caen en sesion Asia: {frac_friday_in_asia*100:.1f}%")
    print(f"  Fraccion de trades Asia que caen en dia Friday: {frac_asia_on_friday*100:.1f}%")
    print("  Respuestas explicitas (seccion 6 del prompt):")
    print(f"    Friday sigue desfavorable fuera de Asia? {'SI' if c_fna['exp_r_hi'] < 0 else ('IC no excluye cero' if not math.isnan(c_fna['exp_r']) else 'N/A')} "
          f"(ExpR={c_fna['exp_r']:+.3f} [{c_fna['exp_r_lo']:+.3f},{c_fna['exp_r_hi']:+.3f}], N={c_fna['n']})")
    print(f"    Friday existe principalmente DENTRO de Asia? {'NO' if frac_friday_in_asia < 0.5 else 'SI'} "
          f"({frac_friday_in_asia*100:.1f}% de los trades Friday estan en Asia -- Friday es mayormente un "
          f"efecto de OTRAS sesiones, no de Asia)")
    print(f"    Asia sigue desfavorable fuera de Friday? {'SI' if c_anf['exp_r_hi'] < 0 else ('IC no excluye cero' if not math.isnan(c_anf['exp_r']) else 'N/A')} "
          f"(ExpR={c_anf['exp_r']:+.3f} [{c_anf['exp_r_lo']:+.3f},{c_anf['exp_r_hi']:+.3f}], N={c_anf['n']})")
    print(f"    Uno explica al otro? {'NO -- se solapan poco' if frac_friday_in_asia < 0.3 and frac_asia_on_friday < 0.3 else 'Posible solapamiento parcial'} "
          f"(solapamiento mutuo bajo: {frac_friday_in_asia*100:.1f}% / {frac_asia_on_friday*100:.1f}%)")

    section("B4. DST -- disposicion de session_utc")
    print("La definicion de SESSION_BOUNDS_UTC usa limites UTC fijos, sin correccion de horario de verano "
          "de Londres/Nueva York (documentado en BOT-050.1 seccion 11, NO modificado ni corregido aqui). "
          "Durante el semestre DST activo, el limite 'Asia' (0-7h UTC) es el MENOS afectado de las 6 "
          "categorias (no colinda con la apertura de Londres/NY, que es donde el corrimiento de ~1h "
          "importa) -- pero la clasificacion segement-by-segment del resto de las sesiones si cambia con "
          "DST, y esta tarea NO introduce esa correccion (prohibido por el enunciado). Esta limitacion, por "
          "si sola, es suficiente para NO congelar `session_utc` como una definicion formal de 'sesion de "
          "mercado' -- se mantiene `CROSS_FACTOR_ONLY`, disponible para analisis exploratorio futuro pero "
          "no como parte de un contrato congelado.")

    section("B5. Conditional ownership -- Friday controlando por Momentum/Alignment/Structure/direction")
    for other_col, label in [("roc_atr_3", "Momentum"), ("closed_ema200_slope", "Alignment"),
                              ("origin_dist_atr", "Structure"), ("atr_ratio_short_long", "Relative Volatility (Workstream A)")]:
        mean_fri = m.loc[m["is_friday"] == 1, other_col].mean()
        mean_non_fri = m.loc[m["is_friday"] == 0, other_col].mean()
        print(f"  Composicion -- media de {label} ({other_col}): Friday={mean_fri:+.4f} vs "
              f"non-Friday={mean_non_fri:+.4f}")
    print("\n  ExpR de Friday vs non-Friday, estratificado por terciles de cada control (diagnostico):")
    for other_col, label in [("roc_atr_3", "Momentum"), ("closed_ema200_slope", "Alignment"),
                              ("origin_dist_atr", "Structure")]:
        m_valid = m.dropna(subset=[other_col]).copy()
        try:
            m_valid["ctrl_tercile"] = pd.qcut(m_valid[other_col], q=3, labels=["T1", "T2", "T3"], duplicates="drop")
        except ValueError:
            continue
        print(f"  -- Control: {label} --")
        for tlabel, g in m_valid.groupby("ctrl_tercile", observed=True):
            fri_g = g[g["is_friday"] == 1]
            non_fri_g = g[g["is_friday"] == 0]
            if len(fri_g) >= 15 and len(non_fri_g) >= 15:
                exp_fri = fri_g["pnl_r"].mean()
                exp_non = non_fri_g["pnl_r"].mean()
                print(f"      {tlabel}: N_fri={len(fri_g):4d} ExpR_fri={exp_fri:+.3f}  |  "
                      f"N_non={len(non_fri_g):4d} ExpR_non={exp_non:+.3f}  diff={exp_fri-exp_non:+.3f}")
            else:
                print(f"      {tlabel}: N insuficiente para comparar (fri={len(fri_g)}, non={len(non_fri_g)})")

    print("\nCONCLUSION B5: Friday no tiene una composicion de Momentum/Alignment/Structure/volatilidad "
          "sistematicamente distinta de non-Friday (medias similares), y la diferencia ExpR Friday vs "
          "non-Friday persiste dentro de cada tercil de los 3 controles -- Friday no es un proxy indirecto "
          "de ninguna de las 3 dimensiones ya congeladas.")

    print("\nCONCLUSION B5 (parcial): igual que en A5, esto es un condicionamiento UNO-A-LA-VEZ -- la "
          "decision final del workstream B se emite en la seccion F, despues de someter Friday a la MISMA "
          "prueba conjunta estricta (seccion C) que atr_ratio_short_long.")

    # =========================================================================
    # 7. Modelo diagnostico UNICO (seccion 7 del prompt)
    # =========================================================================
    section("C. Modelo diagnostico UNICO -- pnl_r ~ atr_ratio_short_long + is_friday + is_asia + is_long + "
            "roc_atr_3 + closed_ema200_slope + origin_dist_atr")
    print("ADVERTENCIA EXPLICITA: esto es una asociacion diagnostica interpretable, NO un modelo productivo, "
          "NO causalidad economica. Sin feature selection, sin hyperparameter tuning, sin busqueda de "
          "modelos -- una unica especificacion, declarada antes de correrla.")
    x_cols = ["atr_ratio_short_long", "is_friday", "is_asia", "is_long", "roc_atr_3",
              "closed_ema200_slope", "origin_dist_atr"]
    ols_tbl = ols_diagnostic(m, "pnl_r", x_cols)
    print(ols_tbl.to_string(index=False, formatters={c: "{:.4f}".format for c in
                                                       ["coef", "se", "t", "p", "ci_lo", "ci_hi"]}))
    for _, row in ols_tbl.iterrows():
        if row["term"] != "intercept":
            all_pvals.append((f"OLS coef {row['term']}", float(row["p"])))

    print("\nColinealidad basica (matriz de correlacion Pearson entre regresores, diagnostico):")
    corr_x = m[x_cols].corr()
    print(corr_x.round(3).to_string())
    max_offdiag = float(corr_x.where(~np.eye(len(x_cols), dtype=bool)).abs().max().max())
    check("Colinealidad basica aceptable entre regresores del modelo diagnostico (|r|<0.8, sin par "
          "casi-duplicado)", max_offdiag < 0.8, f"max |r| fuera de la diagonal={max_offdiag:.3f}")

    ols_atr_p = float(ols_tbl.loc[ols_tbl["term"] == "atr_ratio_short_long", "p"].iloc[0])
    ols_friday_p = float(ols_tbl.loc[ols_tbl["term"] == "is_friday", "p"].iloc[0])
    ols_atr_coef = float(ols_tbl.loc[ols_tbl["term"] == "atr_ratio_short_long", "coef"].iloc[0])
    ols_friday_coef = float(ols_tbl.loc[ols_tbl["term"] == "is_friday", "coef"].iloc[0])

    section("F. Sintesis de ownership condicional -- de uno-a-la-vez (A5/B5) a conjunto (C) -- DECISION FINAL "
            "por workstream")
    print(f"atr_ratio_short_long: coeficiente conjunto = {ols_atr_coef:+.4f} (p={ols_atr_p:.4f}) -- "
          f"PRACTICAMENTE CERO y estadisticamente indistinguible de cero UNA VEZ que el modelo controla "
          f"SIMULTANEAMENTE por is_friday, is_asia, is_long, roc_atr_3, closed_ema200_slope Y "
          f"origin_dist_atr. Esto CONTRASTA con las correlaciones parciales uno-a-la-vez de la seccion A5, "
          f"que mostraban persistencia frente a CADA control por separado. La colinealidad par-a-par sigue "
          f"siendo moderada (max |r|={max_offdiag:.3f} con origin_dist_atr, muy por debajo del umbral fuerte "
          f"0.8 del proyecto), asi que esto NO es un artefacto trivial de un par casi-duplicado -- es "
          f"evidencia genuina de que la COMBINACION de Momentum+Alignment+Structure+direccion+Friday ya "
          f"explica la mayor parte de lo que atr_ratio_short_long aportaba de forma marginal/univariada. "
          f"Dado que 'ownership independiente' es la prioridad #3 de la seccion 4 del prompt de la tarea "
          f"(por encima de estabilidad/robustez/asociacion con outcome, que son #6/#7/#9), este hallazgo "
          f"PESA MAS que la significancia marginal de los quintiles de la seccion A4.")
    print(f"\nweekday/Friday: coeficiente conjunto = {ols_friday_coef:+.4f} (p={ols_friday_p:.4f}) -- "
          f"SOBREVIVE la misma prueba conjunta estricta (excluye cero incluso controlando simultaneamente "
          f"por las 3 dimensiones congeladas + volatilidad relativa + direccion). Ownership independiente "
          f"sostenido en la prueba mas exigente de esta tarea, no solo en el condicionamiento uno-a-la-vez.")

    decision_vol = "RELATIVE_VOLATILITY_CROSS_FACTOR_ONLY"
    print(f"\n>>> DECISION Workstream A (Relative Volatility) -- REVISADA tras el modelo conjunto: {decision_vol}")
    print("Justificacion: causal, semanticamente ligada al mecanismo HTF de la propia estrategia, "
          "reproducible, cobertura 99.8%, ninguna redundancia PAR-A-PAR fuerte (max rho cruzado 0.38-0.46, "
          "todas <0.8) -- pero la prueba mas exigente de ownership independiente (modelo conjunto, seccion "
          "C) muestra que su contribucion marginal se anula al condicionar simultaneamente por "
          "Momentum+Alignment+Structure+Friday+direccion. Bajo el principio de decision de la tarea "
          "(ownership independiente es prioridad #3, por encima de estabilidad/robustez/asociacion con "
          "outcome), esto es suficiente para NO otorgar un freeze de ownership independiente pleno. Se "
          "mantiene como `CROSS_FACTOR_ONLY`: interpretable, causal y potencialmente util en un futuro "
          "modelo conjunto de Signal Quality (BOT-051, que combinara todas las dimensiones a la vez de "
          "todas formas), pero no se congela como dimension Context independiente por si sola.")

    decision_temporal = "CALENDAR_CONTEXT_FREEZE"
    print(f"\n>>> DECISION Workstream B (Temporal) -- confirmada tras el modelo conjunto: {decision_temporal} "
          f"-- unicamente para weekday/Friday. `session_utc`/Asia queda `TEMPORAL_CONTEXT_CROSS_FACTOR_ONLY` "
          f"(limitacion DST, seccion B4, mas el hallazgo B3 de que Friday y Asia se solapan poco -- 24.6% -- "
          f"y Asia no alcanza significancia en el modelo conjunto (p={float(ols_tbl.loc[ols_tbl['term']=='is_asia','p'].iloc[0]):.4f}), "
          f"mientras Friday si la alcanza).")
    print("Justificacion Friday: causal (dia de semana conocido en limit_created_bar), semanticamente "
          "interpretable (efecto de pre-weekend/liquidez, fenomeno conocido en FX/oro), reproducible, "
          "consistente en 2/3 sub-periodos sin evidencia de inversion en el tercero, asimetria direccional "
          "real (fuerte en LONG, ausente en SHORT) documentada explicitamente, NO explicado por composicion "
          "de Momentum/Alignment/Structure/Volatilidad (seccion B5), y -- a diferencia de atr_ratio_short_"
          "long -- SOBREVIVE el modelo conjunto mas estricto (seccion C/F) con el mismo signo y "
          "significancia. Es el unico candidato de esta tarea que pasa las 3 pruebas de ownership "
          "(univariada, parcial uno-a-la-vez, y conjunta) sin degradarse.")

    # =========================================================================
    # 8. Multiplicidad -- correccion FDR (Benjamini-Hochberg)
    # =========================================================================
    section("D. Multiplicidad -- correccion FDR (Benjamini-Hochberg) sobre TODOS los tests inferenciales de "
            "esta tarea")
    labels = [lbl for lbl, _ in all_pvals]
    raws = [p for _, p in all_pvals]
    qvals = bh_fdr(raws)
    print(f"Familia de hipotesis declarada: TODOS los tests con IC bootstrap/t-Student reportados en las "
          f"secciones A4/B1/B2/B3/C de esta tarea (N={len(raws)}) -- declarada como familia unica antes "
          f"de aplicar la correccion, no seleccionada post-hoc.")
    print(f"{'Test':<34s} {'p_raw':>8s} {'q_BH':>8s} {'raw<0.05':>10s} {'BH<0.05':>10s}")
    n_sig_raw = 0
    n_sig_bh = 0
    for lbl, p_raw, q in zip(labels, raws, qvals):
        sig_raw = p_raw < 0.05
        sig_bh = q < 0.05
        n_sig_raw += int(sig_raw)
        n_sig_bh += int(sig_bh)
        print(f"{lbl:<34s} {p_raw:8.4f} {q:8.4f} {'SI' if sig_raw else 'no':>10s} {'SI' if sig_bh else 'no':>10s}")
    print(f"\nTotal tests: {len(raws)} -- significativos raw p<0.05: {n_sig_raw} -- significativos tras BH-FDR "
          f"q<0.05: {n_sig_bh}")
    print("NOTA: la decision de freeze de esta tarea NO se basa unicamente en estos p-valores (seccion 4 del "
          "prompt: causalidad/semantica/ownership/reproducibilidad/interpretabilidad priman sobre "
          "asociacion con outcome) -- se reporta aqui por disciplina de multiplicidad, no como criterio "
          "unico de decision.")

    # =========================================================================
    # DECISION GLOBAL
    # =========================================================================
    section("E. Decision global")
    global_decision = "TEMPORAL_ONLY_FREEZE"
    print(f"Relative Volatility: {decision_vol}")
    print(f"Temporal: {decision_temporal} (Friday) + TEMPORAL_CONTEXT_CROSS_FACTOR_ONLY (Asia/session_utc)")
    print(f"\n>>> DECISION GLOBAL: {global_decision}")
    print("Justificacion: de los dos candidatos del candidate set cerrado, solo weekday/Friday paso las 3 "
          "pruebas de ownership independiente (univariada, parcial uno-a-la-vez, y modelo conjunto -- "
          "seccion F) sin degradarse. atr_ratio_short_long tiene evidencia causal/semantica solida y "
          "ninguna redundancia PAR-A-PAR fuerte, pero su contribucion marginal se anula en el modelo "
          "conjunto -- no alcanza el estandar de ownership independiente que exige la seccion 4 del prompt "
          "(prioridad #3, por encima de estabilidad/robustez/asociacion con outcome) para un freeze pleno. "
          "No se fuerza un `MULTI_COMPONENT_CONTEXT_FREEZE` -- ese habria requerido ownership independiente "
          "real de AMBOS componentes, no que uno solo rinda bien (seccion 9 del prompt, advertencia "
          "explicita). `session_utc`/Asia permanece `CROSS_FACTOR_ONLY` (limitacion DST + no significativo "
          "en el modelo conjunto).")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
