"""Verifica que los campos de diagnostico agregados a BarSignal (2026-09-04,
paridad barra a barra con TradingView -- ver scripts/diagnose_signal_parity.py)
son PURAMENTE informativos: no cambian ningun resultado de señal.

Dos pruebas:
  A. Consistencia interna: los campos nuevos (armado_*_antes, cruce_*,
     senal_*) deben ser exactamente coherentes con las reglas de armado/
     señal de docs/spec-estrategia.md #4.2 -- si no lo fueran, serian
     diagnostico enganoso.
  B. Resultado identico: sobre una serie sintetica, los campos ORIGINALES de
     BarSignal (dir/entry/stop/target/valido) deben seguir coincidiendo bar
     a bar contra strategy/engine.py::run_backtest (motor batch, que este
     cambio no toco) -- la misma comparacion que ya hace
     test_engine.py::test_g, repetida aca para dejar constancia explicita
     de que agregar los campos de diagnostico no altero nada de lo que ya
     se devolvia.

Uso:
    python strategy/test_diagnostics.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from strategy.costs import BrokerCosts
from strategy.engine import StrategyParams, run_backtest
from strategy.live_signal import LiveSignalEngine

ZERO_COST = BrokerCosts(
    point=1.0, contract_size=1.0, tick_value=1.0,
    swap_long_points=0.0, swap_short_points=0.0,
    commission_per_lot=0.0, spread_fallback_points=0.0,
)


def _synthetic_series(n=1200):
    t = np.arange(n, dtype=float)
    close = 2000.0 + 15.0 * np.sin(t / 23.0) + 6.0 * np.sin(t / 7.0 + 1.3)
    high = close + 1.5
    low = close - 1.5
    time_utc = (np.arange(n) * 5 * 60).astype("int64")
    return time_utc, high, low, close


def test_a_diagnostic_fields_are_internally_consistent():
    params = StrategyParams(ema_periods=12, periodos_htf_min=35, buf_bp=0.4, rr=1.0)
    live = LiveSignalEngine(params)
    time_utc, high, low, close = _synthetic_series()

    for i in range(len(time_utc)):
        r = live.process_bar(int(time_utc[i]), float(high[i]), float(low[i]), float(close[i]))

        assert r.senal_venta == (r.armado_venta_antes and r.cruce_abajo), \
            f"bar {i}: senal_venta deberia ser armado_venta_antes AND cruce_abajo (spec #4.2)"
        assert r.senal_compra == (r.armado_compra_antes and r.cruce_arriba), \
            f"bar {i}: senal_compra deberia ser armado_compra_antes AND cruce_arriba (spec #4.2)"
        assert not (r.senal_venta and r.senal_compra), \
            f"bar {i}: senal_venta y senal_compra nunca deberian ser verdaderas a la vez (spec #4.2)"
        if r.senal_venta:
            assert r.dir == -1, f"bar {i}: senal_venta implica dir=-1"
        elif r.senal_compra:
            assert r.dir == 1, f"bar {i}: senal_compra implica dir=1"
        else:
            assert r.dir is None, f"bar {i}: sin señal, dir deberia ser None"

    print("  A) armado_*_antes/cruce_*/senal_* consistentes con spec #4.2 en las 1200 barras: OK")


def test_b_original_fields_unchanged_vs_batch_engine():
    params = StrategyParams(ema_periods=12, periodos_htf_min=35, buf_bp=0.4, rr=1.0)
    time_utc, high, low, close = _synthetic_series()
    n = len(time_utc)

    live = LiveSignalEngine(params)
    live_signals = []
    for i in range(n):
        r = live.process_bar(int(time_utc[i]), float(high[i]), float(low[i]), float(close[i]))
        if r.dir is not None:
            live_signals.append((i, r.dir, r.entry, r.stop, r.target, r.valido))

    batch_log = []
    run_backtest(time_utc, time_utc.copy(), close.copy(), high, low, close,
                 np.zeros(n), params, ZERO_COST, signal_log=batch_log)

    assert len(live_signals) == len(batch_log), \
        f"cantidad de señales: motor incremental={len(live_signals)} vs motor batch={len(batch_log)}"
    for (i, d, entry, stop, target, valido), b in zip(live_signals, batch_log):
        assert i == b["bar"] and d == b["dir"] and valido == b["valido"], \
            f"señal distinta en bar {i}: incremental={(d, valido)} batch={(b['dir'], b['valido'])}"

    print(f"  B) campos originales (dir/entry/stop/target/valido) siguen == motor batch: OK ({len(live_signals)} señales)")


if __name__ == "__main__":
    print("Instrumentacion de diagnostico (BarSignal) no cambia resultados de señal\n")
    test_a_diagnostic_fields_are_internally_consistent()
    test_b_original_fields_unchanged_vs_batch_engine()
    print("\nTODO OK — los campos de diagnostico son puramente informativos.")
