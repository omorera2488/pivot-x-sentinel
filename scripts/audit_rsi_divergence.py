"""Auditoria tecnica, SOLO LECTURA, de la implementacion actual de
Divergencia RSI (strategy/scoring.py: rsi, find_confirmed_pivots,
divergence_score). NO modifica produccion, NO cambia parametros, NO corrige
nada -- unicamente ejecuta pruebas deterministas contra el codigo real y
imprime evidencia reproducible.

Uso:
    .venv/Scripts/python.exe scripts/audit_rsi_divergence.py > reports/RSI-DIVERGENCE-EVIDENCE.log

Cada seccion imprime un encabezado "=== N. titulo ===" que corresponde a la
seccion homonima de reports/AUDIT-RSI-DIVERGENCE.md, y termina cada
verificacion con PASS / FAIL / WARN + una linea de evidencia numerica.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from strategy.scoring import (
    DIVERGENCE_FRESH_BARS, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT,
    DIVERGENCE_RANGE_MAX, DIVERGENCE_RANGE_MIN, DIVERGENCE_RESOLUTION_CONFLICT,
    DIVERGENCE_RESOLUTION_MOST_RECENT, DIVERGENCE_STATE_BEARISH, DIVERGENCE_STATE_BULLISH,
    DIVERGENCE_STATE_CONFLICT, RSI_PERIOD,
    DivergenceCandidate, Pivot, _most_recent_fresh, _prior_in_range, divergence_detail,
    divergence_score, find_confirmed_pivots, resolve_divergence, rsi,
)

FAILURES: list[str] = []
WARNINGS: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def warn(label: str, evidence: str) -> None:
    print(f"[WARN] {label}\n       {evidence}")
    WARNINGS.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# 2/3. RSI Wilder(14): parametros + verificacion numerica independiente
# ---------------------------------------------------------------------------

def independent_wilder_rsi(close: np.ndarray, period: int) -> np.ndarray:
    """Segunda implementacion, escrita de forma distinta (acumuladores
    explicitos con listas + validacion NaN separada) para cruzar contra
    strategy.scoring.rsi sin reusar una sola linea de esa funcion."""
    n = len(close)
    out = [float("nan")] * n
    if n < period + 1:
        return np.array(out)
    changes = [close[i] - close[i - 1] for i in range(1, n)]
    up = [max(c, 0.0) for c in changes]
    dn = [max(-c, 0.0) for c in changes]

    seed_up = sum(up[:period]) / period
    seed_dn = sum(dn[:period]) / period
    ru, rd = seed_up, seed_dn
    if rd == 0:
        out[period] = 100.0 if ru > 0 else 50.0
    else:
        out[period] = 100.0 - 100.0 / (1.0 + ru / rd)

    for i in range(period + 1, n):
        u, d = up[i - 1], dn[i - 1]
        ru = (ru * (period - 1) + u) / period
        rd = (rd * (period - 1) + d) / period
        if rd == 0:
            out[i] = 100.0 if ru > 0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + ru / rd)
    return np.array(out)


def audit_rsi_wilder() -> None:
    section("3. RSI Wilder(14) -- parametros y verificacion numerica")

    check("RSI_PERIOD constante == 14", RSI_PERIOD == 14, f"RSI_PERIOD={RSI_PERIOD}")

    rng = np.random.default_rng(20260919)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, size=500))
    a = rsi(close, period=14)
    b = independent_wilder_rsi(close, period=14)
    both_nan = np.isnan(a) & np.isnan(b)
    diff = np.nanmax(np.abs(a[~both_nan] - b[~both_nan]))
    same_nan_mask = np.array_equal(np.isnan(a), np.isnan(b))
    check("scoring.rsi coincide con segunda implementacion Wilder independiente (500 barras, ruido gaussiano)",
          same_nan_mask and diff < 1e-9,
          f"mascara NaN identica={same_nan_mask}, diff maxima={diff:.3e}")

    # Fuente: close (no high/low/hl2)
    import inspect
    src = inspect.getsource(rsi)
    check("rsi() usa 'close' como unica fuente (no high/low/hlc)",
          "close" in inspect.signature(rsi).parameters,
          f"firma: {inspect.signature(rsi)}")

    # Historial insuficiente -> NaN total
    short = np.array([1.0, 2.0, 3.0])
    out_short = rsi(short, period=14)
    check("n < period+1 -> array NaN completo (sin excepcion)",
          np.isnan(out_short).all() and len(out_short) == len(short),
          f"len={len(short)}, periodo=14, salida={out_short}")

    # Exactamente period+1 barras -> un unico valor valido, en out[period]
    exact = np.array([1.0, 2.0, 1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 3.0, 4.0, 5.0, 4.0, 5.0, 6.0, 5.0])
    out_exact = rsi(exact, period=14)
    check("n == period+1 -> exactamente 1 valor no-NaN, en indice=period",
          np.isnan(out_exact[:14]).all() and not math.isnan(out_exact[14]) and len(out_exact) == 15,
          f"len={len(exact)}, out[13] nan={math.isnan(out_exact[13])}, out[14]={out_exact[14]:.6f}")

    # Movimiento monotono ascendente -> avg_loss=0 -> RSI=100 (rama especial)
    up_only = np.arange(1.0, 40.0)
    out_up = rsi(up_only, period=14)
    check("subida monotona estricta -> RSI=100.0 exacto (avg_loss=0, rama especial)",
          math.isclose(out_up[-1], 100.0, abs_tol=1e-9),
          f"close monotono ascendente, rsi[-1]={out_up[-1]}")

    down_only = np.arange(40.0, 1.0, -1.0)
    out_down = rsi(down_only, period=14)
    check("bajada monotona estricta -> RSI=0.0 exacto (avg_gain=0, formula normal, no rama especial)",
          math.isclose(out_down[-1], 0.0, abs_tol=1e-9),
          f"close monotono descendente, rsi[-1]={out_down[-1]}")

    # Precio perfectamente plano -> avg_gain=avg_loss=0 -> RSI=50 (rama especial, decision de diseno)
    flat = np.full(30, 100.0)
    out_flat = rsi(flat, period=14)
    warn("precio perfectamente plano -> RSI=50.0 por rama especial (avg_gain=0 y avg_loss=0 -> 0/0 matematicamente indefinido)",
         f"rsi[-1]={out_flat[-1]!r} -- NO se pudo confirmar contra TradingView en vivo en este entorno (sin acceso). "
         f"Es una decision de diseno razonable (evita NaN) pero no verificada bit a bit contra ta.rsi de Pine para este caso degenerado.")

    print(f"\nResumen RSI Wilder: {len([f for f in FAILURES if 'RSI' in f or 'rsi' in f.lower()])} fallas, "
          f"{len(WARNINGS)} advertencias hasta aqui.")


# ---------------------------------------------------------------------------
# 4. Pivotes RSI 5/5 -- semantica, empates, bar vs confirmed_bar
# ---------------------------------------------------------------------------

def audit_pivots() -> None:
    section("4. Pivotes RSI 5/5 -- semantica y empates")

    check("DIVERGENCE_LB_LEFT == 5", DIVERGENCE_LB_LEFT == 5, f"valor={DIVERGENCE_LB_LEFT}")
    check("DIVERGENCE_LB_RIGHT == 5", DIVERGENCE_LB_RIGHT == 5, f"valor={DIVERGENCE_LB_RIGHT}")

    # bar vs confirmed_bar exacto
    series = np.array([0, 1, 2, 5, 2, 1, 0], dtype=float)
    highs, lows = find_confirmed_pivots(series, lbL=2, lbR=2)
    check("pivot_bar y confirmed_bar = bar+lbR se distinguen explicitamente",
          len(highs) == 1 and highs[0].bar == 3 and highs[0].confirmed_bar == 5,
          f"highs={highs}")

    # Empate exacto en el maximo del ventana -> el codigo NO marca pivote (uniqueness estricta)
    tie = np.array([0, 1, 5, 5, 1, 0], dtype=float)  # dos valores iguales al maximo, adyacentes
    highs_tie, _ = find_confirmed_pivots(tie, lbL=2, lbR=2)
    warn("empate exacto en el maximo de la ventana -> NINGUN pivote emitido (uniqueness estricta con (window==v).sum()==1)",
         f"series={tie.tolist()}, highs detectados={highs_tie} -- "
         f"la semantica exacta de empates de ta.pivothigh/pivotlow de Pine NO se pudo verificar en vivo en este "
         f"entorno (sin acceso a TradingView); si el indicador real de Pine acepta empates (>=/<= asimetrico en vez "
         f"de estrictamente unico), esta implementacion perderia pivotes validos en datos con RSI redondeado/repetido.")

    # NaN dentro de la ventana -> se salta sin excepcion
    with_nan = np.array([0, 1, float("nan"), 5, 2, 1, 0], dtype=float)
    highs_nan, lows_nan = find_confirmed_pivots(with_nan, lbL=2, lbR=2)
    check("NaN dentro de la ventana de un candidato -> se descarta ese candidato sin excepcion",
          len(highs_nan) == 0,
          f"series con NaN en indice 2: highs={highs_nan}, lows={lows_nan}")

    # borde exacto: pivote justo en el limite derecho del array (debe incluirse) y uno mas alla (no puede)
    edge = np.concatenate([np.zeros(5), [9.0], np.zeros(5)])  # pivote candidato en indice 5, lbL=lbR=5
    highs_edge, _ = find_confirmed_pivots(edge, lbL=5, lbR=5)
    check("pivote exactamente en el borde derecho valido (n-lbR-1) se detecta",
          len(highs_edge) == 1 and highs_edge[0].bar == 5 and highs_edge[0].confirmed_bar == 10,
          f"len(series)={len(edge)}, highs={highs_edge}")

    edge_short = edge[:-1]  # un elemento menos -> el candidato ya no tiene los 5 bares derechos completos
    highs_edge_short, _ = find_confirmed_pivots(edge_short, lbL=5, lbR=5)
    check("el mismo pivote SIN el ultimo bar derecho disponible -> no se detecta (loop bound n-lbR correcto, sin slice truncado silencioso)",
          len(highs_edge_short) == 0,
          f"len(series)={len(edge_short)}, highs={highs_edge_short}")


# ---------------------------------------------------------------------------
# 5. Causalidad estricta: un pivote en bar=100 con lbR=5 no puede conocerse
#    antes de current_bar=105
# ---------------------------------------------------------------------------

def audit_causality() -> None:
    section("5. Auditoria critica de causalidad")

    n = 160
    rsi_full = np.full(n, 50.0)
    rsi_full[60] = 20.0    # pivote RSI previo (mas bajo)
    rsi_full[100] = 30.0   # pivote RSI reciente, minimo aislado y estricto en ventana [95,105], MAS ALTO que el previo (HL)
    close_full = np.full(n, 100.0)
    close_full[60] = 95.0
    close_full[100] = 90.0  # precio: minimo en 100 (90) MAS BAJO que el de 60 (95) -> LL de precio + HL de RSI = divergencia alcista regular

    print("Timeline causal (pivot_bar=100, lbR=5, confirmation_bar=105):")
    for t in range(96, 108):
        rsi_slice = rsi_full[:t + 1]
        highs, lows = find_confirmed_pivots(rsi_slice, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
        bar100_known = any(p.bar == 100 for p in lows)
        estado = "ACTIVA/CONOCIDA" if bar100_known else "NO CONOCIDA"
        print(f"  t={t:3d}  len(slice)={len(rsi_slice):3d}  pivot(bar=100) conocido={bar100_known}  -> {estado}")

    known_before = any(
        any(p.bar == 100 for p in find_confirmed_pivots(rsi_full[:t + 1], DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)[1])
        for t in range(100, 105)
    )
    check("pivote en bar=100 (lbR=5) NO es conocido/utilizable en current_bar=100..104",
          not known_before,
          "verificado para t=100,101,102,103,104: pivote ausente de la lista en los 5 casos")

    known_at_105 = any(p.bar == 100 for p in find_confirmed_pivots(rsi_full[:106], DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)[1])
    check("pivote en bar=100 (lbR=5) SI es conocido/utilizable exactamente en current_bar=105",
          known_at_105,
          f"find_confirmed_pivots(rsi_full[:106])[1] incluye bar=100: {known_at_105}")

    # Ahora a nivel de divergence_score completo (no solo find_confirmed_pivots)
    print("\nDivergence score usando el pivote de bar=100 como confirmado en distintos current_bar:")
    scores = {}
    for t in [100, 101, 102, 103, 104, 105, 106, 114, 115, 116]:
        s, r = divergence_score(+1, close_full, rsi_full, t)
        scores[t] = (s, r)
        print(f"  current_bar={t:3d}  score={s:+d}  reason={r!r}")

    check("divergence_score(current_bar<105) nunca reporta la divergencia bullish del par (60,100) -- todas dan 0",
          all(scores[t][0] == 0 for t in [100, 101, 102, 103, 104]),
          f"scores 100..104 = {[scores[t][0] for t in [100,101,102,103,104]]}")
    check("divergence_score(current_bar=105) SI reporta la divergencia (recien confirmada)",
          scores[105][0] == 1,
          f"score en t=105 = {scores[105]}")
    check("divergence_score sigue ACTIVA hasta current_bar=115 (confirmed_bar=105 + fresh_bars=10)",
          scores[114][0] == 1 and scores[115][0] == 1,
          f"score t=114={scores[114][0]}, t=115={scores[115][0]}")
    check("divergence_score EXPIRA en current_bar=116 (edad=11 > fresh_bars=10)",
          scores[116][0] == 0,
          f"score t=116={scores[116]}")


# ---------------------------------------------------------------------------
# 6. Asociacion precio <-> pivote RSI: debe usar close[pivot_bar], no
#    close[confirmed_bar] ni high/low
# ---------------------------------------------------------------------------

def audit_price_pivot_association() -> None:
    section("6. Asociacion precio <-> pivote RSI")

    n = 40
    rsi_vals = np.full(n, 50.0)
    rsi_vals[10] = 20.0   # pivote bajo previo
    rsi_vals[20] = 30.0   # pivote bajo reciente, RSI mas ALTO -> condicion alcista de RSI OK

    close = np.full(n, 100.0)
    # Sentinela: si el codigo usara por error el precio de confirmed_bar (20+5=25) en vez de pivot_bar (20),
    # el resultado cambiaria de signo. Se fuerza que SOLO la lectura en pivot_bar (10 y 20) sea consistente
    # con una divergencia alcista valida; confirmed_bar (15 y 25) tiene el patron CONTRARIO.
    close[10] = 100.0   # pivot_bar del pivote previo -> precio "alto"
    close[15] = 80.0    # confirmed_bar del pivote previo -> precio "bajo" (patron opuesto si se usara por error)
    close[20] = 90.0    # pivot_bar del pivote reciente -> mas BAJO que close[10] (100) => cumple "minimo mas bajo"
    close[25] = 110.0   # confirmed_bar del pivote reciente -> mas ALTO (patron opuesto si se usara por error)

    score, reason = divergence_score(+1, close, rsi_vals, current_bar=25, lbL=5, lbR=5,
                                      range_min=5, range_max=60, fresh_bars=10)
    check("divergence_score usa close[pivot_bar] (10 y 20), NO close[confirmed_bar] (15 y 25)",
          score == 1 and "alcista" in reason,
          f"close[10]={close[10]}, close[20]={close[20]} (cumple LL), "
          f"close[15]={close[15]}, close[25]={close[25]} (patron opuesto) -> score={score}, reason={reason!r}")

    import inspect
    from strategy.scoring import _bearish_candidate, _bullish_candidate
    src = inspect.getsource(_bullish_candidate) + inspect.getsource(_bearish_candidate)
    check("la deteccion de candidatos (bullish/bearish) referencia unicamente el array 'close' "
          "(no 'high'/'low') para el precio del pivote -- logica sin cambios tras el fix, solo se movio "
          "de divergence_score() a _bullish_candidate()/_bearish_candidate()",
          "high[" not in src and "low[" not in src and "close[" in src,
          "grep del cuerpo de ambas funciones: no aparecen indexaciones high[..]/low[..], solo close[..]")
    warn("uso de 'close' para ambos lados de la divergencia (bullish y bearish)",
         "El indicador publico de referencia 'Divergence Indicator' de TradingView mas difundido (y varias "
         "reimplementaciones conocidas) compara 'low' para divergencias alcistas y 'high' para bajistas, no 'close' "
         "en ambos casos. El propio docstring de strategy/scoring.py (lineas 43-46) ya advierte que estos son "
         "'defaults publicos' y NO los parametros reales del indicador del usuario (todavia no provistos). "
         "No se pudo confirmar en vivo contra TradingView en este entorno -- queda pendiente de verificacion "
         "cuando el usuario provea su configuracion real del indicador.")


# ---------------------------------------------------------------------------
# 7. Separacion 5-60: boundary tests directos sobre _prior_in_range +
#    hallazgo geometrico (min separation alcanzable con lbL=lbR=5)
# ---------------------------------------------------------------------------

def audit_separation() -> None:
    section("7. Separacion entre pivotes (range_min=5, range_max=60)")

    check("DIVERGENCE_RANGE_MIN == 5", DIVERGENCE_RANGE_MIN == 5, f"valor={DIVERGENCE_RANGE_MIN}")
    check("DIVERGENCE_RANGE_MAX == 60", DIVERGENCE_RANGE_MAX == 60, f"valor={DIVERGENCE_RANGE_MAX}")

    # --- boundary puro sobre _prior_in_range, con Pivots sinteticos (sin geometria de find_confirmed_pivots) ---
    latest = Pivot(bar=100, confirmed_bar=105, value=1.0)
    for gap, expect_accept in [(4, False), (5, True), (6, True), (59, True), (60, True), (61, False)]:
        prior = Pivot(bar=100 - gap, confirmed_bar=100 - gap + 5, value=2.0)
        result = _prior_in_range([prior], latest, DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX)
        accepted = result is not None
        check(f"_prior_in_range: separacion={gap} barras -> {'aceptado' if expect_accept else 'rechazado'}",
              accepted == expect_accept,
              f"gap={gap}, range=[{DIVERGENCE_RANGE_MIN},{DIVERGENCE_RANGE_MAX}], resultado={'aceptado' if accepted else 'rechazado'}")

    # --- hallazgo geometrico: con lbL=lbR=5 (produccion), ¿puede existir un par de pivotes REALES a distancia < 6? ---
    print("\nHallazgo geometrico: separacion minima REAL alcanzable entre dos pivotes del mismo tipo con lbL=lbR=5:")
    achievable = {}
    for gap in [3, 4, 5, 6, 7, 8]:
        n = 200
        series = np.full(n, 50.0)
        base_bar = 100
        series[base_bar] = 10.0
        series[base_bar + gap] = 5.0  # el segundo, mas bajo, para intentar sobrevivir ambas ventanas
        _, lows = find_confirmed_pivots(series, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
        bars_found = sorted(p.bar for p in lows)
        both_survive = base_bar in bars_found and (base_bar + gap) in bars_found
        achievable[gap] = both_survive
        print(f"  gap={gap}: pivotes detectados en {bars_found} -> ambos sobreviven={both_survive}")

    check("con lbL=lbR=5, NINGUN gap < 6 produce dos pivotes independientes reales "
          "(el mas cercano invalida la unicidad del otro dentro de su propia ventana)",
          all(not achievable[g] for g in [3, 4, 5]),
          f"achievable={achievable}")
    check("con lbL=lbR=5, gap=6 (o mas) SI puede producir dos pivotes independientes",
          achievable[6],
          f"achievable[6]={achievable[6]}")

    if all(not achievable[g] for g in [3, 4, 5]) and achievable[6]:
        warn("range_min=5 es geometricamente INALCANZABLE (dead code en la practica) con lbL=lbR=5",
             "Dado que ningun par de pivotes reales del mismo tipo puede estar a menos de 6 barras de distancia "
             "cuando lbL=lbR=5 (uno invalida al otro por unicidad estricta dentro de la ventana del otro), el "
             "chequeo 'range_min<=separacion' NUNCA rechaza un par real en la configuracion de produccion actual: "
             "la separacion minima efectiva es 6, no 5. El parametro DIVERGENCE_RANGE_MIN=5 esta documentado como "
             "'5-60' pero en la practica equivale a '6-60'. No es un bug de calculo (la formula es correcta), pero "
             "es una discrepancia entre la especificacion documentada (5-60) y el comportamiento real posible.")


# ---------------------------------------------------------------------------
# 8. Vigencia (freshness) -- timeline explicita
# ---------------------------------------------------------------------------

def audit_validity_timeline() -> None:
    section("8. Vigencia de la divergencia (DIVERGENCE_FRESH_BARS=10)")

    check("DIVERGENCE_FRESH_BARS == 10", DIVERGENCE_FRESH_BARS == 10, f"valor={DIVERGENCE_FRESH_BARS}")

    pivot = Pivot(bar=100, confirmed_bar=105, value=1.0)
    print("Timeline (pivot_bar=100, confirmation_bar=105, fresh_bars=10):")
    print(f"{'bar':>5} {'estado segun _most_recent_fresh':<40} {'edad (current-confirmed)'}")
    rows = []
    for t in range(98, 118):
        found = _most_recent_fresh([pivot], t, DIVERGENCE_FRESH_BARS)
        if t < pivot.confirmed_bar:
            estado = "NO CONOCIDA"
        elif found is not None:
            estado = "ACTIVA"
        else:
            estado = "EXPIRADA"
        edad = t - pivot.confirmed_bar
        rows.append((t, estado, edad))
        print(f"{t:>5} {estado:<40} {edad}")

    no_conocida = all(estado == "NO CONOCIDA" for t, estado, _ in rows if t < 105)
    activa = all(estado == "ACTIVA" for t, estado, _ in rows if 105 <= t <= 115)
    expirada = all(estado == "EXPIRADA" for t, estado, _ in rows if t >= 116)
    check("NO CONOCIDA para current_bar < confirmed_bar (105)", no_conocida, f"filas t<105: {[r for r in rows if r[0]<105]}")
    check("ACTIVA para confirmed_bar <= current_bar <= confirmed_bar+fresh_bars (105..115, 11 barras)", activa,
          f"filas 105..115: {[r for r in rows if 105<=r[0]<=115]}")
    check("EXPIRADA para current_bar > confirmed_bar+fresh_bars (>=116)", expirada, f"filas t>=116: {[r for r in rows if r[0]>=116]}")

    warn("'vigencia maxima 10 barras' se traduce en 11 barras vigentes en total (confirmed_bar + 0..10 de edad)",
         "current_bar - confirmed_bar <= fresh_bars(=10) incluye la propia barra de confirmacion (edad=0) hasta "
         "edad=10 inclusive -- son 11 barras con la divergencia activa, no 10. Es una ambiguedad de nomenclatura "
         "('10 barras de vigencia' vs '10 barras de margen tras la confirmacion'), no necesariamente un bug, pero "
         "debe confirmarse cual de las dos interpretaciones es la intencion real de diseno.")


# ---------------------------------------------------------------------------
# 9. Evento vs estado vigente
# ---------------------------------------------------------------------------

def audit_event_vs_state() -> None:
    section("9. Divergencia como evento vs estado vigente")

    n = 160
    rsi_full = np.full(n, 50.0)
    rsi_full[60], rsi_full[100] = 20.0, 30.0
    close_full = np.full(n, 100.0)
    close_full[60], close_full[100] = 95.0, 90.0

    reasons = {}
    for t in range(105, 116):
        s, r = divergence_score(+1, close_full, rsi_full, t)
        reasons[t] = (s, r)

    same_reason = len({r for _, r in reasons.values()}) == 1
    check("el texto de 'reason' es IDENTICO en cada barra mientras la divergencia sigue activa "
          "(no se distingue 'recien detectada' vs 'ya vigente hace N barras')",
          same_reason,
          f"reasons unicos observados entre t=105..115: {set(r for _, r in reasons.values())}")

    import dataclasses
    from strategy.scoring import EntryScore
    fields = {f.name for f in dataclasses.fields(EntryScore)}
    traceability_fields = {
        "divergencia_resolved_state", "divergencia_resolution",
        "divergencia_bullish_active", "divergencia_bullish_pivot_bar",
        "divergencia_bullish_confirmation_bar", "divergencia_bullish_age",
        "divergencia_bearish_active", "divergencia_bearish_pivot_bar",
        "divergencia_bearish_confirmation_bar", "divergencia_bearish_age",
    }
    check("RESUELTO (fix reports/AUDIT-RSI-DIVERGENCE.md hallazgo #5): EntryScore ahora expone "
          "pivot_bar/confirmation_bar/age de cada lado (bullish/bearish) + resolved_state/resolution",
          traceability_fields <= fields,
          f"campos de EntryScore relacionados a divergencia: {sorted(f for f in fields if 'diverg' in f)}")

    detail = divergence_detail(+1, close_full, rsi_full, 108)
    check("la trazabilidad permite reconstruir pivot_bar/confirmation_bar/age sin recorrer de nuevo los datos de mercado",
          detail.bullish is not None and detail.bullish.pivot_bar == 100 and detail.bullish.confirmation_bar == 105
          and detail.bullish.age == 3,
          f"detail.bullish={detail.bullish}")

    warn("sigue sin haber estado PERSISTIDO de 'detected_at' entre llamadas -- cada llamada recalcula desde cero",
         "divergence_detail()/divergence_score() siguen siendo funciones puras sin memoria entre llamadas (se "
         "mantuvo intencionalmente esa propiedad, ver reports/AUDIT-RSI-DIVERGENCE.md seccion de recomendaciones "
         "#6). Ya no es un gap de trazabilidad -- score_entry() ahora vuelca pivot_bar/confirmation_bar/age de cada "
         "candidato a EntryScore en cada llamada -- pero sigue sin haber una unica fila 'nace aqui' persistida: si "
         "una divergencia dura 5 barras, se recalculan y registran 5 veces (una por score_entry) con la misma edad "
         "creciente, no una sola vez con un evento de nacimiento.")


# ---------------------------------------------------------------------------
# 10. LONG / SHORT
# ---------------------------------------------------------------------------

def audit_long_short() -> None:
    section("10. LONG / SHORT")

    n = 40
    rsi_bull = np.full(n, 50.0)
    rsi_bull[10], rsi_bull[20] = 20.0, 30.0
    close_bull = np.full(n, 100.0)
    close_bull[10], close_bull[20] = 100.0, 90.0  # LL en precio, HL en RSI -> alcista

    rsi_bear = np.full(n, 50.0)
    rsi_bear[10], rsi_bear[20] = 80.0, 70.0
    close_bear = np.full(n, 100.0)
    close_bear[10], close_bear[20] = 100.0, 110.0  # HH en precio, LH en RSI -> bajista

    kwargs = dict(lbL=5, lbR=5, range_min=5, range_max=60, fresh_bars=10)
    matrix = {
        ("bullish", +1): divergence_score(+1, close_bull, rsi_bull, 25, **kwargs),
        ("bullish", -1): divergence_score(-1, close_bull, rsi_bull, 25, **kwargs),
        ("bearish", +1): divergence_score(+1, close_bear, rsi_bear, 25, **kwargs),
        ("bearish", -1): divergence_score(-1, close_bear, rsi_bear, 25, **kwargs),
    }
    print("Tabla LONG/SHORT real observada:")
    for (tipo, direction), (score, reason) in matrix.items():
        print(f"  {tipo:8s} direction={direction:+d} -> score={score:+d}  ({reason})")

    check("Bullish + LONG(+1) = +1", matrix[("bullish", +1)][0] == 1, str(matrix[("bullish", +1)]))
    check("Bullish + SHORT(-1) = -1", matrix[("bullish", -1)][0] == -1, str(matrix[("bullish", -1)]))
    check("Bearish + SHORT(-1) = +1", matrix[("bearish", -1)][0] == 1, str(matrix[("bearish", -1)]))
    check("Bearish + LONG(+1) = -1", matrix[("bearish", +1)][0] == -1, str(matrix[("bearish", +1)]))


# ---------------------------------------------------------------------------
# 11. Divergencias simultaneas / opuestas -- resolucion explicita por
#     confirmation_bar (fix reports/AUDIT-RSI-DIVERGENCE.md hallazgo #1)
# ---------------------------------------------------------------------------

def audit_simultaneous_divergences() -> None:
    section("11. Divergencias simultaneas/opuestas -- resolucion por confirmation_bar")

    n = 160
    rsi_vals = np.full(n, 50.0)
    # bullish: lows en 60 (RSI=20) y 100 (RSI=30, mas alto) -> confirmed_bar=105
    rsi_vals[60] = 20.0
    rsi_vals[100] = 30.0
    # bearish: highs en 65 (RSI=80) y 101 (RSI=70, mas bajo) -> confirmed_bar=106, MAS RECIENTE que la bullish
    rsi_vals[65] = 80.0
    rsi_vals[101] = 70.0

    close = np.full(n, 100.0)
    close[60] = 95.0
    close[100] = 90.0   # LL en precio (90<95), HL en RSI (30>20) -> alcista OK
    close[65] = 100.0
    close[101] = 110.0  # HH en precio (110>100), LH en RSI (70<80) -> bajista OK

    current_bar = 106  # ambos pivotes confirmados y frescos (bullish edad=1, bearish edad=0)
    detail_long = divergence_detail(+1, close, rsi_vals, current_bar)
    score_long, reason_long = divergence_score(+1, close, rsi_vals, current_bar)
    score_short, reason_short = divergence_score(-1, close, rsi_vals, current_bar)
    print(f"current_bar={current_bar}: ambas divergencias vigentes "
          f"(bullish confirmation_bar={detail_long.bullish.confirmation_bar}, "
          f"bearish confirmation_bar={detail_long.bearish.confirmation_bar}, bearish es la MAS RECIENTE)")
    print(f"  resolved_state={detail_long.resolved_state}  resolution={detail_long.resolution}")
    print(f"  direction=+1 (LONG)  -> score={score_long:+d}  reason={reason_long!r}")
    print(f"  direction=-1 (SHORT) -> score={score_short:+d}  reason={reason_short!r}")

    check("RESUELTO (fix hallazgo #1): con bullish Y bearish vigentes, gana la de confirmation_bar MAS RECIENTE "
          "(bearish=106 > bullish=105), ya no hay prioridad fija a favor de bullish",
          detail_long.resolved_state == DIVERGENCE_STATE_BEARISH and detail_long.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT,
          f"resolved_state={detail_long.resolved_state}, resolution={detail_long.resolution}")

    check("regresion del bug original: SHORT ahora da +1 (antes del fix daba -1, ver reports/AUDIT-RSI-DIVERGENCE.md hallazgo #1)",
          score_short == 1 and "bajista" in reason_short and "a favor" in reason_short,
          f"score_short={score_short:+d} reason_short={reason_short!r}")
    check("LONG da -1 (bajista en contra) -- consistente con que la bearish, mas reciente, es la que manda",
          score_long == -1 and "bajista" in reason_long,
          f"score_long={score_long:+d} reason_long={reason_long!r}")

    # --- caso simetrico: bullish mas reciente -> debe ganar bullish ---
    rsi_vals2 = np.full(n, 50.0)
    close2 = np.full(n, 100.0)
    rsi_vals2[60], close2[60] = 20.0, 95.0
    rsi_vals2[101], close2[101] = 30.0, 90.0   # bullish, confirmation_bar=106 -- MAS RECIENTE
    rsi_vals2[65], close2[65] = 80.0, 100.0
    rsi_vals2[100], close2[100] = 70.0, 110.0  # bearish, confirmation_bar=105
    detail2 = divergence_detail(+1, close2, rsi_vals2, current_bar)
    check("simetrico: con bullish MAS reciente (106>105), ahora gana bullish (antes tambien ganaba bullish, pero por "
          "casualidad de orden de codigo -- ahora es por confirmation_bar, se verifica explicitamente)",
          detail2.resolved_state == DIVERGENCE_STATE_BULLISH and detail2.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT,
          f"resolved_state={detail2.resolved_state}, resolution={detail2.resolution}, "
          f"bullish.confirmation_bar={detail2.bullish.confirmation_bar}, bearish.confirmation_bar={detail2.bearish.confirmation_bar}")

    # --- CONFLICT: mismo confirmation_bar (candidatos sinteticos, ver nota en strategy/test_scoring.py) ---
    bullish_tie = DivergenceCandidate(kind="bullish", pivot_bar=100, confirmation_bar=105, age=0,
                                       prior_pivot_bar=60, prior_confirmation_bar=65,
                                       latest_rsi=30.0, prior_rsi=20.0, latest_price=90.0, prior_price=95.0)
    bearish_tie = DivergenceCandidate(kind="bearish", pivot_bar=100, confirmation_bar=105, age=0,
                                       prior_pivot_bar=61, prior_confirmation_bar=66,
                                       latest_rsi=70.0, prior_rsi=80.0, latest_price=110.0, prior_price=100.0)
    res_conflict_long = resolve_divergence(+1, bullish_tie, bearish_tie)
    res_conflict_short = resolve_divergence(-1, bullish_tie, bearish_tie)
    print(f"\nCONFLICT (mismo confirmation_bar=105 para ambas): "
          f"LONG -> score={res_conflict_long.score:+d} reason={res_conflict_long.reason!r}; "
          f"SHORT -> score={res_conflict_short.score:+d} reason={res_conflict_short.reason!r}")
    check("empate exacto de confirmation_bar -> CONFLICT, score=0 (NO es lo mismo que NONE)",
          res_conflict_long.resolved_state == DIVERGENCE_STATE_CONFLICT
          and res_conflict_short.resolved_state == DIVERGENCE_STATE_CONFLICT
          and res_conflict_long.resolution == DIVERGENCE_RESOLUTION_CONFLICT
          and res_conflict_long.score == 0 and res_conflict_short.score == 0
          and "conflicto" in res_conflict_long.reason,
          f"long={res_conflict_long}, short={res_conflict_short}")
    check("CONFLICT se distingue textualmente de NONE ('sin divergencia vigente')",
          res_conflict_long.reason != "sin divergencia vigente",
          f"reason CONFLICT={res_conflict_long.reason!r} (distinto de 'sin divergencia vigente')")


# ---------------------------------------------------------------------------
# 12. Casos borde
# ---------------------------------------------------------------------------

def audit_edge_cases() -> None:
    section("12. Casos borde")

    # historial insuficiente para RSI
    close_tiny = np.array([1.0, 2.0, 3.0])
    r = rsi(close_tiny, period=14)
    check("historial insuficiente para RSI -> todo NaN, sin excepcion", np.isnan(r).all(), f"len=3, periodo=14")

    # historial suficiente para RSI pero no para pivotes (necesita lbL+lbR+1 valores RSI validos)
    n_partial = 14 + 1 + 5  # un solo valor de RSI valido mas alla del warmup, insuficiente para lbL=lbR=5
    close_partial = 100.0 + np.cumsum(np.sin(np.arange(n_partial)))
    rsi_partial = rsi(close_partial, period=14)
    highs_p, lows_p = find_confirmed_pivots(rsi_partial, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
    check("RSI valido pero insuficiente para completar una ventana de pivote 5/5 -> sin pivotes, sin excepcion",
          highs_p == [] and lows_p == [],
          f"n={n_partial}, valores RSI no-NaN={np.sum(~np.isnan(rsi_partial))}, highs={highs_p}, lows={lows_p}")

    # primer pivote sin pivote anterior
    only_one = Pivot(bar=100, confirmed_bar=105, value=1.0)
    prior = _prior_in_range([], only_one, DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX)
    check("primer pivote sin pivote previo -> _prior_in_range devuelve None (sin excepcion)", prior is None, "lista vacia de pivotes previos")

    n = 200
    rsi_vals = np.full(n, 50.0)
    close = np.full(n, 100.0)

    # precios iguales (close[latest]==close[prior]) -> NO cumple estricta "<" -> sin divergencia
    rsi_vals[60], rsi_vals[100] = 20.0, 30.0
    close[60], close[100] = 95.0, 95.0  # igual precio -> no es "mas bajo estricto"
    s_eqprice, r_eqprice = divergence_score(+1, close, rsi_vals, 105)
    check("precios EXACTAMENTE iguales en los dos pivotes -> sin divergencia (comparacion estricta '<')",
          s_eqprice == 0, f"close[60]=close[100]=95.0 -> score={s_eqprice} ({r_eqprice})")

    # RSI iguales -> NO cumple estricta ">" -> sin divergencia
    rsi_vals2 = np.full(n, 50.0)
    close2 = np.full(n, 100.0)
    rsi_vals2[60], rsi_vals2[100] = 20.0, 20.0  # mismo valor RSI -> no es "mas alto estricto"
    close2[60], close2[100] = 95.0, 90.0
    s_eqrsi, r_eqrsi = divergence_score(+1, close2, rsi_vals2, 105)
    check("valores de RSI EXACTAMENTE iguales en los dos pivotes -> sin divergencia (comparacion estricta '>')",
          s_eqrsi == 0, f"rsi[60]=rsi[100]=20.0 -> score={s_eqrsi} ({r_eqrsi})")

    # bullish seguida de bullish (tercer low mas reciente reemplaza al segundo como referencia "latest")
    rsi_vals3 = np.full(300, 50.0)
    close3 = np.full(300, 100.0)
    rsi_vals3[60], rsi_vals3[100], rsi_vals3[140] = 10.0, 20.0, 30.0  # tres minimos RSI crecientes
    close3[60], close3[100], close3[140] = 100.0, 95.0, 90.0          # tres minimos precio decrecientes
    s_3rd, r_3rd = divergence_score(+1, close3, rsi_vals3, 145)  # confirmed_bar del 3ro=145... usar 146
    s_3rd, r_3rd = divergence_score(+1, close3, rsi_vals3, 146)
    check("bullish seguida de bullish -> se compara SIEMPRE el ultimo pivote fresco contra el previo en rango, "
          "ignorando pivotes mas viejos que el previo inmediato",
          s_3rd == 1, f"score={s_3rd} ({r_3rd})")

    # NaN dentro de la serie de precio/RSI en medio del historial (ademas del warmup) no rompe el calculo
    rsi_nan = np.full(200, 50.0)
    rsi_nan[60], rsi_nan[100] = 20.0, 30.0
    rsi_nan[80] = float("nan")  # NaN aislado en medio, lejos de cualquier ventana de pivote relevante
    close_nan = np.full(200, 100.0)
    close_nan[60], close_nan[100] = 95.0, 90.0
    try:
        s_nan, r_nan = divergence_score(+1, close_nan, rsi_nan, 105)
        ok_nan = True
    except Exception as e:  # pragma: no cover
        s_nan, r_nan, ok_nan = None, str(e), False
    check("un NaN aislado en el RSI (lejos de las ventanas de pivote relevantes) no produce excepcion",
          ok_nan, f"score={s_nan} ({r_nan})")


# ---------------------------------------------------------------------------
# 13. Paridad batch vs secuencial/live
# ---------------------------------------------------------------------------

def audit_batch_vs_sequential_parity() -> None:
    section("13. Paridad batch vs secuencial/live")

    n = 400
    t = np.arange(n, dtype=float)
    close_full = 1900.0 + 12.0 * np.sin(t / 17.0) + 4.0 * np.sin(t / 5.3 + 0.7) + 0.3 * np.sin(t / 2.1)

    rsi_batch = rsi(close_full, period=RSI_PERIOD)

    mismatches = []
    rows = []
    warmup = RSI_PERIOD + DIVERGENCE_LB_LEFT + DIVERGENCE_LB_RIGHT + DIVERGENCE_RANGE_MIN + 2
    for cur in range(warmup, n):
        close_seq = close_full[:cur + 1]
        rsi_seq = rsi(close_seq, period=RSI_PERIOD)  # recalculado SOLO con datos hasta 'cur' -- nunca ve el futuro

        for direction in (+1, -1):
            s_batch, r_batch = divergence_score(direction, close_full, rsi_batch, cur)
            s_seq, r_seq = divergence_score(direction, close_seq, rsi_seq, cur)
            rows.append((cur, direction, s_batch, s_seq))
            if s_batch != s_seq or r_batch != r_seq:
                mismatches.append((cur, direction, s_batch, r_batch, s_seq, r_seq))

    check(f"paridad EXACTA batch vs secuencial en {len(rows)} combinaciones (barras {warmup}..{n - 1} x direction +-1) "
          f"-- 'secuencial' recalcula RSI y pivotes SOLO con bars[0:cur+1] en cada paso, nunca con bars[0:N]",
          len(mismatches) == 0,
          f"comparaciones={len(rows)}, discrepancias={len(mismatches)}"
          + (f", primeras discrepancias={mismatches[:5]}" if mismatches else ""))


# ---------------------------------------------------------------------------
# 14. Paridad en el momento de creacion del LIMIT
# ---------------------------------------------------------------------------

def audit_limit_time_parity() -> None:
    section("14. Paridad en el momento de creacion del LIMIT")

    n = 160
    rsi_vals = np.full(n, 50.0)
    rsi_vals[60], rsi_vals[100] = 20.0, 30.0  # bullish: previo=60, reciente=100, confirmed_bar=105
    close = np.full(n, 100.0)
    close[60], close[100] = 95.0, 90.0

    print("Simulando creacion de un LIMIT en cada barra 101..106 (segundo pivote en bar=100, confirmed_bar=105):")
    results = {}
    for limit_bar in range(101, 107):
        # 'current_bar' == barra de la señal/LIMIT; solo datos hasta esa barra son visibles en ese instante
        s, r = divergence_score(+1, close[:limit_bar + 1], rsi_vals[:limit_bar + 1], limit_bar)
        results[limit_bar] = (s, r)
        print(f"  LIMIT en bar={limit_bar}: score={s:+d}  reason={r!r}")

    check("un LIMIT creado en bars 101-104 NO puede usar la divergencia cuyo pivote en bar=100 "
          "todavia no esta confirmado (requiere 5 barras derechas, confirmed_bar=105)",
          all(results[b][0] == 0 for b in [101, 102, 103, 104]),
          f"scores 101..104 = {[results[b][0] for b in [101,102,103,104]]}")
    check("el LIMIT en bar=105 (o posterior) SI puede usar la divergencia, recien confirmada",
          results[105][0] == 1 and results[106][0] == 1,
          f"scores 105,106 = {results[105][0]}, {results[106][0]}")


# ---------------------------------------------------------------------------

def main() -> int:
    print("AUDITORIA RSI DIVERGENCE -- strategy/scoring.py")
    print("SOLO LECTURA. No se modifico ningun archivo de produccion.\n")

    audit_rsi_wilder()
    audit_pivots()
    audit_causality()
    audit_price_pivot_association()
    audit_separation()
    audit_validity_timeline()
    audit_event_vs_state()
    audit_long_short()
    audit_simultaneous_divergences()
    audit_edge_cases()
    audit_batch_vs_sequential_parity()
    audit_limit_time_parity()

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    print(f"WARNINGS: {len(WARNINGS)}")
    for w in WARNINGS:
        print(f"  - {w}")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
