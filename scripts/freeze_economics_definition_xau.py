"""BOT-049.2 -- Economics Definition Freeze, XAU.

`DEFINITION / COMPARISON / FREEZE` -- explicitamente **no es discovery**. Sucesora de
`BOT-049.1` (Economics Feature Discovery, DONE). No abre familias nuevas, no hace grid
search, no busca ventanas ni thresholds optimos. Performance historica NO es el criterio
de decision -- la decision se justifica por semantica, causalidad, interpretabilidad,
reproducibilidad, independencia conceptual, no-redundancia y ownership limpio entre
factores (Momentum/Alignment/Structure/Economics/Context/CVP/execution).

100% reusa los datasets YA CAUSALES y YA VALIDADOS de BOT-049.1
(`reports/BOT-049.1-economics-limits-xau.csv`) y BOT-048.1
(`reports/BOT-048.1-structure-limits-xau.csv`) -- no se vuelve a correr el motor de
produccion, no se recalcula ninguna feature desde cero. Los DOS checks deterministicos de
esta tarea son:

  1. `risk_atr` (BOT-049.1) vs `origin_dist_atr` (Structure, BOT-048.2 `ORIGIN_ONLY_FREEZE`)
     -- verifica, sobre el dataset ya congelado, si son la misma cantidad fisica bajo el
     diseno actual de la estrategia (stop = nivel de origen HTF +/- buffer minimo).
  2. `cvp_margin` (recalculado con `strategy.scoring.cvp_score()`, funcion REAL de
     produccion, sin modificar) vs `breakeven_pct` (BOT-049.1) -- verifica, sobre TODO el
     universo (no una muestra), si son la misma cantidad hasta una constante aditiva
     (`aciertos_pct`).

Uso:
    .venv/Scripts/python.exe scripts/freeze_economics_definition_xau.py \
        > reports/BOT-049.2-ECONOMICS-DEFINITION-FREEZE-EVIDENCE.log

No requiere MT5 (reusa CSVs ya generados y `strategy.scoring.cvp_score()`, logica pura).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from strategy import scoring as sc

REPORTS_DIR = REPO_ROOT / "reports"
CSV_ECON_A = REPORTS_DIR / "BOT-049.1-economics-limits-xau.csv"
CSV_STRUCT_A = REPORTS_DIR / "BOT-048.1-structure-limits-xau.csv"

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    print("BOT-049.2 -- Economics Definition Freeze, XAU")
    print("DEFINITION/FREEZE, no discovery. Reusa datasets ya congelados de BOT-049.1/BOT-048.1.")
    print("No se modifico ningun archivo de produccion. No se crea score/peso/gate.\n")

    econ = pd.read_csv(CSV_ECON_A)
    struct = pd.read_csv(CSV_STRUCT_A)
    check("Universo A de BOT-049.1 tiene 3.207 filas (mismo Universo A que BOT-024.2/BOT-047.1/BOT-048.1)",
          len(econ) == 3207, f"N={len(econ)}")
    check("Universo A de BOT-048.1 tiene 3.207 filas", len(struct) == 3207, f"N={len(struct)}")

    # -------------------------------------------------------------------
    # 1. risk_atr (Economics) vs origin_dist_atr (Structure, ORIGIN_ONLY_FREEZE)
    # -------------------------------------------------------------------
    section("1. risk_atr (BOT-049.1) vs origin_dist_atr (Structure, BOT-048.2 ORIGIN_ONLY_FREEZE)")
    m = econ.merge(struct[["limit_created_bar", "origin_dist_atr", "origin_age_bars"]],
                    on="limit_created_bar", how="inner")
    check("Merge por limit_created_bar reproduce el Universo A completo (mismo motor/dataset/Config A)",
          len(m) == 3207, f"merged={len(m)}")

    diff = m["risk_atr"] - m["origin_dist_atr"]
    rho_raw = m["risk_atr"].corr(m["origin_dist_atr"])
    rho_rank = m["risk_atr"].rank().corr(m["origin_dist_atr"].rank())
    n_nonpos_origin = int((m["origin_dist_atr"] <= 0).sum())
    frac_tight = float((diff.abs() <= 0.10).mean())

    print(f"Argumento algebraico (derivado de strategy/engine.py, sin datos): stop = resistencia[b]*(1+buf) "
          f"(SHORT) o soporte[b]*(1-buf) (LONG), con buf_bp=0.4 (buf=0.00004) -- un desplazamiento MINIMO "
          f"respecto del nivel HTF. `origin_level` (Structure, BOT-048.1) es el nivel HTF que armo la senal "
          f"por ultima vez ANTES de disparar -- casi siempre el MISMO nivel que resistencia[b]/soporte[b] en "
          f"la barra de la senal, salvo re-armado intermedio dentro del mismo bloque ('auto-armado' de "
          f"engine.bucket_levels, ya documentado y verificado causal en BOT-048.1). Por lo tanto: "
          f"risk_price = |stop-entry| ~= |origin_level-entry| + nivel*buf = origin_dist_price_signed + "
          f"termino de buffer minimo -- la MISMA distancia fisica que Structure ya mide, mas un offset "
          f"minusculo.")
    print(f"\nVerificacion empirica sobre el dataset congelado (N={len(m)}):")
    print(f"  correlacion (Pearson, valores crudos): {rho_raw:.4f}")
    print(f"  correlacion (Spearman via rangos): {rho_rank:.4f}")
    print(f"  eventos con origin_dist_atr<=0 (atipico, esperado 0): {n_nonpos_origin}")
    print(f"  diff=risk_atr-origin_dist_atr: media={diff.mean():.4f} mediana={diff.median():.4f} "
          f"std={diff.std():.4f} min={diff.min():.4f} max={diff.max():.4f}")
    print(f"  fraccion con |diff|<=0.10 ATR (banda estrecha frente a la escala tipica de risk_atr, "
          f"mediana~1.75-1.79 ATR): {frac_tight*100:.1f}%")

    check("origin_dist_atr es SIEMPRE positivo (0 eventos <=0) -- consistente con 'entry siempre mas alla "
          "del origen en la direccion favorable del trade', condicion necesaria para la identidad algebraica",
          n_nonpos_origin == 0, f"n_nonpos={n_nonpos_origin}/{len(m)}")
    check("risk_atr y origin_dist_atr son CASI LA MISMA cantidad fisica (rho>=0.95, consistente con la "
          "derivacion algebraica: misma distancia +/- buffer minimo/re-armado ocasional)",
          rho_raw >= 0.95 and rho_rank >= 0.95, f"rho_raw={rho_raw:.4f} rho_rank={rho_rank:.4f}")

    # -------------------------------------------------------------------
    # 2. breakeven_pct (Economics) vs cvp_score() real de produccion
    # -------------------------------------------------------------------
    section("2. breakeven_pct (BOT-049.1) vs strategy.scoring.cvp_score() (funcion REAL de produccion)")
    print("cvp_score() solo usa abs(entry-stop)/abs(target-entry) -- un origen arbitrario (entry=0.0) con "
          "stop/target desplazados +/-risk_price/reward_price reproduce EXACTAMENTE las mismas distancias "
          "que el evento real (no se aproxima nada).")
    aciertos_pct_illustrative = 49.372724  # WR agregado de Config A, Universo B -- ILUSTRATIVO, ver BOT-049.1 seccion P
    margins = []
    for _, r in econ.iterrows():
        d = 1 if r["direction"] == "LONG" else -1
        _, _, margin = sc.cvp_score(
            direction=d, entry=0.0, stop=(-d * r["risk_price"]), target=(d * r["reward_price"]),
            spread_price=r["spread_price"], commission_usd=0.0, fixed_lot=0.01,
            contract_size=1.0, aciertos_pct=aciertos_pct_illustrative)
        margins.append(margin)
    econ = econ.assign(cvp_margin_illustrative=margins)
    reconstructed = econ["cvp_margin_illustrative"] + econ["breakeven_pct"]
    max_dev = float((reconstructed - aciertos_pct_illustrative).abs().max())

    print(f"\ncvp_margin_illustrative + breakeven_pct, sobre las {len(econ)} filas COMPLETAS de Universo A "
          f"(no una muestra): debe ser EXACTAMENTE constante == aciertos_pct_illustrative "
          f"({aciertos_pct_illustrative}), por la propia definicion de cvp_score() "
          f"(`margen = aciertos_pct - breakeven_pct`).")
    print(f"  media={reconstructed.mean():.10f}  std={reconstructed.std():.2e}  "
          f"max|desviacion vs aciertos_pct|={max_dev:.2e}")

    check("cvp_margin_illustrative + breakeven_pct es CONSTANTE (== aciertos_pct) para las 3.207 filas -- "
          "prueba EXHAUSTIVA (no muestral) de que breakeven_pct de Economics y el termino de costo de "
          "cvp_score() son LA MISMA cantidad, no una aproximacion",
          max_dev < 1e-6, f"max_dev={max_dev:.3e}")

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
