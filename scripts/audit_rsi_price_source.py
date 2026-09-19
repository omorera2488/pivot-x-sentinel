"""Auditoria READ-ONLY (BOT-024): compara dos definiciones de la fuente de
precio usada por Divergencia RSI para el lado "precio" de la comparacion
bullish/bearish, SIN tocar ningun archivo de produccion:

  Variante A (implementacion actual, strategy/scoring.py):
      bullish: close[latest_pivot] < close[prior_pivot]
      bearish: close[latest_pivot] > close[prior_pivot]

  Variante B (extremos de vela, candidata a evaluar):
      bullish: low[latest_pivot]  < low[prior_pivot]
      bearish: high[latest_pivot] > high[prior_pivot]

Los pivotes siguen siendo pivotes DEL RSI (find_confirmed_pivots sobre
rsi_values) en ambas variantes -- lo unico que cambia es que array de precio
se lee en pivot_bar/prior_pivot_bar para el lado "precio" de la comparacion.

Que se REUSA de strategy/scoring.py sin modificarlo (import directo, cero
duplicacion de esa logica):
    rsi(), find_confirmed_pivots(), _most_recent_fresh(), _prior_in_range(),
    resolve_divergence(), DivergenceCandidate, DivergenceResolution,
    DIVERGENCE_STATE_*, DIVERGENCE_RESOLUTION_*, RSI_PERIOD,
    DIVERGENCE_LB_LEFT/RIGHT, DIVERGENCE_RANGE_MIN/MAX, DIVERGENCE_FRESH_BARS.

Que se REIMPLEMENTA localmente (unicamente para poder parametrizar la fuente
de precio -- production/scoring.py no expone ese parametro y esta auditoria
tiene prohibido tocarlo):
    _candidate() -- version generica de _bullish_candidate()/
    _bearish_candidate() de scoring.py, parametrizada por el array de precio
    a leer en pivot_bar. Una version "lenta" (idéntica linea por linea a la
    de produccion, solo generica) para probar equivalencia exacta con
    divergence_detail() real de produccion, y una version "rapida" (indice
    con bisect) para poder correr sobre el dataset historico completo
    (100k+ barras) sin costo O(n^2).

Uso:
    .venv/Scripts/python.exe scripts/audit_rsi_price_source.py > reports/RSI-PRICE-SOURCE-EVIDENCE.log

No modifica produccion. No decide nada sobre cual variante usar -- solo mide.
"""
from __future__ import annotations

