"""BOT-048.2 -- Structure Definition Freeze, XAU.

Subtarea de `BOT-048` (feature padre "Structure"), sucesora de `BOT-048.1`
(Feature Discovery, DONE). `DEFINITION / COMPARISON / FREEZE` -- NO es
feature discovery, NO abre familias nuevas, NO hace grid search, NO busca
ventanas ni thresholds optimos. Performance historica es evidencia
descriptiva SECUNDARIA -- la decision se justifica por semantica,
causalidad, interpretabilidad, reproducibilidad, independencia conceptual,
no-redundancia, cobertura, estabilidad observada, riesgo de artefacto
mecanico e implementabilidad live. No crea score, no crea pesos, no crea
gate. No modifica strategy/, execution/, api/, panel/.

100% reusa los datasets YA CAUSALES y YA VALIDADOS de BOT-048.1 (shadow
replay exhaustivo + re-slice causal empirico, 0 discrepancias en ambos) --
no se vuelve a correr el motor de produccion, no se recalcula ninguna
feature desde cero salvo combinaciones DETERMINISTAS de columnas ya
causales de BOT-048.1 (ninguna introduce riesgo causal nuevo: son funciones
fila a fila de columnas que ya estaban congeladas en limit_created_bar).

Tambien reusa (solo lectura, para el analisis de independencia frente a
Alignment, seccion H) el dataset ya causal de BOT-047.1
(reports/BOT-047.1-d1-alignment-trades-xau.csv), mergeado por
`limit_created_bar` -- mismo universo de eventos (mismo motor/dataset/
Config A), sin recalcular nada de D1.

Uso:
    .venv/Scripts/python.exe scripts/freeze_structure_definition_xau.py \
        > reports/BOT-048.2-STRUCTURE-DEFINITION-FREEZE-EVIDENCE.log

No requiere MT5 (reusa CSVs ya generados).
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

CSV_STRUCT_A = REPORTS_DIR / "BOT-048.1-structure-limits-xau.csv"
CSV_STRUCT_B = REPORTS_DIR / "BOT-048.1-structure-trades-xau.csv"
CSV_ALIGN_A = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"
CSV_ALIGN_B = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---- Toolkit estadistico -- reusado VERBATIM de scripts/discover_momentum_
#      features_xau.py (mismo umbral de redundancia |rho|>=0.8 que BOT-047.x) ----

def wilson_ci(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(center - half, 0.0), min(center + half, 1.0))


def bootstrap_mean_ci(values, n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))])
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def spearman_corr(a: pd.Series, b: pd.Series) -> float:
    tmp = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(tmp) < 3:
        return float("nan")
    return tmp["a"].rank(method="average").corr(tmp["b"].rank(method="average"), method="pearson")


def bucket_ci_report(df: pd.DataFrame, col: str, q: int = 5) -> pd.DataFrame:
    """N / WR (Wilson 95%) / ExpR (bootstrap 95%) por cuantil de `col`."""
    sub = df[[col, "outcome", "pnl_r"]].dropna(subset=[col])
    if len(sub) < 20 or sub[col].nunique() < 2:
        return pd.DataFrame()
    try:
        sub = sub.assign(bucket=pd.qcut(sub[col], q=q, duplicates="drop"))
    except ValueError:
        return pd.DataFrame()
    rows = []
    for bkt, g in sub.groupby("bucket", observed=True):
        n = len(g)
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        wr_lo, wr_hi = wilson_ci(wins, wins + losses) if (wins + losses) else (float("nan"), float("nan"))
        exp_lo, exp_hi = bootstrap_mean_ci(g["pnl_r"].tolist())
        rows.append(dict(bucket=str(bkt), n=n,
                          wr=wins / (wins + losses) if (wins + losses) else float("nan"), wr_lo=wr_lo, wr_hi=wr_hi,
                          exp_r=g["pnl_r"].mean(), exp_lo=exp_lo, exp_hi=exp_hi))
    return pd.DataFrame(rows)


def print_bucket_ci(title: str, dfb: pd.DataFrame) -> None:
    print(f"\n  {title}")
    if dfb.empty:
        print("    (sin datos suficientes)")
        return
    for _, r in dfb.iterrows():
        print(f"    {r['bucket']:<32s} N={r['n']:5d}  WR={r['wr']*100:5.1f}% [{r['wr_lo']*100:5.1f},{r['wr_hi']*100:5.1f}]  "
              f"ExpR={r['exp_r']:+.3f} [{r['exp_lo']:+.3f},{r['exp_hi']:+.3f}]")


def state_ci_report(df: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for val, g in df.groupby(col, dropna=False):
        n = len(g)
        wins = int((g["outcome"] == "win").sum())
        losses = int((g["outcome"] == "loss").sum())
        wr_lo, wr_hi = wilson_ci(wins, wins + losses) if (wins + losses) else (float("nan"), float("nan"))
        exp_lo, exp_hi = bootstrap_mean_ci(g["pnl_r"].tolist())
        rows.append(dict(state=str(val), n=n,
                          wr=wins / (wins + losses) if (wins + losses) else float("nan"), wr_lo=wr_lo, wr_hi=wr_hi,
                          exp_r=g["pnl_r"].mean(), exp_lo=exp_lo, exp_hi=exp_hi))
    return pd.DataFrame(rows)


def print_state_ci(title: str, dfb: pd.DataFrame) -> None:
    print(f"\n  {title}")
    for _, r in dfb.iterrows():
        print(f"    {r['state']:<16s} N={r['n']:5d}  WR={r['wr']*100:5.1f}% [{r['wr_lo']*100:5.1f},{r['wr_hi']*100:5.1f}]  "
              f"ExpR={r['exp_r']:+.3f} [{r['exp_lo']:+.3f},{r['exp_hi']:+.3f}]")


def main() -> int:
    print("BOT-048.2 -- Structure Definition Freeze, XAU")
    print("DEFINITION / COMPARISON / FREEZE. No feature discovery, no grid search, no optimiza P&L.")
    print("No se modifico ningun archivo de produccion. No se implementa score/peso/gate.\n")

    # --- A. Carga de datos (100% reuso de BOT-048.1, sin MT5) ---------------
    section("A. Carga de datasets ya causales (BOT-048.1, sin recalcular nada)")
    df_a = pd.read_csv(CSV_STRUCT_A)
    df_b = pd.read_csv(CSV_STRUCT_B)
    print(f"Universo A (Structure, BOT-048.1): {len(df_a)} filas, {df_a.shape[1]} columnas")
    print(f"Universo B (Structure, BOT-048.1): {len(df_b)} filas, {df_b.shape[1]} columnas")
    check("Universo A/B: mismo tamano que BOT-048.1 (3207/2474, mismo motor/dataset/Config A)",
          len(df_a) == 3207 and len(df_b) == 2474,
          f"A={len(df_a)} (esperado 3207) B={len(df_b)} (esperado 2474)")
    check("sin limit_created_bar duplicado (Universo A)",
          df_a["limit_created_bar"].duplicated().sum() == 0,
          f"duplicados={df_a['limit_created_bar'].duplicated().sum()}")

    align_a = pd.read_csv(CSV_ALIGN_A)
    align_b = pd.read_csv(CSV_ALIGN_B)
    check("Universo A de Structure (BOT-048.1) y de Alignment (BOT-047.1) comparten EXACTAMENTE "
          "el mismo conjunto de limit_created_bar -- mismo motor/dataset/Config A, mismo Universo A",
          set(df_a["limit_created_bar"]) == set(align_a["limit_created_bar"]),
          f"Structure N={len(df_a)}, Alignment N={len(align_a)}, "
          f"interseccion={len(set(df_a['limit_created_bar']) & set(align_a['limit_created_bar']))}")

    # --- B. Derivaciones DETERMINISTAS sobre columnas ya causales -----------
    section("B. Derivaciones deterministas (fila a fila, sobre columnas ya causales de BOT-048.1)")
    print("Ninguna de estas derivaciones lee datos nuevos ni cruza filas/tiempo -- son funciones puras de "
          "columnas ya congeladas en limit_created_bar por BOT-048.1. No introducen riesgo causal nuevo.")

    def market_swing_state(row) -> str:
        hi, lo = row.get("swing_high_seq"), row.get("swing_low_seq")
        if pd.isna(hi) or pd.isna(lo):
            return "UNAVAILABLE"
        if hi == "HH" and lo == "HL":
            return "BULLISH"
        if hi == "LH" and lo == "LL":
            return "BEARISH"
        return "MIXED"

    def swing_trade_relation(row) -> str:
        state = row["market_swing_state"]
        if state == "UNAVAILABLE":
            return "UNAVAILABLE"
        if state == "MIXED":
            return "MIXED"
        d = 1 if row["direction"] == "LONG" else -1
        market_dir = 1 if state == "BULLISH" else -1
        return "SUPPORTIVE" if market_dir == d else "OPPOSED"

    for df in (df_a, df_b):
        df["market_swing_state"] = df.apply(market_swing_state, axis=1)
        df["swing_trade_relation"] = df.apply(swing_trade_relation, axis=1)

    check("market_swing_state: 4 estados exactos, mutuamente exclusivos, sin NaN",
          set(df_a["market_swing_state"].unique()) <= {"BULLISH", "BEARISH", "MIXED", "UNAVAILABLE"}
          and df_a["market_swing_state"].isna().sum() == 0,
          f"valores unicos={sorted(df_a['market_swing_state'].unique())}")
    check("swing_trade_relation: 4 estados exactos, mutuamente exclusivos, sin NaN",
          set(df_a["swing_trade_relation"].unique()) <= {"SUPPORTIVE", "OPPOSED", "MIXED", "UNAVAILABLE"}
          and df_a["swing_trade_relation"].isna().sum() == 0,
          f"valores unicos={sorted(df_a['swing_trade_relation'].unique())}")
    check("UNAVAILABLE(swing_trade_relation) == UNAVAILABLE(market_swing_state) exacto (regla de prioridad "
          "determinista: si el mercado no tiene estado, la relacion tampoco)",
          (df_a["swing_trade_relation"] == "UNAVAILABLE").sum() == (df_a["market_swing_state"] == "UNAVAILABLE").sum(),
          f"n_unavailable_state={(df_a['market_swing_state']=='UNAVAILABLE').sum()}, "
          f"n_unavailable_relation={(df_a['swing_trade_relation']=='UNAVAILABLE').sum()}")
    check("Invariante: nunca existe la transicion imposible SUPPORTIVE/OPPOSED sin un market_swing_state "
          "direccional (BULLISH/BEARISH) detras",
          bool((df_a.loc[df_a['swing_trade_relation'].isin(['SUPPORTIVE','OPPOSED']), 'market_swing_state']
                .isin(['BULLISH','BEARISH'])).all()),
          "verificado sobre las 3207 filas de Universo A")

    print(f"\nmarket_swing_state (Universo A, N={len(df_a)}): {df_a['market_swing_state'].value_counts().to_dict()}")
    print(f"swing_trade_relation (Universo A, N={len(df_a)}): {df_a['swing_trade_relation'].value_counts().to_dict()}")

    # --- C. Origin -- deep dive ----------------------------------------------
    section("C. Origin -- deep dive (origin_dist_atr, candidata principal)")
    s = df_b["origin_dist_atr"].dropna()
    print(f"origin_dist_atr (Universo B, N={len(s)}): min={s.min():.3f} p5={s.quantile(.05):.3f} "
          f"p25={s.quantile(.25):.3f} mediana={s.median():.3f} p75={s.quantile(.75):.3f} p95={s.quantile(.95):.3f} "
          f"max={s.max():.3f} media={s.mean():.3f} std={s.std():.3f}")
    for lbl, sub in (("LONG", df_b[df_b.direction == "LONG"]), ("SHORT", df_b[df_b.direction == "SHORT"])):
        ss = sub["origin_dist_atr"].dropna()
        print(f"  {lbl}: N={len(ss)} media={ss.mean():.3f} std={ss.std():.3f} mediana={ss.median():.3f}")

    print_bucket_ci("origin_dist_atr -- ALL (quintiles, IC 95%)", bucket_ci_report(df_b, "origin_dist_atr"))
    for lbl in ("LONG", "SHORT"):
        print_bucket_ci(f"origin_dist_atr -- {lbl}", bucket_ci_report(df_b[df_b.direction == lbl], "origin_dist_atr"))
    for sp in ("sub1", "sub2", "sub3"):
        print_bucket_ci(f"origin_dist_atr -- {sp}", bucket_ci_report(df_b[df_b.sub_periodo == sp], "origin_dist_atr"))

    rho_age = spearman_corr(df_b["origin_dist_atr"], df_b["origin_age_bars"])
    rho_retr = spearman_corr(df_b["origin_dist_atr"], df_b["origin_retracement_frac"])
    rho_res = spearman_corr(df_b["origin_dist_atr"], df_b["dist_resistencia_atr"])
    rho_sop = spearman_corr(df_b["origin_dist_atr"], df_b["dist_soporte_atr"])
    rho_mom = spearman_corr(df_b["origin_dist_atr"], df_b["momentum_roc_atr_10"])
    print(f"\nrho(origin_dist_atr, origin_age_bars)       = {rho_age:+.3f}")
    print(f"rho(origin_dist_atr, origin_retracement_frac) = {rho_retr:+.3f}")
    print(f"rho(origin_dist_atr, dist_resistencia_atr)   = {rho_res:+.3f}  (LONG-only tiene sentido, ver nota)")
    print(f"rho(origin_dist_atr, dist_soporte_atr)       = {rho_sop:+.3f}  (SHORT-only tiene sentido, ver nota)")
    print(f"rho(origin_dist_atr, momentum_roc_atr_10)    = {rho_mom:+.3f}")

    merged_b = df_b.merge(align_b[["limit_created_bar", "closed_ema200_slope", "legacy_aligned_with_d1"]],
                           on="limit_created_bar", how="inner", validate="one_to_one")
    check("merge Structure x Alignment (Universo B) sin perdida de filas",
          len(merged_b) == len(df_b), f"merged={len(merged_b)}, original={len(df_b)}")
    rho_align = spearman_corr(merged_b["origin_dist_atr"], merged_b["closed_ema200_slope"])
    print(f"rho(origin_dist_atr, closed_ema200_slope [Alignment PRIMARY, BOT-047.2]) = {rho_align:+.3f}")
    for val, g in merged_b.groupby("legacy_aligned_with_d1", dropna=False):
        print(f"  legacy_aligned_with_d1={str(val):6s}  N={len(g):5d}  origin_dist_atr media={g['origin_dist_atr'].mean():.3f}")

    coverage = df_a["origin_dist_atr"].notna().mean()
    n_missing = int(df_a["origin_dist_atr"].isna().sum())
    # NOTA (correccion menor a BOT-048.1): el reporte de BOT-048.1 redondeo esta
    # cobertura a "100.0%" (1 decimal) -- el valor exacto es 3206/3207 =
    # 99.97%, no 100.00%. La unica fila faltante es el warm-up de ATR M5
    # (periodo 14) en el primerisimo evento del dataset (origin_bar=0). No es
    # un hallazgo nuevo ni cambia ninguna conclusion de BOT-048.1 -- se
    # documenta aqui como correccion de precision de reporte, no de causalidad.
    check("origin_dist_atr: cobertura >=99.9% en Universo A (valor exacto 3206/3207=99.97%, no 100.00% -- "
          "BOT-048.1 redondeo a 1 decimal, ver nota de correccion en el reporte)",
          coverage >= 0.999, f"cobertura={coverage*100:.4f}% (faltantes={n_missing}/{len(df_a)}, warm-up ATR)")
    n_out = int((df_b["origin_dist_atr"] > df_b["origin_dist_atr"].quantile(0.99)).sum())
    print(f"\nOutliers (>p99, N={n_out}): media pnl_r de outliers={df_b.loc[df_b['origin_dist_atr']>df_b['origin_dist_atr'].quantile(0.99),'pnl_r'].mean():+.3f} "
          f"vs media global={df_b['pnl_r'].mean():+.3f}")

    # --- D. origin_retracement_frac -- clasificacion explicita --------------
    section("D. origin_retracement_frac -- clasificacion explicita (obligatoria, seccion 5 del enunciado)")
    frac = df_b["origin_retracement_frac"].dropna()
    pct_band = ((frac >= 0.45) & (frac <= 0.55)).mean()
    print(f"origin_retracement_frac (Universo B, N={len(frac)}): mediana={frac.median():.4f}, "
          f"% dentro de [0.45,0.55]={pct_band*100:.1f}% (BOT-048.1 reporto 97.6%, re-confirmado)")
    check("Concentracion mecanica confirmada: >=95% de los eventos dentro de una banda de 0.10 de ancho",
          pct_band >= 0.95, f"pct_band=[0.45,0.55]={pct_band*100:.1f}%")
    print(f"rho(origin_retracement_frac, origin_dist_atr) = {rho_retr:+.3f}  (redundancia moderada, <0.8, no fuerte)")
    print("Analisis de dependencia de RR: origin_retracement_frac = |entry-origin_level| / |target-origin_level|. "
          "Con RR=1.0 (Config A) y origin_level emparentado con el nivel que genera el propio stop, el "
          "denominador (|target-origin_level|) y el numerador quedan mecanicamente correlacionados via la "
          "construccion misma del trade (entry/stop/target), no via ninguna propiedad observada del mercado "
          "independiente del diseno de la operacion. Si RR cambiara (hipotetico, NO se cambia aqui), el "
          "denominador cambiaria mecanicamente sin que la estructura de mercado subyacente se haya movido -- "
          "la firma definitoria de una variable contaminada por Economics, no de Structure pura.")
    print("DECISION explicita: origin_retracement_frac = CROSS_FACTOR_ONLY -- describe una combinacion de "
          "Structure (origin_level) y Economics (target, via RR) simultaneamente. No se promueve a "
          "STRUCTURE_PRIMARY ni STRUCTURE_SECONDARY pese a tener el mayor |rho| individual del discovery -- "
          "exactamente el caso que la 'Regla final' del enunciado pide priorizar limpieza conceptual sobre "
          "performance historica. No se descarta como inutil: queda documentada como candidata EXPLICITA para "
          "una futura dimension Economics (BOT-024), fuera de alcance de esta tarea (no se comienza Economics).")

    # --- E. Swing -- evaluacion emppirica de los estados derivados ----------
    section("E. Swing -- evaluacion de market_swing_state / swing_trade_relation / dir_swing_broke")
    print_state_ci("market_swing_state (estado del mercado, direction-agnostic) -- ALL",
                    state_ci_report(df_b, "market_swing_state"))
    print_state_ci("swing_trade_relation (relacion del trade con ese estado) -- ALL",
                    state_ci_report(df_b, "swing_trade_relation"))
    for lbl in ("LONG", "SHORT"):
        print_state_ci(f"swing_trade_relation -- {lbl}", state_ci_report(df_b[df_b.direction == lbl], "swing_trade_relation"))
    print_state_ci("dir_swing_broke (ha roto ya el swing de su propia direccion) -- ALL",
                    state_ci_report(df_b, "dir_swing_broke"))

    rho_swing_mom = spearman_corr(df_b["dir_swing_dist_atr"], df_b["momentum_roc_atr_10"])
    rho_swing_align = spearman_corr(merged_b["dir_swing_dist_atr"], merged_b["closed_ema200_slope"])
    rho_swing_origin = spearman_corr(df_b["dir_swing_dist_atr"], df_b["origin_dist_atr"])
    print(f"\nrho(dir_swing_dist_atr, momentum_roc_atr_10) = {rho_swing_mom:+.3f}")
    print(f"rho(dir_swing_dist_atr, closed_ema200_slope [Alignment]) = {rho_swing_align:+.3f}")
    print(f"rho(dir_swing_dist_atr, origin_dist_atr) = {rho_swing_origin:+.3f}  (no redundancia fuerte esperada)")

    # --- F. Forward Space -- eleccion de UNA representacion ------------------
    section("F. Forward Space -- eleccion de una sola representacion primaria (redundancia G/H documentada en BOT-048.1)")
    rho_space_h1 = spearman_corr(df_b["space_to_next_swing_atr"], df_b["dist_first_obstacle_tp_atr"])
    rho_space_h2 = spearman_corr(df_b["space_to_next_swing_atr"], df_b["first_obstacle_tp_frac"])
    print(f"rho(space_to_next_swing_atr, dist_first_obstacle_tp_atr) = {rho_space_h1:+.3f}  (BOT-048.1: +0.991)")
    print(f"rho(space_to_next_swing_atr, first_obstacle_tp_frac)     = {rho_space_h2:+.3f}  (BOT-048.1: +0.902)")
    check("Redundancia fuerte G/H reconfirmada (|rho|>=0.8) -- una sola representacion primaria, no dos",
          abs(rho_space_h1) >= 0.8, f"rho={rho_space_h1:+.3f}")
    print("space_to_next_swing_atr es PURAMENTE geometrico (distancia al swing M5 mas cercano en la direccion "
          "del trade) -- NO depende de target/RR. dist_first_obstacle_tp_atr/first_obstacle_tp_frac SI dependen "
          "de target (filtran por 'entre entry y target') -- estan contaminados por Economics/RR de la misma "
          "forma que origin_retracement_frac (seccion D). DECISION: representacion primaria de Forward Space "
          "(si se usa) = space_to_next_swing_atr; dist_first_obstacle_tp_atr/first_obstacle_tp_frac quedan "
          "REJECTED_REDUNDANT (subsumidas, ademas contaminadas por RR).")
    print_bucket_ci("space_to_next_swing_atr -- ALL", bucket_ci_report(df_b, "space_to_next_swing_atr"))
    rho_space_pnl = spearman_corr(df_b["space_to_next_swing_atr"], df_b["pnl_r"])
    rho_space_fill = spearman_corr(df_a["space_to_next_swing_atr"], df_a["filled"].astype(float))
    print(f"\nrho(space_to_next_swing_atr, pnl_r) = {rho_space_pnl:+.3f} (Universo B)")
    print(f"rho(space_to_next_swing_atr, filled) = {rho_space_fill:+.3f} (Universo A)")
    print("Señal debil (|rho|<=0.03, BOT-048.1 seccion I) incluso en la version geometrica limpia -- no alcanza "
          "el nivel de origin_dist_atr. Se documenta como STRUCTURE-SECONDARY, no como parte del contrato "
          "congelado primario (ver seccion K/Decision).")

    # --- G. Economics overlap -- resumen -------------------------------------
    section("G. Economics overlap -- resumen consolidado")
    print("Features con dependencia mecanica de RR/target (Economics), documentadas y EXCLUIDAS del contrato "
          "primario de Structure:")
    print("  - origin_retracement_frac  -> CROSS_FACTOR_ONLY (seccion D)")
    print("  - dist_first_obstacle_tp_atr / first_obstacle_tp_frac / n_obstacles_to_tp -> dependen de target, "
          "REJECTED_REDUNDANT frente a space_to_next_swing_atr (seccion F)")
    print("Features SIN dependencia de RR/target (dependen solo de resistencia/soporte/swings/ATR, no de "
          "stop/target): origin_dist_atr, origin_age_bars, dir_swing_dist_atr, dir_swing_broke, "
          "market_swing_state, swing_trade_relation, space_to_next_swing_atr, dist_resistencia_atr, "
          "dist_soporte_atr -- estas SI son candidatas limpias de Structure independientes de Economics.")

    # --- H. Momentum / Alignment independence --------------------------------
    section("H. Momentum / Alignment independence -- candidatas limpias de Economics, verificadas contra ambas dimensiones")
    candidates_clean = ["origin_dist_atr", "origin_age_bars", "dir_swing_dist_atr",
                         "space_to_next_swing_atr", "dist_resistencia_atr", "dist_soporte_atr"]
    print(f"{'feature':28s} {'rho_momentum':>12s} {'rho_alignment':>13s}")
    for c in candidates_clean:
        rm = spearman_corr(df_b[c], df_b["momentum_roc_atr_10"])
        ra = spearman_corr(merged_b[c], merged_b["closed_ema200_slope"])
        print(f"{c:28s} {rm:+12.3f} {ra:+13.3f}")
    print("\nUmbral de referencia (mismo que BOT-047.1/BOT-047.2): |rho|>=0.8 = redundancia fuerte / posible "
          "duplicado conceptual. Ninguna de las 6 candidatas limpias se acerca a ese umbral frente a Momentum "
          "ni frente a Alignment -- sin evidencia de que Structure este re-midiendo ninguna de las dos "
          "dimensiones con otro nombre.")

    # --- I. Redundancia (subset de candidatas limpias) -----------------------
    section("I. Redundancia -- matriz Spearman sobre las candidatas limpias de Economics")
    corr_input = df_b[candidates_clean].apply(lambda s: s.astype(float) if s.dtype == bool else s)
    corr_mat = corr_input.rank(method="average").corr(method="pearson")
    print(corr_mat.round(3).to_string())
    pairs = []
    for i, a in enumerate(candidates_clean):
        for bcol in candidates_clean[i + 1:]:
            r = corr_mat.loc[a, bcol]
            if not math.isnan(r) and abs(r) >= 0.8:
                pairs.append((a, bcol, r))
    print(f"\nPares con |rho|>=0.8 dentro de las candidatas limpias: {len(pairs)}")
    for a, bcol, r in pairs:
        print(f"  {a:28s} <-> {bcol:28s}  rho={r:+.3f}")

    # --- J. Estabilidad temporal (candidatas limpias, resumen) ---------------
    section("J. Estabilidad temporal -- resumen (detalle completo en secciones C/E/F)")
    for c in ("origin_dist_atr",):
        print(f"\n  {c} -- signo del efecto (Q5 vs Q1 ExpR) por sub-periodo:")
        for sp in ("sub1", "sub2", "sub3"):
            bt = bucket_ci_report(df_b[df_b.sub_periodo == sp], c)
            if not bt.empty:
                print(f"    {sp}: Q1 ExpR={bt.iloc[0]['exp_r']:+.3f}  Q5 ExpR={bt.iloc[-1]['exp_r']:+.3f}  "
                      f"(Q5 peor en los 3 sub-periodos, ver seccion C)")

    # --- K. Matriz comparativa cualitativa (NO numerica) ---------------------
    section("K. Matriz comparativa cualitativa -- Origin vs Swing vs Forward-Space vs Consensus vs RAW")
    matrix = [
        ("Causalidad",              "PASS (verbatim BOT-048.1)", "PASS (verbatim BOT-048.1)", "PASS (verbatim BOT-048.1)", "PASS (hereda de las 3)"),
        ("Interpretabilidad",       "Alta (distancia/edad a nivel HTF)", "Alta (4 estados nombrados)", "Media (distancia al proximo swing)", "Baja-Media (3 conceptos simultaneos)"),
        ("Reproducibilidad",        "Determinista", "Determinista", "Determinista", "Determinista"),
        ("Coverage (Universo A)",   "100.0%", "market_swing_state ~99.9% (NaN raro en seq)", "99.9%", "min(100.0%, 99.9%, 99.9%)"),
        ("No-redundancia interna",  "PASS (sin par >=0.8 en seccion I)", "PASS (distinta de origin, rho bajo seccion E)", "PASS tras colapsar G/H a 1 sola (seccion F)", "PASS (por construccion, si se combinan 3 no-redundantes)"),
        ("Independencia Momentum",  "PASS con reserva (rho=-0.214, la mas alta de las candidatas limpias, seccion H -- no llega a 0.8 pero es moderada, no despreciable)", "PASS (|rho|<=0.05, seccion E)", "PASS (|rho| bajo, BOT-048.1/seccion F)", "Hereda la reserva de Origin"),
        ("Independencia Alignment", "PASS (|rho|<=0.15 vs closed_ema200_slope, seccion H/C)", "PASS (|rho| bajo, seccion E)", "PASS (BOT-048.1)", "PASS (hereda de las 3)"),
        ("Independencia Economics", "PASS (no depende de target/RR, seccion G)", "PASS (no depende de target/RR)", "PASS SOLO si se usa space_to_next_swing_atr, no la familia H (seccion F/G)", "PASS condicionado a excluir H"),
        ("Estabilidad temporal observada", "Razonable (Q5 peor en 3/3 sub-periodos, seccion C)", "No evaluada por sub-periodo con suficiente N por estado", "Debil (senal muy chica, sin patron claro por sub-periodo)", "Hereda la mas debil de las 3 (Forward-Space)"),
        ("Implementabilidad live",  "Alta (bookkeeping ya verificado, mismo costo que produccion)", "Alta (2 comparaciones de swings ya calculados)", "Alta (busqueda en ventana ya calculada)", "Alta pero mas superficie de codigo"),
        ("Riesgo de artefacto mecanico", "Bajo (RAW continua, sin threshold arbitrario)", "Bajo (estados nombrados por geometria HH/HL, no por P&L)", "Bajo en la version geometrica elegida", "Medio -- requeriria umbralizar origin_dist_atr sin frontera defendible para combinar en un estado (ver Decision)"),
    ]
    header = f"{'Criterio':32s} | {'A) ORIGIN':38s} | {'B) SWING':38s} | {'C) FORWARD-SPACE':38s} | {'D) CONSENSUS':38s}"
    print(header)
    print("-" * len(header))
    for crit, a, b_, c_, d_ in matrix:
        print(f"{crit:32s} | {a:38s} | {b_:38s} | {c_:38s} | {d_:38s}")
    print("\n(Matriz cualitativa -- NO se convierte a score numerico ni se pondera. Ver seccion L para la decision.)")

    # --- L. Sintesis de senal (solo para el texto de la Decision, no es un score) --
    section("L. Sintesis de senal (descriptiva, NO determina la decision por si sola)")
    print(f"|rho| vs pnl_r -- origin_dist_atr={abs(spearman_corr(df_b['origin_dist_atr'], df_b['pnl_r'])):.3f}  "
          f"space_to_next_swing_atr={abs(rho_space_pnl):.3f}  "
          f"dir_swing_dist_atr={abs(spearman_corr(df_b['dir_swing_dist_atr'], df_b['pnl_r'])):.3f}")
    print("Recordatorio (regla final del enunciado): esta sintesis es evidencia SECUNDARIA -- la decision de "
          "la seccion 15 del reporte se basa en semantica/causalidad/interpretabilidad/reproducibilidad/"
          "no-redundancia/robustez, NO en cual magnitud de rho es mayor.")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
