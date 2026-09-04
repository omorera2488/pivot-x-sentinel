"""Tests de alineacion del bloque HTF -- docs/spec-estrategia.md #3.1
(enmienda 2026-09-04). Ver strategy/htf_session.py para la evidencia
completa (limites medidos en TradingView, formula, supuestos pendientes).

Uso:
    python strategy/test_htf_session.py
Sale con exit code 0 y "TODO OK" si las 5 pruebas se cumplen.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, para "import strategy"

from strategy.engine import StrategyParams, bucket_levels
from strategy.htf_session import bucket_start_utc_seconds
from strategy.live_signal import LiveSignalEngine


def _dt(y, m, d, hh, mm, ss=0):
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).timestamp())


# Los 3 limites medidos DIRECTAMENTE en TradingView (time("800") sobre
# XAUUSD/OZ, feed TVC) el 2026-09-03/04 -- ver htf_session.py, docstring del
# modulo, para el detalle completo de la medicion.
OBSERVED_BOUNDARIES = [
    _dt(2026, 9, 2, 22, 0),
    _dt(2026, 9, 3, 11, 20),
    _dt(2026, 9, 3, 22, 0),
]


def test_a_observed_boundaries_are_bucket_starts():
    """Cada limite medido debe ser exactamente el inicio del bloque que le
    corresponde, y el instante justo anterior debe pertenecer TODAVIA al
    bloque previo (no al nuevo)."""
    periodos = 800
    for boundary in OBSERVED_BOUNDARIES:
        start = bucket_start_utc_seconds(boundary, periodos)
        assert start == boundary, (
            f"el limite medido {datetime.fromtimestamp(boundary, tz=timezone.utc)} "
            f"deberia ser el inicio de su propio bloque, dio "
            f"{datetime.fromtimestamp(start, tz=timezone.utc)}"
        )
        one_sec_before = bucket_start_utc_seconds(boundary - 1, periodos)
        assert one_sec_before != boundary, \
            "un segundo antes del limite todavia deberia pertenecer al bloque anterior"
    print("  A) los 3 limites medidos en TradingView son inicios de bloque exactos: OK")


def test_b_block_lengths_match_observed_pattern():
    """22:00->11:20 = 800min (bloque completo). 11:20->22:00 = 640min
    (bloque truncado por el limite de sesion, NO 800) -- este es el patron
    que la formula vieja (modulo fijo sobre epoca Unix) NO puede producir,
    por eso quedo descartada (ver htf_session.py)."""
    b0, b1, b2 = OBSERVED_BOUNDARIES
    assert (b1 - b0) / 60 == 800, "primer bloque: deberian ser 800min completos"
    assert (b2 - b1) / 60 == 640, "segundo bloque: deberia truncarse a 640min (1440-800)"
    print("  B) largo de bloque 800min / 640min truncado / 800min: OK")


def test_c_no_spurious_bucket_within_block():
    """Velas de 5 minutos a lo largo de TODO un bloque de 800min (incluido
    el truncado de 640min) no deben generar ningun bloque nuevo de mas."""
    for start, end in [(OBSERVED_BOUNDARIES[0], OBSERVED_BOUNDARIES[1]),
                        (OBSERVED_BOUNDARIES[1], OBSERVED_BOUNDARIES[2])]:
        expected = bucket_start_utc_seconds(start, 800)
        t = start
        while t < end:
            got = bucket_start_utc_seconds(t, 800)
            assert got == expected, (
                f"{datetime.fromtimestamp(t, tz=timezone.utc)} genero un bloque nuevo "
                f"de mas dentro del bloque vigente"
            )
            t += 5 * 60
    print("  C) velas de 5min intermedias no generan bloques nuevos espurios: OK")


def test_d_run_high_low_reset_on_new_bucket():
    """Al cruzar a un bloque nuevo, runHigh/runLow arrancan de la barra que
    cruza (no arrastran el bloque anterior) -- verificado cruzando el limite
    REAL 2026-09-03 11:20 UTC (el truncado a 640min, el caso mas propenso a
    errores de implementacion) con el motor incremental."""
    params = StrategyParams(ema_periods=1, periodos_htf_min=800, buf_bp=0.0, rr=1.0)
    live = LiveSignalEngine(params)

    boundary = OBSERVED_BOUNDARIES[1]  # 2026-09-03 11:20 UTC
    bars = [(boundary + k * 5 * 60, 2000.0 + k, 1990.0 - k) for k in range(-3, 3)]
    results = [live.process_bar(t, h, l, (h + l) / 2) for t, h, l in bars]

    before = results[2]       # k=-1, ultima barra del bloque VIEJO
    at_boundary = results[3]  # k=0, primera barra del bloque NUEVO (el propio limite)

    assert at_boundary.resistencia == bars[3][1], \
        "en el instante del nuevo bloque, resistencia deberia ser el high de esa misma barra"
    assert at_boundary.soporte == bars[3][2], \
        "en el instante del nuevo bloque, soporte deberia ser el low de esa misma barra"
    assert at_boundary.resistencia != before.resistencia, \
        "el bloque nuevo no deberia arrastrar la resistencia del bloque anterior"
    print("  D) runHigh/runLow resetean en la barra que cruza al bloque nuevo (limite truncado real): OK")


def test_e_batch_matches_live_across_real_boundaries():
    """engine.bucket_levels() (motor batch) y LiveSignalEngine (motor en
    vivo) deben producir el mismo bloque bar a bar, cruzando los 3 limites
    reales medidos -- misma garantia de paridad que test_g de
    test_engine.py, pero anclada a las fechas reales en vez de un t=0
    sintetico (para probar la alineacion de sesion de verdad, no solo un
    caso que por casualidad no cruza ningun limite de dia)."""
    start = OBSERVED_BOUNDARIES[0] - 3 * 3600  # arranca 3hs antes del primer limite
    end = OBSERVED_BOUNDARIES[2] + 3 * 3600    # termina 3hs despues del ultimo
    times = np.arange(start, end, 5 * 60, dtype="int64")
    n = len(times)
    high = 2000.0 + np.sin(np.arange(n) / 5.0) * 3.0
    low = high - 5.0

    batch_res, batch_sop = bucket_levels(times, high, low, periodos_min=800)

    live = LiveSignalEngine(StrategyParams(ema_periods=1, periodos_htf_min=800, buf_bp=0.0, rr=1.0))
    for i in range(n):
        r = live.process_bar(int(times[i]), float(high[i]), float(low[i]), float((high[i] + low[i]) / 2))
        assert r.resistencia == batch_res[i], f"resistencia diverge en la barra {i}"
        assert r.soporte == batch_sop[i], f"soporte diverge en la barra {i}"

    print(f"  E) motor batch == motor incremental cruzando los 3 limites reales ({n} barras): OK")


if __name__ == "__main__":
    print("Alineacion del bloque HTF (docs/spec-estrategia.md #3.1, enmienda 2026-09-04)\n")
    test_a_observed_boundaries_are_bucket_starts()
    test_b_block_lengths_match_observed_pattern()
    test_c_no_spurious_bucket_within_block()
    test_d_run_high_low_reset_on_new_bucket()
    test_e_batch_matches_live_across_real_boundaries()
    print("\nTODO OK — bloque HTF alineado a la sesion medida en TradingView, paridad batch/vivo mantenida.")