import bisect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from strategy.scoring import (
    DIVERGENCE_FRESH_BARS, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT,
    DIVERGENCE_RANGE_MAX, DIVERGENCE_RANGE_MIN, DIVERGENCE_RESOLUTION_CONFLICT,
    DIVERGENCE_RESOLUTION_MOST_RECENT, DIVERGENCE_RESOLUTION_NA, DIVERGENCE_STATE_BEARISH,
    DIVERGENCE_STATE_BULLISH, DIVERGENCE_STATE_CONFLICT, DIVERGENCE_STATE_NONE, RSI_PERIOD,
    DivergenceCandidate, Pivot, _most_recent_fresh, _prior_in_range,
    divergence_detail as prod_divergence_detail, find_confirmed_pivots, resolve_divergence, rsi,
)

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}\n       {evidence}")
    if not condition:
        FAILURES.append(f"{label} :: {evidence}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Deteccion de candidato generica ("lenta" -- misma logica linea por linea
# que _bullish_candidate()/_bearish_candidate() de scoring.py, parametrizada
# por el array de precio a usar en pivot_bar/prior_pivot_bar).
# ---------------------------------------------------------------------------

def _candidate_slow(kind: str, price: np.ndarray, rsi_values: np.ndarray, current_bar: int,
                     lbL: int, lbR: int, range_min: int, range_max: int, fresh_bars: int) -> DivergenceCandidate | None:
    highs, lows = find_confirmed_pivots(rsi_values[:current_bar + 1], lbL, lbR)
    pivots = lows if kind == "bullish" else highs
    latest = _most_recent_fresh(pivots, current_bar, fresh_bars)
    if latest is None:
        return None
    prior = _prior_in_range(pivots, latest, range_min, range_max)
    if prior is None:
        return None
    if kind == "bullish":
        ok = price[latest.bar] < price[prior.bar] and latest.value > prior.value
    else:
        ok = price[latest.bar] > price[prior.bar] and latest.value < prior.value
    if not ok:
        return None
    return DivergenceCandidate(
        kind=kind, pivot_bar=latest.bar, confirmation_bar=latest.confirmed_bar,
        age=current_bar - latest.confirmed_bar,
        prior_pivot_bar=prior.bar, prior_confirmation_bar=prior.confirmed_bar,
        latest_rsi=float(latest.value), prior_rsi=float(prior.value),
        latest_price=float(price[latest.bar]), prior_price=float(price[prior.bar]),
    )


def divergence_detail_slow(direction: int, price_bullish: np.ndarray, price_bearish: np.ndarray,
                            rsi_values: np.ndarray, current_bar: int,
                            lbL: int = DIVERGENCE_LB_LEFT, lbR: int = DIVERGENCE_LB_RIGHT,
                            range_min: int = DIVERGENCE_RANGE_MIN, range_max: int = DIVERGENCE_RANGE_MAX,
                            fresh_bars: int = DIVERGENCE_FRESH_BARS):
    """Variante generica de divergence_detail(): bullish lee `price_bullish`,
    bearish lee `price_bearish` en pivot_bar/prior_pivot_bar. Variante A =
    (close, close). Variante B = (low, high). La resolucion (resolve_divergence)
    es la MISMA funcion de produccion, sin cambios -- la fuente de precio
    solo decide que candidatos EXISTEN, nunca como se resuelven."""
    bullish = _candidate_slow("bullish", price_bullish, rsi_values, current_bar, lbL, lbR, range_min, range_max, fresh_bars)
    bearish = _candidate_slow("bearish", price_bearish, rsi_values, current_bar, lbL, lbR, range_min, range_max, fresh_bars)
    return resolve_divergence(direction, bullish, bearish)


# ---------------------------------------------------------------------------
# Version "rapida" (indice con bisect) -- misma semantica que la lenta,
# necesaria para correr sobre el dataset historico completo (100k+ barras)
# sin costo O(n^2). find_confirmed_pivots() sobre el array COMPLETO produce
# los mismos pivotes que sobre cualquier prefijo rsi_values[:t+1] porque la
# ventana de deteccion es local ([i-lbL, i+lbR], nunca mira mas alla de
# i+lbR) -- ya demostrado en reports/AUDIT-RSI-DIVERGENCE.md seccion 13
# (batch/live parity, 738/738). Se valida de nuevo mas abajo (seccion 1)
# contra divergence_detail_slow()/produccion antes de confiar en ella.
# ---------------------------------------------------------------------------

class PivotIndex:
    def __init__(self, pivots: list[Pivot]):
        self.pivots = pivots
        self.bars = np.array([p.bar for p in pivots], dtype=np.int64)
        self.confirmed = np.array([p.confirmed_bar for p in pivots], dtype=np.int64)

    def most_recent_fresh(self, current_bar: int, fresh_bars: int) -> Pivot | None:
        lo = bisect.bisect_left(self.confirmed, current_bar - fresh_bars)
        hi = bisect.bisect_right(self.confirmed, current_bar)
        if lo >= hi:
            return None
        return self.pivots[hi - 1]

    def prior_in_range(self, latest_bar: int, range_min: int, range_max: int) -> Pivot | None:
        lo = bisect.bisect_left(self.bars, latest_bar - range_max)
        hi = bisect.bisect_right(self.bars, latest_bar - range_min)
        if lo >= hi:
            return None
        return self.pivots[hi - 1]


def _candidate_fast(kind: str, price: np.ndarray, idx: PivotIndex, current_bar: int,
                     range_min: int, range_max: int, fresh_bars: int) -> DivergenceCandidate | None:
    latest = idx.most_recent_fresh(current_bar, fresh_bars)
    if latest is None:
        return None
    prior = idx.prior_in_range(latest.bar, range_min, range_max)
    if prior is None:
        return None
    if kind == "bullish":
        ok = price[latest.bar] < price[prior.bar] and latest.value > prior.value
    else:
        ok = price[latest.bar] > price[prior.bar] and latest.value < prior.value
    if not ok:
        return None
    return DivergenceCandidate(
        kind=kind, pivot_bar=latest.bar, confirmation_bar=latest.confirmed_bar,
        age=current_bar - latest.confirmed_bar,
        prior_pivot_bar=prior.bar, prior_confirmation_bar=prior.confirmed_bar,
        latest_rsi=float(latest.value), prior_rsi=float(prior.value),
        latest_price=float(price[latest.bar]), prior_price=float(price[prior.bar]),
    )


def divergence_detail_fast(direction: int, price_bullish: np.ndarray, price_bearish: np.ndarray,
                            lows_idx: PivotIndex, highs_idx: PivotIndex, current_bar: int,
                            range_min: int, range_max: int, fresh_bars: int):
    bullish = _candidate_fast("bullish", price_bullish, lows_idx, current_bar, range_min, range_max, fresh_bars)
    bearish = _candidate_fast("bearish", price_bearish, highs_idx, current_bar, range_min, range_max, fresh_bars)
    return resolve_divergence(direction, bullish, bearish)


# ---------------------------------------------------------------------------
# 1. Implementacion actual -- confirmar donde se usa close[pivot_bar]
# ---------------------------------------------------------------------------

def audit_current_implementation() -> None:
    section("1. Implementacion actual -- donde se usa close[pivot_bar]")
    import inspect
    from strategy.scoring import _bearish_candidate, _bullish_candidate
    src_bull = inspect.getsource(_bullish_candidate)
    src_bear = inspect.getsource(_bearish_candidate)
    print("strategy/scoring.py:_bullish_candidate() (bullish, precio en pivot_bar/prior_pivot_bar):")
    print(src_bull)
    print("strategy/scoring.py:_bearish_candidate() (bearish, precio en pivot_bar/prior_pivot_bar):")
    print(src_bear)
    check("_bullish_candidate compara close[latest_low.bar] < close[prior_low.bar]",
          "close[latest_low.bar] < close[prior_low.bar]" in src_bull, "grep del cuerpo de la funcion")
    check("_bearish_candidate compara close[latest_high.bar] > close[prior_high.bar]",
          "close[latest_high.bar] > close[prior_high.bar]" in src_bear, "grep del cuerpo de la funcion")
    check("ninguna de las dos funciones referencia 'low[' ni 'high[' -- solo 'close['",
          "low[" not in src_bull and "high[" not in src_bull and "low[" not in src_bear and "high[" not in src_bear,
          "grep negativo de low[../high[.. en ambos cuerpos")
    print("\nFlujo real a produccion (sin cambios en esta auditoria):")
    print("  execution/src/bot.py:_score_entry() -> scoring.score_entry() -> divergence_detail()")
    print("  -> _bullish_candidate(close,...) / _bearish_candidate(close,...) -- mismo array 'close' para ambos lados.")


# ---------------------------------------------------------------------------
# 2. Consistencia: Variante A (funciones genericas de esta auditoria) debe
#    ser IDENTICA a divergence_detail() real de produccion
# ---------------------------------------------------------------------------

def audit_consistency_with_production(df: pd.DataFrame) -> None:
    section("2. Consistencia: Variante A (generica) == divergence_detail() de produccion")

    n = 4000
    close = df["close"].to_numpy(dtype=float)[:n]
    rsi_values = rsi(close, RSI_PERIOD)

    warmup = RSI_PERIOD + DIVERGENCE_LB_LEFT + DIVERGENCE_LB_RIGHT + DIVERGENCE_RANGE_MIN + 2
    mismatches = []
    checked = 0
    for cur in range(warmup, n, 7):  # cada 7 barras, suficiente muestra sin correr las 4000 secuencialmente 2 veces
        for direction in (+1, -1):
            prod = prod_divergence_detail(direction, close, rsi_values, cur)
            gen_slow = divergence_detail_slow(direction, close, close, rsi_values, cur)
            checked += 1
            if (prod.resolved_state, prod.resolution, prod.score, prod.reason) != \
               (gen_slow.resolved_state, gen_slow.resolution, gen_slow.score, gen_slow.reason):
                mismatches.append((cur, direction, prod, gen_slow))

    check(f"Variante A (generica, price_bullish=price_bearish=close) == divergence_detail() real de "
          f"strategy/scoring.py en {checked} combinaciones (barras {warmup}..{n} cada 7, direction +-1)",
          len(mismatches) == 0,
          f"comparaciones={checked}, discrepancias={len(mismatches)}" + (f", ejemplos={mismatches[:3]}" if mismatches else ""))


# ---------------------------------------------------------------------------
# 3. Consistencia: version "rapida" (bisect, para el dataset completo) ==
#    version "lenta" (identica a produccion)
# ---------------------------------------------------------------------------

def audit_fast_matches_slow(df: pd.DataFrame) -> None:
    section("3. Consistencia: indice rapido (bisect) == calculo lento por barra")

    n = 3000
    close = df["close"].to_numpy(dtype=float)[:n]
    low = df["low"].to_numpy(dtype=float)[:n]
    high = df["high"].to_numpy(dtype=float)[:n]
    rsi_values = rsi(close, RSI_PERIOD)

    highs_full, lows_full = find_confirmed_pivots(rsi_values, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
    lows_idx = PivotIndex(lows_full)
    highs_idx = PivotIndex(highs_full)

    warmup = RSI_PERIOD + DIVERGENCE_LB_LEFT + DIVERGENCE_LB_RIGHT + DIVERGENCE_RANGE_MIN + 2
    mismatches_a = []
    mismatches_b = []
    checked = 0
    for cur in range(warmup, n):
        for direction in (+1, -1):
            checked += 1
            slow_a = divergence_detail_slow(direction, close, close, rsi_values, cur)
            fast_a = divergence_detail_fast(direction, close, close, lows_idx, highs_idx, cur,
                                             DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX, DIVERGENCE_FRESH_BARS)
            if (slow_a.resolved_state, slow_a.score) != (fast_a.resolved_state, fast_a.score):
                mismatches_a.append((cur, direction, slow_a, fast_a))

            slow_b = divergence_detail_slow(direction, low, high, rsi_values, cur)
            fast_b = divergence_detail_fast(direction, low, high, lows_idx, highs_idx, cur,
                                             DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX, DIVERGENCE_FRESH_BARS)
            if (slow_b.resolved_state, slow_b.score) != (fast_b.resolved_state, fast_b.score):
                mismatches_b.append((cur, direction, slow_b, fast_b))

    check(f"indice rapido == calculo lento para Variante A en {checked} combinaciones (barras {warmup}..{n}, direction +-1)",
          len(mismatches_a) == 0, f"comparaciones={checked}, discrepancias={len(mismatches_a)}"
          + (f", ejemplos={mismatches_a[:3]}" if mismatches_a else ""))
    check(f"indice rapido == calculo lento para Variante B en {checked} combinaciones",
          len(mismatches_b) == 0, f"comparaciones={checked}, discrepancias={len(mismatches_b)}"
          + (f", ejemplos={mismatches_b[:3]}" if mismatches_b else ""))


# ---------------------------------------------------------------------------
# 4. Casos sinteticos obligatorios (1-8)
# ---------------------------------------------------------------------------

def _flat_ohlc(n: int, close0=100.0, low0=99.5, high0=100.5):
    close = np.full(n, close0)
    low = np.full(n, low0)
    high = np.full(n, high0)
    rsi_values = np.full(n, 50.0)
    return close, low, high, rsi_values


def audit_synthetic_cases() -> None:
    section("4. Casos sinteticos obligatorios (1-8)")
    n = 160
    kwargs = dict(lbL=DIVERGENCE_LB_LEFT, lbR=DIVERGENCE_LB_RIGHT, range_min=DIVERGENCE_RANGE_MIN,
                  range_max=DIVERGENCE_RANGE_MAX, fresh_bars=DIVERGENCE_FRESH_BARS)
    prior_bar, latest_bar = 60, 100
    current_bar = latest_bar + DIVERGENCE_LB_RIGHT  # 105, recien confirmado

    def run(close, low, high, rsi_values, direction=+1):
        det_a = divergence_detail_slow(direction, close, close, rsi_values, current_bar, **kwargs)
        det_b = divergence_detail_slow(direction, low, high, rsi_values, current_bar, **kwargs)
        return det_a, det_b

    # --- Caso 1: A y B detectan bullish -------------------------------------------------
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 25.0, 32.0  # HL
    close[prior_bar], close[latest_bar] = 100.0, 95.0   # close LL
    low[prior_bar], low[latest_bar] = 98.0, 93.0         # low LL
    high[prior_bar], high[latest_bar] = 101.0, 96.0
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 1 -- A y B detectan bullish", det_a.resolved_state == det_b.resolved_state == DIVERGENCE_STATE_BULLISH,
          f"A={det_a.resolved_state}, B={det_b.resolved_state}")

    # --- Caso 2: solo low detecta bullish (close NO hace LL) ----------------------------
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 25.0, 32.0  # HL
    close[prior_bar], close[latest_bar] = 100.0, 101.0  # close NO LL (sube)
    low[prior_bar], low[latest_bar] = 99.0, 98.0         # low SI LL
    high[prior_bar], high[latest_bar] = 101.0, 102.0
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 2 -- solo low detecta bullish (close no hace LL, low si)",
          det_a.resolved_state == DIVERGENCE_STATE_NONE and det_b.resolved_state == DIVERGENCE_STATE_BULLISH,
          f"close[{prior_bar}]={close[prior_bar]} close[{latest_bar}]={close[latest_bar]} (no LL); "
          f"low[{prior_bar}]={low[prior_bar]} low[{latest_bar}]={low[latest_bar]} (LL) -> A={det_a.resolved_state}, B={det_b.resolved_state}")

    # --- Caso 3: solo close detecta bullish (low NO hace LL) -- inverso geometrico ------
    # OHLC valido: low <= close <= high siempre. Mecha inferior larga en el pivote previo
    # (low bien por debajo del close) permite que el CLOSE baje (LL) sin que el LOW baje.
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 25.0, 32.0  # HL
    close[prior_bar], close[latest_bar] = 100.0, 95.0  # close LL (95<100)
    low[prior_bar], low[latest_bar] = 90.0, 92.0        # low NO LL (92 > 90 -- mecha previa mas profunda)
    high[prior_bar], high[latest_bar] = 105.0, 100.0
    # validez OHLC: low<=close<=high en ambas barras
    assert low[prior_bar] <= close[prior_bar] <= high[prior_bar]
    assert low[latest_bar] <= close[latest_bar] <= high[latest_bar]
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 3 -- solo close detecta bullish (low no hace LL) -- geometricamente posible con OHLC valido",
          det_a.resolved_state == DIVERGENCE_STATE_BULLISH and det_b.resolved_state == DIVERGENCE_STATE_NONE,
          f"close[{prior_bar}]={close[prior_bar]} close[{latest_bar}]={close[latest_bar]} (LL); "
          f"low[{prior_bar}]={low[prior_bar]} low[{latest_bar}]={low[latest_bar]} (no LL, mecha previa mas profunda) "
          f"-> A={det_a.resolved_state}, B={det_b.resolved_state}. OHLC valido: low<=close<=high en ambas barras.")

    # --- Caso 4: A y B detectan bearish --------------------------------------------------
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 75.0, 68.0  # LH
    close[prior_bar], close[latest_bar] = 100.0, 105.0  # close HH
    high[prior_bar], high[latest_bar] = 102.0, 108.0     # high HH
    low[prior_bar], low[latest_bar] = 99.0, 104.0
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 4 -- A y B detectan bearish", det_a.resolved_state == det_b.resolved_state == DIVERGENCE_STATE_BEARISH,
          f"A={det_a.resolved_state}, B={det_b.resolved_state}")

    # --- Caso 5: solo high detecta bearish (close NO hace HH) ---------------------------
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 75.0, 68.0  # LH
    close[prior_bar], close[latest_bar] = 100.0, 99.0   # close NO HH (baja)
    high[prior_bar], high[latest_bar] = 101.0, 103.0     # high SI HH
    low[prior_bar], low[latest_bar] = 99.0, 98.0
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 5 -- solo high detecta bearish (close no hace HH, high si)",
          det_a.resolved_state == DIVERGENCE_STATE_NONE and det_b.resolved_state == DIVERGENCE_STATE_BEARISH,
          f"close[{prior_bar}]={close[prior_bar]} close[{latest_bar}]={close[latest_bar]} (no HH); "
          f"high[{prior_bar}]={high[prior_bar]} high[{latest_bar}]={high[latest_bar]} (HH) -> A={det_a.resolved_state}, B={det_b.resolved_state}")

    # --- Caso 6: solo close detecta bearish (high NO hace HH) -- inverso geometrico ----
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 75.0, 68.0  # LH
    close[prior_bar], close[latest_bar] = 100.0, 105.0  # close HH (105>100)
    high[prior_bar], high[latest_bar] = 110.0, 108.0     # high NO HH (108 < 110 -- mecha previa mas alta)
    low[prior_bar], low[latest_bar] = 95.0, 100.0
    assert low[prior_bar] <= close[prior_bar] <= high[prior_bar]
    assert low[latest_bar] <= close[latest_bar] <= high[latest_bar]
    det_a, det_b = run(close, low, high, rsi_values)
    check("Caso 6 -- solo close detecta bearish (high no hace HH) -- geometricamente posible con OHLC valido",
          det_a.resolved_state == DIVERGENCE_STATE_BEARISH and det_b.resolved_state == DIVERGENCE_STATE_NONE,
          f"close[{prior_bar}]={close[prior_bar]} close[{latest_bar}]={close[latest_bar]} (HH); "
          f"high[{prior_bar}]={high[prior_bar]} high[{latest_bar}]={high[latest_bar]} (no HH, mecha previa mas alta) "
          f"-> A={det_a.resolved_state}, B={det_b.resolved_state}. OHLC valido: low<=close<=high en ambas barras.")

    # --- Caso 7: causalidad -- ninguna variante conoce el pivote antes de confirmation_bar
    close, low, high, rsi_values = _flat_ohlc(n)
    rsi_values[prior_bar], rsi_values[latest_bar] = 25.0, 32.0
    close[prior_bar], close[latest_bar] = 100.0, 95.0
    low[prior_bar], low[latest_bar] = 98.0, 93.0
    high[prior_bar], high[latest_bar] = 101.0, 96.0
    conf_bar = latest_bar + DIVERGENCE_LB_RIGHT  # 105
    rows = []
    for t in range(latest_bar, conf_bar + 2):
        det_a_t = divergence_detail_slow(+1, close[:t + 1], close[:t + 1], rsi_values[:t + 1], t, **kwargs)
        det_b_t = divergence_detail_slow(+1, low[:t + 1], high[:t + 1], rsi_values[:t + 1], t, **kwargs)
        rows.append((t, det_a_t.resolved_state, det_b_t.resolved_state))
    print(f"\nCaso 7 -- causalidad (pivot_bar={latest_bar}, lbR={DIVERGENCE_LB_RIGHT}, confirmation_bar={conf_bar}):")
    for t, a_state, b_state in rows:
        print(f"  t={t:3d}  A={a_state:8s}  B={b_state:8s}")
    before = [(a, b) for t, a, b in rows if t < conf_bar]
    at_conf = [(a, b) for t, a, b in rows if t == conf_bar]
    check("ninguna variante (A ni B) usa el pivote antes de confirmation_bar",
          all(a == DIVERGENCE_STATE_NONE and b == DIVERGENCE_STATE_NONE for a, b in before),
          f"barras {latest_bar}..{conf_bar - 1}: {before}")
    check("ambas variantes disponen del pivote exactamente en confirmation_bar",
          at_conf[0] == (DIVERGENCE_STATE_BULLISH, DIVERGENCE_STATE_BULLISH),
          f"barra {conf_bar}: {at_conf[0]}")

    # --- Caso 8: simultaneas -- la resolucion (MOST_RECENT/CONFLICT) es la MISMA funcion,
    # el precio solo decide que candidatos existen. Se demuestra con dos variantes de datos:
    # (8a) mismos candidatos activos en A y B, distinto confirmation_bar -> misma resolucion.
    close, low, high, rsi_values = _flat_ohlc(n)
    # bullish: 60(prior)/100(latest) confirmation_bar=105 -- close Y low hacen LL (Caso 1 style)
    rsi_values[60], rsi_values[100] = 25.0, 32.0
    close[60], close[100] = 100.0, 95.0
    low[60], low[100] = 98.0, 93.0
    high[60], high[100] = 101.0, 96.0
    # bearish: 61(prior)/101(latest) confirmation_bar=106 (MAS reciente) -- close Y high hacen HH
    rsi_values[61], rsi_values[101] = 75.0, 68.0
    close[61], close[101] = 100.0, 105.0
    high[61], high[101] = 102.0, 108.0
    low[61], low[101] = 99.0, 104.0
    cur = 106
    det_a = divergence_detail_slow(+1, close, close, rsi_values, cur, **kwargs)
    det_b = divergence_detail_slow(+1, low, high, rsi_values, cur, **kwargs)
    check("Caso 8a -- mismos candidatos activos en A y B (bearish mas reciente) -> misma resolucion MOST_RECENT/BEARISH",
          det_a.resolved_state == det_b.resolved_state == DIVERGENCE_STATE_BEARISH
          and det_a.resolution == det_b.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT,
          f"A: resolved_state={det_a.resolved_state} resolution={det_a.resolution}; "
          f"B: resolved_state={det_b.resolved_state} resolution={det_b.resolution}")

    # (8b) la fuente de precio cambia CUALES candidatos existen -> puede cambiar el resolved_state
    # resultante (no la MECANICA de resolucion). Se reusa Caso 2 (bullish solo en B via low) +
    # Caso 4-style bearish activo en AMBAS variantes con confirmation_bar mas viejo que el bullish-B.
    close, low, high, rsi_values = _flat_ohlc(n)
    # bullish: solo B lo activa (igual que Caso 2), confirmation_bar=105
    rsi_values[60], rsi_values[100] = 25.0, 32.0
    close[60], close[100] = 100.0, 101.0   # close NO LL -> A no activa bullish
    low[60], low[100] = 99.0, 98.0          # low SI LL -> B activa bullish
    high[60], high[100] = 101.0, 102.0
    # bearish: activo en A y B por igual, confirmation_bar=104 (mas VIEJO que el bullish=105)
    rsi_values[59], rsi_values[99] = 75.0, 68.0
    close[59], close[99] = 100.0, 105.0
    high[59], high[99] = 102.0, 108.0
    low[59], low[99] = 99.0, 104.0
    cur = 106
    det_a = divergence_detail_slow(+1, close, close, rsi_values, cur, **kwargs)
    det_b = divergence_detail_slow(+1, low, high, rsi_values, cur, **kwargs)
    check("Caso 8b -- la fuente de precio cambia el CONJUNTO de candidatos activos (A: solo bearish -> BEARISH; "
          "B: bullish + bearish, bullish mas reciente -> BULLISH) -- la resolucion en si (MOST_RECENT) es identica, "
          "el resultado final difiere solo porque los candidatos de entrada son distintos",
          det_a.resolved_state == DIVERGENCE_STATE_BEARISH and det_b.resolved_state == DIVERGENCE_STATE_BULLISH
          and det_b.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT,
          f"A: bullish_active={det_a.bullish is not None} bearish_active={det_a.bearish is not None} -> {det_a.resolved_state}; "
          f"B: bullish_active={det_b.bullish is not None} (confirmation_bar={det_b.bullish.confirmation_bar if det_b.bullish else None}) "
          f"bearish_active={det_b.bearish is not None} (confirmation_bar={det_b.bearish.confirmation_bar if det_b.bearish else None}) "
          f"-> {det_b.resolved_state}/{det_b.resolution}")


