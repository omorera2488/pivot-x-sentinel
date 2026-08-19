"""Motor de señal incremental — misma logica de engine.py (EMA, bloque HTF,
armado, señal), pero bar-a-bar en vez de sobre un array completo. Lo usa
/execution (Fase 4): en vivo no existe un array de velas completo, llegan una
por una, y el estado de armado tiene que persistir entre llamadas.

No maneja el ciclo de vida de la orden (pendiente/abierta) — eso en vivo lo
gestiona /execution contra el estado real del broker, no en memoria (ver
docs/spec-live-execution.md #1). Esta clase solo decide SI y CON QUE
parametros se dispara una señal nueva en la barra que se le pasa.

Sin MT5, sin red — logica pura, igual que engine.py. Debe producir
exactamente los mismos resistencia/soporte/armado/señal que engine.py
corrido en modo batch sobre la misma secuencia de barras — ver
strategy/test_live_signal.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .engine import StrategyParams


@dataclass
class BarSignal:
    dir: int | None          # -1 venta, +1 compra, None si no hubo señal esta barra
    entry: float | None
    stop: float | None
    target: float | None
    valido: bool              # False si hubo señal pero el stop quedo del lado incorrecto (spec-estrategia #4.4)
    resistencia: float
    soporte: float
    ema: float
    armado_venta: bool        # estado DESPUES de procesar esta barra
    armado_compra: bool


class LiveSignalEngine:
    """Estado persistente de armado/bloque HTF/EMA, actualizado una barra
    cerrada a la vez, en orden. Ver docs/spec-live-execution.md #3/#4 para el
    protocolo de arranque (replay) y de deteccion de vela cerrada."""

    def __init__(self, params: StrategyParams):
        self.params = params
        self._alpha = 2.0 / (params.ema_periods + 1)
        self._buf = params.buf_bp / 10000.0

        self.armado_venta = False
        self.armado_compra = False

        self._ema_prev: float | None = None
        self._close_prev: float | None = None

        self._bucket_len_s = params.periodos_htf_min * 60
        self._cur_bucket = None
        self._cur_high = math.nan
        self._cur_low = math.nan
        self._prev_high = math.nan
        self._prev_low = math.nan
        self._have_prev_bucket = False

    def process_bar(self, time_utc: int, high: float, low: float, close: float) -> BarSignal:
        # --- EMA (misma formula que engine.ema: arranca en la primera barra,
        # sin sembrar con SMA — ver docs/spec-estrategia.md #4.1) ---
        ema_now = close if self._ema_prev is None else close * self._alpha + self._ema_prev * (1 - self._alpha)

        # --- bloque HTF (engine.bucket_levels, incremental) ---
        bucket_id = time_utc // self._bucket_len_s
        if self._cur_bucket is None:
            self._cur_bucket = bucket_id
            self._cur_high, self._cur_low = high, low
        elif bucket_id != self._cur_bucket:
            self._prev_high, self._prev_low = self._cur_high, self._cur_low
            self._have_prev_bucket = True
            self._cur_bucket = bucket_id
            self._cur_high, self._cur_low = high, low
        else:
            if high > self._cur_high:
                self._cur_high = high
            if low < self._cur_low:
                self._cur_low = low

        resistencia = self._prev_high if self._have_prev_bucket else math.nan
        soporte = self._prev_low if self._have_prev_bucket else math.nan

        # --- cruce + señal (con el armado tal como quedo de barras anteriores) ---
        if self._close_prev is None:
            senal_venta = senal_compra = False
        else:
            down = self._close_prev >= self._ema_prev and close < ema_now
            up = self._close_prev <= self._ema_prev and close > ema_now
            senal_venta = self.armado_venta and down
            senal_compra = self.armado_compra and up

        if senal_venta:
            self.armado_venta = False
        if senal_compra:
            self.armado_compra = False
        if not math.isnan(resistencia) and high >= resistencia:
            self.armado_venta = True
        if not math.isnan(soporte) and low <= soporte:
            self.armado_compra = True

        # --- stop/target si hubo señal ---
        d = entry = stop = target = None
        valido = True
        if senal_venta or senal_compra:
            d = -1 if senal_venta else 1
            entry = ema_now
            stop = resistencia * (1 + self._buf) if d < 0 else soporte * (1 - self._buf)
            valido = (stop > entry) if d < 0 else (stop < entry)
            if valido:
                risk = abs(stop - entry)
                target = entry - self.params.rr * risk if d < 0 else entry + self.params.rr * risk
            else:
                target = None

        self._ema_prev = ema_now
        self._close_prev = close

        return BarSignal(
            dir=d, entry=entry, stop=stop, target=target, valido=valido,
            resistencia=resistencia, soporte=soporte, ema=ema_now,
            armado_venta=self.armado_venta, armado_compra=self.armado_compra,
        )
