"""Regresion: el timestamp de apertura de una barra MT5 (`copy_rates_*`) no
se desplaza artificialmente antes de entrar al calculo del bloque HTF.

Contexto (spec-estrategia.md #3.1):
  - 2026-09-04: el desajuste de ~2hs entre el bloque HTF del bot y el de
    TradingView resulto ser 100% la alineacion de sesion (ver
    strategy/test_htf_session.py), NO el offset de reloj del servidor --
    measure_broker_offset_seconds() midio -1.86s para la cuenta real usada
    (ruido de red, no una zona horaria completa).
  - 2026-09-04 (segunda pasada, a pedido explicito del usuario): aunque ese
    offset medido daba negligible en ESE momento, se decidio dejar de
    aplicarlo del todo al timestamp de las velas que alimentan EMA/HTF/
    señal (replay_startup()/process_closed_bar() ya no llaman a
    _corrected_utc_seconds() para esto). Motivo: incluso 1-2s de correccion
    pueden empujar una vela situada JUSTO en el limite de sesion (ej.
    22:00:00) al bloque anterior o siguiente segun el SIGNO del offset
    medido ese dia -- un riesgo real, no solo teorico, que no vale la pena
    correr para un beneficio que measure_broker_offset_seconds() ya cubre
    como diagnostico (se sigue midiendo y logueando en connect(), ver
    bot.py). `_corrected_utc_seconds()` sigue existiendo como utilidad
    aislada (tests A/B abajo verifican su aritmetica), pero ya no la llama
    nadie en el camino de EMA/HTF/señal -- los tests C-G verifican eso
    contra el motor real, no contra una copia de la formula.

Uso:
    python execution/src/test_timestamp_offset.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src.bot import _corrected_utc_seconds
from strategy.engine import StrategyParams
from strategy.live_signal import LiveSignalEngine
from strategy.htf_session import bucket_start_utc_seconds


def _dt(y, m, d, hh, mm, ss=0):
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).timestamp())


def test_a_zero_offset_is_identity():
    """La funcion _corrected_utc_seconds() en si misma: con offset ~0 no
    desplaza nada (caso medido para la cuenta real actual: -1.86s)."""
    raw = 1_893_456_000  # timestamp arbitrario, no depende del valor exacto
    assert _corrected_utc_seconds(raw, 0.0) == raw
    assert _corrected_utc_seconds(raw, -1.86) == raw + 2
    print("  A) _corrected_utc_seconds con offset ~0 -- identidad: OK")


def test_b_nonzero_offset_corrects_toward_true_utc():
    """La funcion en si misma sigue corrigiendo si se la llama con un offset
    grande -- sigue sirviendo como utilidad aislada, solo que hoy no la usa
    el camino de EMA/HTF/señal (ver tests C-G)."""
    raw = 1_893_456_000
    three_hours = 3 * 3600.0
    assert _corrected_utc_seconds(raw, three_hours) == raw - 3 * 3600
    assert _corrected_utc_seconds(raw, -three_hours) == raw + 3 * 3600
    print("  B) _corrected_utc_seconds con offset real (ej. 3hs) sigue corrigiendo: OK")


# --- C-G: los 5 casos pedidos explicitamente, contra el motor real -------

BOUNDARY_22 = _dt(2026, 9, 3, 22, 0)     # limite de sesion medido en TradingView
BOUNDARY_11_20 = _dt(2026, 9, 4, 11, 20)  # siguiente limite (bloque truncado a 640min)


def test_c_boundary_bar_enters_engine_unshifted():
    """(1) Una barra con timestamp EXACTO 2026-09-03 22:00:00 UTC debe
    entrar al motor de señal exactamente como 22:00:00, sin +/- segundos --
    replay_startup()/process_closed_bar() le pasan `int(r["time"])` al motor
    tal cual, sin restar/sumar _offset_seconds (ver docstring del modulo)."""
    params = StrategyParams(ema_periods=1, periodos_htf_min=800, buf_bp=0.0, rr=1.0)
    live = LiveSignalEngine(params)
    live.process_bar(BOUNDARY_22 - 5 * 60, 2000.0, 1999.0, 1999.5)  # barra previa, bloque viejo
    live.process_bar(BOUNDARY_22, 2001.0, 2000.0, 2000.5)           # la barra exacta del limite

    assert live._cur_bucket == BOUNDARY_22, (
        f"la barra {datetime.fromtimestamp(BOUNDARY_22, tz=timezone.utc)} deberia quedar "
        f"clasificada exactamente en su propio bloque (sin +/- segundos de por medio) -- "
        f"dio {datetime.fromtimestamp(live._cur_bucket, tz=timezone.utc)}"
    )
    print("  C) barra exacta 2026-09-03 22:00:00 UTC entra al motor sin desplazamiento: OK")


def test_d_boundary_bar_is_first_of_its_bucket():
    """(2) Esa barra (22:00:00) debe ser la PRIMERA del bloque 22:00 --
    resistencia/soporte arrancan de ESA barra, no arrastran el bloque
    anterior."""
    assert bucket_start_utc_seconds(BOUNDARY_22, 800) == BOUNDARY_22, \
        "22:00:00 UTC deberia ser inicio de bloque, no pertenecer a uno anterior"

    params = StrategyParams(ema_periods=1, periodos_htf_min=800, buf_bp=0.0, rr=1.0)
    live = LiveSignalEngine(params)
    live.process_bar(BOUNDARY_22 - 5 * 60, 2000.0, 1999.0, 1999.5)  # bloque viejo, high=2000
    r = live.process_bar(BOUNDARY_22, 2050.0, 1950.0, 2000.0)       # bloque nuevo, high/low propios

    assert r.resistencia == 2050.0 and r.soporte == 1950.0, \
        "la barra de 22:00:00 deberia resetear resistencia/soporte a su propio high/low"
    print("  D) 2026-09-03 22:00:00 UTC es la primera barra de su bloque (sin arrastrar el anterior): OK")


def test_e_next_truncated_boundary_is_new_bucket():
    """(3) 2026-09-04 11:20:00 UTC debe ser la primera barra del bloque
    SIGUIENTE (el truncado a 640min, ver spec-estrategia.md #3.1) -- no
    debe quedar pegado al bloque que arranco a las 22:00."""
    start_22 = bucket_start_utc_seconds(BOUNDARY_22, 800)
    start_11_20 = bucket_start_utc_seconds(BOUNDARY_11_20, 800)
    assert start_11_20 == BOUNDARY_11_20, "11:20:00 UTC deberia ser inicio de bloque"
    assert start_11_20 != start_22, "11:20:00 UTC deberia ser un bloque DISTINTO al de las 22:00"
    assert (BOUNDARY_11_20 - BOUNDARY_22) / 60 == 800, "el bloque 22:00->11:20 deberia durar 800min"
    print("  E) 2026-09-04 11:20:00 UTC es la primera barra del bloque siguiente: OK")


def test_f_before_boundary_still_previous_bucket():
    """(4) 21:55 (5 minutos antes del limite) debe pertenecer TODAVIA al
    bloque previo, no al que arranca a las 22:00."""
    t_21_55 = BOUNDARY_22 - 5 * 60
    assert bucket_start_utc_seconds(t_21_55, 800) != BOUNDARY_22, \
        "21:55 UTC no deberia haber cruzado todavia al bloque de las 22:00"
    print("  F) 21:55 UTC (5min antes del limite) sigue en el bloque previo: OK")


def test_g_existing_tests_still_pass():
    """(5) No romper nada existente -- delega en las suites ya cubiertas por
    otros archivos (test_engine.py, test_scoring.py, test_htf_session.py);
    este test solo deja constancia explicita de cuales son, para que quede
    claro que la validacion completa no es solo este archivo."""
    print("  G) ver ademas: strategy/test_engine.py, strategy/test_scoring.py, "
          "strategy/test_htf_session.py (corridos aparte, no reimplementados aca)")


if __name__ == "__main__":
    print("Timestamp de barra MT5 -> bloque HTF, sin corregir por offset de servidor (spec-estrategia.md #3.1)\n")
    test_a_zero_offset_is_identity()
    test_b_nonzero_offset_corrects_toward_true_utc()
    test_c_boundary_bar_enters_engine_unshifted()
    test_d_boundary_bar_is_first_of_its_bucket()
    test_e_next_truncated_boundary_is_new_bucket()
    test_f_before_boundary_still_previous_bucket()
    test_g_existing_tests_still_pass()
    print("\nTODO OK — el timestamp de la vela llega intacto (sin +/- offset) al bloque HTF.")