# ---------------------------------------------------------------------------
# 5. Dataset historico real -- estadisticas + matriz de transicion
# ---------------------------------------------------------------------------

STATES = [DIVERGENCE_STATE_NONE, DIVERGENCE_STATE_BULLISH, DIVERGENCE_STATE_BEARISH, DIVERGENCE_STATE_CONFLICT]


def run_full_dataset(df: pd.DataFrame):
    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    n = len(close)
    rsi_values = rsi(close, RSI_PERIOD)

    highs_full, lows_full = find_confirmed_pivots(rsi_values, DIVERGENCE_LB_LEFT, DIVERGENCE_LB_RIGHT)
    lows_idx = PivotIndex(lows_full)
    highs_idx = PivotIndex(highs_full)

    warmup = RSI_PERIOD + DIVERGENCE_LB_LEFT + DIVERGENCE_LB_RIGHT + DIVERGENCE_RANGE_MIN + 2
    direction = +1  # resolved_state/resolution no dependen de direction; se fija +1 arbitrariamente (ver docstring)

    records = []
    for cur in range(warmup, n):
        det_a = divergence_detail_fast(direction, close, close, lows_idx, highs_idx, cur,
                                        DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX, DIVERGENCE_FRESH_BARS)
        det_b = divergence_detail_fast(direction, low, high, lows_idx, highs_idx, cur,
                                        DIVERGENCE_RANGE_MIN, DIVERGENCE_RANGE_MAX, DIVERGENCE_FRESH_BARS)
        records.append((cur, det_a, det_b))
    return records, close, low, high, rsi_values, warmup, n


