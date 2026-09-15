"""Dia operativo -- BOT-032 (Kill switch / maxima perdida diaria).

Hasta esta US el bot no tenia ningun concepto de "dia" (ver
docs/reports/AUDIT-BOT032_day_definition.md): todo lo que agrega P&L
(`execution/src/bot.py::_aciertos_pct()`, `api/app.py::history()`) usa
ventanas moviles de N dias desde `datetime.now(timezone.utc)`, nunca una
frontera de medianoche.

Este modulo define esa frontera por primera vez, de forma explicita y
timezone-aware -- NO como "UTC menos 6 horas" a mano (eso se rompe apenas la
zona tenga horario de verano), sino delegando el calculo completo a la base
de datos IANA via `zoneinfo` (stdlib desde Python 3.9). Asi, si en el futuro
se cambia `DEFAULT_OPERATING_TIMEZONE` a una zona con DST, la logica sigue
siendo correcta sin tocar una sola linea de aritmetica.

Nota de packaging: `zoneinfo` necesita el paquete `tzdata` instalado para
resolver nombres IANA en Windows (el SO no trae la base de datos como Linux/
macOS) -- ver `execution/requirements.txt` y `packaging/pivot_x_sentinel.spec`.
Verificado en esta misma maquina: sin `tzdata`, `ZoneInfo("America/Costa_Rica")`
lanza `ZoneInfoNotFoundError`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Fuente de verdad unica de la zona horaria del "dia operativo" -- el backend
# decide esto, nunca el navegador/PC del cliente (ver panel/calendar.html,
# que consume `operating_timezone` via GET /status en vez de agrupar por
# hora local del navegador). Para adaptar esta instalacion a otro pais/
# broker, cambiar solo esta constante -- el resto de la aritmetica (DST
# incluido) sigue funcionando sola.
DEFAULT_OPERATING_TIMEZONE = "America/Costa_Rica"


def operating_day_bounds_utc(
    now_utc: datetime,
    tz_name: str = DEFAULT_OPERATING_TIMEZONE,
) -> tuple[datetime, datetime, date]:
    """Limites [inicio, fin) del dia operativo que contiene `now_utc`, en UTC
    real, mas la fecha operativa misma (fecha calendario en `tz_name`).

    Un dia operativo es 00:00:00 -> 00:00:00 del dia siguiente, hora LOCAL de
    `tz_name` -- convertido de vuelta a UTC real para poder compararlo contra
    timestamps de MT5/deals (que este bot ya trata como UTC en todo el resto
    del codigo, ver AUDIT-BOT032_day_definition.md #3). `now_utc` debe ser
    timezone-aware (UTC).
    """
    tz = ZoneInfo(tz_name)
    local_now = now_utc.astimezone(tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = local_midnight.astimezone(timezone.utc)
    end_utc = (local_midnight + timedelta(days=1)).astimezone(timezone.utc)
    return start_utc, end_utc, local_midnight.date()


def current_operating_date(now_utc: datetime, tz_name: str = DEFAULT_OPERATING_TIMEZONE) -> date:
    """Solo la fecha operativa (sin los limites UTC) -- usada para comparar
    contra la fecha de un override persistido (execution/src/kill_switch_store.py)."""
    _, _, operating_date = operating_day_bounds_utc(now_utc, tz_name)
    return operating_date
