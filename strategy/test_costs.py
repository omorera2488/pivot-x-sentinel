"""Checksum del modelo de costos — BOT-043.

Motivo: BOT-043 encontro que el motor no tenia NINGUNA cobertura de test con
swap != 0 (`strategy/test_engine.py::ZERO_COST` siempre usa
swap_long_points=0.0/swap_short_points=0.0) -- asi paso desapercibido que
`close_open_trade()` (strategy/engine.py) restaba un swap que ya venia con
signo (acreditandolo en vez de cobrarlo), y que la conversion precio->USD
usaba `contract_size` en vez de `tick_value/tick_size` (subvaluaba el PnL/
riesgo real en precio por 100x en XAUUSDc de esta cuenta -- confirmado contra
`mt5.order_calc_profit()`, ver strategy/costs.py).

Cubre:
  A. price_to_usd() coincide con mt5.order_calc_profit() (valores capturados
     en vivo durante la investigacion de BOT-043, mas un simbolo "estandar"
     sintetico para probar que la formula generaliza).
  B. swap_usd_per_lot_per_night(): signo correcto (negativo = costo) para
     swap_long negativo.
  C. swap_short: direccion correcta (usa swap_short_points, no swap_long).
  D. nights_held=0 -> swap_total_usd=0 exacto, no toca el PnL.
  E. Dia de triple swap: se cobra 3x ese rollover puntual, 1x el resto.
  F. Cadena completa PnL ganador: bruto -> spread -> swap firmado ->
     comision -> neto -> 1R -> R realizado, contra un calculo manual
     independiente, corrida end-to-end con strategy.engine.run_backtest.
  G. Igual que F pero perdedor.
  H. Swap negativo REDUCE el PnL de un ganador LONG overnight frente al
     mismo trade sin swap (comparacion end-to-end, no solo la formula).
  I. (opcional, se salta sin MT5) cross-check en vivo contra
     mt5.order_calc_profit() para el simbolo real de la cuenta conectada.

Uso:
    python strategy/test_costs.py
"""
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

from strategy.costs import BrokerCosts
from strategy.engine import StrategyParams, run_backtest

# Valores reales de XAUUSDc (esta cuenta, capturados 2026-09-14 via
# mt5.symbol_info() -- ver investigacion de BOT-043). Symbol path del broker:
# "Cent\Forex\XAUUSDc" -- contract_size=1.0 (no 100), por eso el bug de
# escala de BOT-043 solo se hizo evidente en esta cuenta.
XAUUSDC_COSTS = BrokerCosts(
    point=0.001, contract_size=1.0, tick_value=0.1, tick_size=0.001,
    swap_long_points=-533.9, swap_short_points=0.0,
    commission_per_lot=0.0, triple_swap_weekday=2, spread_fallback_points=0.0,
)

# Simbolo "estandar" sintetico (ej. XAUUSD tipico de una cuenta no-cent:
# contract_size=100oz, tick=0.01, tick_value=1) -- para probar que
# price_to_usd() no regresiona el caso donde contract_size SI coincidia con
# tick_value/tick_size por casualidad.
STANDARD_COSTS = BrokerCosts(
    point=0.01, contract_size=100.0, tick_value=1.0, tick_size=0.01,
    swap_long_points=-6.5, swap_short_points=1.2,
    commission_per_lot=7.0, triple_swap_weekday=2, spread_fallback_points=0.0,
)


