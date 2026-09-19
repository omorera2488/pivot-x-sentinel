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
    DIVERGENCE_RESOLUTION_CONFLICT, DIVERGENCE_RESOLUTION_MOST_RECENT, DIVERGENCE_RESOLUTION_NA,
    DIVERGENCE_STATE_BEARISH, DIVERGENCE_STATE_BULLISH, DIVERGENCE_STATE_CONFLICT, DIVERGENCE_STATE_NONE,
    DivergenceCandidate, cvp_score, divergence_detail, divergence_score, find_confirmed_pivots, node_score,
    resolve_divergence, rsi, trend_score,
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


# ---- Fix reports/AUDIT-RSI-DIVERGENCE.md hallazgo #1 (2026-09-19): bullish -----
# ---- y bearish se detectan independientemente y se resuelven por --------------
# ---- confirmation_bar mas reciente (nunca prioridad fija por orden de codigo) -

def _bullish_series(n, prior_bar, prior_rsi, prior_close, latest_bar, latest_rsi, latest_close):
    rsi_vals = np.full(n, 50.0)
    close = np.full(n, 100.0)
    rsi_vals[prior_bar], close[prior_bar] = prior_rsi, prior_close
    rsi_vals[latest_bar], close[latest_bar] = latest_rsi, latest_close
    return rsi_vals, close


def test_i_divergence_only_bullish():
    # unico candidato vigente es bullish (prior bar=60 RSI=20, latest bar=100
    # RSI=30 -- HL) con precio LL (95->90) -- pivotes 5/5 default,
    # confirmation_bar=105.
    rsi_vals, close = _bullish_series(160, 60, 20.0, 95.0, 100, 30.0, 90.0)
    current_bar = 105  # recien confirmado
    score_long, reason_long = divergence_score(+1, close, rsi_vals, current_bar)
    score_short, reason_short = divergence_score(-1, close, rsi_vals, current_bar)
    assert score_long == 1 and "alcista" in reason_long and "a favor" in reason_long
    assert score_short == -1 and "en contra" in reason_short
    detail = divergence_detail(+1, close, rsi_vals, current_bar)
    assert detail.resolved_state == DIVERGENCE_STATE_BULLISH and detail.resolution == DIVERGENCE_RESOLUTION_NA
    assert detail.bearish is None and detail.bullish is not None
    print("  I) solo bullish vigente -> BULLISH, LONG=+1/SHORT=-1: OK")


def test_j_divergence_only_bearish():
    # unico candidato vigente es bearish (prior bar=60 RSI=80, latest bar=100
    # RSI=70 -- LH) con precio HH (100->110) -- confirmation_bar=105.
    rsi_vals = np.full(160, 50.0)
    close = np.full(160, 100.0)
    rsi_vals[60], close[60] = 80.0, 100.0
    rsi_vals[100], close[100] = 70.0, 110.0
    current_bar = 105
    score_long, reason_long = divergence_score(+1, close, rsi_vals, current_bar)
    score_short, reason_short = divergence_score(-1, close, rsi_vals, current_bar)
    assert score_long == -1 and "en contra" in reason_long
    assert score_short == 1 and "bajista" in reason_short and "a favor" in reason_short
    detail = divergence_detail(+1, close, rsi_vals, current_bar)
    assert detail.resolved_state == DIVERGENCE_STATE_BEARISH and detail.resolution == DIVERGENCE_RESOLUTION_NA
    assert detail.bullish is None and detail.bearish is not None
    print("  J) solo bearish vigente -> BEARISH, LONG=-1/SHORT=+1: OK")


def test_k_divergence_none_resolved_state():
    rsi_vals = np.full(160, 50.0)
    close = np.full(160, 100.0)
    detail = divergence_detail(+1, close, rsi_vals, 105)
    assert detail.score == 0 and detail.resolved_state == DIVERGENCE_STATE_NONE
    assert detail.resolution == DIVERGENCE_RESOLUTION_NA
    assert detail.bullish is None and detail.bearish is None
    print("  K) sin ningun candidato vigente -> resolved_state=NONE: OK")


