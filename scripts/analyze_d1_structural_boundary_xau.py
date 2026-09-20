"""BOT-047.2.2 -- D1 Structural Boundary Validation, XAU.

Subtarea experimental de `BOT-047.2` (sucesora de `BOT-047.2.1`, Structural
Alignment Definition & Legacy Decomposition, DONE -- PROVISIONAL). READ-ONLY
/ OFFLINE / RESEARCH / VALIDATION -- no modifica produccion.

Pregunta central: BOT-047.2.1 encontro que S0 (legacy exacto, particion
"naive" de dia-calendario UTC 00:00->00:00, heredada de BOT-045) muestra una
separacion ALIGNED/AGAINST mas fuerte y mas estable (STABLE en ALL/LONG/
SHORT) que S0b (MISMA regla estructural, particion true-anchor documentada
22:00->22:00 UTC, PARTIALLY_STABLE/STABLE). Esta tarea investiga POR QUE --
si el edge pertenece genuinamente a la estructura D1, o si la estabilidad
extraordinaria de S0 depende especificamente del corte 00:00 UTC.

Restriccion explicita: esto NO es boundary mining. Solo se comparan boundaries
DEFINIDOS ANTES DE MIRAR RESULTADOS, con justificacion semantica
independiente de performance:

  B0 -- Legacy calendar UTC (00:00->00:00), bucket_id = time_utc // 86400.
        Justificacion: comportamiento historico heredado (BOT-045), NO
        incluido porque haya ganado retrospectivamente -- es el status quo
        que se esta auditando.
  B1 -- Canonical D1 session boundary (22:00->22:00 UTC),
        bucket_start_utc_seconds(). Justificacion: convencion D1 documentada
        en `strategy/htf_session.py` (BOT-004), usada para HTF/D1_CLOSED en
        toda la linea BOT-047.x.
  B2 -- CONSIDERADO Y EXCLUIDO, ver seccion 0 (dia del bróker, `time_server`,
        misma convencion que `strategy/engine.py::_server_date()` usa para
        contar noches de swap) -- se verifico ANTES de mirar cualquier
        metrica de performance que, para este dataset/broker especifico, el
        offset `time_server - time_utc` es de solo -3 segundos (no una
        diferencia de zona horaria real) -- la particion resultante es
        estructuralmente indistinguible de B0 (mismos indices de barra en
        practicamente todas las transiciones), asi que NO aporta un punto de
        comparacion independiente para este dataset. Se documenta el chequeo,
        no se fuerza su inclusion como boundary adicional.

No se prueban mas boundaries (no se recorre 00:00..23:00, no hay grid
search). `TREND_LOOKBACK_BLOCKS=3` y la regla HH/HL/LH/LL se mantienen
identicas a BOT-047.2.1 -- el UNICO factor experimental es el boundary.

100% reusa las funciones YA CAUSALES de BOT-047.2.1 (`build_naive_blocks`,
`build_true_blocks`, `naive_trend_at`, `true_trend_at`, `alignment_label`)
via import directo, sin reimplementar la logica de particion de bloques.

Uso:
    .venv/Scripts/python.exe scripts/analyze_d1_structural_boundary_xau.py \
        > reports/BOT-047.2.2-D1-STRUCTURAL-BOUNDARY-EVIDENCE.log

No requiere MT5 (100% offline).
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
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_d1_structural_alignment_xau import (  # noqa: E402
    build_naive_blocks, naive_trend_at, build_true_blocks, true_trend_at, alignment_label, STATE_LABEL,
    perf_stats, fmt_stats, spearman_corr, tercile_label, D1_WINDOW_MIN, LOOKBACK_LEGACY, MIN_CELL_N,
    REPORTS_DIR, DATA_PATH, CSV_TRADES, CSV_LIMITS,
)
from strategy import scoring as sc  # noqa: E402

PRIOR_CSV = REPORTS_DIR / "BOT-047.2.1-legacy-decomposition-xau.csv"
MIN_TRANSITION_N = 15  # umbral minimo para reportar una celda de la matriz de transicion, definido antes de mirar N

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n{'=' * 3} {title} {'=' * 3}")


def stability_label(ev: pd.DataFrame, df_b: pd.DataFrame, candidate_col: str, cut_label: str, mask: pd.Series) -> str:
    cell_ns = []
    signs = []
    for sp in ("sub1", "sub2", "sub3"):
        m_a = mask & (ev["sub_periodo"] == sp) & (ev[candidate_col] == "ALIGNED")
        m_g = mask & (ev["sub_periodo"] == sp) & (ev[candidate_col] == "AGAINST")
        n_a, n_g = int(m_a.sum()), int(m_g.sum())
        cell_ns.append((n_a, n_g))
        exp_a = df_b.loc[m_a.values, "pnl_r"].mean() if n_a else float("nan")
        exp_g = df_b.loc[m_g.values, "pnl_r"].mean() if n_g else float("nan")
        signs.append((exp_a > exp_g) if (n_a and n_g) else None)
    if any(n_a < MIN_CELL_N or n_g < MIN_CELL_N for n_a, n_g in cell_ns):
        return "INSUFFICIENT_N"
    n_true = sum(1 for ok in signs if ok)
    return "STABLE" if n_true == 3 else ("PARTIALLY_STABLE" if n_true == 2 else "UNSTABLE")


# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------

def preflight():
    section("0. PRE-FLIGHT")

    for p in (CSV_LIMITS, CSV_TRADES, PRIOR_CSV,
              REPORTS_DIR / "BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md",
              REPORTS_DIR / "BOT-047.2-ALIGNMENT-DEFINITION-FREEZE.md",
              REPORTS_DIR / "BOT-047.2.1-STRUCTURAL-ALIGNMENT-DEFINITION.md",
              REPO_ROOT / "scripts" / "analyze_d1_structural_alignment_xau.py"):
        check(f"artefacto existe: {p.relative_to(REPO_ROOT)}", p.exists(), str(p))

    df_meta = pd.read_parquet(DATA_PATH)
    n_bars = len(df_meta)
    t0 = pd.to_datetime(df_meta["time_utc"].iloc[0], unit="s")
    t1 = pd.to_datetime(df_meta["time_utc"].iloc[-1], unit="s")
    check("dataset XAU: 100.505 barras M5, rango 2025-04-14..2026-09-15",
          n_bars == 100505 and str(t0.date()) == "2025-04-14" and str(t1.date()) == "2026-09-15",
          f"n_bars={n_bars}, {t0}..{t1}")

    df_a = pd.read_csv(CSV_LIMITS)
    df_b = pd.read_csv(CSV_TRADES)
    check("Universo A == 3.207 LIMITS", len(df_a) == 3207, f"len(df_a)={len(df_a)}")
    check("Universo B == 2.474 trades FILLED_CLOSED", len(df_b) == 2474, f"len(df_b)={len(df_b)}")

    prior = pd.read_csv(PRIOR_CSV)
    check("BOT-047.2.1 CSV tiene 2.474 filas (misma base)", len(prior) == 2474, f"len(prior)={len(prior)}")

    # -- reproducir S0/S0b EXACTOS antes de continuar --
    n0_a = int((prior["S0_legacy_naive"] == "ALIGNED").sum())
    n0_g = int((prior["S0_legacy_naive"] == "AGAINST").sum())
    exp0_a = prior.loc[prior["S0_legacy_naive"] == "ALIGNED", "pnl_r"].mean()
    exp0_g = prior.loc[prior["S0_legacy_naive"] == "AGAINST", "pnl_r"].mean()
    check("S0 reproducido: N ALIGNED=321 / AGAINST=323, ExpR +0.073/-0.178",
          n0_a == 321 and n0_g == 323 and abs(exp0_a - 0.073) < 0.01 and abs(exp0_g - (-0.178)) < 0.01,
          f"N={n0_a}/{n0_g}  ExpR={exp0_a:+.4f}/{exp0_g:+.4f}")

    n0b_a = int((prior["S0b_legacy_true_anchor"] == "ALIGNED").sum())
    n0b_g = int((prior["S0b_legacy_true_anchor"] == "AGAINST").sum())
    exp0b_a = prior.loc[prior["S0b_legacy_true_anchor"] == "ALIGNED", "pnl_r"].mean()
    exp0b_g = prior.loc[prior["S0b_legacy_true_anchor"] == "AGAINST", "pnl_r"].mean()
    check("S0b reproducido: N ALIGNED=455 / AGAINST=457, ExpR -0.003/-0.100",
          n0b_a == 455 and n0b_g == 457 and abs(exp0b_a - (-0.003)) < 0.01 and abs(exp0b_g - (-0.100)) < 0.01,
          f"N={n0b_a}/{n0b_g}  ExpR={exp0b_a:+.4f}/{exp0b_g:+.4f}")

    print("\nProduccion: sin cambios en strategy/, execution/, api/, panel/ (tarea 100% read-only) -- no se ejecuta "
          "ningun backtest nuevo, no se reconecta a MT5.")

    if FAILURES:
        print("\n*** STOP: discrepancia en pre-flight. No se continua con el analisis. ***")
    return df_a, df_b, prior


# ---------------------------------------------------------------------------
# 0.5 B2 -- considerado y excluido (ver docstring del modulo)
# ---------------------------------------------------------------------------

def check_b2_excluded(time_utc: np.ndarray, time_server: np.ndarray, high: np.ndarray, low: np.ndarray):
    section("B2 CONSIDERADO -- dia del broker (time_server), ver docstring")
    offset = time_server.astype(np.int64) - time_utc.astype(np.int64)
    print(f"offset time_server - time_utc: min={offset.min()} max={offset.max()} (constante esperada si el broker "
          f"no tiene un ajuste de zona horaria material para este dataset)")
    bucket_id_b0, block_ids_b0, _ = build_naive_blocks(time_utc, high, low)
    bucket_id_b2, block_ids_b2, _ = build_naive_blocks(time_server, high, low)
    trans_b0 = set(np.where(np.diff(bucket_id_b0) != 0)[0].tolist())
    trans_b2 = set(np.where(np.diff(bucket_id_b2) != 0)[0].tolist())
    overlap = len(trans_b0 & trans_b2)
    union = len(trans_b0 | trans_b2)
    print(f"transiciones B0 (naive, time_utc)={len(trans_b0)}  B2 candidato (naive, time_server)={len(trans_b2)}  "
          f"coincidentes={overlap}/{union} ({overlap/union*100:.1f}%)")
    print(f"CONCLUSION (verificada ANTES de mirar cualquier metrica de performance): offset={offset[0]}s constante "
          f"-- no es una diferencia de zona horaria real para este dataset/broker, la particion resultante es "
          f"~{overlap/union*100:.1f}% identica a B0. B2 NO se incluye como boundary independiente -- no aportaria "
          f"un punto de comparacion distinto para esta muestra (documentado, no se fuerza su inclusion).")


# ---------------------------------------------------------------------------
# A. Reconstruir B0/B1 desde cero (cross-check contra BOT-047.2.1) + tabla evento
# ---------------------------------------------------------------------------

def build_event_table(df_b: pd.DataFrame, prior: pd.DataFrame, time_utc, high, low, open_, close) -> pd.DataFrame:
    section("A. Reconstruccion B0/B1 (cross-check contra BOT-047.2.1) + tabla evento-por-evento")

    bucket_id_naive, block_ids_naive, blocks_naive = build_naive_blocks(time_utc, high, low)
    d1_true, closing_bar_true, blocks_true = build_true_blocks(time_utc, open_, high, low, close)

    rows = []
    for _, r in df_b.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1

        state_b0, _ = naive_trend_at(bucket_id_naive, block_ids_naive, blocks_naive, b, LOOKBACK_LEGACY)
        state_b1, _ = true_trend_at(closing_bar_true, blocks_true, b, LOOKBACK_LEGACY)

        rows.append(dict(
            trade_id=r["trade_id"], limit_created_bar=b, direction=r["direction"], direction_sign=d,
            sub_periodo=r["sub_periodo"], pnl_r=r["pnl_r"], pnl_usd=r["pnl_usd"], outcome=r["outcome"],
            closed_ema200_slope=r["closed_ema200_slope"], momentum_roc_atr_10=r.get("momentum_roc_atr_10", np.nan),
            B0_state=state_b0, B0_alignment=alignment_label(state_b0, d),
            B1_state=state_b1, B1_alignment=alignment_label(state_b1, d),
        ))
    ev = pd.DataFrame(rows)
    ev["state_changed"] = ev["B0_state"] != ev["B1_state"]
    ev["alignment_changed"] = ev["B0_alignment"] != ev["B1_alignment"]

    # cross-check contra BOT-047.2.1 (misma logica, debe coincidir 100%)
    check("Reconstruccion B0 == S0_legacy_naive de BOT-047.2.1, evento por evento",
          bool((ev["B0_alignment"] == prior["S0_legacy_naive"]).all()),
          f"coincidencias={int((ev['B0_alignment']==prior['S0_legacy_naive']).sum())}/{len(ev)}")
    check("Reconstruccion B1 == S0b_legacy_true_anchor de BOT-047.2.1, evento por evento",
          bool((ev["B1_alignment"] == prior["S0b_legacy_true_anchor"]).all()),
          f"coincidencias={int((ev['B1_alignment']==prior['S0b_legacy_true_anchor']).sum())}/{len(ev)}")

    return ev


# ---------------------------------------------------------------------------
# C. Causalidad
# ---------------------------------------------------------------------------

def causal_audit(ev: pd.DataFrame, time_utc, open_, high, low, close):
    section("C. CAUSALIDAD -- constructive proof + empirical replay")
    print("Constructive proof: B0/B1 reusan EXACTAMENTE `build_naive_blocks`/`naive_trend_at`/`build_true_blocks`/"
          "`true_trend_at` de BOT-047.2.1 (mismas funciones, sin modificar) -- ya auditadas constructivamente en esa "
          "tarea (bucket_levels/build_d1_history causales por construccion, _classify_sequence opera solo sobre "
          "bloques ya filtrados como cerrados antes de la barra evaluada). Ningun eslabon lee informacion con "
          "indice de barra > limit_created_bar. No se reintroduce ningun uso de fill_bar, cierre del trade ni "
          "informacion posterior en esta tarea -- todo se evalua en limit_created_bar, igual que BOT-047.2.1.")

    print("\nEmpirical replay (muestra nueva, semilla distinta de BOT-047.2.1 para independencia):")
    sample = ev.sample(n=min(60, len(ev)), random_state=47022).sort_values("limit_created_bar")
    mismatches = []
    checked = 0
    for _, r in sample.iterrows():
        b = int(r["limit_created_bar"])
        d = r["direction_sign"]
        if b < 5:
            continue
        checked += 1
        time_t, high_t, low_t, open_t, close_t = time_utc[:b + 1], high[:b + 1], low[:b + 1], open_[:b + 1], close[:b + 1]

        bucket_id_t, block_ids_t, blocks_t = build_naive_blocks(time_t, high_t, low_t)
        state_b0_trunc, _ = naive_trend_at(bucket_id_t, block_ids_t, blocks_t, b, LOOKBACK_LEGACY)
        if state_b0_trunc != r["B0_state"]:
            mismatches.append((b, "B0", r["B0_state"], state_b0_trunc))

        d1_t, closing_bar_t, blocks_true_t = build_true_blocks(time_t, open_t, high_t, low_t, close_t)
        state_b1_trunc, _ = true_trend_at(closing_bar_t, blocks_true_t, b, LOOKBACK_LEGACY)
        if state_b1_trunc != r["B1_state"]:
            mismatches.append((b, "B1", r["B1_state"], state_b1_trunc))

    check(f"Replay de historia truncada (B0+B1) == calculo sobre historial completo, {checked} eventos",
          len(mismatches) == 0,
          f"eventos verificados={checked}, discrepancias={len(mismatches)}"
          + (f", ejemplos={mismatches[:5]}" if mismatches else " -- 0 mismatches"))
    if mismatches:
        print("\n  *** DETENIENDO: discrepancias en el replay causal. ***")


# ---------------------------------------------------------------------------
# D. Transition analysis
# ---------------------------------------------------------------------------

def transition_analysis(ev: pd.DataFrame) -> pd.DataFrame:
    section("D. TRANSITION ANALYSIS -- matriz B0 state -> B1 state")

    states = ["ALIGNED", "AGAINST", "NEUTRAL_MIXED", "UNAVAILABLE"]
    mat = pd.crosstab(ev["B0_alignment"], ev["B1_alignment"]).reindex(index=states, columns=states, fill_value=0)
    print("\nMatriz de transicion (filas=B0, columnas=B1, conteo N):")
    print(mat.to_string())

    n_same = int((~ev["alignment_changed"]).sum())
    n_changed = int(ev["alignment_changed"].sum())
    print(f"\nSAME (B0==B1): {n_same} ({n_same/len(ev)*100:.1f}%)   CHANGED (B0!=B1): {n_changed} ({n_changed/len(ev)*100:.1f}%)")

    rows = []
    for s0 in states:
        for s1 in states:
            sub = ev[(ev["B0_alignment"] == s0) & (ev["B1_alignment"] == s1)]
            n = len(sub)
            if n == 0:
                continue
            row = dict(B0=s0, B1=s1, N=n, pct_universe=n / len(ev) * 100)
            if n >= MIN_TRANSITION_N:
                wins = int((sub["outcome"] == "win").sum())
                losses = int((sub["outcome"] == "loss").sum())
                wr = wins / (wins + losses) if (wins + losses) else float("nan")
                row.update(WR=wr, ExpR=sub["pnl_r"].mean(),
                           n_long=int((sub["direction"] == "LONG").sum()), n_short=int((sub["direction"] == "SHORT").sum()))
                print(f"  {s0:14s} -> {s1:14s}  N={n:5d} ({n/len(ev)*100:4.1f}%)  WR={wr*100:5.1f}%  "
                      f"ExpR={sub['pnl_r'].mean():+.3f}  LONG={row['n_long']} SHORT={row['n_short']}")
            else:
                print(f"  {s0:14s} -> {s1:14s}  N={n:5d} ({n/len(ev)*100:4.1f}%)  (N<{MIN_TRANSITION_N}, sin metricas)")
            rows.append(row)

    print(f"\nP(ALIGNED_B1 | ALIGNED_B0) = {len(ev[(ev.B0_alignment=='ALIGNED')&(ev.B1_alignment=='ALIGNED')])}/{len(ev[ev.B0_alignment=='ALIGNED'])} "
          f"= {len(ev[(ev.B0_alignment=='ALIGNED')&(ev.B1_alignment=='ALIGNED')])/max(1,len(ev[ev.B0_alignment=='ALIGNED']))*100:.1f}%")
    print(f"P(AGAINST_B1 | AGAINST_B0) = {len(ev[(ev.B0_alignment=='AGAINST')&(ev.B1_alignment=='AGAINST')])}/{len(ev[ev.B0_alignment=='AGAINST'])} "
          f"= {len(ev[(ev.B0_alignment=='AGAINST')&(ev.B1_alignment=='AGAINST')])/max(1,len(ev[ev.B0_alignment=='AGAINST']))*100:.1f}%")

    print("\nDesglose SAME/CHANGED por direccion y sub-periodo:")
    for dlabel in ("LONG", "SHORT"):
        sub = ev[ev["direction"] == dlabel]
        n_s = int((~sub["alignment_changed"]).sum())
        n_c = int(sub["alignment_changed"].sum())
        print(f"  {dlabel:5s}  SAME={n_s} ({n_s/len(sub)*100:.1f}%)  CHANGED={n_c} ({n_c/len(sub)*100:.1f}%)")
    for sp in ("sub1", "sub2", "sub3"):
        sub = ev[ev["sub_periodo"] == sp]
        n_s = int((~sub["alignment_changed"]).sum())
        n_c = int(sub["alignment_changed"].sum())
        print(f"  {sp}    SAME={n_s} ({n_s/len(sub)*100:.1f}%)  CHANGED={n_c} ({n_c/len(sub)*100:.1f}%)")

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# E. Structural anatomy
# ---------------------------------------------------------------------------

def structural_anatomy(ev: pd.DataFrame, df_b: pd.DataFrame, time_utc, open_, high, low, close):
    section("E. STRUCTURAL ANATOMY -- que cambia en los bloques al mover el boundary")

    bucket_id_naive, block_ids_naive, blocks_naive = build_naive_blocks(time_utc, high, low)
    d1_true, closing_bar_true, blocks_true = build_true_blocks(time_utc, open_, high, low, close)

    changed = ev[ev["state_changed"]].copy()
    print(f"Eventos con state_changed=True (B0 raw state != B1 raw state): {len(changed)}/{len(ev)} "
          f"({len(changed)/len(ev)*100:.1f}%)")

    # muestra deterministica (stride regular, NO cherry-picking), distribuida en el tiempo
    stride = max(1, len(changed) // 15)
    sample = changed.iloc[::stride].head(15)
    print(f"\nMuestra de {len(sample)} eventos (stride regular sobre los {len(changed)} con state_changed, "
          f"distribuidos en el tiempo -- no seleccionados por resultado):\n")

    for _, r in sample.iterrows():
        b = int(r["limit_created_bar"])
        idx_naive = int(np.searchsorted(block_ids_naive, bucket_id_naive[b], side="left"))
        idx_true = int(np.searchsorted(closing_bar_true, b, side="left"))
        print(f"--- trade={r['trade_id']}  bar={b}  {pd.Timestamp(int(time_utc[b]), unit='s', tz='UTC')}  "
              f"dir={r['direction']}  B0={STATE_LABEL.get(r['B0_state'])}  B1={STATE_LABEL.get(r['B1_state'])} ---")
        if idx_naive >= LOOKBACK_LEGACY:
            print("  B0 (00:00 UTC) ultimos 3 bloques:")
            for blk_id, hi, lo in blocks_naive[idx_naive - LOOKBACK_LEGACY:idx_naive]:
                ts = pd.Timestamp(int(blk_id) * 86400, unit="s", tz="UTC")
                print(f"    dia calendario {ts.date()}  high={hi:.3f}  low={lo:.3f}")
        else:
            print("  B0: <3 bloques cerrados disponibles")
        if idx_true >= LOOKBACK_LEGACY:
            print("  B1 (22:00 UTC) ultimos 3 bloques:")
            for k in range(idx_true - LOOKBACK_LEGACY, idx_true):
                ts = pd.Timestamp(int(d1_true["bucket_start"][k]), unit="s", tz="UTC")
                print(f"    sesion iniciada {ts}  high={d1_true['high'][k]:.3f}  low={d1_true['low'][k]:.3f}")
        else:
            print("  B1: <3 bloques cerrados disponibles")

    print("\nMecanismo (descriptivo, no evaluado por performance): B0 particiona por dia-calendario UTC "
          "(00:00->00:00); cada 'bloque' B0 captura el high/low observado entre dos medianoches UTC. B1 particiona "
          "por sesion de trading (22:00->22:00 UTC); cada 'bloque' B1 captura el high/low de una sesion completa, "
          "que incluye las ultimas 2 horas del 'dia B0 anterior' junto con las primeras 22 horas del 'dia B0 "
          "siguiente'. El desplazamiento de 2 horas mueve sistematicamente que barras M5 caen en cada bloque cerca "
          "de la medianoche UTC -- si el mercado hizo un extremo (high/low) en esa ventana de 2 horas, B0 y B1 "
          "pueden asignarlo a bloques (y por tanto a 'dias') distintos, cambiando el high/low registrado de cada "
          "bloque y, en consecuencia, la clasificacion HH/HL/LH/LL de la secuencia de 3 bloques. Ver el CSV de "
          "trazabilidad para la enumeracion completa (no solo la muestra impresa aqui).")


# ---------------------------------------------------------------------------
# F/G/H/I/J -- performance, LONG+AGAINST, estabilidad, coverage, regime
# ---------------------------------------------------------------------------

def performance_and_stability(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("F. PERFORMANCE ALL/LONG/SHORT por boundary")
    for col, label in (("B0_alignment", "B0 (00:00 UTC, legacy)"), ("B1_alignment", "B1 (22:00 UTC, documentado)")):
        print(f"\n--- {label} ---")
        for dlabel, mask in (("ALL", pd.Series(True, index=ev.index)), ("LONG", ev["direction"] == "LONG"),
                              ("SHORT", ev["direction"] == "SHORT")):
            for state in ("ALIGNED", "AGAINST"):
                idx = mask & (ev[col] == state)
                sub = df_b[idx.values]
                print(f"  {dlabel:5s} {state:8s} {fmt_stats(perf_stats(sub))}")

    section("G. LONG + AGAINST -- robustez al boundary")
    long_ev = ev[ev["direction"] == "LONG"]
    cohorts = {
        "against en ambos (B0=AGAINST y B1=AGAINST)": (long_ev["B0_alignment"] == "AGAINST") & (long_ev["B1_alignment"] == "AGAINST"),
        "against solo B0 (B0=AGAINST, B1!=AGAINST)": (long_ev["B0_alignment"] == "AGAINST") & (long_ev["B1_alignment"] != "AGAINST"),
        "against solo B1 (B1=AGAINST, B0!=AGAINST)": (long_ev["B1_alignment"] == "AGAINST") & (long_ev["B0_alignment"] != "AGAINST"),
        "against en ninguno": (long_ev["B0_alignment"] != "AGAINST") & (long_ev["B1_alignment"] != "AGAINST"),
    }
    long_mask_all = (ev["direction"] == "LONG")
    for label, cond in cohorts.items():
        full_mask = long_mask_all & cond.reindex(ev.index, fill_value=False)
        sub = df_b[full_mask.values]
        print(f"  {label:45s} {fmt_stats(perf_stats(sub))}")
        for sp in ("sub1", "sub2", "sub3"):
            sub_sp = df_b[(full_mask & (ev["sub_periodo"] == sp)).values]
            if len(sub_sp):
                print(f"    {sp}  {fmt_stats(perf_stats(sub_sp))}")

    section("H. ESTABILIDAD TEMPORAL")
    print(f"Criterios (identicos a BOT-047.2.1, definidos antes de clasificar): STABLE=ExpR(ALIGNED)>ExpR(AGAINST) "
          f"en 3/3 sub-periodos; PARTIALLY_STABLE=2/3; UNSTABLE<=1/3; INSUFFICIENT_N si alguna celda N<{MIN_CELL_N}.")
    stability = {}
    for col, label in (("B0_alignment", "B0"), ("B1_alignment", "B1")):
        stability[label] = {}
        for cut_label, mask in (("ALL", pd.Series(True, index=ev.index)), ("LONG", ev["direction"] == "LONG"),
                                 ("SHORT", ev["direction"] == "SHORT")):
            lab = stability_label(ev, df_b, col, cut_label, mask)
            stability[label][cut_label] = lab
            print(f"  {label} {cut_label:5s} -> {lab}")

    section("I. COVERAGE por boundary")
    for col, label in (("B0_alignment", "B0"), ("B1_alignment", "B1")):
        counts = ev[col].value_counts()
        total = len(ev)
        print(f"  {label}: " + "  ".join(f"{k}={v} ({v/total*100:.1f}%)" for k, v in counts.items()))

    section("J. REDUNDANCIA CON D1 REGIME (closed_ema200_slope)")
    for col, label in (("B0_alignment", "B0"), ("B1_alignment", "B1")):
        num = ev[col].map({"ALIGNED": 1.0, "AGAINST": 0.0})
        valid = num.notna()
        rho = spearman_corr(ev.loc[valid, "closed_ema200_slope"], num[valid])
        print(f"  rho(closed_ema200_slope, {label}) sobre cobertura {label} = {rho:+.4f}")
    print("  closed_ema200_slope se mantiene como referencia de D1 Regime/Trend Strength (no Alignment) -- no se "
          "reinterpreta en esta tarea.")

    return stability


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-047.2.2 -- D1 Structural Boundary Validation, XAU")
    print("READ-ONLY / OFFLINE / RESEARCH / VALIDATION. No se modifico produccion. No se ejecuta BOT-047.3.\n")

    df_a, df_b, prior = preflight()
    if FAILURES:
        _print_summary()
        return 1

    df_meta = pd.read_parquet(DATA_PATH)
    time_utc = df_meta["time_utc"].to_numpy()
    time_server = df_meta["time_server"].to_numpy()
    open_ = df_meta["open"].to_numpy(dtype=float)
    high = df_meta["high"].to_numpy(dtype=float)
    low = df_meta["low"].to_numpy(dtype=float)
    close = df_meta["close"].to_numpy(dtype=float)
    del df_meta

    check_b2_excluded(time_utc, time_server, high, low)

    ev = build_event_table(df_b, prior, time_utc, high, low, open_, close)
    if FAILURES:
        _print_summary()
        return 1

    causal_audit(ev, time_utc, open_, high, low, close)
    if FAILURES:
        _print_summary()
        return 1

    transitions = transition_analysis(ev)
    structural_anatomy(ev, df_b, time_utc, open_, high, low, close)
    stability = performance_and_stability(ev, df_b)

    section("Artefactos CSV de trazabilidad")
    ev.to_csv(REPORTS_DIR / "BOT-047.2.2-boundary-event-comparison-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.2-boundary-event-comparison-xau.csv'} ({len(ev)} filas)")

    mat = pd.crosstab(ev["B0_alignment"], ev["B1_alignment"])
    mat.to_csv(REPORTS_DIR / "BOT-047.2.2-boundary-transition-matrix-xau.csv")
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.2-boundary-transition-matrix-xau.csv'}")

    transitions.to_csv(REPORTS_DIR / "BOT-047.2.2-boundary-performance-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.2-boundary-performance-xau.csv'}")

    section("SEMANTIC SUMMARY (para el reporte .md)")
    n_same = int((~ev["alignment_changed"]).sum())
    n_changed = int(ev["alignment_changed"].sum())
    print(f"SAME={n_same} ({n_same/len(ev)*100:.1f}%)  CHANGED={n_changed} ({n_changed/len(ev)*100:.1f}%)")
    print(f"stability={stability}")

    _print_summary()
    return 1 if FAILURES else 0


def _print_summary():
    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")


if __name__ == "__main__":
    sys.exit(main())
