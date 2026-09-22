"""Signal Quality v1 -- BOT-051.4, primera implementacion productiva.

Contrato congelado (no reinterpretado aca): `reports/BOT-051.2-signal-
quality-contract.json` / `reports/BOT-051.2-signal-quality-definition-
freeze.md`. Los cuatro factores y sus fuentes de research:

    Momentum  = roc_atr_3            RAW continuo    BOT-024.4
    Alignment = Structural Consensus categorico       BOT-047.2.3
    Structure = origin_dist_atr      RAW continuo    BOT-048.2
    Context   = weekday              categorico       BOT-050.2

Economics: AUSENTE (BOT-049.2, NO_VALID_ECONOMICS_FREEZE) -- no es un campo
de este modulo, ni `null` ni `UNAVAILABLE`.

Principio de diseño de esta tarea: UNA sola funcion (`compute_signal_
quality_at_bar`) calcula el vector completo a partir de arrays de mercado
truncados en `b` -- la usan tanto el bot en vivo (`execution/src/bot.py`,
donde `b == len(ventana_traida)-1`) como el script de paridad historica
(`scripts/verify_signal_quality_live_parity_xau.py`, donde `b` es el
`limit_created_bar` real de cada uno de los 3.207 eventos de `BOT-051.3`).
Mismo codigo, mismo resultado -- no hay una version "para produccion" y otra
"para research" que puedan divergir.

Reusa sin modificar: `strategy.engine.ema`/`bucket_levels`,
`strategy.scoring._classify_sequence`/`_closed_blocks`/
`_closed_blocks_session_anchored`, `strategy.scoring.TREND_LOOKBACK_BLOCKS`.
No importa nada de `backtests/`, `reports/` ni de los scripts de research
offline (direccion de dependencia correcta, ver seccion 6 del enunciado de
BOT-051.4) -- `atr_wilder()` de aca es la implementacion canonica unica; los
scripts offline pueden actualizarse para importarla (ver
`scripts/signal_quality_vector.py`).

Puramente observacional: ninguna funcion de este modulo lee ni puede leer
`pnl_r`/`pnl_usd`/`outcome`/`fill_bar`/MFE/MAE -- no existe ningun parametro
por el que esa informacion podria pasarse (ver
strategy/test_signal_quality.py, seccion de no-outcome-leakage).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, Literal, Optional, TypeVar

import numpy as np

from . import engine
from . import scoring

SCHEMA_VERSION = "1.0.0"

ALIGNMENT_STATES = frozenset({
    "AGAINST_CONFIRMED", "AGAINST_SINGLE", "NEUTRAL",
    "ALIGNED_SINGLE", "ALIGNED_CONFIRMED",
})
WEEKDAY_STATES = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)
_WEEKDAY_STATES_SET = frozenset(WEEKDAY_STATES)

ATR_PERIOD = 14
MOMENTUM_LOOKBACK_BARS = 3          # roc_atr_3 -- BOT-024.4
D1_WINDOW_MIN = 1440                # 24h -- misma constante que htf_session.MINUTES_PER_DAY

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Esquema tipado (BOT-051.2, promovido aca desde scripts/signal_quality_vector.py
# -- unica fuente de verdad, ver seccion 8 del enunciado de BOT-051.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FactorObservation(Generic[T]):
    """Wrapper unico de disponibilidad para los 4 factores (BOT-051.2 seccion
    4): `status` es una proyeccion determinista del contrato congelado de
    cada factor, nunca un segundo juicio independiente. `value` presente y no
    nulo ssi `status == AVAILABLE`; `None` ssi `status == UNAVAILABLE` --
    nunca un sentinel numerico (nunca 0, nunca un promedio)."""
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    value: Optional[T]

    def __post_init__(self) -> None:
        if self.status == "AVAILABLE" and self.value is None:
            raise ValueError("FactorObservation: status=AVAILABLE requiere un value no nulo")
        if self.status == "UNAVAILABLE" and self.value is not None:
            raise ValueError("FactorObservation: status=UNAVAILABLE debe tener value=None (nunca un sentinel numerico)")


@dataclass(frozen=True)
class SignalQualityVectorV1:
    """Congelado en reports/BOT-051.2-signal-quality-contract.json. Exactamente
    cuatro dimensiones de quality mas `direction` como metadata obligatoria.
    Economics esta ausente por diseño -- no hay ningun campo para eso aca."""
    schema_version: str
    observed_at_bar: int
    observed_at_time_utc: datetime
    direction: Literal["LONG", "SHORT"]
    momentum: FactorObservation[float]
    alignment: FactorObservation[str]
    structure: FactorObservation[float]
    context: FactorObservation[str]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version inesperado {self.schema_version!r}, se esperaba {SCHEMA_VERSION!r}")
        if self.direction not in ("LONG", "SHORT"):
            raise ValueError(f"direction debe ser LONG o SHORT, se recibio {self.direction!r}")
        if self.alignment.status == "AVAILABLE" and self.alignment.value not in ALIGNMENT_STATES:
            raise ValueError(f"alignment.value {self.alignment.value!r} no es uno de los 5 estados sustantivos congelados")
        if self.context.status == "AVAILABLE" and self.context.value not in _WEEKDAY_STATES_SET:
            raise ValueError(f"context.value {self.context.value!r} no es un dia de semana valido")

    def to_dict(self) -> dict:
        """Serializacion plana para persistencia (execution/src/score_store.py)
        -- misma forma ilustrada en reports/BOT-051.2-signal-quality-contract.json."""
        def _fo(fo: FactorObservation) -> dict:
            return {"status": fo.status, "value": fo.value}
        return {
            "schema_version": self.schema_version,
            "observed_at_bar": self.observed_at_bar,
            "observed_at_time_utc": self.observed_at_time_utc.isoformat(),
            "direction": self.direction,
            "momentum": _fo(self.momentum),
            "alignment": _fo(self.alignment),
            "structure": _fo(self.structure),
            "context": _fo(self.context),
        }


def _float_observation(raw_value) -> FactorObservation[float]:
    """Momentum/Structure: RAW continuo, UNAVAILABLE ssi el valor crudo es
    NaN/None."""
    if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=float(raw_value))


def _alignment_observation(raw_state: str) -> FactorObservation[str]:
    """Alignment: `status` es una proyeccion 1:1 del propio enum congelado del
    factor -- `raw_state=="UNAVAILABLE"` es la UNICA fuente de verdad de
    indisponibilidad aca."""
    if raw_state == "UNAVAILABLE":
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=raw_state)


def _context_observation(raw_weekday) -> FactorObservation[str]:
    if raw_weekday is None:
        return FactorObservation(status="UNAVAILABLE", value=None)
    return FactorObservation(status="AVAILABLE", value=str(raw_weekday))


def produce_signal_quality_vector(
    *,
    observed_at_bar: int,
    observed_at_time_utc: datetime,
    direction: Literal["LONG", "SHORT"],
    roc_atr_3: Optional[float],
    alignment_consensus_state: str,
    origin_dist_atr: Optional[float],
    weekday: Optional[str],
) -> SignalQualityVectorV1:
    """Unico camino de ensamblado. Acepta valores YA computados de los 4
    factores congelados (nunca recalcula una feature aca mismo) y devuelve un
    vector tipado, validado y congelado (`@dataclass(frozen=True)`, en los dos
    niveles)."""
    return SignalQualityVectorV1(
        schema_version=SCHEMA_VERSION,
        observed_at_bar=observed_at_bar,
        observed_at_time_utc=observed_at_time_utc,
        direction=direction,
        momentum=_float_observation(roc_atr_3),
        alignment=_alignment_observation(alignment_consensus_state),
        structure=_float_observation(origin_dist_atr),
        context=_context_observation(weekday),
    )


# ---------------------------------------------------------------------------
# ATR-Wilder -- implementacion canonica unica (BOT-051.4 seccion 6.1)
# ---------------------------------------------------------------------------

def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = ATR_PERIOD) -> np.ndarray:
    """Average True Range de Wilder -- suavizado recursivo, `atr[i]` depende
    UNICAMENTE de `high/low/close[0..i]` (causal por construccion, sin
    lookahead posible). Formula identica, verbatim, a la que ya usaban
    duplicada `backtests/scripts/07_bot045_regime_dataset.py::atr_wilder` y
    cada script offline de la linea BOT-024.2/BOT-047.x/BOT-048.x/BOT-049.x/
    BOT-050.x/BOT-051.1/.2/.3 -- esta es ahora la UNICA implementacion,
    reutilizable desde produccion (antes no existia ninguna copia dentro de
    `strategy/`). Verificada por paridad exhaustiva contra los valores ya
    publicados de `roc_atr_3`/`origin_dist_atr` -- ver
    reports/BOT-051.4-signal-quality-live-parity-xau.csv."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n <= period:
        return atr
    atr[period] = tr[1:period + 1].mean()
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