def test_l_divergence_both_bullish_more_recent():
    # bullish: prior=60(RSI20) latest=105(RSI30) -> confirmation_bar=110
    # bearish: prior=50(RSI80) latest=103(RSI70) -> confirmation_bar=108
    # bullish es la MAS RECIENTE (110 > 108) -> debe ganar.
    n = 160
    rsi_vals = np.full(n, 50.0)
    close = np.full(n, 100.0)
    rsi_vals[60], close[60] = 20.0, 95.0
    rsi_vals[105], close[105] = 30.0, 90.0   # bullish LL+HL
    rsi_vals[50], close[50] = 80.0, 100.0
    rsi_vals[103], close[103] = 70.0, 110.0  # bearish HH+LH
    current_bar = 111  # bullish age=1, bearish age=3 -- ambas frescas
    detail = divergence_detail(+1, close, rsi_vals, current_bar)
    assert detail.bullish is not None and detail.bearish is not None, "el caso debe tener ambos candidatos vigentes"
    assert detail.bullish.confirmation_bar == 110 and detail.bearish.confirmation_bar == 108
    assert detail.resolved_state == DIVERGENCE_STATE_BULLISH and detail.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT
    score_long, _ = divergence_score(+1, close, rsi_vals, current_bar)
    score_short, _ = divergence_score(-1, close, rsi_vals, current_bar)
    assert score_long == 1 and score_short == -1
    print("  L) ambas vigentes, bullish mas reciente (110>108) -> BULLISH/MOST_RECENT: OK")


def test_m_divergence_both_bearish_more_recent():
    # Reproduce EXACTAMENTE el bug de la auditoria (hallazgo #1): bullish
    # confirmation_bar=105, bearish confirmation_bar=106 (MAS reciente).
    # Antes del fix, bullish ganaba siempre por orden de codigo (SHORT daba
    # -1). Ahora debe ganar bearish (SHORT debe dar +1).
    n = 160
    rsi_vals = np.full(n, 50.0)
    close = np.full(n, 100.0)
    rsi_vals[60], close[60] = 20.0, 95.0
    rsi_vals[100], close[100] = 30.0, 90.0   # bullish LL+HL, confirmation_bar=105
    rsi_vals[61], close[61] = 80.0, 100.0
    rsi_vals[101], close[101] = 70.0, 110.0  # bearish HH+LH, confirmation_bar=106
    current_bar = 106  # bullish age=1, bearish age=0 -- ambas vigentes
    detail = divergence_detail(-1, close, rsi_vals, current_bar)
    assert detail.bullish.confirmation_bar == 105 and detail.bearish.confirmation_bar == 106
    assert detail.resolved_state == DIVERGENCE_STATE_BEARISH and detail.resolution == DIVERGENCE_RESOLUTION_MOST_RECENT

    score_short, reason_short = divergence_score(-1, close, rsi_vals, current_bar)
    assert score_short == 1, f"BUG DE LA AUDITORIA REGRESO: SHORT deberia dar +1 (bearish mas reciente), dio {score_short}"
    assert "bajista" in reason_short and "a favor" in reason_short

    score_long, reason_long = divergence_score(+1, close, rsi_vals, current_bar)
    assert score_long == -1 and "bajista" in reason_long and "en contra" in reason_long
    print("  M) ambas vigentes, bearish mas reciente (106>105) -> BEARISH/MOST_RECENT (bug de la auditoria corregido): OK")


def test_n_divergence_conflict_same_confirmation_bar():
    # CONFLICT solo puede probarse con candidatos sinteticos: con lbL/lbR
    # fijos e iguales para ambos lados, un mismo bar no puede ser a la vez
    # maximo y minimo estricto de RSI -- por eso se prueba resolve_divergence()
    # directamente en vez de armar una serie de precio real (ver
    # reports/AUDIT-RSI-DIVERGENCE.md, seccion de tests obligatorios #F).
    bullish = DivergenceCandidate(kind="bullish", pivot_bar=100, confirmation_bar=105, age=0,
                                   prior_pivot_bar=60, prior_confirmation_bar=65,
                                   latest_rsi=30.0, prior_rsi=20.0, latest_price=90.0, prior_price=95.0)
    bearish = DivergenceCandidate(kind="bearish", pivot_bar=100, confirmation_bar=105, age=0,
                                   prior_pivot_bar=61, prior_confirmation_bar=66,
                                   latest_rsi=70.0, prior_rsi=80.0, latest_price=110.0, prior_price=100.0)

    res_long = resolve_divergence(+1, bullish, bearish)
    res_short = resolve_divergence(-1, bullish, bearish)
    for res in (res_long, res_short):
        assert res.resolved_state == DIVERGENCE_STATE_CONFLICT
        assert res.resolution == DIVERGENCE_RESOLUTION_CONFLICT
        assert res.score == 0 and "conflicto" in res.reason
    print("  N) empate exacto de confirmation_bar -> CONFLICT, score=0 (LONG y SHORT): OK")