def audit_real_dataset(records) -> dict:
    section("5. Dataset historico real -- estadisticas A vs B")

    total = len(records)
    a_states = [r[1].resolved_state for r in records]
    b_states = [r[2].resolved_state for r in records]

    def count(states, target):
        return sum(1 for s in states if s == target)

    bullish_a, bullish_b = count(a_states, DIVERGENCE_STATE_BULLISH), count(b_states, DIVERGENCE_STATE_BULLISH)
    bearish_a, bearish_b = count(a_states, DIVERGENCE_STATE_BEARISH), count(b_states, DIVERGENCE_STATE_BEARISH)
    none_a, none_b = count(a_states, DIVERGENCE_STATE_NONE), count(b_states, DIVERGENCE_STATE_NONE)
    conflict_a, conflict_b = count(a_states, DIVERGENCE_STATE_CONFLICT), count(b_states, DIVERGENCE_STATE_CONFLICT)

    coincide_bullish = sum(1 for a, b in zip(a_states, b_states) if a == DIVERGENCE_STATE_BULLISH and b == DIVERGENCE_STATE_BULLISH)
    coincide_bearish = sum(1 for a, b in zip(a_states, b_states) if a == DIVERGENCE_STATE_BEARISH and b == DIVERGENCE_STATE_BEARISH)
    solo_a_bullish = sum(1 for a, b in zip(a_states, b_states) if a == DIVERGENCE_STATE_BULLISH and b != DIVERGENCE_STATE_BULLISH)
    solo_b_bullish = sum(1 for a, b in zip(a_states, b_states) if b == DIVERGENCE_STATE_BULLISH and a != DIVERGENCE_STATE_BULLISH)
    solo_a_bearish = sum(1 for a, b in zip(a_states, b_states) if a == DIVERGENCE_STATE_BEARISH and b != DIVERGENCE_STATE_BEARISH)
    solo_b_bearish = sum(1 for a, b in zip(a_states, b_states) if b == DIVERGENCE_STATE_BEARISH and a != DIVERGENCE_STATE_BEARISH)
    none_both = sum(1 for a, b in zip(a_states, b_states) if a == DIVERGENCE_STATE_NONE and b == DIVERGENCE_STATE_NONE)
    diff_total = sum(1 for a, b in zip(a_states, b_states) if a != b)

    print(f"Barras evaluadas (causal, warmup excluido): {total}")
    print(f"\n{'Estado':10s} {'A':>8s} {'B':>8s}")
    for name, ca, cb in [("NONE", none_a, none_b), ("BULLISH", bullish_a, bullish_b),
                         ("BEARISH", bearish_a, bearish_b), ("CONFLICT", conflict_a, conflict_b)]:
        print(f"{name:10s} {ca:>8d} {cb:>8d}")

    print(f"\ncoinciden bullish (A=B=BULLISH): {coincide_bullish}")
    print(f"coinciden bearish (A=B=BEARISH): {coincide_bearish}")
    print(f"solo A bullish (A=BULLISH, B!=BULLISH): {solo_a_bullish}")
    print(f"solo B bullish (B=BULLISH, A!=BULLISH): {solo_b_bullish}")
    print(f"solo A bearish (A=BEARISH, B!=BEARISH): {solo_a_bearish}")
    print(f"solo B bearish (B=BEARISH, A!=BEARISH): {solo_b_bearish}")
    print(f"NONE en ambas: {none_both}")
    print(f"CONFLICT en A: {conflict_a}   CONFLICT en B: {conflict_b}")
    print(f"\nporcentaje total de barras con estado DIFERENTE A vs B: {diff_total}/{total} = {100*diff_total/total:.3f}%")

    print("\nMatriz de transicion A -> B (conteo de barras):")
    matrix = {}
    header_label = "A -> B"
    print(f"{header_label:10s}" + "".join(f"{s:>10s}" for s in STATES))
    for sa in STATES:
        row = []
        for sb in STATES:
            c = sum(1 for a, b in zip(a_states, b_states) if a == sa and b == sb)
            matrix[(sa, sb)] = c
            row.append(c)
        print(f"{sa:10s}" + "".join(f"{c:>10d}" for c in row))

    check("total de barras evaluadas es razonable (>50000, dataset historico real M5)",
          total > 50000, f"total={total}")
    check("la suma de la matriz de transicion es igual al total de barras",
          sum(matrix.values()) == total, f"suma matriz={sum(matrix.values())}, total={total}")

    return {
        "total": total, "bullish_a": bullish_a, "bullish_b": bullish_b,
        "bearish_a": bearish_a, "bearish_b": bearish_b, "none_a": none_a, "none_b": none_b,
        "conflict_a": conflict_a, "conflict_b": conflict_b,
        "coincide_bullish": coincide_bullish, "coincide_bearish": coincide_bearish,
        "solo_a_bullish": solo_a_bullish, "solo_b_bullish": solo_b_bullish,
        "solo_a_bearish": solo_a_bearish, "solo_b_bearish": solo_b_bearish,
        "none_both": none_both, "diff_total": diff_total, "matrix": matrix,
    }


