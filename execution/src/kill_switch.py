"""Calculo del P&L realizado del dia operativo -- BOT-032 (Kill switch /
maxima perdida diaria).

Logica pura de dominio, sin estado: dado un rango [day_start_utc, day_end_utc)
ya resuelto por `execution/src/operating_day.py`, calcula cuanto gano/perdio
ESTE bot (symbol+magic) en deals ya CERRADOS dentro de esa ventana. Nunca usa
P&L flotante de posiciones abiertas (`positions_get`) -- solo deals de
`history_deals_get()`, igual que `execution/src/bot.py::_aciertos_pct()` y
`api/app.py::history()`.

No persiste nada (ver `execution/src/kill_switch_store.py` para lo unico que
si se persiste: el override diario) -- el P&L se recalcula siempre desde MT5,
a proposito, para que un reinicio de la app nunca pueda evadir la proteccion
(BOT-032 #12/#14)."""
from __future__ import annotations

from datetime import datetime, timedelta

import MetaTrader5 as mt5

from .mt5_utils import filter_own_deals

# Cuanto hay que mirar hacia atras del inicio del dia operativo para poder
# identificar la POSICION de una operacion que cerro hoy pero abrio antes de
# hoy (ej. una operacion de varios dias) -- filter_own_deals() necesita ver
# el deal de APERTURA (entry=IN) para anclar el magic+simbolo con seguridad;
# si esa apertura quedara fuera de la ventana consultada a MT5, el deal de
# cierre de hoy no se atribuiria a ninguna posicion propia y se perderia del
# calculo. 60 dias es un margen generoso frente a max_bars_trade/valid_bars
# tipicos del bot (spec-estrategia.md #5), sin ser una consulta cara.
POSITION_LOOKBACK_DAYS = 60


def daily_realized_pnl(symbol: str, magic: int, day_start_utc: datetime, day_end_utc: datetime,
                        lookback_days: int = POSITION_LOOKBACK_DAYS) -> float | None:
    """P&L neto (profit+swap+commission+fee) de los deals de CIERRE
    (DEAL_ENTRY_OUT) de posiciones propias cuyo timestamp cae dentro de
    [day_start_utc, day_end_utc). `None` si no se pudo consultar MT5 -- nunca
    se asume 0.0 (fail-safe, ver BOT-032 #19 y bot.py::_refresh_kill_switch_state)."""
    wide_from = day_end_utc - timedelta(days=lookback_days)
    deals = mt5.history_deals_get(wide_from, day_end_utc)
    if deals is None:
        return None
    own = filter_own_deals(deals, magic, symbol)
    day_start_s = day_start_utc.timestamp()
    day_end_s = day_end_utc.timestamp()
    closed_today = [d for d in own
                    if d.entry == mt5.DEAL_ENTRY_OUT and day_start_s <= d.time < day_end_s]
    return sum((d.profit or 0.0) + (d.swap or 0.0) + (d.commission or 0.0) + getattr(d, "fee", 0.0)
               for d in closed_today)