# ---------------------------------------------------------------------------
# Alignment -- Structural Alignment Consensus (BOT-047.2.3)
# ---------------------------------------------------------------------------

def _alignment_label(state: int | None, direction_sign: int) -> str:
    """Identico a `alignment_label()` de
    scripts/analyze_d1_structural_alignment_xau.py (BOT-047.2.1, reusado sin
    modificar en toda la linea BOT-047.x/BOT-051.x)."""
    if state is None:
        return "UNAVAILABLE"
    if state == 0:
        return "NEUTRAL_MIXED"
    return "ALIGNED" if state == direction_sign else "AGAINST"


def _consensus(b0_alignment: str, b1_alignment: str) -> str:
    """Regla de consenso exacta congelada en reports/BOT-047.2.3-STRUCTURAL-
    ALIGNMENT-CONSENSUS-FREEZE.md (reusada verbatim, verificada de nuevo en
    BOT-051.1/.2/.3 contra la distribucion ya publicada -- 0 discrepancias)."""
    if b0_alignment == "UNAVAILABLE" or b1_alignment == "UNAVAILABLE":
        return "UNAVAILABLE"
    if b0_alignment == "AGAINST" and b1_alignment == "AGAINST":
        return "AGAINST_CONFIRMED"
    if b0_alignment == "ALIGNED" and b1_alignment == "ALIGNED":
        return "ALIGNED_CONFIRMED"
    against_count = (b0_alignment == "AGAINST") + (b1_alignment == "AGAINST")
    aligned_count = (b0_alignment == "ALIGNED") + (b1_alignment == "ALIGNED")
    if against_count == 1 and (b0_alignment == "NEUTRAL_MIXED" or b1_alignment == "NEUTRAL_MIXED"):
        return "AGAINST_SINGLE"
    if aligned_count == 1 and (b0_alignment == "NEUTRAL_MIXED" or b1_alignment == "NEUTRAL_MIXED"):
        return "ALIGNED_SINGLE"
    if b0_alignment == "NEUTRAL_MIXED" and b1_alignment == "NEUTRAL_MIXED":
        return "NEUTRAL"
    return "UNAVAILABLE"  # flip directo AGAINST<->ALIGNED -- N=0 observado historicamente
                            # (BOT-047.2.3); nunca se fuerza un estado no definido por el
                            # contrato -- UNAVAILABLE, no un valor adivinado.