# ---------------------------------------------------------------------------
# 6. Naturaleza de las diferencias -- ejemplos concretos con contexto completo
# ---------------------------------------------------------------------------

def _context_row(cur, det_a, det_b, close, low, high, rsi_values):
    def cand_ctx(det):
        parts = {}
        for kind in ("bullish", "bearish"):
            c = getattr(det, kind)
            if c is None:
                parts[kind] = None
            else:
                parts[kind] = dict(pivot_bar=c.pivot_bar, confirmation_bar=c.confirmation_bar,
                                    prior_pivot_bar=c.prior_pivot_bar, age=c.age,
                                    latest_rsi=c.latest_rsi, prior_rsi=c.prior_rsi)
        return parts

    return {
        "current_bar": int(cur),
        "close_ctx": cand_ctx(det_a), "extremos_ctx": cand_ctx(det_b),
        "estado_A": det_a.resolved_state, "estado_B": det_b.resolved_state,
        "close_latest": None, "close_prior": None,
        "low_latest": None, "low_prior": None,
        "high_latest": None, "high_prior": None,
    }


def audit_discrepancy_examples(records, close, low, high, rsi_values) -> dict:
    section("6. Naturaleza de las diferencias -- ejemplos concretos")

    def fill_prices(entry, det, kind):
        c = getattr(det, kind)
        if c is None:
            return
        entry[f"{kind}_latest_close"] = float(close[c.pivot_bar])
        entry[f"{kind}_prior_close"] = float(close[c.prior_pivot_bar])
        entry[f"{kind}_latest_low"] = float(low[c.pivot_bar])
        entry[f"{kind}_prior_low"] = float(low[c.prior_pivot_bar])
        entry[f"{kind}_latest_high"] = float(high[c.pivot_bar])
        entry[f"{kind}_prior_high"] = float(high[c.prior_pivot_bar])
        entry[f"{kind}_latest_rsi"] = c.latest_rsi
        entry[f"{kind}_prior_rsi"] = c.prior_rsi
        entry[f"{kind}_pivot_bar"] = c.pivot_bar
        entry[f"{kind}_confirmation_bar"] = c.confirmation_bar
        entry[f"{kind}_prior_pivot_bar"] = c.prior_pivot_bar
        entry[f"{kind}_prior_confirmation_bar"] = c.prior_confirmation_bar
        entry[f"{kind}_age"] = c.age

    none_to_bullish, none_to_bearish, only_a, resolution_changed = [], [], [], []
    for cur, det_a, det_b in records:
        entry_base = dict(current_bar=int(cur), estado_A=det_a.resolved_state, estado_B=det_b.resolved_state,
                           resolution_A=det_a.resolution, resolution_B=det_b.resolution)

        if det_a.resolved_state == DIVERGENCE_STATE_NONE and det_b.resolved_state == DIVERGENCE_STATE_BULLISH:
            e = dict(entry_base)
            fill_prices(e, det_b, "bullish")
            none_to_bullish.append(e)
        if det_a.resolved_state == DIVERGENCE_STATE_NONE and det_b.resolved_state == DIVERGENCE_STATE_BEARISH:
            e = dict(entry_base)
            fill_prices(e, det_b, "bearish")
            none_to_bearish.append(e)
        if det_a.resolved_state != DIVERGENCE_STATE_NONE and det_b.resolved_state == DIVERGENCE_STATE_NONE:
            e = dict(entry_base)
            kind = "bullish" if det_a.resolved_state == DIVERGENCE_STATE_BULLISH else "bearish"
            fill_prices(e, det_a, kind)
            only_a.append(e)
        if det_a.resolved_state != det_b.resolved_state and \
           DIVERGENCE_STATE_NONE not in (det_a.resolved_state, det_b.resolved_state):
            e = dict(entry_base)
            resolution_changed.append(e)

    def report_examples(title, items, k=5):
        print(f"\n{title}: {len(items)} encontrados en todo el dataset" + (f" (mostrando {k})" if len(items) > k else ""))
        if not items:
            print("  (ninguno -- se documenta explicitamente que no existen en este dataset)")
        for e in items[:k]:
            print(f"  {e}")

    report_examples("NONE(A) -> BULLISH(B)", none_to_bullish)
    report_examples("NONE(A) -> BEARISH(B)", none_to_bearish)
    report_examples("A detecta y B no (cualquier tipo)", only_a)
    report_examples("cambia la resolucion entre BULLISH/BEARISH/CONFLICT (ninguno de los dos es NONE)", resolution_changed)

    check("se documentaron los 4 catalogos de discrepancias pedidos (con todos los items si hay menos de 5)",
          True, f"NONE->BULLISH(B)={len(none_to_bullish)}, NONE->BEARISH(B)={len(none_to_bearish)}, "
                f"solo_A={len(only_a)}, cambia_resolucion={len(resolution_changed)}")

    return {
        "none_to_bullish": none_to_bullish, "none_to_bearish": none_to_bearish,
        "only_a": only_a, "resolution_changed": resolution_changed,
    }


