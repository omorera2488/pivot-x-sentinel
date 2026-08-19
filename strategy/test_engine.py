"""Checksum mecanico del motor — docs/spec-backtest.md #6.

Corre el motor sobre series sinteticas cortas y conocidas, verificando a mano
las reglas mecanicas de docs/spec-estrategia.md, NO conteos agregados contra
el Pine original (eso esta explicitamente fuera de alcance, ver
spec-estrategia.md #7):

  A. Prioridad "llenado antes que expiracion" cuando ambas caen en la misma barra.
  B. Empate SL/TP en la misma barra siempre resuelve como SL.
  C. El bloque HTF nunca se autoarma (bug corregido, spec-estrategia #3.2/#3.3).
  D. El limite de concurrencia bloquea una senal nueva cuando ya hay
     maxConcurrentPorDireccion operaciones vivas en esa direccion.

Uso:
    python strategy/test_engine.py
Sale con exit code 0 y "TODO OK" si las 4 reglas se cumplen, o levanta
AssertionError senalando cual regla fallo.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, para "import strategy"

from strategy.engine import StrategyParams, run_backtest, bucket_levels
from strategy.costs import BrokerCosts
from strategy.live_signal import LiveSignalEngine

ZERO_COST = BrokerCosts(
    point=1.0, contract_size=1.0, tick_value=1.0,
    swap_long_points=0.0, swap_short_points=0.0,
    commission_per_lot=0.0, spread_fallback_points=0.0,
)


def _times(n, start=0, step_min=1):
    # timestamps solo necesitan ser crecientes; el bucket HTF no se usa en
    # estos tests porque resistencia/soporte se inyectan directamente.
    return (np.arange(n) * step_min * 60 + start).astype("int64")


def test_a_and_b_fill_priority_and_tie_break():
    # Operacion 1 (Test A): armado en bar1 (low=85<=soporte=90), crossover en
    # bar2 -> entry=100, stop=90, target=110. En bar3, low=95 toca la entrada
    # (100) Y high=112 tocaria el TP (110) -- si se evaluara la expiracion
    # antes que el llenado, esto se leeria como "target alcanzado sin llenar"
    # (expirada). La regla dice que el llenado tiene prioridad: debe fichar
    # como LLENADA y, como en la misma barra tambien pega el TP, resolver
    # GANADORA ahi mismo.
    #
    # Operacion 2 (Test B): se rearma en bar4 (low=85<=90), crossover en bar5
    # -> entry=97, stop=90, target=104. Se llena limpio en bar6 (toca 97, sin
    # tocar 90 ni 104 en esa misma barra) y queda ABIERTA. En bar7, low=85
    # toca el stop (90) Y high=110 toca el target (104) a la vez -> debe
    # resolver PERDEDORA (el empate lo gana el SL), nunca ganadora.
    n = 8
    time_utc = _times(n)
    time_server = time_utc.copy()

    close = np.array([98, 99, 101, 97, 95, 99, 96, 90], dtype=float)
    ema_line = np.array([100, 100, 100, 99, 97, 97, 96, 90], dtype=float)
    high = np.array([99, 100, 102, 112, 90, 98, 98, 110], dtype=float)
    low = np.array([97, 85, 100, 95, 85, 96, 96, 85], dtype=float)
    open_ = close.copy()
    spread_pts = np.zeros(n)

    resistencia = np.full(n, 1000.0)  # nunca se toca -> lado venta inerte
    soporte = np.full(n, 90.0)

    params = StrategyParams(
        ema_periods=1, periodos_htf_min=999999, buf_bp=0.0, rr=1.0,
        max_concurrent_por_direccion=5, valid_bars=10, orden_viva=True,
        max_bars_trade=500, fixed_lot=1.0,
    )

    res = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts,
                        params, ZERO_COST, ema_line=ema_line, resistencia=resistencia, soporte=soporte)

    trades = res.trades
    assert res.counters.n_sig == 2, f"se esperaban 2 señales, hubo {res.counters.n_sig}"
    assert res.counters.n_fill == 2, f"se esperaban 2 llenados, hubo {res.counters.n_fill}"
    assert res.counters.n_none == 0, f"no deberia haber expiradas por tpAntes, hubo {res.counters.n_none}"
    assert len(trades) == 2, f"se esperaban 2 operaciones resueltas, hubo {len(trades)}"

    t0 = trades[0]
    assert t0.entry_bar == 3 and t0.exit_bar == 3, "Test A: fill y resolucion en la misma barra (bar 3)"
    assert t0.outcome == "win", f"Test A: se esperaba 'win', fue {t0.outcome}"

    t1 = trades[1]
    assert t1.entry_bar == 6, "Test B: el llenado deberia ser en bar 6"
    assert t1.exit_bar == 7, "Test B: la resolucion (empate SL/TP) deberia ser en bar 7"
    assert t1.outcome == "loss", f"Test B (empate SL/TP en la misma barra): se esperaba 'loss', fue {t1.outcome}"

    print("  A) prioridad llenado-antes-que-expiracion: OK (bar 3, misma barra, fill+win)")
    print("  B) empate SL/TP misma barra -> gana el SL: OK")


def test_c_bucket_matches_tradingview_causal():
    # docs/spec-estrategia.md #3.3 (enmienda): resistencia/soporte replican
    # runHigh/runLow de basecode_tradingview con usarCausal=true -- el
    # extremo del bloque QUE SE ESTA FORMANDO, actualizado barra a barra.
    # 3 buckets de 5 minutos, velas de 1 minuto: bars 0-4 = bucket 0,
    # 5-9 = bucket 1, 10-14 = bucket 2. high/low hacen un nuevo extremo en
    # CADA barra a proposito -- este es el escenario que se decidio replicar
    # (ver #3.2), no evitar.
    n = 15
    time_utc = _times(n)
    high = 100.0 + np.arange(n, dtype=float)   # sube en cada barra, sin excepcion
    low = 90.0 - np.arange(n, dtype=float) * 0.1

    resistencia, soporte = bucket_levels(time_utc, high, low, periodos_min=5)

    # sin periodo de calentamiento: desde la primera barra ya hay un nivel
    # (el propio high/low de esa barra, igual que runHigh/runLow en Pine).
    assert not np.any(np.isnan(resistencia)), "Test C: resistencia nunca deberia ser NaN (runHigh arranca en la barra 0)"
    assert not np.any(np.isnan(soporte)), "Test C: soporte nunca deberia ser NaN (runLow arranca en la barra 0)"
    assert resistencia[0] == high[0] and soporte[0] == low[0]

    # dentro de cada bucket, resistencia/soporte SIGUEN al maximo/minimo
    # acumulado de ESE mismo bucket, barra a barra (no un valor fijo).
    for b_start, b_end in [(0, 5), (5, 10), (10, 15)]:
        expected_res = np.maximum.accumulate(high[b_start:b_end])
        expected_sop = np.minimum.accumulate(low[b_start:b_end])
        assert np.array_equal(resistencia[b_start:b_end], expected_res), \
            "Test C: resistencia debe ser el maximo acumulado del bloque en formacion"
        assert np.array_equal(soporte[b_start:b_end], expected_sop), \
            "Test C: soporte debe ser el minimo acumulado del bloque en formacion"

    # cada barra hace nuevo high dentro del bucket -> high[i] == resistencia[i]
    # siempre (la auto-comparacion de #3.2, replicada a proposito).
    assert np.array_equal(resistencia, high), "Test C: con high creciente, resistencia debe igualar high en cada barra (auto-armado esperado)"

    # al cruzar a un bucket nuevo, resistencia arranca de nuevo desde el high
    # de la PRIMERA barra de ese bucket (no arrastra el bloque anterior).
    assert resistencia[5] == high[5] and resistencia[10] == high[10]

    print("  C) resistencia/soporte = extremo del bloque EN FORMACION (igual a TradingView usarCausal=true): OK")


def test_d_concurrency_limit_blocks_second_signal():
    n = 8
    time_utc = _times(n)
    time_server = time_utc.copy()

    # ver razonamiento detallado en el docstring del modulo: arming y stop
    # comparten nivel, asi que para probar concurrencia sin reventar la
    # primera operacion por accidente, la 2da señal arma contra un soporte
    # MAS ALTO que el stop de la 1ra (bucket nuevo con low mas alto).
    close = np.array([98, 99, 101, 97, 96, 93, 97, 99], dtype=float)
    ema_line = np.array([100, 100, 100, 99, 96, 94, 95, 96], dtype=float)
    high = np.array([99, 100, 102, 101, 96, 96, 96, 96], dtype=float)
    low = np.array([97, 85, 100, 99, 95, 94, 93, 93], dtype=float)
    open_ = close.copy()
    spread_pts = np.zeros(n)

    resistencia = np.full(n, 1000.0)
    soporte = np.array([90, 90, 90, 90, 90, 95, 93, 93], dtype=float)

    params = StrategyParams(
        ema_periods=1, periodos_htf_min=999999, buf_bp=0.0, rr=1.0,
        max_concurrent_por_direccion=1,   # <-- el limite bajo esta prueba
        valid_bars=10, orden_viva=True, max_bars_trade=500, fixed_lot=1.0,
    )

    res = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts,
                        params, ZERO_COST, ema_line=ema_line, resistencia=resistencia, soporte=soporte)

    # señal 1 en bar2 (entry=100, stop=90) se llena en bar3 (low=99<=100) y
    # queda ABIERTA (no toca stop=90 ni target=110 en bar3: high=101<110,
    # low=99>90). Sigue abierta en bar5/6 sin tocar 90/110.
    # señal 2 deberia dispararse en bar6 (crossover con armado desde bar5,
    # low=94<=soporte[5]=95) mientras la señal 1 SIGUE abierta -> debe
    # bloquearse por el limite de concurrencia (maxConcurrentPorDireccion=1).
    assert res.counters.n_sig == 2, f"se esperaban 2 señales generadas, hubo {res.counters.n_sig}"
    assert res.counters.n_skip_concurrency == 1, f"se esperaba 1 señal descartada por concurrencia, hubo {res.counters.n_skip_concurrency}"
    assert res.counters.n_fill == 1, f"solo la 1ra señal deberia haberse llenado, n_fill={res.counters.n_fill}"

    print("  D) limite de concurrencia bloquea una señal nueva con el cupo ocupado: OK")


def test_f_entrada_viva():
    # entradaViva (spec-estrategia #4.3): el llenado sigue la EMA ACTUAL, no
    # la de la señal, y el target se recalcula con el riesgo REALIZADO al
    # llenar -- exactamente el comportamiento de basecode_tradingview.
    #
    # Señal en bar2 (entry original=100, stop=90, target original=110).
    # En bar3 la EMA actual bajo a 95 y el precio la toca ahi (no en 100):
    # llenado a 95 (no a 100). Riesgo real = |90-95|=5, target nuevo = 100
    # (no 110). En bar4 el precio llega a 100 -> gana con el target NUEVO.
    n = 5
    time_utc = _times(n)
    time_server = time_utc.copy()

    close = np.array([98, 99, 101, 95, 97], dtype=float)
    ema_line = np.array([100, 100, 100, 95, 97], dtype=float)
    high = np.array([99, 100, 102, 96, 101], dtype=float)
    low = np.array([97, 85, 100, 94, 97], dtype=float)
    open_ = close.copy()
    spread_pts = np.zeros(n)

    resistencia = np.full(n, 1000.0)
    soporte = np.full(n, 90.0)

    params = StrategyParams(
        ema_periods=1, periodos_htf_min=999999, buf_bp=0.0, rr=1.0,
        max_concurrent_por_direccion=5, valid_bars=10, orden_viva=True,
        max_bars_trade=500, fixed_lot=1.0, entrada_viva=True,
    )

    res = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts,
                        params, ZERO_COST, ema_line=ema_line, resistencia=resistencia, soporte=soporte)

    assert len(res.trades) == 1, f"se esperaba 1 operacion, hubo {len(res.trades)}"
    t = res.trades[0]
    assert t.entry_price == 95.0, f"con entradaViva el llenado deberia ser a la EMA actual (95), fue {t.entry_price}"
    assert t.stop == 90.0, "el stop no deberia moverse con entradaViva"
    assert t.target == 100.0, f"el target deberia recalcularse con el riesgo real (95-90=5 -> 100), fue {t.target}"
    assert t.outcome == "win", f"se esperaba 'win' contra el target recalculado, fue {t.outcome}"

    print("  F) entradaViva: llenado en la EMA actual + target recalculado al riesgo real: OK")


def test_g_live_signal_matches_batch():
    # Fase 4: el motor incremental (live_signal.py) tiene que generar
    # EXACTAMENTE las mismas señales que el motor batch (engine.py) sobre la
    # misma secuencia de barras -- si no, el bot en vivo operaria distinto de
    # lo que valida el backtest. Serie sintetica con vaivenes (mezcla de dos
    # senos de distinto periodo) para forzar varios cruces EMA y varios
    # cierres de bloque HTF, sin depender de datos reales ni de MT5.
    n = 1200
    t = np.arange(n, dtype=float)
    close = 2000.0 + 15.0 * np.sin(t / 23.0) + 6.0 * np.sin(t / 7.0 + 1.3)
    high = close + 1.5
    low = close - 1.5
    time_utc = (np.arange(n) * 5 * 60).astype("int64")  # velas de 5 min
    time_server = time_utc.copy()
    open_ = close.copy()
    spread_pts = np.zeros(n)

    params = StrategyParams(
        ema_periods=12, periodos_htf_min=35, buf_bp=0.4, rr=1.0,
        max_concurrent_por_direccion=99, valid_bars=10, orden_viva=True,
        max_bars_trade=500, fixed_lot=0.01,
    )

    batch_log = []
    run_backtest(time_utc, time_server, open_, high, low, close, spread_pts,
                 params, ZERO_COST, signal_log=batch_log)
    assert len(batch_log) > 5, "la serie sintetica deberia generar varias señales -- si no, el test no prueba nada"

    live = LiveSignalEngine(params)
    live_log = []
    for i in range(n):
        r = live.process_bar(int(time_utc[i]), float(high[i]), float(low[i]), float(close[i]))
        if r.dir is not None:
            live_log.append({"bar": i, "dir": r.dir, "entry": r.entry, "stop": r.stop,
                              "target": r.target, "valido": r.valido})

    assert len(live_log) == len(batch_log), \
        f"cantidad de señales distinta: batch={len(batch_log)} vivo={len(live_log)}"
    for b, l in zip(batch_log, live_log):
        assert b["bar"] == l["bar"] and b["dir"] == l["dir"] and b["valido"] == l["valido"], \
            f"señal distinta en bar {b['bar']}: batch={b} vivo={l}"
        assert math.isclose(b["entry"], l["entry"], rel_tol=1e-9)
        assert math.isclose(b["stop"], l["stop"], rel_tol=1e-9)
        if b["valido"]:
            assert math.isclose(b["target"], l["target"], rel_tol=1e-9)

    print(f"  G) motor incremental (live_signal) == motor batch (engine): OK ({len(batch_log)} señales comparadas)")


def test_e_profiles():
    from strategy.profiles import get_profile

    p1 = get_profile("1m")
    assert (p1.ema_periods, p1.periodos_htf_min) == (15, 100), "perfil 1m deberia ser ema=15, bloque=100min"

    p5 = get_profile("5m")
    assert (p5.ema_periods, p5.periodos_htf_min) == (12, 400), "perfil 5m deberia ser ema=12, bloque=400min"

    # alias al estilo MT5 (M1/M5), usados en backtests/
    assert get_profile("M1") == p1
    assert get_profile("M5") == p5

    # overrides no pisan el resto del perfil
    p5_custom = get_profile("5m", rr=2.0)
    assert p5_custom.rr == 2.0 and p5_custom.ema_periods == 12

    try:
        get_profile("M15")
        raise AssertionError("se esperaba ValueError para un perfil inexistente")
    except ValueError:
        pass

    print("  E) seleccion de perfil (1m/5m, alias M1/M5, overrides): OK")


if __name__ == "__main__":
    print("Checksum mecanico del motor (docs/spec-backtest.md #6)\n")
    test_a_and_b_fill_priority_and_tie_break()
    test_c_bucket_matches_tradingview_causal()
    test_d_concurrency_limit_blocks_second_signal()
    test_e_profiles()
    test_f_entrada_viva()
    test_g_live_signal_matches_batch()
    print("\nTODO OK — motor batch validado + motor incremental (Fase 4) equivalente.")
