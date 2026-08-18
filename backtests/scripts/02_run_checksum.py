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
    python scripts/02_run_checksum.py
Sale con exit code 0 y "TODO OK" si las 4 reglas se cumplen, o levanta
AssertionError senalando cual regla fallo.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.engine import StrategyParams, run_backtest, bucket_levels
from src.costs import BrokerCosts

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


def test_c_bucket_no_self_arm():
    # 3 buckets de 5 minutos, velas de 1 minuto: bars 0-4 = bucket 0,
    # 5-9 = bucket 1, 10-14 = bucket 2. Dentro de cada bucket el high/low
    # hacen un nuevo extremo en CADA barra (el escenario que gatillaba el bug
    # original: comparar el bloque contra si mismo).
    n = 15
    time_utc = _times(n)
    high = 100.0 + np.arange(n, dtype=float)   # sube en cada barra, sin excepcion
    low = 90.0 - np.arange(n, dtype=float) * 0.1

    resistencia, soporte = bucket_levels(time_utc, high, low, periodos_min=5)

    # bucket 0 (bars 0-4): no hay bloque anterior -> nunca hay nivel de referencia
    assert np.all(np.isnan(resistencia[0:5])), "Test C: bucket 0 no deberia tener resistencia (sin bloque previo)"
    assert np.all(np.isnan(soporte[0:5])), "Test C: bucket 0 no deberia tener soporte (sin bloque previo)"

    # bucket 1 (bars 5-9): resistencia/soporte = high/low FINAL y FIJO del bucket 0,
    # constante durante todo el bucket 1 aunque high seguira subiendo barra a barra.
    bucket0_final_high = high[4]
    bucket0_final_low = low[4]
    assert np.all(resistencia[5:10] == bucket0_final_high), "Test C: resistencia del bucket 1 debe ser fija = high final del bucket 0"
    assert np.all(soporte[5:10] == bucket0_final_low), "Test C: soporte del bucket 1 debe ser fijo = low final del bucket 0"
    # el punto central del bug: NO debe ir cambiando bar a bar dentro del bucket 1
    assert len(set(resistencia[5:10].tolist())) == 1, "Test C: resistencia no deberia variar dentro del mismo bucket (bug de autoarmado)"

    # bucket 2 (bars 10-14): ahora la referencia es el bucket 1 (que a su vez
    # siguio subiendo en cada barra) -- prueba que el "cierre" del bloque
    # anterior toma su extremo FINAL, no el primero.
    bucket1_final_high = high[9]
    assert np.all(resistencia[10:15] == bucket1_final_high), "Test C: resistencia del bucket 2 debe ser el high final del bucket 1"

    print("  C) el bloque HTF nunca se autoarma (resistencia/soporte fijos del bloque anterior cerrado): OK")


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


if __name__ == "__main__":
    print("Checksum mecanico del motor (docs/spec-backtest.md #6)\n")
    test_a_and_b_fill_priority_and_tie_break()
    test_c_bucket_no_self_arm()
    test_d_concurrency_limit_blocks_second_signal()
    print("\nTODO OK — las 4 reglas mecanicas se cumplen.")