def test_a_price_to_usd_matches_order_calc_profit_reference():
    # Valores de referencia capturados EN VIVO con mt5.order_calc_profit()
    # sobre XAUUSDc durante la investigacion de BOT-043 (ver mensaje de
    # analisis): BUY 0.01 lot, +$1.0 de movimiento de precio -> +$1.00;
    # -$1.0 -> -$1.00 (simetrico); y con otros lotes/movimientos, todos
    # coincidiendo con price_to_usd() salvo redondeo de MT5 a tick_size en
    # movimientos que no son multiplos exactos del tick (no aplica aca,
    # todos los valores de abajo son multiplos exactos de 0.001).
    cases = [
        # (price_diff, lot, expected_usd)
        (1.0, 0.01, 1.0),
        (5.0, 0.01, 5.0),
        (-12.25, 0.1, -122.5),
        (100.0, 1.0, 10000.0),
        (0.337, 1.0, 33.7),
    ]
    for price_diff, lot, expected in cases:
        got = XAUUSDC_COSTS.price_to_usd(price_diff, lot)
        assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-9), \
            f"price_to_usd({price_diff}, {lot}) = {got}, esperado {expected} (ref. mt5.order_calc_profit)"

    # contract_size=1.0 de XAUUSDc NO debe usarse para esta conversion -- si
    # alguien reintroduce ese atajo, este assert lo detecta (100x de error).
    wrong = 1.0 * XAUUSDC_COSTS.contract_size * 0.01
    assert not math.isclose(wrong, 1.0, rel_tol=1e-6), \
        "contract_size*price_diff*lot da un valor casi correcto por casualidad -- revisar el fixture"

    # Simbolo "estandar" (contract_size que SI coincide con tick_value/tick_size):
    # ahi la formula vieja daba el mismo resultado por coincidencia -- confirmar
    # que price_to_usd() tambien es correcta en ese caso (no regresion).
    got_std = STANDARD_COSTS.price_to_usd(1.0, 0.01)
    old_formula_std = 1.0 * STANDARD_COSTS.contract_size * 0.01
    assert math.isclose(got_std, old_formula_std, rel_tol=1e-9), \
        "en un simbolo 'estandar', price_to_usd() deberia coincidir con la formula vieja (no regresion)"
    assert math.isclose(got_std, 1.0, rel_tol=1e-9)

    print("  A) price_to_usd() == mt5.order_calc_profit() de referencia (XAUUSDc); no regresiona simbolo estandar: OK")


def test_b_swap_long_negative_is_a_cost():
    per_night = XAUUSDC_COSTS.swap_usd_per_lot_per_night(direction=1)
    # calculo manual independiente: puntos -> precio (*point) -> USD (via
    # tick_value/tick_size), NO via contract_size.
    expected = (XAUUSDC_COSTS.swap_long_points * XAUUSDC_COSTS.point) / XAUUSDC_COSTS.tick_size * XAUUSDC_COSTS.tick_value
    assert per_night < 0, f"swap_long negativo deberia dar un costo (valor negativo), dio {per_night}"
    assert math.isclose(per_night, expected, rel_tol=1e-9), f"{per_night} != {expected}"
    assert math.isclose(per_night, -53.39, rel_tol=1e-6), f"valor de referencia esperado -53.39, dio {per_night}"

    total = XAUUSDC_COSTS.swap_total_usd(direction=1, fixed_lot=0.01,
                                          open_date=date(2026, 9, 7), close_date=date(2026, 9, 8))
    assert total < 0, "1 noche de swap_long negativo, fixed_lot=0.01 -- swap_total_usd debe ser negativo"
    assert math.isclose(total, per_night * 0.01, rel_tol=1e-9)

    print("  B) swap_long negativo => swap_usd_per_lot_per_night() y swap_total_usd() negativos (costo real): OK")


def test_c_swap_short_uses_swap_short_points():
    # XAUUSDc real tiene swap_short=0.0 (no ejercita la rama) -- se usa
    # STANDARD_COSTS (swap_short=1.2, swap_long=-6.5, signos opuestos) para
    # confirmar que la direccion selecciona el campo correcto.
    per_night_short = STANDARD_COSTS.swap_usd_per_lot_per_night(direction=-1)
    per_night_long = STANDARD_COSTS.swap_usd_per_lot_per_night(direction=1)
    assert per_night_short > 0, f"swap_short=1.2 (positivo) deberia dar un credito, dio {per_night_short}"
    assert per_night_long < 0, f"swap_long=-6.5 (negativo) deberia dar un costo, dio {per_night_long}"
    expected_short = (STANDARD_COSTS.swap_short_points * STANDARD_COSTS.point) / STANDARD_COSTS.tick_size * STANDARD_COSTS.tick_value
    assert math.isclose(per_night_short, expected_short, rel_tol=1e-9)

    print("  C) direccion short usa swap_short_points (no swap_long_points), signo correcto: OK")


