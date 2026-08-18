"""Medicion del offset horario del servidor de un broker MT5 contra UTC.

Ver docs/spec-estrategia.md #3.1 y docs/spec-backtest.md #2.1: en vez de
asumir la zona horaria de un broker en particular, se mide en vivo con un
tick reciente (symbol_info_tick, que trae su propio timestamp de servidor)
comparado contra el reloj UTC del sistema en el instante exacto de la
consulta. Funciona igual sin importar que broker sea.
"""
from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5


def measure_broker_offset_seconds(symbol: str, samples: int = 3) -> float:
    """Devuelve el offset (segundos) del servidor del broker respecto a UTC.

    offset > 0  => el reloj del servidor va ADELANTADO respecto a UTC.
    offset < 0  => el reloj del servidor va ATRASADO respecto a UTC.

    Se promedian varias muestras para amortiguar el jitter de red/latencia
    entre la consulta y la respuesta.
    """
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar el simbolo {symbol!r}: {mt5.last_error()}")

    offsets = []
    for _ in range(samples):
        t0 = datetime.now(timezone.utc).timestamp()
        tick = mt5.symbol_info_tick(symbol)
        t1 = datetime.now(timezone.utc).timestamp()
        if tick is None:
            continue
        local_mid = (t0 + t1) / 2.0
        offsets.append(tick.time - local_mid)

    if not offsets:
        raise RuntimeError(f"No se pudo obtener ningun tick de {symbol!r} para medir el offset: {mt5.last_error()}")

    return sum(offsets) / len(offsets)