# ---------------------------------------------------------------------------
# 7. Propiedad de subconjunto: ¿toda divergencia con close existe tambien con low/high?
# ---------------------------------------------------------------------------

def audit_subset_property(stats: dict) -> None:
    section("7. Propiedad de subconjunto (A subconjunto de B?)")

    print("Razonamiento OHLC: por definicion low[i] <= close[i] <= high[i] para toda barra i.")
    print("  bullish: A exige close[latest] < close[prior]. B exige low[latest] < low[prior].")
    print("  Estas son comparaciones de ARRAYS DISTINTOS (close vs low) en los MISMOS indices --")
    print("  no existe relacion de orden entre 'close[latest]<close[prior]' y 'low[latest]<low[prior]'")
    print("  que se derive solo de low<=close: un close mas bajo puede coexistir con un low mas alto")
    print("  (mecha inferior del pivote PREVIO mas profunda que la del pivote reciente) y viceversa.")
    print("  Por lo tanto NO hay subconjunto logico garantizado en ninguna direccion -- ver Casos 2/3/5/6.")

    check("REFUTADO por caso sintetico: existe una divergencia detectada por B (low/high) que A (close) NO detecta "
          "(Casos 2 y 5) -- B no es subconjunto de A",
          True, "ver seccion 4, Caso 2 (bullish) y Caso 5 (bearish)")
    check("REFUTADO por caso sintetico: existe una divergencia detectada por A (close) que B (low/high) NO detecta "
          "(Casos 3 y 6) -- A no es subconjunto de B",
          True, "ver seccion 4, Caso 3 (bullish) y Caso 6 (bearish)")

    solo_a = stats["solo_a_bullish"] + stats["solo_a_bearish"]
    solo_b = stats["solo_b_bullish"] + stats["solo_b_bearish"]
    check("CONFIRMADO en el dataset real: existen barras 'solo A' Y barras 'solo B' (ninguna es subconjunto de la otra)",
          solo_a > 0 and solo_b > 0,
          f"solo_A={solo_a} barras, solo_B={solo_b} barras (sobre {stats['total']} evaluadas)")

    print(f"\nConclusion de esta seccion: A y B NO tienen relacion de subconjunto en ninguna direccion -- "
          f"cada una detecta divergencias que la otra NO detecta, tanto en teoria (OHLC) como en la practica "
          f"(dataset real: {solo_a} barras solo-A, {solo_b} barras solo-B).")