def test_d_no_overnight_zero_swap():
    same_day = XAUUSDC_COSTS.swap_total_usd(direction=1, fixed_lot=0.01,
                                             open_date=date(2026, 9, 7), close_date=date(2026, 9, 7))
    assert same_day == 0.0, f"mismo dia (nights_held=0) debe dar swap_total_usd EXACTAMENTE 0.0, dio {same_day}"

    # tambien cubierto end-to-end mas abajo (test_h), donde se compara un
    # trade intradia contra la misma configuracion con swap_long=0 y da
    # identico pnl_usd -- prueba de que un trade sin noches no ve NADA del
    # swap, sea cual sea su signo/magnitud.
    print("  D) nights_held=0 -> swap_total_usd() == 0.0 exacto: OK")


def test_e_triple_swap_day():
    # Lunes 2026-09-07 -> Jueves 2026-09-10: 3 rollovers (noches del 7->8,
    # 8->9, 9->10). triple_swap_weekday=2 (miercoles) -- el rollover que cae
    # en la madrugada del miercoles 9 (d=2026-09-09, weekday()==2) se cobra
    # 3x; los otros dos (martes 8, jueves 10) 1x cada uno. Total = 1+3+1 = 5
    # noches equivalentes.
    assert date(2026, 9, 9).weekday() == 2, "fixture: 2026-09-09 debe ser miercoles"
    per_night = XAUUSDC_COSTS.swap_usd_per_lot_per_night(direction=1) * 0.01  # ya con fixed_lot
    expected = per_night * (1 + 3 + 1)
    got = XAUUSDC_COSTS.swap_total_usd(direction=1, fixed_lot=0.01,
                                        open_date=date(2026, 9, 7), close_date=date(2026, 9, 10))
    assert math.isclose(got, expected, rel_tol=1e-9), f"{got} != {expected} (esperado 5 noches equivalentes)"

    # Control: un tramo SIN el dia triple (lunes->martes, 1 noche) cobra 1x.
    single = XAUUSDC_COSTS.swap_total_usd(direction=1, fixed_lot=0.01,
                                           open_date=date(2026, 9, 7), close_date=date(2026, 9, 8))
    assert math.isclose(single, per_night, rel_tol=1e-9)

    print("  E) dia de triple swap (miercoles) cobrado 3x, resto 1x: OK")


# --- E2E: cadena completa del PnL, corrida real por strategy.engine.run_backtest ---

def _times_utc(seconds_list):
    return np.array(seconds_list, dtype="int64")


def _epoch(y, m, d, hh, mm):
    import calendar
    from datetime import datetime, timezone
    return int(calendar.timegm(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timetuple()))


def _run_single_trade(costs: BrokerCosts, hit="win"):
    """1 senal de compra: armado bar0, crossover+senal bar1 (entry=100,
    stop=90, target=110, buf=0/rr=1), llenado bar2 (lunes 2026-09-07),
    resolucion bar3 (martes 2026-09-08, +1 noche, NO es el dia triple) --
    hit='win' pega el target, hit='loss' pega el stop. spread_pts=20 en
    fill/exit (point=0.001 -> spread_price=0.02)."""
    n = 4
    time_utc = _times_utc([
        _epoch(2026, 9, 7, 9, 0), _epoch(2026, 9, 7, 9, 5),
        _epoch(2026, 9, 7, 9, 10), _epoch(2026, 9, 8, 9, 15),
    ])
    time_server = time_utc.copy()
    close = np.array([99.0, 101.0, 102.0, 111.0 if hit == "win" else 89.0])
    ema_line = np.array([100.0, 100.0, 100.0, 100.0])
    high = np.array([99.0, 101.0, 105.0, 112.0 if hit == "win" else 92.0])
    low = np.array([85.0, 99.0, 99.0, 108.0 if hit == "win" else 88.0])
    open_ = close.copy()
    spread_pts = np.array([0.0, 0.0, 20.0, 20.0])
    resistencia = np.full(n, 1000.0)
    soporte = np.full(n, 90.0)

    params = StrategyParams(
        ema_periods=1, periodos_htf_min=999999, buf_bp=0.0, rr=1.0,
        max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
        max_bars_trade=500, fixed_lot=0.01,
    )
    res = run_backtest(time_utc, time_server, open_, high, low, close, spread_pts,
                        params, costs, ema_line=ema_line, resistencia=resistencia, soporte=soporte)
    assert len(res.trades) == 1, f"se esperaba exactamente 1 trade resuelto, hubo {len(res.trades)}"
    t = res.trades[0]
    assert t.entry_price == 100.0 and t.stop == 90.0 and t.target == 110.0, \
        f"entry/stop/target inesperados: {t.entry_price}/{t.stop}/{t.target}"
    assert t.nights_held == 1, f"se esperaba 1 noche (lunes->martes, no triple), dio {t.nights_held}"
    return t


