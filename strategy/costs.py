"""Modelo de costos: spread real por vela, comision explicita, swap por rollover.

Ver docs/spec-backtest.md #3. Nada de esto se hardcodea a un broker: los
valores de punto/tick/swap se leen de symbol_info en tiempo de ejecucion (ver
scripts/03_run_sweep.py); esta clase solo aplica la formula.

BOT-043 (2026-09-14): la conversion de una diferencia de PRECIO a USD reales
NO es `diff * contract_size * lot` -- eso asume que `contract_size` equivale
a "USD por unidad de precio por lote 1.0", lo cual solo es cierto por
casualidad en algunos simbolos (ej. contract_size=100, tick_size=0.01,
tick_value=1 -> tick_value/tick_size=100=contract_size) pero NO en general.
Se valido contra `mt5.order_calc_profit()` (la referencia de la propia
plataforma) sobre XAUUSDc de esta cuenta: contract_size=1.0 pero
tick_value/tick_size=100 -- la formula vieja infravaloraba el PnL/riesgo real
en precio por un factor de 100x. La formula correcta, validada bar a bar
contra `order_calc_profit()`, es `price_to_usd()` mas abajo. `contract_size`
se conserva en el dataclass solo a titulo informativo (no se usa para
convertir precio->USD en ningun metodo de esta clase)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class BrokerCosts:
    point: float                  # tamano de un punto de precio del simbolo
    contract_size: float          # unidades por lote (ej. 100 oz para XAUUSD) -- SOLO informativo,
                                   # ver nota BOT-043 arriba: NO usar para convertir precio->USD
    tick_value: float             # USD por movimiento de tick_size, por lote 1.0 (symbol_info().trade_tick_value)
    tick_size: float              # minimo movimiento de precio cotizable (symbol_info().trade_tick_size) --
                                   # junto con tick_value, la conversion precio->USD correcta (BOT-043)
    swap_long_points: float       # symbol_info().swap_long, en PUNTOS de precio (point)/lote/noche
    swap_short_points: float      # symbol_info().swap_short, en PUNTOS de precio (point)/lote/noche
    commission_per_lot: float = 0.0   # USD, round-turn, por lote — no consultable via API
    triple_swap_weekday: int = 2      # 0=lunes .. 6=domingo; default miercoles (a confirmar, ver spec #3.3)
    spread_fallback_points: float | None = None  # si una vela no trae 'spread'

    def price_to_usd(self, price_diff: float, lot: float) -> float:
        """Convierte una diferencia de PRECIO (mismas unidades que entry/stop/
        target/close, no puntos) a USD reales para `lot` lotes. Formula nativa
        de MT5 (independiente de contract_size), validada bar a bar contra
        `mt5.order_calc_profit()` en BOT-043 -- ver nota de modulo. Unico
        punto de conversion precio->USD de todo el motor: lo usan tanto el
        PnL de precio (engine.py) como el riesgo de 1R (mismo denominador,
        misma formula, para que R quede bien definido)."""
        return price_diff / self.tick_size * self.tick_value * lot

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
        """USD (signo incluido: negativo = costo real para el trader, positivo
        = credito) por lote 1.0 por noche. swap_long/swap_short de MT5 vienen
        en PUNTOS de precio (swap_mode POINTS) -- se convierten a precio con
        `* self.point` y de ahi a USD con la MISMA formula de price_to_usd()
        que el resto del motor (BOT-043), en vez de asumir point==tick_size."""
        points = self.swap_long_points if direction > 0 else self.swap_short_points
        return self.price_to_usd(points * self.point, lot=1.0)

    def swap_total_usd(self, direction: int, fixed_lot: float, open_date: date, close_date: date) -> float:
        """Swap total acumulado (CON SIGNO -- negativo = costo, ver
        swap_usd_per_lot_per_night) por todas las medianoches (rollovers) del
        broker que la posicion paso abierta, con el dia designado cobrado
        triple. El llamador debe SUMAR este valor al PnL (`pnl_usd +=
        swap_total_usd(...)`), nunca restarlo -- restar un costo ya negativo
        lo acreditaria (BOT-043)."""
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