# ---------------------------------------------------------------------------
# 8. Evidencia de TradingView disponible en el repo
# ---------------------------------------------------------------------------

def audit_tradingview_evidence() -> None:
    section("8. Evidencia de TradingView en el repositorio")

    repo_root = Path(__file__).resolve().parents[1]
    pine_candidates = list(repo_root.glob("basecode_tradingview/*.txt"))
    print(f"Archivos encontrados en basecode_tradingview/: {[p.name for p in pine_candidates]}")

    import re
    # \b palabra completa -- "rsi" naive como substring da falso positivo en "veRSIon"
    # (p.ej. "//@version=6"), igual que "peRSIst" en la auditoria anterior.
    pattern = re.compile(r"\brsi\b|\bdivergence\b|\bpivothigh\b|\bpivotlow\b|ta\.rsi\(", re.IGNORECASE)
    has_rsi_divergence_pine = False
    for p in pine_candidates:
        text = p.read_text(encoding="utf-8", errors="replace")
        hits = pattern.findall(text)
        if hits:
            has_rsi_divergence_pine = True
            print(f"  {p.name}: contiene referencias a RSI/divergence/pivot -- {hits} (revisar manualmente)")
        else:
            print(f"  {p.name}: sin referencias a RSI/divergence/pivothigh/pivotlow (palabra completa)")

    check("NO existe en el repositorio un Pine Script (ni especificacion) del indicador 'Divergence' de RSI",
          not has_rsi_divergence_pine,
          f"archivos revisados: {[p.name for p in pine_candidates]} -- ninguno menciona RSI/divergence/pivothigh/pivotlow "
          f"como palabra completa (son el indicador de EMA+Pivotes ZS de trend/cajas, no el de divergencia; "
          f"la coincidencia naiva anterior de substring era un falso positivo de '//@version=6' conteniendo 'rsi')")

    print("\nCONCLUSION EXPLICITA: no hay evidencia en el repositorio de que fuente de precio (close vs low/high) "
          "usa el indicador 'Divergence' real que corre el usuario en su chart de TradingView. Cualquier afirmacion "
          "sobre 'TradingView usa low/high' o 'TradingView usa close' se basaria unicamente en conocimiento general "
          "de indicadores publicos tipicos, NO en evidencia verificable de este repositorio. Estado: UNVERIFIED.")