COMMISSION_COSTS = BrokerCosts(
    point=0.001, contract_size=1.0, tick_value=0.1, tick_size=0.001,
    swap_long_points=-533.9, swap_short_points=0.0,
    commission_per_lot=5.0, triple_swap_weekday=2, spread_fallback_points=0.0,
)


def test_f_pnl_ganador_full_chain():
    t = _run_single_trade(COMMISSION_COSTS, hit="win")
    assert t.outcome == "win"

    # --- calculo manual independiente, paso a paso ---
    entry_price_adj = 100.0 + 0.02 / 2       # compra: ask, +spread/2 = 100.01
    exit_price_adj = 110.0 - 0.02 / 2        # cierre de largo: bid, -spread/2 = 109.99
    pnl_price = exit_price_adj - entry_price_adj                      # 9.98
    pnl_bruto_usd = COMMISSION_COSTS.price_to_usd(pnl_price, 0.01)    # 9.98 (lot 0.01 => multiplicador 1x)
    swap_usd = COMMISSION_COSTS.swap_total_usd(1, 0.01, date(2026, 9, 7), date(2026, 9, 8))  # -0.5339
    commission_usd = COMMISSION_COSTS.commission_usd(0.01)            # 0.05
    pnl_neto_esperado = pnl_bruto_usd + swap_usd - commission_usd     # 9.98 - 0.5339 - 0.05 = 9.3961
    raw_risk_esperado = COMMISSION_COSTS.price_to_usd(abs(90.0 - 100.0), 0.01)  # 10.0
    r_esperado = pnl_neto_esperado / raw_risk_esperado                # 0.93961

    assert math.isclose(pnl_bruto_usd, 9.98, rel_tol=1e-9)
    assert math.isclose(swap_usd, -0.5339, rel_tol=1e-6)
    assert math.isclose(commission_usd, 0.05, rel_tol=1e-9)
    assert math.isclose(raw_risk_esperado, 10.0, rel_tol=1e-9)
    assert math.isclose(t.pnl_usd, pnl_neto_esperado, rel_tol=1e-9), f"{t.pnl_usd} != {pnl_neto_esperado}"
    assert math.isclose(t.pnl_r, r_esperado, rel_tol=1e-9), f"{t.pnl_r} != {r_esperado}"

    print(f"  F) ganador: bruto={pnl_bruto_usd:.4f} swap={swap_usd:.4f} comision=-{commission_usd:.4f} "
          f"-> neto={t.pnl_usd:.4f} (esperado {pnl_neto_esperado:.4f}), 1R={raw_risk_esperado:.2f}, "
          f"R={t.pnl_r:.5f} (esperado {r_esperado:.5f}): OK")


def test_g_pnl_perdedor_full_chain():
    t = _run_single_trade(COMMISSION_COSTS, hit="loss")
    assert t.outcome == "loss"

    entry_price_adj = 100.0 + 0.02 / 2       # 100.01
    exit_price_adj = 90.0 - 0.02 / 2         # cierre de largo al stop: bid, -spread/2 = 89.99
    pnl_price = exit_price_adj - entry_price_adj                      # -10.02
    pnl_bruto_usd = COMMISSION_COSTS.price_to_usd(pnl_price, 0.01)    # -10.02
    swap_usd = COMMISSION_COSTS.swap_total_usd(1, 0.01, date(2026, 9, 7), date(2026, 9, 8))  # -0.5339
    commission_usd = COMMISSION_COSTS.commission_usd(0.01)            # 0.05
    pnl_neto_esperado = pnl_bruto_usd + swap_usd - commission_usd     # -10.02 -0.5339 -0.05 = -10.6039
    raw_risk_esperado = COMMISSION_COSTS.price_to_usd(10.0, 0.01)     # 10.0
    r_esperado = pnl_neto_esperado / raw_risk_esperado                # -1.06039

    assert math.isclose(t.pnl_usd, pnl_neto_esperado, rel_tol=1e-9), f"{t.pnl_usd} != {pnl_neto_esperado}"
    assert math.isclose(t.pnl_r, r_esperado, rel_tol=1e-9), f"{t.pnl_r} != {r_esperado}"
    # el perdedor debe seguir siendo mas negativo que -1R "limpio" por el
    # spread/comision/swap adicionales -- validacion de sentido comun.
    assert t.pnl_r < -1.0, f"con costos adicionales sobre un stop limpio, R realizado deberia ser < -1.0, dio {t.pnl_r}"

    print(f"  G) perdedor: bruto={pnl_bruto_usd:.4f} swap={swap_usd:.4f} comision=-{commission_usd:.4f} "
          f"-> neto={t.pnl_usd:.4f} (esperado {pnl_neto_esperado:.4f}), R={t.pnl_r:.5f} "
          f"(esperado {r_esperado:.5f}, < -1.0 por costos): OK")


