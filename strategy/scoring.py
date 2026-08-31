"""Calificacion de cada entrada -- Divergencia (RSI 14 close) + Tendencia
(multi-timeframe via bucket_levels) + CVP (breakeven neto vs aciertos% real).
Diseno cerrado con el usuario el 2026-08-31 (chat del panel), 3 factores:

  1. Divergencia: RSI(14, close), pivotes tipo ta.pivothigh/pivotlow de
     TradingView. +1 si la divergencia vigente apoya el sentido de la
     entrada, -1 si lo contradice, 0 si no hay ninguna vigente.
  2. Tendencia: bucket_levels() (el mismo bloque HTF que ya usa engine.py)
     corrido con dos ventanas de minutos distintas sobre la MISMA serie de
     barras -- sin pedir otro timeframe a MT5. +1 si ambas ventanas
     coinciden a favor, -1 si coinciden en contra, 0 si no coinciden entre
     si (sin tendencia clara / sin momentum).
  3. CVP (cost-volume-profit): margen = aciertos% real (medido de las
     operaciones YA cerradas por este bot, nunca de un backtest) menos el
     breakeven neto de ESTA entrada (SL/TP con spread+comision reales
     sumados). +1 si el margen es holgado, 0 si es marginal o si falta
     historial, nunca bloquea la entrada.

IMPORTANTE: este modulo solo CALIFICA una entrada que engine.py/
live_signal.py ya decidio -- no cambia si se opera ni el volumen. El "gate"
de CVP (rechazar la entrada si el margen da negativo) esta descripto en el
diseño pero deliberadamente DESACTIVADO en esta primera pasada: se registra
el numero y el motivo, nada mas.

Logica pura: sin MT5, sin red -- mismo espiritu y mismo estilo de test que
engine.py (ver strategy/test_scoring.py).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

RSI_PERIOD = 14

# Defaults del indicador "Divergence" estandar de TradingView -- no son los
# parametros reales configurados en el chart del usuario (todavia no los
# dio), son los defaults publicos del indicador. Ajustables aca el dia que
# se confirmen los propios (Pivot Lookback Left/Right, Range Min/Max).
DIVERGENCE_LB_LEFT = 5
DIVERGENCE_LB_RIGHT = 5
DIVERGENCE_RANGE_MIN = 5
DIVERGENCE_RANGE_MAX = 60
DIVERGENCE_FRESH_BARS = 10  # velas desde CONFIRMADO un pivote que sigue "vigente" (lag lbR + margen)

# Ventanas de tendencia (minutos), por perfil -- confirmadas por el usuario:
# 1m -> 15min y 60min; 5m -> 30min y 240min (4h).
TREND_WINDOWS_MIN: dict[str, tuple[int, int]] = {"1m": (15, 60), "5m": (30, 240)}
TREND_LOOKBACK_BLOCKS = 3  # cuantos bloques CERRADOS mira para la secuencia HH/HL o LH/LL

CVP_MIN_SAMPLE = 10        # operaciones cerradas minimas para confiar en aciertos_pct
CVP_MARGIN_HOLGADO = 10.0  # puntos porcentuales de margen para considerarse "holgado"


# ---- Divergencia -----------------------------------------------------------

def rsi(close: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
    """RSI de Wilder: suavizado exponencial (alpha=1/period) sembrado con el
    promedio simple de las primeras `period` variaciones -- formula estandar
    de Wilder, la misma que usa ta.rsi de Pine. NaN mientras no hay
    suficiente historial."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)
    for i in range(period + 1, n):
        g, l = gains[i - 1], losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass(frozen=True)
class Pivot:
    bar: int             # indice de la barra donde ESTA el pivote
    confirmed_bar: int    # indice desde el que se SABE que es un pivote real (bar + lbR)
    value: float


def find_confirmed_pivots(series: np.ndarray, lbL: int = DIVERGENCE_LB_LEFT,
                           lbR: int = DIVERGENCE_LB_RIGHT) -> tuple[list[Pivot], list[Pivot]]:
    """Replica ta.pivothigh/ta.pivotlow de Pine: series[i] es pivote alto si
    es el maximo ESTRICTO (unico) de la ventana [i-lbL, i+lbR] (pivote bajo:
    minimo estricto). Un pivote solo se sabe real desde confirmed_bar=i+lbR
    en adelante -- es el lag estructural inevitable de cualquier metodo de
    pivotes (mismo tipo de cosa que el bloque HTF, ver engine.bucket_levels)."""
    n = len(series)
    highs: list[Pivot] = []
    lows: list[Pivot] = []
    for i in range(lbL, n - lbR):
        v = series[i]
        if math.isnan(v):
            continue
        window = series[i - lbL:i + lbR + 1]
        if np.isnan(window).any():
            continue
        if v == window.max() and (window == v).sum() == 1:
            highs.append(Pivot(bar=i, confirmed_bar=i + lbR, value=v))
        if v == window.min() and (window == v).sum() == 1:
            lows.append(Pivot(bar=i, confirmed_bar=i + lbR, value=v))
    return highs, lows