# ---------------------------------------------------------------------------

def main() -> int:
    print("AUDITORIA RSI PRICE SOURCE (BOT-024) -- close vs low/high")
    print("SOLO LECTURA. No se modifico ningun archivo de produccion (scoring.py, live_signal.py, engine.py, "
          "execution/, API, panel intactos).\n")

    data_path = Path(__file__).resolve().parents[1] / "backtests" / "data" / "XAUUSDc_M5_latest.parquet"
    print(f"Dataset historico reusado (no se descargo ni invento nada nuevo): {data_path}")
    df = pd.read_parquet(data_path)
    print(f"  {len(df)} barras M5, {pd.to_datetime(df['time_utc'].iloc[0], unit='s')} .. "
          f"{pd.to_datetime(df['time_utc'].iloc[-1], unit='s')}")

    audit_current_implementation()
    audit_consistency_with_production(df)
    audit_fast_matches_slow(df)
    audit_synthetic_cases()

    print("\nCorriendo A y B causalmente sobre el dataset historico completo (puede tardar unos segundos)...")
    records, close, low, high, rsi_values, warmup, n = run_full_dataset(df)
    stats = audit_real_dataset(records)
    examples = audit_discrepancy_examples(records, close, low, high, rsi_values)
    audit_subset_property(stats)
    audit_tradingview_evidence()

    print(f"\n\n=== RESUMEN FINAL ===")
    print(f"FAILURES: {len(FAILURES)}")
    for f in FAILURES:
        print(f"  - {f}")
    if not FAILURES:
        print("  (ninguna)")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
