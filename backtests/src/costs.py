"""Modelo de costos: spread real por vela, comision explicita, swap por rollover.

Ver docs/spec-backtest.md #3. Nada de esto se hardcodea a un broker: los
valores de punto/contrato/tick_value/swap se leen de symbol_info en tiempo de
ejecucion (ver scripts/03_run_sweep.py); esta clase solo aplica la formula.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class BrokerCosts:
    point: float                  # tamano de un punto de precio del simbolo
    contract_size: float          # unidades por lote (ej. 100 oz para XAUUSD)
    tick_value: float             # USD por tick (point) por lote 1.0
    swap_long_points: float       # symbol_info().swap_long, en puntos/lote/noche
    swap_short_points: float      # symbol_info().swap_short, en puntos/lote/noche
    commission_per_lot: float = 0.0   # USD, round-turn, por lote — no consultable via API
    triple_swap_weekday: int = 2      # 0=lunes .. 6=domingo; default miercoles (a confirmar, ver spec #3.3)
    spread_fallback_points: float | None = None  # si una vela no trae 'spread'

    def spread_price(self, bar_spread_points: float) -> float:
        pts = bar_spread_points
        invalid = pts is None or (isinstance(pts, float) and math.isnan(pts)) or pts <= 0
        if invalid:
            if self.spread_fallback_points is None:
                raise ValueError("Vela sin spread valido y sin spreadFallbackPts configurado")
            pts = self.spread_fallback_points
        return pts * self.point

    def adjust_entry_price(self, direction: int, price: float, spread_price: float) -> float:
        # vender (direction<0) al bid (peor, mas bajo); comprar (direction>0) al ask (peor, mas alto)
        return price - spread_price / 2.0 if direction < 0 else price + spread_price / 2.0

    def adjust_exit_price(self, direction: int, price: float, spread_price: float) -> float:
        # cerrar un corto = comprar = ask (peor, mas alto); cerrar un largo = vender = bid (peor, mas bajo)
        return price + spread_price / 2.0 if direction < 0 else price - spread_price / 2.0

    def swap_usd_per_lot_per_night(self, direction: int) -> float:
        points = self.swap_long_points if direction > 0 else self.swap_short_points
        return points * self.tick_value

    def swap_total_usd(self, direction: int, fixed_lot: float, open_date: date, close_date: date) -> float:
        """Swap total acumulado por todas las medianoches (rollovers) del broker
        que la posicion paso abierta, con el dia designado cobrado triple."""
        if close_date <= open_date:
            return 0.0
        per_night = self.swap_usd_per_lot_per_night(direction) * fixed_lot
        total = 0.0
        d = open_date + timedelta(days=1)
        while d <= close_date:
            mult = 3 if d.weekday() == self.triple_swap_weekday else 1
            total += per_night * mult
            d += timedelta(days=1)
        return total

    def commission_usd(self, fixed_lot: float) -> float:
        return self.commission_per_lot * fixed_lot