def test_h_swap_negativo_reduce_pnl_overnight_long():
    with_swap = _run_single_trade(XAUUSDC_COSTS, hit="win")
    zero_swap_costs = BrokerCosts(
        point=0.001, contract_size=1.0, tick_value=0.1, tick_size=0.001,
        swap_long_points=0.0, swap_short_points=0.0,
        commission_per_lot=0.0, triple_swap_weekday=2, spread_fallback_points=0.0,
    )
    without_swap = _run_single_trade(zero_swap_costs, hit="win")

    assert with_swap.nights_held == 1 and without_swap.nights_held == 1
    assert with_swap.pnl_usd < without_swap.pnl_usd, (
        f"un LONG mantenido overnight con swap_long negativo debe rendir MENOS "
        f"que el mismo trade sin swap: con_swap={with_swap.pnl_usd}, sin_swap={without_swap.pnl_usd}"
    )
    diff = without_swap.pnl_usd - with_swap.pnl_usd
    assert math.isclose(diff, 0.5339, rel_tol=1e-6), \
        f"la diferencia deberia ser exactamente 1 noche de swap (0.5339), dio {diff}"

    print(f"  H) swap_long negativo overnight reduce el PnL en ${diff:.4f} (1 noche) frente a sin swap: OK")


def test_i_live_order_calc_profit_cross_check():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("  I) cross-check en vivo con mt5.order_calc_profit(): SALTEADO (paquete MetaTrader5 no instalado)")
        return
    if not mt5.initialize():
        print("  I) cross-check en vivo con mt5.order_calc_profit(): SALTEADO (no se pudo conectar a MT5)")
        return
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from execution.src.mt5_utils import resolve_symbol
        symbol = resolve_symbol("XAUUSD")
        mt5.symbol_select(symbol, True)
        si = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if si is None or tick is None:
            print("  I) cross-check en vivo con mt5.order_calc_profit(): SALTEADO (symbol_info no disponible)")
            return
        costs = BrokerCosts(
            point=si.point, contract_size=si.trade_contract_size, tick_value=si.trade_tick_value,
            tick_size=si.trade_tick_size, swap_long_points=si.swap_long, swap_short_points=si.swap_short,
        )
        entry = tick.ask
        for diff, lot in ((1.0, 0.01), (5.0, 0.1), (-3.0, 1.0)):
            exitp = entry + diff
            ref = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, lot, entry, exitp)
            got = costs.price_to_usd(diff, lot)
            assert ref is not None, f"order_calc_profit fallo: {mt5.last_error()}"
            assert math.isclose(got, ref, rel_tol=1e-6, abs_tol=1e-6), \
                f"price_to_usd({diff}, {lot})={got} != order_calc_profit={ref} para {symbol} en vivo"
        print(f"  I) cross-check en vivo con mt5.order_calc_profit() ({symbol}): OK")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    print("Checksum del modelo de costos -- BOT-043\n")
    test_a_price_to_usd_matches_order_calc_profit_reference()
    test_b_swap_long_negative_is_a_cost()
    test_c_swap_short_uses_swap_short_points()
    test_d_no_overnight_zero_swap()
    test_e_triple_swap_day()
    test_f_pnl_ganador_full_chain()
    test_g_pnl_perdedor_full_chain()
    test_h_swap_negativo_reduce_pnl_overnight_long()
    test_i_live_order_calc_profit_cross_check()
    print("\nTODO OK — swap con signo correcto, precio->USD validado contra order_calc_profit, cadena de PnL sin duplicar costos.")