def test_o_divergence_validity_unchanged():
    # La resolucion no debe alterar la vigencia: edad 0..10 activa, 11 expirada
    # (mismo comportamiento que antes del fix, ver reports/AUDIT-RSI-DIVERGENCE.md).
    rsi_vals, close = _bullish_series(160, 60, 20.0, 95.0, 100, 30.0, 90.0)  # confirmation_bar=105
    for current_bar in range(100, 105):
        score, _ = divergence_score(+1, close, rsi_vals, current_bar)
        assert score == 0, f"bar={current_bar} deberia ser NO CONOCIDA (0), dio {score}"
    for current_bar in range(105, 116):
        score, _ = divergence_score(+1, close, rsi_vals, current_bar)
        assert score == 1, f"bar={current_bar} deberia seguir ACTIVA (+1), dio {score}"
    score_expired, _ = divergence_score(+1, close, rsi_vals, 116)
    assert score_expired == 0, f"bar=116 deberia estar EXPIRADA (0), dio {score_expired}"
    print("  O) vigencia sin cambios: activa barras 105..115 (edad 0..10), expira en 116: OK")


def test_p_divergence_causality_unchanged():
    # Causalidad sin cambios: un LIMIT en 101..104 no puede usar el pivote
    # confirmado recien en 105 (mismo escenario que reports/AUDIT-RSI-DIVERGENCE.md).
    rsi_vals, close = _bullish_series(160, 60, 20.0, 95.0, 100, 30.0, 90.0)
    for limit_bar in range(101, 105):
        score, reason = divergence_score(+1, close[:limit_bar + 1], rsi_vals[:limit_bar + 1], limit_bar)
        assert score == 0 and "sin divergencia" in reason, f"LIMIT en {limit_bar} no deberia ver el pivote aun, dio {score}/{reason}"
    score_105, _ = divergence_score(+1, close[:106], rsi_vals[:106], 105)
    assert score_105 == 1, f"LIMIT en 105 deberia ver el pivote recien confirmado, dio {score_105}"
    print("  P) causalidad sin cambios: LIMIT 101-104 -> 0, LIMIT 105 -> divergencia disponible: OK")


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


def test_h_node_score():
    # 10 barras de 1 minuto, periodos_htf_min=100 -> las 10 caen en el MISMO
    # bloque (bucket de 6000s). Casi todo el rango es [100,101] excepto la
    # barra 5, que sube a [104,105] con un volumen 100x mayor al resto --
    # el perfil de volumen deberia concentrar el POC/value area ahi.
    n = 10
    time_utc = (np.arange(n) * 60).astype("int64")
    high = np.full(n, 101.0)
    low = np.full(n, 100.0)
    high[5], low[5] = 105.0, 104.0
    volume = np.full(n, 1.0)
    volume[5] = 100.0

    # camino 100->110 pasa por la zona ~104-105 -> freno, -1
    score_overlap, reason_overlap = node_score(100.0, 110.0, time_utc, high, low, volume, periodos_htf_min=100)
    assert score_overlap == -1, f"camino que pasa por el nodo deberia dar -1, dio {score_overlap} ({reason_overlap})"
    assert "104" in reason_overlap or "105" in reason_overlap, f"el motivo deberia mencionar la zona del nodo: {reason_overlap}"

    # camino 200->210 no pasa cerca del nodo -> 0, nunca suma por ausencia
    score_clear, reason_clear = node_score(200.0, 210.0, time_utc, high, low, volume, periodos_htf_min=100)
    assert score_clear == 0, f"camino lejos del nodo deberia dar 0, dio {score_clear} ({reason_clear})"

    # periodos_htf_min=1 -> bucket de 60s == espaciado de las barras -> el
    # bloque "actual" es UNA sola barra (la ultima), menos que NODE_MIN_BARS
    score_insuf, reason_insuf = node_score(100.0, 110.0, time_utc, high, low, volume, periodos_htf_min=1)
    assert score_insuf == 0 and "insuficiente" in reason_insuf, f"se esperaba 0/insuficiente, dio {score_insuf}/{reason_insuf}"

    print("  H) Nodo (perfil de volumen de rango fijo): freno si el camino cruza el nodo (-1), 0 si no, 0 sin historial: OK")


if __name__ == "__main__":
    print("Checksum mecanico del scoring (Divergencia + Tendencia + CVP)\n")
    test_a_rsi_wilder()
    test_b_confirmed_pivots()
    test_c_divergence_bullish_and_bearish()
    test_d_divergence_none()
    test_i_divergence_only_bullish()
    test_j_divergence_only_bearish()
    test_k_divergence_none_resolved_state()
    test_l_divergence_both_bullish_more_recent()
    test_m_divergence_both_bearish_more_recent()
    test_n_divergence_conflict_same_confirmation_bar()
    test_o_divergence_validity_unchanged()
    test_p_divergence_causality_unchanged()
    test_e_trend_agreement()
    test_f_trend_insufficient_history()
    test_g_cvp_margin()
    test_h_node_score()
    print("\nTODO OK — scoring de entradas validado.")
