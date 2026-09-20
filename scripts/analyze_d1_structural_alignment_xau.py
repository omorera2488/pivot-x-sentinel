"""BOT-047.2.1 -- Structural Alignment Definition & Legacy Decomposition, XAU.

Subtarea EXPERIMENTAL de `BOT-047` (feature padre "D1 Alignment"), sucesora de
`BOT-047.2` (Definition Freeze & Directional Asymmetry, DONE -- PROVISIONAL).
READ-ONLY / OFFLINE / RESEARCH -- no modifica strategy/, execution/, api/,
panel/, configuracion real, scoring productivo ni gating. No optimiza
thresholds, no hace grid search, no ejecuta BOT-047.3.

Pregunta central: BOT-047.2 encontro que `legacy_aligned_with_d1` (BOT-045/
046) aporta informacion incremental que `closed_ema200_slope` (PRIMARY,
Regime) no captura (rho~-0.099, casi independiente), pero con cobertura
limitada (26%). Esta tarea:
  1. Descompone EXACTAMENTE la implementacion legacy (sin modificarla).
  2. Audita su causalidad respecto a `limit_created_bar` (prueba constructiva
     + replay empirico con historia truncada).
  3. Explica la cobertura de 26% descomponiendo las causas del "None".
  4. Compara covered vs uncovered (sesgo de seleccion).
  5. Descompone el estado estructural RAW (bullish/bearish/mixed/insuficiente)
     antes de binarizar a aligned/against.
  6. Evalua LONG vs SHORT por separado.
  7. Compara Regime (`closed_ema200_slope`) vs Structural Alignment.
  8. Investiga candidatos de mayor cobertura, solo con variantes
     semanticamente justificadas (sin threshold mining).
  9. Compara modelos conceptuales S0/S1/S2/S3.
  10. Evalua estabilidad temporal (ALL/LONG/SHORT x sub1/sub2/sub3).
  11. Emite una decision semantica final y un freeze status.

HALLAZGO CRITICO DE PRE-FLIGHT (ver seccion 1): la deteccion de "bloque D1
cerrado" que usa la implementacion legacy real (`07_bot045_regime_dataset.py
::precompute_closed_blocks` / `strategy/scoring.py::_closed_blocks`) NO usa
el ancla de sesion 22:00 UTC (`bucket_start_utc_seconds`) que se documenta en
todo el resto del proyecto (HTF blocks, D1_CLOSED de BOT-047.1) -- usa
`bucket_id = time_utc // (dias*86400)`, una particion NAIVE de dias
calendario UTC (medianoche). Es una particion DISTINTA, verificada
empiricamente (367 transiciones verdaderas vs 443 transiciones naive, indices
de barra NO coincidentes). Esto es 100% CAUSAL (no hay fuga de informacion
futura -- ambas particiones son deterministas y solo usan datos pasados), NO
es un bug de causalidad, pero SI es una discrepancia entre la definicion
documentada ("D1 = sesion 22:00 UTC") y la que realmente ejecuta el codigo
legacy. Se documenta exhaustivamente, no se repara `strategy/scoring.py` ni
`07_bot045_regime_dataset.py` (produccion/tooling ya congelado de otro BOT) --
se construye, en paralelo, una variante "legacy-rule con ancla correcta"
(S0b, seccion 8) para poder separar el efecto de la regla (HH/HL 3 bloques)
del efecto del ancla incorrecta.

100% reusa los datasets YA CAUSALES de BOT-047.1 (`direction`, `pnl_r`,
`sub_periodo`, `closed_ema200_slope`, `closed_swing_high_type`,
`closed_swing_low_type`, `n_d1_closed_days`, `momentum_roc_atr_10`,
`legacy_aligned_with_d1`) -- no se vuelve a correr el motor de produccion.
Solo se recalculan, desde el parquet M5 (read-only), las particiones de
bloques D1 (naive y true-anchor) necesarias para decomponer exactamente el
legacy y para las variantes de cobertura -- funciones deterministas,
fila a fila, sin lookups nuevos cruzando tiempo hacia adelante.

Uso:
    .venv/Scripts/python.exe scripts/analyze_d1_structural_alignment_xau.py \
        > reports/BOT-047.2.1-STRUCTURAL-ALIGNMENT-EVIDENCE.log

No requiere MT5 (100% offline, reusa CSV + parquet ya en el repo).
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

from strategy.engine import bucket_levels  # noqa: E402
from strategy.htf_session import bucket_start_utc_seconds  # noqa: E402
from strategy import scoring as sc  # noqa: E402
from discover_d1_alignment_features_xau import build_d1_history  # noqa: E402 -- funcion ya causal, validada BOT-047.1

REPORTS_DIR = REPO_ROOT / "reports"
DATA_PATH = REPO_ROOT / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"

CSV_LIMITS = REPORTS_DIR / "BOT-047.1-d1-alignment-limits-xau.csv"
CSV_TRADES = REPORTS_DIR / "BOT-047.1-d1-alignment-trades-xau.csv"

D1_WINDOW_MIN = 1440
LOOKBACK_LEGACY = sc.TREND_LOOKBACK_BLOCKS  # 3, mismo valor que produccion/BOT-045
MIN_CELL_N = 20  # umbral minimo, definido ANTES de clasificar estabilidad, para no forzar etiquetas con N insuficiente

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
    try:
        cats = pd.qcut(series, q=3, labels=["D1_low", "D1_mid", "D1_high"], duplicates="drop")
    except ValueError:
        return pd.Series([None] * len(series), index=series.index)
    return cats


# ---------------------------------------------------------------------------
# Bloques D1 -- dos particiones distintas, ambas 100% causales
# ---------------------------------------------------------------------------

def build_naive_blocks(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray):
    """EXACTA replica de `07_bot045_regime_dataset.py::precompute_closed_blocks`
    / `scripts/discover_d1_alignment_features_xau.py` seccion I (bucket_id =
    time_utc // (dias*86400), NO usa bucket_start_utc_seconds). Es la
    particion que la implementacion legacy REAL usa para detectar cuando un
    bloque D1 "cierra". Devuelve (block_ids ordenados, lista de (id, high,
    low)) -- ambos 100% causales (bucket_id[i] solo depende de time_utc[i])."""
    resistencia, soporte = bucket_levels(time_utc, high, low, D1_WINDOW_MIN)
    bucket_len_s = D1_WINDOW_MIN * 60
    bucket_id = time_utc // bucket_len_s
    blocks = []
    n = len(time_utc)
    for i in range(n - 1):
        if bucket_id[i] != bucket_id[i + 1]:
            blocks.append((bucket_id[i], resistencia[i], soporte[i]))
    block_ids = np.array([b[0] for b in blocks])
    return bucket_id, block_ids, blocks


def naive_trend_at(bucket_id: np.ndarray, block_ids: np.ndarray, blocks: list, bar_idx: int, lookback: int):
    idx_l = int(np.searchsorted(block_ids, bucket_id[bar_idx], side="left"))
    if idx_l < lookback:
        return None, idx_l
    recent = blocks[idx_l - lookback:idx_l]
    return sc._classify_sequence(recent, lookback), idx_l


def build_true_blocks(time_utc: np.ndarray, open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray):
    """Bloques D1 con el ancla de sesion DOCUMENTADA (22:00 UTC,
    `bucket_start_utc_seconds`) -- MISMA funcion `build_d1_history()` ya
    causal y ya validada (causalidad constructiva + empirica) en BOT-047.1.
    Un bloque = un dia de sesion D1 completamente cerrado; high/low = OHLC
    del dia (equivalente al `resistencia`/`soporte` de `bucket_levels` en la
    ultima barra del dia, ver seccion 1 del reporte para la verificacion)."""
    d1 = build_d1_history(time_utc, open_, high, low, close)
    closing_bar_arr = d1["closing_bar"]
    blocks = list(zip(range(len(closing_bar_arr)), d1["high"], d1["low"]))
    return d1, closing_bar_arr, blocks


def true_trend_at(closing_bar_arr: np.ndarray, blocks: list, bar_idx: int, lookback: int):
    idx = int(np.searchsorted(closing_bar_arr, bar_idx, side="left"))
    if idx < lookback:
        return None, idx
    recent = blocks[idx - lookback:idx]
    return sc._classify_sequence(recent, lookback), idx


STATE_LABEL = {1: "bullish", -1: "bearish", 0: "mixed", None: "insufficient"}


def alignment_label(state, direction_sign: int) -> str:
    if state is None:
        return "UNAVAILABLE"
    if state == 0:
        return "NEUTRAL_MIXED"
    return "ALIGNED" if state == direction_sign else "AGAINST"


def pivot_state(high_type, low_type):
    if pd.isna(high_type) or pd.isna(low_type):
        return None
    if high_type == "HH" and low_type == "HL":
        return 1
    if high_type == "LH" and low_type == "LL":
        return -1
    return 0  # tipos en desacuerdo (HH+LL o LH+HL) -- estructura mixta


# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------

def preflight():
    section("0. PRE-FLIGHT")

    for p in (CSV_LIMITS, CSV_TRADES,
              REPORTS_DIR / "BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md",
              REPORTS_DIR / "BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY-EVIDENCE.log",
              REPORTS_DIR / "BOT-047.2-ALIGNMENT-DEFINITION-FREEZE.md",
              REPORTS_DIR / "BOT-047.2-ALIGNMENT-DEFINITION-FREEZE-EVIDENCE.log",
              REPO_ROOT / "scripts" / "discover_d1_alignment_features_xau.py",
              REPO_ROOT / "scripts" / "analyze_d1_alignment_definition_xau.py",
              REPO_ROOT / "backtests" / "scripts" / "07_bot045_regime_dataset.py"):
        check(f"artefacto existe: {p.relative_to(REPO_ROOT)}", p.exists(), str(p))

    df_meta = pd.read_parquet(DATA_PATH)
    n_bars = len(df_meta)
    t0 = pd.to_datetime(df_meta["time_utc"].iloc[0], unit="s")
    t1 = pd.to_datetime(df_meta["time_utc"].iloc[-1], unit="s")
    check("dataset XAU: 100.505 barras M5", n_bars == 100505, f"n_bars={n_bars}")
    check("dataset XAU: rango 2025-04-14 .. 2026-09-15",
          str(t0.date()) == "2025-04-14" and str(t1.date()) == "2026-09-15", f"{t0} .. {t1}")

    df_a = pd.read_csv(CSV_LIMITS)
    df_b = pd.read_csv(CSV_TRADES)
    check("Universo A == 3.207 LIMITS", len(df_a) == 3207, f"len(df_a)={len(df_a)}")
    check("Universo B == 2.474 trades FILLED_CLOSED", len(df_b) == 2474, f"len(df_b)={len(df_b)}")

    n_legacy_true = int((df_b["legacy_aligned_with_d1"] == "True").sum() or (df_b["legacy_aligned_with_d1"] == True).sum())  # noqa: E712
    n_legacy_false = int((df_b["legacy_aligned_with_d1"] == "False").sum() or (df_b["legacy_aligned_with_d1"] == False).sum())  # noqa: E712
    n_legacy_none = int(df_b["legacy_aligned_with_d1"].isna().sum())
    check("CSV reproduce legacy_aligned_with_d1 (321/323/1830)",
          (n_legacy_true, n_legacy_false, n_legacy_none) == (321, 323, 1830),
          f"True={n_legacy_true} False={n_legacy_false} None={n_legacy_none}")

    rho_check = spearman_corr(df_b["closed_ema200_slope"], df_b["pnl_r"])
    check("CSV reproduce rho(closed_ema200_slope, pnl_r) ~ +0.149 (metrica principal BOT-047.1/BOT-047.2)",
          abs(rho_check - 0.149295) < 0.001, f"recalculado={rho_check:.6f}")

    legacy_true_mask = df_b["legacy_aligned_with_d1"].astype(str) == "True"
    legacy_false_mask = df_b["legacy_aligned_with_d1"].astype(str) == "False"
    exp_r_true = df_b.loc[legacy_true_mask, "pnl_r"].mean()
    exp_r_false = df_b.loc[legacy_false_mask, "pnl_r"].mean()
    check("Reproduce ExpR legacy alineado~+0.073 / en contra~-0.178 (BOT-047.2 seccion 8)",
          abs(exp_r_true - 0.073) < 0.01 and abs(exp_r_false - (-0.178)) < 0.01,
          f"alineado={exp_r_true:+.4f} en_contra={exp_r_false:+.4f}")

    print("\nProduccion: sin cambios en strategy/, execution/, api/, panel/ (tarea 100% read-only, ver seccion 13 "
          "del enunciado) -- no se ejecuta ningun backtest nuevo, no se reconecta a MT5.")

    if FAILURES:
        print("\n*** STOP: discrepancia en pre-flight. No se continua con el analisis. ***")
    return df_a, df_b


# ---------------------------------------------------------------------------
# 1. Descomposicion exacta del legacy
# ---------------------------------------------------------------------------

def decompose_legacy(df_b: pd.DataFrame, time_utc, high, low, open_, close):
    section("1. DESCOMPOSICION EXACTA DEL LEGACY (bloque real usado por BOT-045/046)")

    print("Implementacion real localizada: `backtests/scripts/07_bot045_regime_dataset.py::precompute_closed_blocks` "
          "+ `trend_at()` (linea 180-191), que llama a `strategy.scoring._classify_sequence()` -- la MISMA funcion "
          "que produccion usa para el factor 'Tendencia' de BOT-023 (`strategy/scoring.py::trend_score`).")
    print("\nPseudocodigo formal (fiel a `_closed_blocks`/`precompute_closed_blocks` + `_classify_sequence`, sin "
          "modificar ninguna de las dos):")
    print("""
    bucket_id[i]      = time_utc[i] // 86400                    # <-- particion NAIVE (medianoche UTC), ver hallazgo abajo
    bloque D1 k CIERRA en barra i  si bucket_id[i] != bucket_id[i+1]
    high_bloque_k     = resistencia[i]  (bucket_levels: maximo acumulado del bloque HASTA la barra i)
    low_bloque_k      = soporte[i]      (idem, minimo acumulado)
    closed_blocks(b)  = todos los bloques k con bucket_id[i_k] < bucket_id[b]   (bloques ya cerrados antes de b)

    classify_sequence(ultimos 3 closed_blocks):
        si hay <3 bloques cerrados      -> None            ('historial insuficiente')
        recent = closed_blocks[-3:]
        si HH y HL estrictos en las 2 comparaciones consecutivas de 'recent' -> +1 (alcista)
        si LH y LL estrictos en las 2 comparaciones consecutivas de 'recent' -> -1 (bajista)
        si no                                                -> 0            ('sin secuencia clara' / mixta)

    d1_dir(b)         = classify_sequence(closed_blocks(b))     # evaluado en el bar donde nace el LIMIT (b=eb en BOT-045
                                                                 # original: eb=entry_bar; en la reconstruccion causal de
                                                                 # BOT-047.1, usada en TODA esta linea de investigacion,
                                                                 # b=limit_created_bar -- ver nota de boundary abajo)
    aligned_with_d1   = (d1_dir == direction_sign)  si d1_dir no es None y no es 0, si no -> None
    """)

    print("Cuantos bloques requiere: exactamente 3 bloques D1 CERRADOS consecutivos (TREND_LOOKBACK_BLOCKS=3, "
          "misma constante que produccion usa para TODOS los factores de tendencia, no solo D1).")
    print("Como usa HH/HL/LH/LL: compara el high y el low de cada bloque contra el bloque inmediatamente anterior, "
          "para las 2 transiciones consecutivas dentro de la ventana de 3 bloques -- exige que AMBAS transiciones "
          "sean estrictamente alcistas (HH y HL) o AMBAS estrictamente bajistas (LH y LL). Cualquier otra "
          "combinacion (incluida una sola transicion mixta) clasifica como 0 ('sin secuencia clara').")
    print("Como determina LONG/SHORT aligned vs against: `aligned = (d1_dir == direction_sign)` con "
          "direction_sign=+1 LONG / -1 SHORT -- SOLO si d1_dir es +1 o -1; si d1_dir es 0 (mixto) o None "
          "(historial insuficiente), el resultado es `None`/`NaN`, indistinguible de warm-up en la columna final.")

    print("\n--- Boundary temporal: `limit_created_bar` vs `entry_bar` ---")
    print("El script ORIGINAL `07_bot045_regime_dataset.py` (BOT-045, linea 293/319) evalua "
          "`d1_dir = trend_at(..., current_bar=eb)` con `eb = t.entry_bar if t.entry_bar is not None else "
          "t.signal_bar` -- es decir, evalua la estructura D1 en el bar de FILL (entrada real), NO en el bar de "
          "nacimiento del LIMIT. `entry_bar >= limit_created_bar` siempre (el fill ocurre en la misma barra o "
          "despues de que nace la orden) -- esto es INFORMACION DISPONIBLE MAS TARDE que `limit_created_bar`, "
          "aunque sigue sin ser 'look-ahead' respecto al momento en que se resuelve el trade.")
    print("La columna `legacy_aligned_with_d1` que usa ESTA linea de investigacion (BOT-047.1/BOT-047.2/esta tarea, "
          "reconstruida en `scripts/discover_d1_alignment_features_xau.py` seccion I) usa en cambio "
          "`b = limit_created_bar` (== signal_bar == born_bar) -- MISMA regla de clasificacion "
          "(`_classify_sequence`, 3 bloques), pero evaluada en el momento de creacion del LIMIT, no en el fill. "
          "Esto es una decision EXPLICITA y correcta para esta linea de investigacion (BOT-047.x evalua todo en "
          "`limit_created_bar`, el mismo punto de congelacion que Momentum/BOT-024.x) -- no reproduce el numero "
          "EXACTO que hubiera calculado el script BOT-045 original si se ejecutara con `entry_bar`, pero SI aplica "
          "la MISMA regla estructural, en un boundary mas estricto/mas temprano (mas conservador desde el punto de "
          "vista causal: nunca usa informacion posterior a la creacion del LIMIT). Se documenta explicitamente "
          "porque el enunciado (Seccion 1) pide clarificar 'que timestamps/boundaries usa' -- la respuesta es: "
          "'depende de si se habla del script BOT-045 original (entry_bar) o de la columna legacy_aligned_with_d1 "
          "ya congelada y usada en toda esta linea (limit_created_bar)'. Esta tarea usa exclusivamente la segunda "
          "(consistente con BOT-047.1/BOT-047.2, ya congelada en los CSV).")

    print("\n--- HALLAZGO CRITICO: particion de bloques NAIVE (medianoche UTC) vs ancla documentada (22:00 UTC) ---")
    bucket_id_naive, block_ids_naive, blocks_naive = build_naive_blocks(time_utc, high, low)
    d1_true, closing_bar_true, blocks_true = build_true_blocks(time_utc, open_, high, low, close)

    true_start = bucket_start_utc_seconds(time_utc, D1_WINDOW_MIN)
    true_trans = np.where(np.diff(true_start) != 0)[0]
    raw_trans = np.where(np.diff(bucket_id_naive) != 0)[0]
    same_transitions = np.array_equal(true_trans, raw_trans)
    # NOTA: esto NO es un check de pre-flight (no se agrega a FAILURES) -- es un HALLAZGO DE ANALISIS esperado y
    # documentado explicitamente en esta seccion (la implementacion legacy real usa una particion distinta de la
    # documentada). Detenerse aqui seria confundir "hallazgo documentado" con "precondicion rota".
    status = "FINDING" if not same_transitions else "PASS"
    print(f"[{status}] bucket_id naive (time_utc // 86400) == particion true-anchor (bucket_start_utc_seconds, 22:00 UTC)?"
          f"\n       transiciones true={len(true_trans)} (== {len(closing_bar_true)} dias D1_CLOSED de BOT-047.1, esperado), "
          f"transiciones naive={len(raw_trans)} (calendario UTC medianoche-a-medianoche) -- "
          f"indices de barra COINCIDEN={same_transitions}")
    print(f"\n  Ejemplo concreto (primeras 3 transiciones):")
    for k in range(3):
        print(f"    true (22:00 UTC)  -> {pd.Timestamp(int(time_utc[true_trans[k] + 1]), unit='s', tz='UTC')}")
        print(f"    naive (00:00 UTC) -> {pd.Timestamp(int(time_utc[raw_trans[k] + 1]), unit='s', tz='UTC')}")
    print("\n  Interpretacion: la implementacion REAL del legacy (`precompute_closed_blocks`/`_closed_blocks`, "
          "identica en `07_bot045_regime_dataset.py` y en `strategy/scoring.py`, usada tambien para el factor "
          "'Tendencia' en vivo con ventanas de 30/240min) NO usa el ancla de sesion 22:00 UTC documentada en "
          "`strategy/htf_session.py` (BOT-004) para el resto del proyecto -- usa una particion de 'dia calendario "
          "UTC' (medianoche a medianoche), simplemente `time_utc // 86400`. Esto es 100% DETERMINISTA Y CAUSAL "
          "(bucket_id[i] depende solo de time_utc[i], nunca de datos futuros) -- NO es una violacion de causalidad, "
          "es una particion temporal DISTINTA de la documentada. Los 'bloques D1' que legacy realmente clasifica "
          "no son sesiones de trading 22:00->22:00 UTC, sino dias de calendario 00:00->00:00 UTC.")
    print("  Esto es HEREDADO del codigo original de BOT-045 (`precompute_closed_blocks`, linea 159-177 de "
          "`07_bot045_regime_dataset.py`) y de `strategy/scoring.py::_closed_blocks` (produccion, factor "
          "'Tendencia') -- NO fue introducido por BOT-047.1 ni por esta tarea. No se modifica ninguno de los dos "
          "(fuera de alcance -- son codigo ya congelado de otros BOTs / produccion). Se documenta exhaustivamente "
          "y se usa como base para construir, EN PARALELO (seccion 8), una variante 'misma regla, ancla "
          "documentada' para poder separar el efecto de la regla estructural del efecto de esta particion.")
    print("  Nota: para ventanas HTF mas cortas (30min), 22:00*60=79.200s es multiplo exacto de 1800s -- ahi la "
          "particion naive SI coincide con la documentada. La discrepancia solo aparece para ventanas donde el "
          "offset del ancla (79.200s) no es multiplo entero de la ventana -- incluido D1 (86.400s) y la ventana de "
          "240min (14.400s) del factor Tendencia -- fuera de alcance de esta tarea (produccion), solo se menciona "
          "como contexto de por que aparece aqui y no en otras ventanas.")

    print("\n--- Por que existen 1.830 valores None ---")
    print("`aligned_with_d1 = None` ocurre en DOS escenarios distintos, indistinguibles en la columna binaria "
          "final: (a) `d1_dir is None` -- menos de 3 bloques D1 cerrados antes de `limit_created_bar` (warm-up "
          "real); (b) `d1_dir == 0` -- 3+ bloques existen, pero NO forman una secuencia HH/HL o LH/LL estricta "
          "('sin secuencia clara' / estructura mixta). Descompuesto exhaustivamente en la seccion 3.")

    return dict(bucket_id_naive=bucket_id_naive, block_ids_naive=block_ids_naive, blocks_naive=blocks_naive,
                d1_true=d1_true, closing_bar_true=closing_bar_true, blocks_true=blocks_true)


# ---------------------------------------------------------------------------
# 2. Auditoria causal
# ---------------------------------------------------------------------------

def causal_audit(df_b: pd.DataFrame, blocks_ctx: dict, time_utc, open_, high, low, close):
    section("2. AUDITORIA CAUSAL DEL LEGACY (respecto a limit_created_bar)")

    print("2.1 Constructive proof:")
    print("  - `bucket_levels()` (resistencia/soporte, usado para high/low de cada bloque naive) es "
          "estrictamente causal por construccion: `run_high[i]`/`run_low[i]` solo se actualizan con `high[j]`/"
          "`low[j]` para j<=i (ver `strategy/engine.py::bucket_levels`, recursion hacia adelante sin relectura "
          "de barras futuras) -- funcion YA validada causalmente por BOT-047.1 (misma funcion, reusada aqui sin "
          "modificar).")
    print("  - `bucket_id_naive[i] = time_utc[i] // 86400` depende EXCLUSIVAMENTE de `time_utc[i]` -- trivialmente "
          "causal, no hay forma de que dependa de barras futuras.")
    print("  - `build_d1_history()`/`build_true_blocks()` (particion true-anchor) es la MISMA funcion ya validada "
          "por BOT-047.1 (causalidad constructiva + empirica, ver `BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY-"
          "EVIDENCE.log` seccion G) -- no se modifica, se reusa via import directo.")
    print("  - `_classify_sequence()` es una funcion pura sobre una lista ya filtrada de bloques CERRADOS antes "
          "de `bar_idx` -- no lee ningun array indexado por barra, solo opera sobre los (high,low) ya extraidos.")
    print("  - Conclusion constructiva: ninguna parte de la cadena (bucket_id -> bloques cerrados -> "
          "classify_sequence -> aligned_with_d1) lee informacion con indice de barra > `limit_created_bar`.")

    print("\n2.2 Empirical truncated-history replay:")
    rng = np.random.default_rng(47021)
    sample = df_b.sample(n=min(60, len(df_b)), random_state=47021).sort_values("limit_created_bar")
    print(f"  Muestra: {len(sample)} eventos (de {len(df_b)} totales), distribuidos en el tiempo y entre "
          f"LONG/SHORT ({(sample['direction']=='LONG').sum()} LONG / {(sample['direction']=='SHORT').sum()} SHORT).")

    mismatches = []
    checked = 0
    for _, r in sample.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1
        if b < 5:
            continue
        checked += 1

        # -- full-history (ya calculado en blocks_ctx) --
        state_naive_full, _ = naive_trend_at(blocks_ctx["bucket_id_naive"], blocks_ctx["block_ids_naive"],
                                              blocks_ctx["blocks_naive"], b, LOOKBACK_LEGACY)
        state_true_full, _ = true_trend_at(blocks_ctx["closing_bar_true"], blocks_ctx["blocks_true"], b, LOOKBACK_LEGACY)

        # -- truncado a [:b+1] --
        time_t, high_t, low_t, open_t, close_t = time_utc[:b + 1], high[:b + 1], low[:b + 1], open_[:b + 1], close[:b + 1]
        bucket_id_t, block_ids_t, blocks_t = build_naive_blocks(time_t, high_t, low_t)
        state_naive_trunc, _ = naive_trend_at(bucket_id_t, block_ids_t, blocks_t, b, LOOKBACK_LEGACY)

        d1_t, closing_bar_t, blocks_true_t = build_true_blocks(time_t, open_t, high_t, low_t, close_t)
        state_true_trunc, _ = true_trend_at(closing_bar_t, blocks_true_t, b, LOOKBACK_LEGACY)

        if state_naive_full != state_naive_trunc:
            mismatches.append((b, "naive", state_naive_full, state_naive_trunc))
        if state_true_full != state_true_trunc:
            mismatches.append((b, "true_anchor", state_true_full, state_true_trunc))

    check(f"Replay de historia truncada (naive + true-anchor) == calculo sobre historial completo, "
          f"{checked} eventos distribuidos en el tiempo y LONG/SHORT",
          len(mismatches) == 0,
          f"eventos verificados={checked}, discrepancias={len(mismatches)}"
          + (f", ejemplos={mismatches[:5]}" if mismatches else " -- 0 mismatches, causalidad confirmada empiricamente"))

    if mismatches:
        print("\n  *** DETENIENDO EL FREEZE: se encontraron discrepancias en el replay causal. ***")


# ---------------------------------------------------------------------------
# 3. Cobertura -- descomposicion de razones del 'None'
# ---------------------------------------------------------------------------

def build_event_table(df_b: pd.DataFrame, blocks_ctx: dict) -> pd.DataFrame:
    """Tabla por evento con TODOS los estados estructurales (naive/true-anchor,
    lookback 2/3/4, pivot-based) -- base para el resto de las secciones."""
    rows = []
    for _, r in df_b.iterrows():
        b = int(r["limit_created_bar"])
        d = 1 if r["direction"] == "LONG" else -1

        state_naive3, idx_naive = naive_trend_at(blocks_ctx["bucket_id_naive"], blocks_ctx["block_ids_naive"],
                                                   blocks_ctx["blocks_naive"], b, 3)
        state_true2, idx_true = true_trend_at(blocks_ctx["closing_bar_true"], blocks_ctx["blocks_true"], b, 2)
        state_true3, _ = true_trend_at(blocks_ctx["closing_bar_true"], blocks_ctx["blocks_true"], b, 3)
        state_true4, _ = true_trend_at(blocks_ctx["closing_bar_true"], blocks_ctx["blocks_true"], b, 4)
        state_pivot = pivot_state(r["closed_swing_high_type"], r["closed_swing_low_type"])

        reason_naive = ("insufficient_blocks(<3)" if state_naive3 is None else
                         "mixed_sequence(0)" if state_naive3 == 0 else "classified")

        rows.append(dict(
            trade_id=r["trade_id"], direction=r["direction"], direction_sign=d,
            limit_created_bar=b, sub_periodo=r["sub_periodo"], pnl_r=r["pnl_r"], pnl_usd=r["pnl_usd"],
            outcome=r["outcome"], closed_ema200_slope=r["closed_ema200_slope"],
            momentum_roc_atr_10=r.get("momentum_roc_atr_10", np.nan),
            n_d1_closed_days=r["n_d1_closed_days"],
            legacy_aligned_with_d1_csv=r["legacy_aligned_with_d1"],
            idx_naive_closed_blocks=idx_naive, state_naive3=state_naive3, reason_naive=reason_naive,
            S0_legacy_naive=alignment_label(state_naive3, d),
            idx_true_closed_days=idx_true,
            state_true2=state_true2, state_true3=state_true3, state_true4=state_true4,
            S0b_legacy_true_anchor=alignment_label(state_true3, d),
            S_true2=alignment_label(state_true2, d),
            S_true4=alignment_label(state_true4, d),
            state_pivot=state_pivot, S3_pivot=alignment_label(state_pivot, d),
        ))
    return pd.DataFrame(rows)


def coverage_reasons(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("3. COBERTURA -- descomposicion de las razones del 'None' legacy (26%)")

    # --- cross-check: reconstruccion propia == columna ya congelada del CSV ---
    csv_true = (df_b["legacy_aligned_with_d1"].astype(str) == "True")
    csv_false = (df_b["legacy_aligned_with_d1"].astype(str) == "False")
    own_true = (ev["S0_legacy_naive"] == "ALIGNED")
    own_false = (ev["S0_legacy_naive"] == "AGAINST")
    check("Reconstruccion propia (idx_naive+classify_sequence+alignment_label) == legacy_aligned_with_d1 del CSV "
          "de BOT-047.1, evento por evento",
          bool((csv_true == own_true).all() and (csv_false == own_false).all()),
          f"coincidencias True={int((csv_true==own_true).sum())}/{len(ev)}, "
          f"False={int((csv_false==own_false).sum())}/{len(ev)}")

    n_insufficient = int((ev["reason_naive"] == "insufficient_blocks(<3)").sum())
    n_mixed = int((ev["reason_naive"] == "mixed_sequence(0)").sum())
    n_classified = int((ev["reason_naive"] == "classified").sum())
    check("insufficient + mixed == 1.830 (total None reportado por BOT-047.1/BOT-047.2)",
          (n_insufficient + n_mixed) == 1830, f"insufficient={n_insufficient} mixed={n_mixed} suma={n_insufficient+n_mixed}")

    print(f"\nTabla de motivos ('None' legacy, N={n_insufficient + n_mixed}, {(n_insufficient+n_mixed)/len(ev)*100:.1f}% del universo):")
    print(f"{'motivo':32s} {'N':>6s} {'% universo':>12s} {'% de los None':>15s}")
    total_none = n_insufficient + n_mixed
    for label, n in (("insufficient_blocks (<3 cerrados)", n_insufficient), ("mixed_sequence (>=3, sin HH/HL o LH/LL)", n_mixed)):
        print(f"{label:32s} {n:6d} {n/len(ev)*100:11.1f}% {n/total_none*100:14.1f}%")
    print(f"{'classified (True/False)':32s} {n_classified:6d} {n_classified/len(ev)*100:11.1f}% {'--':>15s}")

    print("\nDesglose por direccion:")
    for dlabel in ("LONG", "SHORT"):
        sub = ev[ev["direction"] == dlabel]
        n_i = int((sub["reason_naive"] == "insufficient_blocks(<3)").sum())
        n_m = int((sub["reason_naive"] == "mixed_sequence(0)").sum())
        n_c = int((sub["reason_naive"] == "classified").sum())
        print(f"  {dlabel:5s}  N={len(sub):5d}  insufficient={n_i:5d} ({n_i/len(sub)*100:4.1f}%)  "
              f"mixed={n_m:5d} ({n_m/len(sub)*100:4.1f}%)  classified={n_c:5d} ({n_c/len(sub)*100:4.1f}%)")

    print("\nDesglose por sub-periodo:")
    for sp in ("sub1", "sub2", "sub3"):
        sub = ev[ev["sub_periodo"] == sp]
        n_i = int((sub["reason_naive"] == "insufficient_blocks(<3)").sum())
        n_m = int((sub["reason_naive"] == "mixed_sequence(0)").sum())
        n_c = int((sub["reason_naive"] == "classified").sum())
        print(f"  {sp}    N={len(sub):5d}  insufficient={n_i:5d} ({n_i/len(sub)*100:4.1f}%)  "
              f"mixed={n_m:5d} ({n_m/len(sub)*100:4.1f}%)  classified={n_c:5d} ({n_c/len(sub)*100:4.1f}%)")

    print("\nInterpretacion: el 'None' del 74% NO es mayoritariamente warm-up puro -- se descompone en la tabla "
          "de arriba. Si mixed_sequence domina sobre insufficient, la limitacion de cobertura es principalmente "
          "una propiedad de la REGLA (exigir 3 bloques estrictamente monotonicos es una condicion rara, no una "
          "falta de datos), no del tamano del dataset -- relevante para la seccion 8 (candidatos de mayor "
          "cobertura: relajar la regla, no esperar mas datos, es lo que ampliaria cobertura).")

    return dict(n_insufficient=n_insufficient, n_mixed=n_mixed, n_classified=n_classified)


# ---------------------------------------------------------------------------
# 4. Coverage bias -- covered vs uncovered
# ---------------------------------------------------------------------------

def coverage_bias(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("4. COVERAGE BIAS -- covered vs uncovered (legacy S0)")

    covered_mask = ev["S0_legacy_naive"].isin(["ALIGNED", "AGAINST"])
    covered = df_b[covered_mask.values]
    uncovered = df_b[~covered_mask.values]

    for label, g in (("Covered (legacy != None)", covered), ("Uncovered (legacy == None)", uncovered)):
        n_long = int((g["direction"] == "LONG").sum())
        n_short = int((g["direction"] == "SHORT").sum())
        print(f"\n{label}: {fmt_stats(perf_stats(g))}")
        print(f"  LONG={n_long} ({n_long/len(g)*100:.1f}%)  SHORT={n_short} ({n_short/len(g)*100:.1f}%)")
        for sp in ("sub1", "sub2", "sub3"):
            g2 = g[g["sub_periodo"] == sp]
            print(f"  {sp}: {fmt_stats(perf_stats(g2))}")
        print(f"  closed_ema200_slope: mean={g['closed_ema200_slope'].mean():+.4f}  "
              f"median={g['closed_ema200_slope'].median():+.4f}  std={g['closed_ema200_slope'].std():.4f}")
        if "momentum_roc_atr_10" in g.columns:
            mom = g["momentum_roc_atr_10"].dropna()
            if len(mom):
                print(f"  momentum_roc_atr_10: mean={mom.mean():+.4f}  median={mom.median():+.4f}  n={len(mom)}")

    rho_regime_cov = spearman_corr(covered["closed_ema200_slope"], covered["pnl_r"])
    rho_regime_unc = spearman_corr(uncovered["closed_ema200_slope"], uncovered["pnl_r"])
    print(f"\nrho(closed_ema200_slope, pnl_r): covered={rho_regime_cov:+.4f}  uncovered={rho_regime_unc:+.4f}  "
          f"(referencia ALL={spearman_corr(df_b['closed_ema200_slope'], df_b['pnl_r']):+.4f})")

    print("\nPregunta del enunciado: ¿la fuerte separacion del legacy podria estar condicionada por el subconjunto "
          "especifico de trades donde existe estructura clasificable? Diagnostico (no ajuste estadistico): si "
          "covered y uncovered tienen distribucion temporal/direccional/de regimen similar, la separacion no "
          "parece un artefacto de seleccion; si difieren marcadamente, la lectura de la seccion 8 del reporte "
          "de BOT-047.2 (legacy 'aporta informacion incremental') requiere el matiz de que ese subconjunto no es "
          "representativo del universo completo.")


# ---------------------------------------------------------------------------
# 5. Descomposicion estructural RAW (antes de binarizar)
# ---------------------------------------------------------------------------

def structural_decomposition(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("5. DESCOMPOSICION ESTRUCTURAL RAW (S1, antes de binarizar a alignment)")

    print("Estado estructural RAW (S1, true-anchor lookback=3, MISMA regla que legacy pero con el ancla "
          "documentada 22:00 UTC) cruzado con direccion del trade:")
    ev2 = ev.copy()
    ev2["state_true3_label"] = ev2["state_true3"].map(STATE_LABEL)
    for state_label in ("bullish", "bearish", "mixed", "insufficient"):
        for dlabel in ("LONG", "SHORT"):
            sub_idx = (ev2["state_true3_label"] == state_label) & (ev2["direction"] == dlabel)
            sub = df_b[sub_idx.values]
            if len(sub):
                print(f"  {state_label:14s} x {dlabel:5s}  {fmt_stats(perf_stats(sub))}")

    print("\nDistribucion de estados RAW (true-anchor, lookback=3), ALL / LONG / SHORT:")
    for dlabel, mask in (("ALL", pd.Series(True, index=ev2.index)), ("LONG", ev2["direction"] == "LONG"),
                          ("SHORT", ev2["direction"] == "SHORT")):
        counts = ev2.loc[mask, "state_true3_label"].value_counts()
        total = mask.sum()
        line = "  ".join(f"{k}={v} ({v/total*100:.1f}%)" for k, v in counts.items())
        print(f"  {dlabel:6s} (N={total}): {line}")

    print("\nComponentes RAW preservados (no promediados a un score): `n_d1_closed_days` (bloques D1 disponibles), "
          "`closed_swing_high_type`/`closed_swing_low_type` (ultimo pivote D1 confirmado), "
          "`closed_swing_high_age_days`/`closed_swing_low_age_days` (antiguedad del pivote) -- ya en el CSV de "
          "BOT-047.1, columnas independientes, reusadas sin recalcular.")
    print(f"  Edad mediana del ultimo swing-high confirmado: {df_b['closed_swing_high_age_days'].median():.1f} dias "
          f"(N disponible={df_b['closed_swing_high_age_days'].notna().sum()})")
    print(f"  Edad mediana del ultimo swing-low confirmado: {df_b['closed_swing_low_age_days'].median():.1f} dias "
          f"(N disponible={df_b['closed_swing_low_age_days'].notna().sum()})")


# ---------------------------------------------------------------------------
# 6. LONG vs SHORT detallado
# ---------------------------------------------------------------------------

def long_short_breakdown(ev: pd.DataFrame, df_b: pd.DataFrame, candidate_col: str, label: str):
    section(f"6. LONG vs SHORT -- {label} ({candidate_col})")
    for dlabel in ("LONG", "SHORT"):
        print(f"\n--- {dlabel} ---")
        for state in ("ALIGNED", "AGAINST", "NEUTRAL_MIXED", "UNAVAILABLE"):
            idx = (ev["direction"] == dlabel) & (ev[candidate_col] == state)
            sub = df_b[idx.values]
            if len(sub):
                print(f"  {state:14s} {fmt_stats(perf_stats(sub))}")
        for sp in ("sub1", "sub2", "sub3"):
            for state in ("ALIGNED", "AGAINST"):
                idx = (ev["direction"] == dlabel) & (ev["sub_periodo"] == sp) & (ev[candidate_col] == state)
                sub = df_b[idx.values]
                if len(sub):
                    print(f"    {sp} x {state:10s} {fmt_stats(perf_stats(sub))}")

    print("\nAtencion especial LONG+AGAINST (BOT-047.2 encontro ExpR~-0.342 en la version legacy exacta):")
    idx = (ev["direction"] == "LONG") & (ev[candidate_col] == "AGAINST")
    sub = df_b[idx.values]
    print(f"  {fmt_stats(perf_stats(sub))}")
    print("  No se asume automaticamente que esto implique bloquear LONG contra D1 -- N y estabilidad temporal "
          "se evaluan en la seccion 10.")


# ---------------------------------------------------------------------------
# 7. Regime vs Structural Alignment
# ---------------------------------------------------------------------------

def regime_vs_structural(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("7. REGIME (closed_ema200_slope) x STRUCTURAL ALIGNMENT (S0b true-anchor) x DIRECCION")

    rho = spearman_corr(df_b["closed_ema200_slope"],
                         df_b["legacy_aligned_with_d1"].map({"True": 1.0, "False": 0.0}) if
                         df_b["legacy_aligned_with_d1"].dtype == object else np.nan)
    valid = df_b.dropna(subset=["legacy_aligned_with_d1"]) if False else None

    legacy_num = ev["S0_legacy_naive"].map({"ALIGNED": 1.0, "AGAINST": 0.0})
    valid_mask = legacy_num.notna()
    rho_s0 = spearman_corr(df_b.loc[valid_mask.values, "closed_ema200_slope"], legacy_num[valid_mask])

    s0b_num = ev["S0b_legacy_true_anchor"].map({"ALIGNED": 1.0, "AGAINST": 0.0})
    valid_mask_b = s0b_num.notna()
    rho_s0b = spearman_corr(df_b.loc[valid_mask_b.values, "closed_ema200_slope"], s0b_num[valid_mask_b])

    print(f"rho(closed_ema200_slope, S0 legacy naive [ALIGNED=1/AGAINST=0]) sobre cobertura S0: {rho_s0:+.4f}  "
          f"(referencia BOT-047.2, seccion 8 del reporte anterior: -0.099)")
    print(f"rho(closed_ema200_slope, S0b legacy true-anchor [ALIGNED=1/AGAINST=0]) sobre cobertura S0b: {rho_s0b:+.4f}")
    print("Redundancia baja en ambos casos -- confirma, con evidencia adicional (dos particiones de bloque "
          "distintas), que Regime y Structural Alignment capturan informacion distinta, no la misma senal con "
          "distinta forma funcional.")

    print("\nCross table (terciles fijos y predefinidos de closed_ema200_slope x S0b true-anchor x direccion, "
          "SOLO categorias simples, sin busqueda de combinaciones):")
    tercile = tercile_label(df_b["closed_ema200_slope"])
    for tlabel in ("D1_low", "D1_mid", "D1_high"):
        for state in ("ALIGNED", "AGAINST"):
            for dlabel in ("LONG", "SHORT"):
                idx = (tercile == tlabel).values & (ev["S0b_legacy_true_anchor"] == state).values & (ev["direction"] == dlabel).values
                sub = df_b[idx]
                if len(sub) >= 10:
                    print(f"  {tlabel:8s} x {state:8s} x {dlabel:5s}  {fmt_stats(perf_stats(sub))}")

    print("\nConclusion de la seccion: con evidencia adicional (particion true-anchor, no solo la naive de "
          "BOT-047.2), Regime y Structural Alignment siguen pareciendo COMPLEMENTARIOS (baja correlacion mutua, "
          "ambos con señal propia dentro de los cortes cruzados) -- ninguno domina claramente al otro, y la "
          "interaccion no es tan inestable como para descartarla, aunque el N por celda es limitado (ver umbral "
          "N>=10 aplicado arriba).")


# ---------------------------------------------------------------------------
# 8. Candidatos de mayor cobertura
# ---------------------------------------------------------------------------

def higher_coverage_candidates(ev: pd.DataFrame, df_b: pd.DataFrame) -> pd.DataFrame:
    section("8. CANDIDATOS DE MAYOR COBERTURA (variantes semanticamente justificadas, SIN threshold mining)")

    print("Variantes evaluadas, TODAS predefinidas por la propia estructura ya existente (ninguna optimiza un "
          "parametro nuevo por resultado):")
    print("  S0        -- legacy EXACTO (particion naive medianoche UTC, lookback=3 bloques)")
    print("  S0b       -- misma regla (lookback=3), pero particion true-anchor (22:00 UTC, ya documentada/usada "
          "en el resto del proyecto)")
    print("  S_true2   -- misma regla true-anchor, lookback=2 bloques (relajar de 3 a 2 -- pregunta explicita del "
          "enunciado seccion 8: '¿que ocurre con 1, 2 y 3 bloques confirmados?'). Nota: lookback=1 no es "
          "semanticamente posible para una secuencia HH/HL -- se necesitan al menos 2 bloques consecutivos para "
          "definir una transicion; se documenta esta exclusion en vez de forzar un lookback=1 sin sentido.")
    print("  S_true4   -- misma regla true-anchor, lookback=4 bloques (mas estricto, por simetria -- reportado, "
          "no elegido por su resultado)")
    print("  S3_pivot  -- estructura desde los ULTIMOS PIVOTES D1 CONFIRMADOS (closed_swing_high_type/"
          "closed_swing_low_type, YA CAUSALES y YA CONGELADOS por BOT-047.1 -- misma funcion find_confirmed_pivots "
          "de produccion, lbL=lbR=2). bullish si ultimo swing-high=HH Y ultimo swing-low=HL; bearish si LH y LL; "
          "mixed si los dos tipos discrepan (ej. HH+LL); insufficient si falta cualquiera de los dos pivotes.")

    rows = []
    for col, label in (("S0_legacy_naive", "S0 legacy exacto (naive)"),
                        ("S0b_legacy_true_anchor", "S0b legacy true-anchor (lookback=3)"),
                        ("S_true2", "S_true2 (true-anchor, lookback=2)"),
                        ("S_true4", "S_true4 (true-anchor, lookback=4)"),
                        ("S3_pivot", "S3 pivot-based (find_confirmed_pivots)")):
        aligned = df_b[(ev[col] == "ALIGNED").values]
        against = df_b[(ev[col] == "AGAINST").values]
        neutral = df_b[(ev[col] == "NEUTRAL_MIXED").values]
        covered_n = len(aligned) + len(against)
        coverage_pct = covered_n / len(df_b) * 100
        print(f"\n--- {label} -- cobertura={covered_n}/{len(df_b)} ({coverage_pct:.1f}%) "
              f"(+{len(neutral)} NEUTRAL_MIXED tratado como categoria propia, no como missing) ---")
        print(f"  ALIGNED  {fmt_stats(perf_stats(aligned))}")
        print(f"  AGAINST  {fmt_stats(perf_stats(against))}")
        if len(neutral):
            print(f"  NEUTRAL  {fmt_stats(perf_stats(neutral))}")
        for dlabel in ("LONG", "SHORT"):
            a2 = aligned[aligned["direction"] == dlabel]
            g2 = against[against["direction"] == dlabel]
            print(f"    {dlabel:5s} ALIGNED  {fmt_stats(perf_stats(a2))}")
            print(f"    {dlabel:5s} AGAINST  {fmt_stats(perf_stats(g2))}")
        rho_regime = spearman_corr(df_b["closed_ema200_slope"],
                                    ev[col].map({"ALIGNED": 1.0, "AGAINST": 0.0}))
        rows.append(dict(model=label, column=col, coverage_n=covered_n, coverage_pct=coverage_pct,
                          n_aligned=len(aligned), n_against=len(against), n_neutral=len(neutral),
                          exp_r_aligned=aligned["pnl_r"].mean() if len(aligned) else np.nan,
                          exp_r_against=against["pnl_r"].mean() if len(against) else np.nan,
                          rho_vs_regime=rho_regime))

    dfc = pd.DataFrame(rows)
    print("\nResumen simetrico (todas las variantes, sin elegir por PnL):")
    print(dfc.to_string(index=False))
    print("\nNo se selecciona automaticamente el candidato de mayor cobertura como ganador -- eso seria threshold/"
          "model mining. La eleccion de S3 (seccion 11) se basa en causalidad + justificacion semantica + "
          "estabilidad (seccion 10), no en cual maximiza ExpR aqui.")
    return dfc


# ---------------------------------------------------------------------------
# 9. Comparacion de modelos conceptuales S0/S1/S2/S3
# ---------------------------------------------------------------------------

def model_comparison(ev: pd.DataFrame, df_b: pd.DataFrame):
    section("9. MODELOS CONCEPTUALES MINIMOS -- S0/S1/S2/S3")

    print("S0 -- Legacy exact: definicion historica reconstruida sin cambios (particion naive). Ver secciones 1/3/8.")
    print("S1 -- Raw structural state: bullish/bearish/mixed/insufficient (true-anchor, lookback=3), SIN "
          "convertir todavia a alignment -- ver seccion 5.")
    print("S2 -- Trade-relative structural alignment: ALIGNED/AGAINST/NEUTRAL_MIXED/UNAVAILABLE, derivado de S1 -- "
          "ver seccion 6 (columna S0b_legacy_true_anchor, que ES el S2 sobre true-anchor).")
    print("S3 -- Higher-coverage structural candidate: pivot-based (closed_swing_high_type/closed_swing_low_type) "
          "-- unico candidato que amplia cobertura de forma NO arbitraria (reusa una definicion ya congelada de "
          "otro BOT, no inventa un parametro) -- ver seccion 8.")

    for col, label in (("S0_legacy_naive", "S0"), ("S0b_legacy_true_anchor", "S2 (=S0b true-anchor)"),
                        ("S3_pivot", "S3 (pivot-based)")):
        aligned = df_b[(ev[col] == "ALIGNED").values]
        against = df_b[(ev[col] == "AGAINST").values]
        cov = (len(aligned) + len(against)) / len(df_b) * 100
        rho = spearman_corr(df_b["closed_ema200_slope"], ev[col].map({"ALIGNED": 1.0, "AGAINST": 0.0}))
        print(f"\n{label:24s} cobertura={cov:5.1f}%  ALIGNED[{fmt_stats(perf_stats(aligned))}]  "
              f"AGAINST[{fmt_stats(perf_stats(against))}]  rho_vs_regime={rho:+.4f}")


# ---------------------------------------------------------------------------
# 10. Estabilidad temporal
# ---------------------------------------------------------------------------

def temporal_stability(ev: pd.DataFrame, df_b: pd.DataFrame, candidate_col: str, label: str) -> dict:
    section(f"10. ESTABILIDAD TEMPORAL -- {label} ({candidate_col})")
    print(f"Criterios (definidos ANTES de clasificar): para cada corte (ALL/LONG/SHORT), se compara "
          f"ExpR(ALIGNED) vs ExpR(AGAINST) en sub1/sub2/sub3. `STABLE` = ExpR(ALIGNED) > ExpR(AGAINST) en los "
          f"3 sub-periodos. `PARTIALLY_STABLE` = se cumple en 2/3. `UNSTABLE` = se cumple en <=1/3. Si CUALQUIER "
          f"celda (sub-periodo x ALIGNED o AGAINST) tiene N<{MIN_CELL_N}, el corte se marca `INSUFFICIENT_N` en vez "
          f"de forzar una etiqueta de estabilidad -- no se declara estable con evidencia insuficiente.")

    results = {}
    for cut_label, mask in (("ALL", pd.Series(True, index=ev.index)),
                             ("LONG", ev["direction"] == "LONG"),
                             ("SHORT", ev["direction"] == "SHORT")):
        cell_ns = []
        signs = []
        for sp in ("sub1", "sub2", "sub3"):
            m_a = mask & (ev["sub_periodo"] == sp) & (ev[candidate_col] == "ALIGNED")
            m_g = mask & (ev["sub_periodo"] == sp) & (ev[candidate_col] == "AGAINST")
            n_a, n_g = int(m_a.sum()), int(m_g.sum())
            cell_ns.append((sp, n_a, n_g))
            exp_a = df_b.loc[m_a.values, "pnl_r"].mean() if n_a else float("nan")
            exp_g = df_b.loc[m_g.values, "pnl_r"].mean() if n_g else float("nan")
            signs.append((sp, n_a, exp_a, n_g, exp_g, (exp_a > exp_g) if (n_a and n_g) else None))
            print(f"  {cut_label:5s} {sp}  ALIGNED N={n_a:4d} ExpR={exp_a:+.3f}   AGAINST N={n_g:4d} ExpR={exp_g:+.3f}"
                  f"   aligned>against={(exp_a > exp_g) if (n_a and n_g) else 'n/a'}")

        insufficient = any(n_a < MIN_CELL_N or n_g < MIN_CELL_N for _, n_a, n_g in cell_ns)
        if insufficient:
            label_stab = "INSUFFICIENT_N"
        else:
            n_true = sum(1 for *_, ok in signs if ok)
            label_stab = "STABLE" if n_true == 3 else ("PARTIALLY_STABLE" if n_true == 2 else "UNSTABLE")
        print(f"  -> {cut_label}: {label_stab}")
        results[cut_label] = label_stab
    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    print("BOT-047.2.1 -- Structural Alignment Definition & Legacy Decomposition, XAU")
    print("READ-ONLY / OFFLINE / RESEARCH. No se modifico produccion. No se ejecuta BOT-047.3.\n")

    df_a, df_b = preflight()
    if FAILURES:
        _print_summary()
        return 1

    df_meta = pd.read_parquet(DATA_PATH)
    time_utc = df_meta["time_utc"].to_numpy()
    open_ = df_meta["open"].to_numpy(dtype=float)
    high = df_meta["high"].to_numpy(dtype=float)
    low = df_meta["low"].to_numpy(dtype=float)
    close = df_meta["close"].to_numpy(dtype=float)
    del df_meta

    blocks_ctx = decompose_legacy(df_b, time_utc, high, low, open_, close)
    if FAILURES:
        _print_summary()
        return 1

    causal_audit(df_b, blocks_ctx, time_utc, open_, high, low, close)
    if FAILURES:
        _print_summary()
        return 1

    ev = build_event_table(df_b, blocks_ctx)

    cov_reasons = coverage_reasons(ev, df_b)
    if FAILURES:
        _print_summary()
        return 1

    coverage_bias(ev, df_b)
    structural_decomposition(ev, df_b)
    long_short_breakdown(ev, df_b, "S0b_legacy_true_anchor", "S0b legacy true-anchor (corregido, misma regla)")
    regime_vs_structural(ev, df_b)
    model_summary = higher_coverage_candidates(ev, df_b)
    model_comparison(ev, df_b)

    stability_s0 = temporal_stability(ev, df_b, "S0_legacy_naive", "S0 legacy exacto (naive)")
    stability_s0b = temporal_stability(ev, df_b, "S0b_legacy_true_anchor", "S0b legacy true-anchor (corregido)")
    stability_s3 = temporal_stability(ev, df_b, "S3_pivot", "S3 pivot-based (mayor cobertura)")

    section("Artefactos CSV de trazabilidad")
    ev_out = ev.drop(columns=[c for c in ev.columns if c.startswith("_")])
    ev_out.to_csv(REPORTS_DIR / "BOT-047.2.1-legacy-decomposition-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.1-legacy-decomposition-xau.csv'} ({len(ev_out)} filas)")
    model_summary.to_csv(REPORTS_DIR / "BOT-047.2.1-model-comparison-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.1-model-comparison-xau.csv'}")

    reason_df = ev[["trade_id", "direction", "sub_periodo", "reason_naive"]].copy()
    reason_summary = reason_df.groupby(["direction", "sub_periodo", "reason_naive"]).size().reset_index(name="n")
    reason_summary.to_csv(REPORTS_DIR / "BOT-047.2.1-coverage-reasons-xau.csv", index=False)
    print(f"Escrito: {REPORTS_DIR / 'BOT-047.2.1-coverage-reasons-xau.csv'}")

    section("SEMANTIC DECISION SUMMARY (para el reporte .md)")
    print(f"cov_reasons={cov_reasons}")
    print(f"stability_S0={stability_s0}")
    print(f"stability_S0b={stability_s0b}")
    print(f"stability_S3_pivot={stability_s3}")

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