def compute_alignment_consensus(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray,
                                 direction_sign: int,
                                 lookback_blocks: int = scoring.TREND_LOOKBACK_BLOCKS,
                                 d1_window_min: int = D1_WINDOW_MIN) -> str:
    """B0 (legacy, `scoring._closed_blocks` -- ya en produccion, usada para
    Tendencia/BOT-023, reusada tal cual con window_min=1440) + B1 (canonico,
    `scoring._closed_blocks_session_anchored`, agregada en esta tarea) +
    `scoring._classify_sequence` (identica funcion que ya usa Tendencia) +
    consenso congelado en BOT-047.2.3."""
    b0_blocks = scoring._closed_blocks(time_utc, high, low, d1_window_min)
    b1_blocks = scoring._closed_blocks_session_anchored(time_utc, high, low, d1_window_min)
    b0_state = scoring._classify_sequence(b0_blocks, lookback_blocks)
    b1_state = scoring._classify_sequence(b1_blocks, lookback_blocks)
    b0_alignment = _alignment_label(b0_state, direction_sign)
    b1_alignment = _alignment_label(b1_state, direction_sign)
    return _consensus(b0_alignment, b1_alignment)


# ---------------------------------------------------------------------------
# Structure -- origin_dist_atr (BOT-048.2): necesita el origen del ultimo
# armado antes de que la señal disparara.
# ---------------------------------------------------------------------------

def _replay_armado_origin(time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                           ema_line: np.ndarray, resistencia: np.ndarray, soporte: np.ndarray) -> dict:
    """Extrae SOLO el bookkeeping de armado/origen del loop de
    `engine.run_backtest()` (sin pending/open_pos/counters -- esos no afectan
    las transiciones de armado y no hacen falta para Structure). Mismo
    algoritmo, verbatim, que `scripts/discover_structure_features_xau.py`
    (BOT-048.1, verificado 0/2.474 discrepancias contra `run_backtest()` real
    + 0/41 re-slice causal). Devuelve el origen (bar, level) para CADA
    direccion tal como estaba INMEDIATAMENTE ANTES del posible re-armado de
    la ULTIMA barra -- el mismo snapshot "prev_origin" que usa una señal que
    dispare en esa barra. Tambien devuelve si, replayando esta ventana, SI
    dispararia señal en la ultima barra y en que direccion -- chequeo de
    autoconsistencia que usa el llamador en vivo (ver
    execution/src/bot.py::_compute_signal_quality) para descartar Structure/
    Alignment si la ventana no alcanzo a capturar el armado real."""
    n = len(close)
    armado_venta = armado_compra = False
    origin_venta = origin_compra = None
    prev_origin_venta = prev_origin_compra = None
    senal_venta = senal_compra = False
    for i in range(n):
        r_i, s_i = resistencia[i], soporte[i]
        prev_origin_venta = origin_venta
        prev_origin_compra = origin_compra
        if i == 0:
            down = up = False
        else:
            down = close[i - 1] >= ema_line[i - 1] and close[i] < ema_line[i]
            up = close[i - 1] <= ema_line[i - 1] and close[i] > ema_line[i]
        senal_venta = armado_venta and down
        senal_compra = armado_compra and up
        if senal_venta:
            armado_venta = False
        if senal_compra:
            armado_compra = False
        if not math.isnan(r_i) and high[i] >= r_i:
            armado_venta = True
            origin_venta = {"bar": i, "level": float(r_i)}
        if not math.isnan(s_i) and low[i] <= s_i:
            armado_compra = True
            origin_compra = {"bar": i, "level": float(s_i)}
    return {
        "venta": prev_origin_venta, "compra": prev_origin_compra,
        "senal_venta_at_last_bar": senal_venta, "senal_compra_at_last_bar": senal_compra,
    }


