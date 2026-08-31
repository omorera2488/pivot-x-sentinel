"""Checksum mecanico del scoring (strategy/scoring.py) -- mismo estilo que
strategy/test_engine.py: series sinteticas cortas y conocidas, verificadas a
mano, sin comparar contra ningun backtest ni conteo agregado.

Uso:
    python strategy/test_scoring.py
Sale con exit code 0 y "TODO OK" si todos los casos se cumplen, o levanta
AssertionError senalando cual caso fallo.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, para "import strategy"

from strategy.scoring import (
    cvp_score, divergence_score, find_confirmed_pivots, rsi, trend_score,
)


def test_a_rsi_wilder():
    # RSI(period=2) sobre close=[1,2,1,2,3], calculado a mano con la formula
    # de Wilder (sembrado con el promedio simple de las primeras `period`
    # variaciones, igual que ta.rsi de Pine):
    #   delta=[1,-1,1,1] -> gains=[1,0,1,1] losses=[0,1,0,0]
    #   avgGain0=mean([1,0])=0.5  avgLoss0=mean([0,1])=0.5 -> rsi[2]=50
    #   avgGain1=(0.5*1+1)/2=0.75 avgLoss1=(0.5*1+0)/2=0.25 -> rsi[3]=75
    #   avgGain2=(0.75*1+1)/2=0.875 avgLoss2=(0.25*1+0)/2=0.125 -> rsi[4]=87.5
    close = np.array([1, 2, 1, 2, 3], dtype=float)
    out = rsi(close, period=2)
    assert np.isnan(out[0]) and np.isnan(out[1]), "sin suficiente historial, debe ser NaN"
    assert math.isclose(out[2], 50.0, abs_tol=1e-9), f"rsi[2] deberia ser 50, fue {out[2]}"
    assert math.isclose(out[3], 75.0, abs_tol=1e-9), f"rsi[3] deberia ser 75, fue {out[3]}"
    assert math.isclose(out[4], 87.5, abs_tol=1e-9), f"rsi[4] deberia ser 87.5, fue {out[4]}"
    print("  A) RSI de Wilder contra calculo a mano (period=2): OK")


def test_b_confirmed_pivots():
    # series=[0,1,2,5,2,1,0], lbL=lbR=2 -> unico pivote alto en bar=3 (valor
    # 5, maximo estricto de la ventana [1,6)), confirmado recien en bar=5.
    # No hay ningun pivote bajo (los extremos del array no tienen ventana
    # completa a ambos lados para calificar).
    series = np.array([0, 1, 2, 5, 2, 1, 0], dtype=float)
    highs, lows = find_confirmed_pivots(series, lbL=2, lbR=2)
    assert len(highs) == 1, f"se esperaba 1 pivote alto, hubo {len(highs)}"
    assert highs[0].bar == 3 and highs[0].value == 5.0 and highs[0].confirmed_bar == 5, \
        f"pivote alto incorrecto: {highs[0]}"
    assert lows == [], f"no se esperaba ningun pivote bajo, hubo {lows}"
    print("  B) deteccion de pivotes confirmados (tipo ta.pivothigh/pivotlow): OK")


def test_c_divergence_bullish_and_bearish():
    # RSI con dos minimos: bar=2 (valor 30) y bar=8 (valor 40, mas alto) --
    # minimo mas ALTO en RSI. Precio con minimos en las mismas barras pero
    # AL REVES: close[8]=8 < close[2]=9 -- minimo mas BAJO en precio.
    # Divergencia alcista regular, vigente (pivote de bar=8 confirmado en
    # bar=9==current_bar, dentro de fresh_bars=3) y a distancia 6 (dentro de
    # range_min=2/range_max=10).
    rsi_vals = np.array([50, 45, 30, 45, 50, 55, 60, 45, 40, 50], dtype=float)
    close = np.array([10, 10, 9, 10, 10, 10, 10, 10, 8, 10], dtype=float)
    current_bar = 9
    kwargs = dict(lbL=1, lbR=1, range_min=2, range_max=10, fresh_bars=3)

    score_buy, reason_buy = divergence_score(+1, close, rsi_vals, current_bar, **kwargs)
    assert score_buy == 1, f"compra + divergencia alcista a favor deberia dar +1, dio {score_buy} ({reason_buy})"
    assert "alcista" in reason_buy and "a favor" in reason_buy

    score_sell, reason_sell = divergence_score(-1, close, rsi_vals, current_bar, **kwargs)
    assert score_sell == -1, f"venta contra divergencia alcista deberia dar -1, dio {score_sell} ({reason_sell})"
    assert "en contra" in reason_sell

    print("  C) divergencia RSI: a favor (+1) y en contra (-1) del sentido de la entrada: OK")


def test_d_divergence_none():
    # RSI plano -- ningun pivote estricto posible, sin divergencia.
    rsi_vals = np.full(10, 50.0)
    close = np.full(10, 100.0)
    score, reason = divergence_score(+1, close, rsi_vals, 9, lbL=1, lbR=1, range_min=2, range_max=10, fresh_bars=3)
    assert score == 0 and "sin divergencia" in reason, f"se esperaba 0/sin divergencia, dio {score}/{reason}"
    print("  D) sin pivotes -> sin divergencia (0): OK")


def _rising_bars(n, high0=100.0, low0=90.0):
    high = high0 + np.arange(n, dtype=float)
    low = low0 + np.arange(n, dtype=float)
    time_utc = (np.arange(n) * 60).astype("int64")  # velas de 1 minuto
    return time_utc, high, low


def test_e_trend_agreement():
    # Barras estrictamente crecientes (high y low suben en cada vela) ->
    # tanto la ventana de 2min como la de 4min ven bloques con maximos y
    # minimos crecientes (HH/HL) -- alcista en ambas, coinciden.
    n = 20
    time_utc, high, low = _rising_bars(n)
    score_buy, reason_buy = trend_score(+1, time_utc, high, low, windows_min=(2, 4), lookback_blocks=3)
    assert score_buy == 1, f"compra a favor de tendencia alcista en ambas ventanas deberia dar +1, dio {score_buy} ({reason_buy})"
    assert "alcista" in reason_buy

    score_sell, reason_sell = trend_score(-1, time_utc, high, low, windows_min=(2, 4), lookback_blocks=3)
    assert score_sell == -1, f"venta contra tendencia alcista deberia dar -1, dio {score_sell} ({reason_sell})"

    print("  E) tendencia: ambas ventanas coinciden (alcista) -> +1 a favor, -1 en contra: OK")


def test_f_trend_insufficient_history():
    n = 3  # menos barras que las necesarias para cerrar 3 bloques de 4min
    time_utc, high, low = _rising_bars(n)
    score, reason = trend_score(+1, time_utc, high, low, windows_min=(2, 4), lookback_blocks=3)
    assert score == 0 and "insuficiente" in reason, f"se esperaba 0/insuficiente, dio {score}/{reason}"
    print("  F) tendencia con historial insuficiente -> 0, sin arriesgar una clasificacion: OK")


def test_g_cvp_margin():
    # entry=100 stop=99 (sl=1) target=102 (tp=2), spread=0.1, sin comision,
    # fixed_lot=1, contract_size=1:
    #   sl_neto=1.1  tp_neto=1.9  breakeven=1.1/3.0*100=36.667%
    # aciertos=80% -> margen=43.33 (> 10 -> holgado, +1)
    # aciertos=30% -> margen=-6.67 (<=0 -> no cubre costos, 0, sin bloquear)
    # aciertos=None -> datos insuficientes, 0
    score_holgado, reason_holgado, margen_holgado = cvp_score(
        +1, entry=100.0, stop=99.0, target=102.0, spread_price=0.1,
        commission_usd=0.0, fixed_lot=1.0, contract_size=1.0, aciertos_pct=80.0)
    assert score_holgado == 1, f"margen holgado deberia dar +1, dio {score_holgado}"
    assert math.isclose(margen_holgado, 43.333333, abs_tol=1e-3), f"margen incorrecto: {margen_holgado}"

    score_neg, reason_neg, margen_neg = cvp_score(
        +1, entry=100.0, stop=99.0, target=102.0, spread_price=0.1,
        commission_usd=0.0, fixed_lot=1.0, contract_size=1.0, aciertos_pct=30.0)
    assert score_neg == 0 and "no cubre costos" in reason_neg, f"margen negativo deberia dar 0/no cubre costos, dio {score_neg}/{reason_neg}"
    assert margen_neg < 0

    score_none, reason_none, margen_none = cvp_score(
        +1, entry=100.0, stop=99.0, target=102.0, spread_price=0.1,
        commission_usd=0.0, fixed_lot=1.0, contract_size=1.0, aciertos_pct=None)
    assert score_none == 0 and margen_none is None and "insuficientes" in reason_none

    print("  G) CVP: margen holgado (+1), margen negativo sin bloquear (0), datos insuficientes (0): OK")


if __name__ == "__main__":
    print("Checksum mecanico del scoring (Divergencia + Tendencia + CVP)\n")
    test_a_rsi_wilder()
    test_b_confirmed_pivots()
    test_c_divergence_bullish_and_bearish()
    test_d_divergence_none()
    test_e_trend_agreement()
    test_f_trend_insufficient_history()
    test_g_cvp_margin()
    print("\nTODO OK — scoring de entradas validado.")