def _most_recent_fresh(pivots: list[Pivot], current_bar: int, fresh_bars: int) -> Pivot | None:
    cands = [p for p in pivots
             if p.confirmed_bar <= current_bar and current_bar - p.confirmed_bar <= fresh_bars]
    return max(cands, key=lambda p: p.bar) if cands else None


def _prior_in_range(pivots: list[Pivot], latest: Pivot, range_min: int, range_max: int) -> Pivot | None:
    cands = [p for p in pivots if p.bar != latest.bar and range_min <= latest.bar - p.bar <= range_max]
    return max(cands, key=lambda p: p.bar) if cands else None


def _signed(direction: int, supports_direction: int, label: str) -> tuple[int, str]:
    if direction == supports_direction:
        return 1, f"{label} -- a favor de la entrada"
    return -1, f"{label} -- en contra de la entrada"


def divergence_score(direction: int, close: np.ndarray, rsi_values: np.ndarray, current_bar: int,
                      lbL: int = DIVERGENCE_LB_LEFT, lbR: int = DIVERGENCE_LB_RIGHT,
                      range_min: int = DIVERGENCE_RANGE_MIN, range_max: int = DIVERGENCE_RANGE_MAX,
                      fresh_bars: int = DIVERGENCE_FRESH_BARS) -> tuple[int, str]:
    """direction: -1 venta, +1 compra. current_bar: indice de la barra de la
    señal (la ultima de close/rsi_values). Busca el pivote de RSI mas
    reciente CONFIRMADO dentro de `fresh_bars` velas antes de current_bar, y
    lo compara contra el pivote previo del mismo tipo dentro de
    [range_min, range_max] velas de distancia -- divergencia regular
    (precio y RSI en sentido opuesto)."""
    highs, lows = find_confirmed_pivots(rsi_values[:current_bar + 1], lbL, lbR)

    # alcista regular: precio hace minimo mas BAJO, RSI hace minimo mas ALTO -- apoya COMPRA
    latest_low = _most_recent_fresh(lows, current_bar, fresh_bars)
    if latest_low is not None:
        prior_low = _prior_in_range(lows, latest_low, range_min, range_max)
        if prior_low is not None and close[latest_low.bar] < close[prior_low.bar] and latest_low.value > prior_low.value:
            return _signed(direction, +1, "divergencia alcista RSI vigente")

    # bajista regular: precio hace maximo mas ALTO, RSI hace maximo mas BAJO -- apoya VENTA
    latest_high = _most_recent_fresh(highs, current_bar, fresh_bars)
    if latest_high is not None:
        prior_high = _prior_in_range(highs, latest_high, range_min, range_max)
        if prior_high is not None and close[latest_high.bar] > close[prior_high.bar] and latest_high.value < prior_high.value:
            return _signed(direction, -1, "divergencia bajista RSI vigente")

    return 0, "sin divergencia vigente"


# ---- Tendencia --------------------------------------------------------------

def _closed_blocks(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, window_min: int):
    """Un (bucket_id, high_final, low_final) por cada bloque HTF ya CERRADO
    (el ultimo bloque, todavia en formacion, se excluye a proposito -- puede
    seguir creciendo)."""
    from .engine import bucket_levels  # import diferido: evita ciclo import si engine llegara a usar scoring

    bucket_len_s = window_min * 60
    bucket_id = time_utc // bucket_len_s
    resistencia, soporte = bucket_levels(time_utc, high, low, window_min)
    n = len(time_utc)
    blocks = []
    for i in range(n - 1):
        if bucket_id[i] != bucket_id[i + 1]:
            blocks.append((bucket_id[i], resistencia[i], soporte[i]))
    return blocks


def _classify_sequence(blocks, lookback_blocks: int) -> int | None:
    """1 = alcista (HH/HL en los ultimos `lookback_blocks` bloques cerrados),
    -1 = bajista (LH/LL), 0 = sin secuencia clara, None = historial insuficiente."""
    if len(blocks) < lookback_blocks:
        return None
    recent = blocks[-lookback_blocks:]
    highs = [b[1] for b in recent]
    lows = [b[2] for b in recent]
    if all(highs[i] > highs[i - 1] and lows[i] > lows[i - 1] for i in range(1, len(recent))):
        return 1
    if all(highs[i] < highs[i - 1] and lows[i] < lows[i - 1] for i in range(1, len(recent))):
        return -1
    return 0


def _trend_label(d: int | None) -> str:
    return {1: "alcista", -1: "bajista", 0: "sin secuencia clara", None: "historial insuficiente"}[d]