# ---------------------------------------------------------------------------
# Context -- weekday (BOT-050.2): enum RAW completo, locale-independiente.
# ---------------------------------------------------------------------------

def _weekday_from_unix(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return WEEKDAY_STATES[dt.weekday()]  # datetime.weekday(): 0=Monday..6=Sunday, no depende de locale


# ---------------------------------------------------------------------------
# Orquestacion -- una sola funcion, usada por produccion (execution/src/bot.py)
# y por el script de paridad historica.
# ---------------------------------------------------------------------------

def compute_signal_quality_at_bar(
    time_utc: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
    b: int, direction: int, entry: float,
    ema_periods: int, periodos_htf_min: int,
    observed_at_bar: int,
) -> tuple[SignalQualityVectorV1, dict]:
    """Calcula SignalQualityVectorV1 causalmente en la barra `b`, usando
    UNICAMENTE `time_utc/high/low/close[0:b+1]` -- nunca nada con indice > b.
    `direction`: +1 LONG, -1 SHORT (misma convencion que engine.py). `entry`:
    el valor YA CALCULADO por el motor de señal real (nunca recalculado aca,
    ver seccion 7 del enunciado de BOT-051.4).

    Devuelve (vector, diagnostics) -- diagnostics incluye
    `structure_replay_matches_signal` (True/False/None), que el llamador en
    vivo puede usar para decidir si confiar en Structure/origin_dist_atr
    dada la ventana de historia efectivamente disponible."""
    t = time_utc[:b + 1]
    h = high[:b + 1]
    l = low[:b + 1]
    c = close[:b + 1]

    ema_line = engine.ema(c, ema_periods)
    resistencia, soporte = engine.bucket_levels(t, h, l, periodos_htf_min)
    atr = atr_wilder(h, l, c, period=ATR_PERIOD)
    atr_b = atr[-1]
    atr_ok = not math.isnan(atr_b) and atr_b > 0

    # --- Momentum: roc_atr_3 ---
    roc_atr_3 = None
    j = b - MOMENTUM_LOOKBACK_BARS
    if j >= 0 and atr_ok:
        roc_atr_3 = direction * (c[-1] - c[j]) / atr_b

    # --- Structure: origin_dist_atr ---
    replay = _replay_armado_origin(t, h, l, c, ema_line, resistencia, soporte)
    origin = replay["venta"] if direction < 0 else replay["compra"]
    replay_matches = (
        (direction < 0 and replay["senal_venta_at_last_bar"]) or
        (direction > 0 and replay["senal_compra_at_last_bar"])
    )
    origin_dist_atr = None
    if origin is not None and atr_ok and replay_matches:
        origin_dist_atr = direction * (entry - origin["level"]) / atr_b

    # --- Alignment: Structural Consensus ---
    direction_sign = 1 if direction > 0 else -1
    alignment_state = compute_alignment_consensus(t, h, l, direction_sign)

    # --- Context: weekday ---
    weekday = _weekday_from_unix(int(t[-1]))

    vector = produce_signal_quality_vector(
        observed_at_bar=observed_at_bar,
        observed_at_time_utc=datetime.fromtimestamp(int(t[-1]), tz=timezone.utc),
        direction="LONG" if direction > 0 else "SHORT",
        roc_atr_3=roc_atr_3,
        alignment_consensus_state=alignment_state,
        origin_dist_atr=origin_dist_atr,
        weekday=weekday,
    )
    diagnostics = {
        "structure_replay_matches_signal": replay_matches,
        "origin_bar": origin["bar"] if origin else None,
        "n_bars_used": len(c),
    }
    return vector, diagnostics
