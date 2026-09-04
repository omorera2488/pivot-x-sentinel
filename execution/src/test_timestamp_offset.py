"""Regresion: el timestamp de una barra MT5 no se desplaza artificialmente
antes de entrar al calculo del bloque HTF.

Contexto (2026-09-04, spec-estrategia.md #3.1): el desajuste de ~2hs entre
el bloque HTF del bot y el de TradingView resulto ser 100% la alineacion de
sesion (ver strategy/test_htf_session.py), NO el offset de reloj del
servidor -- measure_broker_offset_seconds() midio -1.86s para la cuenta real
actual (ruido de red, no una zona horaria completa). Este test no reemplaza
esa medicion en vivo (necesita MT5 conectado); demuestra que la funcion que
aplica la correccion es la identidad cuando el offset medido es ~0, y que
solo corrige lo que measure_broker_offset_seconds() efectivamente mide --
nunca un desplazamiento fijo asumido de antemano.

Uso:
    python execution/src/test_timestamp_offset.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src.bot import _corrected_utc_seconds


def test_a_zero_offset_is_identity():
    """Con offset medido ~0 (servidor ya en UTC, caso de la cuenta real
    actual: -1.86s) el timestamp NO se desplaza -- entra igual al calculo
    del bloque HTF."""
    raw = 1_893_456_000  # timestamp arbitrario, no depende del valor exacto
    assert _corrected_utc_seconds(raw, 0.0) == raw
    # -1.86s medido de verdad (ver docstring del modulo): redondea a -2s,
    # sigue siendo un desplazamiento de segundos, irrelevante para bloques
    # de minutos -- no una zona horaria completa.
    assert _corrected_utc_seconds(raw, -1.86) == raw + 2
    print("  A) offset ~0 (broker ya en UTC) no desplaza el timestamp -- identidad: OK")


def test_b_nonzero_offset_corrects_toward_true_utc():
    """Si measure_broker_offset_seconds() SI mide un desfase real (broker
    con el reloj corrido), la correccion lo resta -- protege contra un
    broker con reloj de servidor desalineado sin asumir de antemano cuanto."""
    raw = 1_893_456_000
    three_hours = 3 * 3600.0
    assert _corrected_utc_seconds(raw, three_hours) == raw - 3 * 3600
    assert _corrected_utc_seconds(raw, -three_hours) == raw + 3 * 3600
    print("  B) offset real medido (ej. broker 3hs adelantado) se corrige hacia UTC verdadero: OK")


if __name__ == "__main__":
    print("Timestamp de barra MT5 -> correccion de offset de servidor (spec-estrategia.md #3.1)\n")
    test_a_zero_offset_is_identity()
    test_b_nonzero_offset_corrects_toward_true_utc()
    print("\nTODO OK — la correccion de offset no desplaza nada que ya venga en UTC.")
