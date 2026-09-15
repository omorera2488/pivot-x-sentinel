"""Regresion de execution/src/operating_day.py -- BOT-032 (kill switch), dia
operativo timezone-aware.

No depende de MT5 -- es aritmetica pura de fechas/horas via `zoneinfo`.

Uso:
    python execution/src/test_operating_day.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src.operating_day import (  # noqa: E402
    DEFAULT_OPERATING_TIMEZONE, current_operating_date, operating_day_bounds_utc,
)


def test_a_boundary_example_from_prompt():
    """El ejemplo pedido explicitamente: 2026-09-15 02:00 UTC en
    America/Costa_Rica (UTC-6, sin DST) debe caer en el dia operativo
    2026-09-14, no 2026-09-15 -- mismo resultado que ya se verifico a mano
    para panel/calendar.html con hora local del navegador en Costa Rica."""
    t = datetime(2026, 9, 15, 2, 0, 0, tzinfo=timezone.utc)
    start, end, op_date = operating_day_bounds_utc(t)
    assert op_date.isoformat() == "2026-09-14", f"esperaba 2026-09-14, dio {op_date}"
    assert start == datetime(2026, 9, 14, 6, 0, 0, tzinfo=timezone.utc), start
    assert end == datetime(2026, 9, 15, 6, 0, 0, tzinfo=timezone.utc), end
    print("  A) 2026-09-15 02:00 UTC -> dia operativo 2026-09-14 (Costa Rica, UTC-6): OK")


def test_b_bounds_are_half_open_24h():
    """[start, end) cubre exactamente 24hs, sin solapar con el dia siguiente."""
    t = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    start, end, _ = operating_day_bounds_utc(t)
    assert (end - start).total_seconds() == 24 * 3600, "el dia operativo deberia durar exactamente 24hs"
    print("  B) limites [inicio, fin) cubren exactamente 24hs: OK")


def test_c_just_before_and_after_midnight_local():
    """23:59:59 y 00:00:00 hora local de Costa Rica deben caer en dias
    operativos DISTINTOS (05:59:59 UTC y 06:00:00 UTC respectivamente)."""
    just_before = datetime(2026, 9, 15, 5, 59, 59, tzinfo=timezone.utc)
    just_after = datetime(2026, 9, 15, 6, 0, 0, tzinfo=timezone.utc)
    _, _, d_before = operating_day_bounds_utc(just_before)
    _, _, d_after = operating_day_bounds_utc(just_after)
    assert d_before.isoformat() == "2026-09-14", d_before
    assert d_after.isoformat() == "2026-09-15", d_after
    assert d_before != d_after
    print("  C) 05:59:59 UTC y 06:00:00 UTC caen en dias operativos distintos: OK")


def test_d_current_operating_date_matches_bounds():
    t = datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
    _, _, expected = operating_day_bounds_utc(t)
    assert current_operating_date(t) == expected
    print("  D) current_operating_date() coincide con operating_day_bounds_utc(): OK")


def test_e_not_hardcoded_utc_minus_6_arithmetic():
    """La arquitectura no debe estar hardcodeada a "restar 6 horas" -- usa
    zoneinfo real, asi que otra zona con DST (ej. America/New_York) da un
    offset DISTINTO segun la epoca del año, sin tocar ninguna aritmetica de
    operating_day.py (parametro `tz_name`, ver docstring del modulo #4)."""
    verano = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)   # EDT, UTC-4
    invierno = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # EST, UTC-5
    start_verano, _, _ = operating_day_bounds_utc(verano, tz_name="America/New_York")
    start_invierno, _, _ = operating_day_bounds_utc(invierno, tz_name="America/New_York")
    assert start_verano.hour == 4, f"esperaba medianoche EDT (UTC-4) -> 04:00 UTC, dio {start_verano}"
    assert start_invierno.hour == 5, f"esperaba medianoche EST (UTC-5) -> 05:00 UTC, dio {start_invierno}"
    assert ZoneInfo(DEFAULT_OPERATING_TIMEZONE) is not None
    print("  E) mismo codigo, otra timezone con DST -> offsets distintos automaticamente: OK")


def main():
    test_a_boundary_example_from_prompt()
    test_b_bounds_are_half_open_24h()
    test_c_just_before_and_after_midnight_local()
    test_d_current_operating_date_matches_bounds()
    test_e_not_hardcoded_utc_minus_6_arithmetic()
    print("\nTODO OK")


if __name__ == "__main__":
    main()