def trend_score(direction: int, time_utc: np.ndarray, high: np.ndarray, low: np.ndarray,
                 windows_min: tuple[int, int], lookback_blocks: int = TREND_LOOKBACK_BLOCKS) -> tuple[int, str]:
    """direction: -1 venta, +1 compra. windows_min: las dos ventanas de
    minutos a comparar (ver TREND_WINDOWS_MIN por perfil). +1 si ambas
    ventanas coinciden a favor de `direction`, -1 si coinciden en contra,
    0 si no coinciden entre si (o si a alguna le falta historial)."""
    w1, w2 = windows_min
    d1 = _classify_sequence(_closed_blocks(time_utc, high, low, w1), lookback_blocks)
    d2 = _classify_sequence(_closed_blocks(time_utc, high, low, w2), lookback_blocks)

    if d1 is None or d2 is None:
        return 0, f"historial insuficiente para clasificar tendencia (ventanas {w1}/{w2}min)"
    if d1 == 0 or d2 == 0 or d1 != d2:
        return 0, f"sin momentum claro -- {w1}min={_trend_label(d1)}, {w2}min={_trend_label(d2)}"

    supports = d1  # ambas ventanas coinciden
    label = f"tendencia {_trend_label(supports)} con momentum en {w1}min y {w2}min"
    return _signed(direction, supports, label)


# ---- CVP ---------------------------------------------------------------------

def cvp_score(direction: int, entry: float, stop: float, target: float, spread_price: float,
              commission_usd: float, fixed_lot: float, contract_size: float,
              aciertos_pct: float | None,
              min_sample: int = CVP_MIN_SAMPLE) -> tuple[int, str, float | None]:
    """Breakeven neto de ESTA entrada = SL_neto / (SL_neto + TP_neto), con
    spread y comision (convertida a precio equivalente) sumados al SL y
    restados del TP. margen = aciertos_pct real (medido en vivo, ver
    execution/src/bot.py) menos ese breakeven. El gate (rechazar si margen
    <=0) esta descripto pero DESACTIVADO aca a proposito -- ver docstring
    del modulo."""
    if aciertos_pct is None:
        return 0, f"datos insuficientes (menos de {min_sample} operaciones cerradas todavia)", None

    sl_price = abs(entry - stop)
    tp_price = abs(target - entry)
    commission_price = commission_usd / (contract_size * fixed_lot) if contract_size and fixed_lot else 0.0
    sl_neto = sl_price + spread_price + commission_price
    tp_neto = max(tp_price - spread_price - commission_price, 0.0)
    breakeven_pct = sl_neto / (sl_neto + tp_neto) * 100 if (sl_neto + tp_neto) > 0 else 100.0
    margen = aciertos_pct - breakeven_pct
    detalle = f"margen {margen:+.1f} pts ({aciertos_pct:.1f}% aciertos vs {breakeven_pct:.1f}% necesario)"

    if margen > CVP_MARGIN_HOLGADO:
        return 1, f"holgado -- {detalle}", margen
    if margen > 0:
        return 0, f"marginal -- {detalle}", margen
    return 0, f"no cubre costos -- {detalle} (gate desactivado en esta fase, se registra igual)", margen


# ---- Score total --------------------------------------------------------------

@dataclass(frozen=True)
class EntryScore:
    direction: int
    divergencia_score: int
    divergencia_reason: str
    tendencia_score: int
    tendencia_reason: str
    cvp_score: int
    cvp_reason: str
    cvp_margin: float | None
    total: int

    def to_dict(self) -> dict:
        return asdict(self)


def score_entry(direction: int, profile_name: str, entry: float, stop: float, target: float,
                 time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 spread_price: float, commission_usd: float, fixed_lot: float, contract_size: float,
                 aciertos_pct: float | None) -> EntryScore:
    """Punto de entrada unico: corre los 3 factores sobre la MISMA ventana de
    barras ya cerradas (time_utc/high/low/close, terminando en la barra de
    la señal) y arma el score total. No decide nada -- solo califica."""
    rsi_values = rsi(close)
    current_bar = len(close) - 1

    d_score, d_reason = divergence_score(direction, close, rsi_values, current_bar)

    windows = TREND_WINDOWS_MIN.get(profile_name)
    if windows is None:
        t_score, t_reason = 0, f"sin ventanas de tendencia definidas para perfil {profile_name!r}"
    else:
        t_score, t_reason = trend_score(direction, time_utc, high, low, windows)

    c_score, c_reason, c_margin = cvp_score(direction, entry, stop, target, spread_price,
                                             commission_usd, fixed_lot, contract_size, aciertos_pct)

    return EntryScore(
        direction=direction,
        divergencia_score=d_score, divergencia_reason=d_reason,
        tendencia_score=t_score, tendencia_reason=t_reason,
        cvp_score=c_score, cvp_reason=c_reason, cvp_margin=c_margin,
        total=d_score + t_score + c_score,
    )
