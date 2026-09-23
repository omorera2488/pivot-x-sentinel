"""BOT-051.4 -- checksum de strategy/signal_quality.py.

Corre como script plano (convencion del proyecto, sin pytest instalado):
    .venv/Scripts/python.exe strategy/test_signal_quality.py

Complementa (no duplica) scripts/test_signal_quality_vector.py -- ese archivo
ya cubre schema/availability/immutability/determinism/no-outcome-leakage
exhaustivamente sobre las MISMAS clases (reexportadas ahora desde aca). Este
archivo cubre lo especifico de la implementacion productiva: ATR-Wilder,
derivacion de consenso de Alignment, replay de armado/origen, weekday
locale-independiente, y causalidad de compute_signal_quality_at_bar()."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, para "import strategy"

from strategy import engine, signal_quality as sq

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    print("=== A. atr_wilder() ===")
    # 20 barras sinteticas, TR conocido a mano para las primeras -- solo se
    # verifica la propiedad estructural (recursion causal, seed correcta),
    # no se reinventa el valor "correcto" a ojo para cada barra.
    n = 30
    rng = np.random.default_rng(42)
    high = 100 + np.cumsum(rng.normal(0, 0.5, n)) + rng.uniform(0.1, 0.5, n)
    low = high - rng.uniform(0.2, 0.8, n)
    close = low + rng.uniform(0, 1, n) * (high - low)
    atr = sq.atr_wilder(high, low, close, period=14)
    check("atr_wilder: NaN durante warm-up (i<14)", np.all(np.isnan(atr[:14])))
    check("atr_wilder: primer valor no-NaN es la media simple de TR[1:15]",
          math.isclose(atr[14], np.array([max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
                                           for i in range(1, 15)]).mean(), rel_tol=1e-9))
    check("atr_wilder: recursion causal -- atr[20] no depende de barras > 20",
          np.array_equal(sq.atr_wilder(high[:21], low[:21], close[:21], 14), atr[:21], equal_nan=True))

    print("\n=== B. Alignment consensus derivation (truth table) ===")
    # _alignment_label(state, direction_sign): None->UNAVAILABLE, 0->NEUTRAL_MIXED,
    # ==direction_sign->ALIGNED, !=direction_sign->AGAINST
    check("_alignment_label(None, 1) == UNAVAILABLE", sq._alignment_label(None, 1) == "UNAVAILABLE")
    check("_alignment_label(0, 1) == NEUTRAL_MIXED", sq._alignment_label(0, 1) == "NEUTRAL_MIXED")
    check("_alignment_label(1, 1) == ALIGNED", sq._alignment_label(1, 1) == "ALIGNED")
    check("_alignment_label(-1, 1) == AGAINST", sq._alignment_label(-1, 1) == "AGAINST")
    check("_alignment_label(1, -1) == AGAINST", sq._alignment_label(1, -1) == "AGAINST")

    # Consensus truth table -- reproduce exactamente los 6 estados congelados
    # en BOT-047.2.3 sin ambiguedad.
    consensus_cases = [
        (("AGAINST", "AGAINST"), "AGAINST_CONFIRMED"),
        (("ALIGNED", "ALIGNED"), "ALIGNED_CONFIRMED"),
        (("AGAINST", "NEUTRAL_MIXED"), "AGAINST_SINGLE"),
        (("NEUTRAL_MIXED", "AGAINST"), "AGAINST_SINGLE"),
        (("ALIGNED", "NEUTRAL_MIXED"), "ALIGNED_SINGLE"),
        (("NEUTRAL_MIXED", "ALIGNED"), "ALIGNED_SINGLE"),
        (("NEUTRAL_MIXED", "NEUTRAL_MIXED"), "NEUTRAL"),
        (("UNAVAILABLE", "AGAINST"), "UNAVAILABLE"),
        (("ALIGNED", "UNAVAILABLE"), "UNAVAILABLE"),
        (("UNAVAILABLE", "UNAVAILABLE"), "UNAVAILABLE"),
        (("AGAINST", "ALIGNED"), "UNAVAILABLE"),  # flip directo -- N=0 historico, nunca se fuerza un estado
        (("ALIGNED", "AGAINST"), "UNAVAILABLE"),
    ]
    for (b0, b1), expected in consensus_cases:
        got = sq._consensus(b0, b1)
        check(f"_consensus({b0!r}, {b1!r}) == {expected!r}", got == expected, f"got {got!r}")

    print("\n=== C. compute_alignment_consensus() -- reproduce distribucion ya publicada (muestra chica sintetica) ===")
    # No se re-verifica sobre el dataset historico completo aca (eso lo hace
    # scripts/verify_signal_quality_live_parity_xau.py, exhaustivo sobre
    # Universo A) -- aca solo se confirma que la funcion no revienta y
    # devuelve un estado valido sobre una ventana D1 sintetica con
    # suficiente historia.
    n2 = 20000  # ~69 dias M5 -- bastante para varios bloques D1 (1440min) cerrados
    time_utc2 = np.arange(n2, dtype=np.int64) * 300 + 1_700_000_000
    high2 = 100 + np.cumsum(rng.normal(0, 0.05, n2))
    low2 = high2 - rng.uniform(0.05, 0.2, n2)
    state = sq.compute_alignment_consensus(time_utc2, high2, low2, direction_sign=1)
    check("compute_alignment_consensus produce un estado valido (6 estados congelados)",
          state in (sq.ALIGNMENT_STATES | {"UNAVAILABLE"}), f"got {state!r}")

    print("\n=== D. _replay_armado_origin() -- origen del ultimo armado antes de la señal ===")
    # Serie sintetica minima con un armado de venta claro (high toca resistencia)
    # seguido de un cruce hacia abajo de EMA que dispara la señal.
    t3 = np.arange(50, dtype=np.int64) * 300 + 1_700_000_000
    h3 = np.full(50, 100.0)
    l3 = np.full(50, 99.0)
    c3 = np.full(50, 99.5)
    ema3 = np.full(50, 99.5)
    resistencia3 = np.full(50, 100.5)
    soporte3 = np.full(50, 98.5)
    # arma venta en bar 10 (high toca resistencia), cruce hacia abajo en bar 20
    h3[10] = 100.6
    c3[19], ema3[19] = 99.6, 99.5
    c3[20], ema3[20] = 99.4, 99.5
    # Nota: high[i]>=r_i / close comparisons devuelven numpy.bool_, no el
    # Python bool singleton -- se compara con `bool(...) ==`, nunca `is`
    # (np.True_ is True -> False, aunque numpy.bool_(True) sea "verdadero").
    replay = sq._replay_armado_origin(t3, h3, l3, c3, ema3, resistencia3, soporte3)
    check("replay NO detecta señal de venta en la ultima barra (armado bar 10, ya disparo en bar 20, sin re-armar)",
          bool(replay["senal_venta_at_last_bar"]) == False)  # la ultima barra simulada es la 49, no la 20

    # Replay truncado exactamente en la barra de señal (20) -- asi se usaria en vivo/parity.
    replay_at_signal = sq._replay_armado_origin(t3[:21], h3[:21], l3[:21], c3[:21], ema3[:21], resistencia3[:21], soporte3[:21])
    check("replay (truncado en bar 20) SI detecta la señal de venta en la ultima barra",
          bool(replay_at_signal["senal_venta_at_last_bar"]) == True)
    check("origen de la venta es bar 10, level 100.5 (el armado real, no la barra de señal)",
          replay_at_signal["venta"] == {"bar": 10, "level": 100.5}, f"got {replay_at_signal['venta']}")

    # BOT-051.6.3 -- root cause de BOT-051.6.2: close[i]/ema_line[i] son
    # numpy.float64 (arrays numpy REALES, no fixtures ya saneados), la
    # comparacion devuelve numpy.bool_, y "armado_venta and down" puede
    # devolver ese numpy.bool_ TAL CUAL -- exactamente el fixture de arriba
    # (replay_at_signal, senal_venta_at_last_bar=True) es el escenario que
    # faltaba cubrir (Structure replay CONFIRMA la señal, el caso normal que
    # revento json.dumps() en produccion con las LIMITs reales 351931195/
    # 352047367). Verificar tipo NATIVO, no solo el valor logico.
    sv = replay_at_signal["senal_venta_at_last_bar"]
    check("senal_venta_at_last_bar es bool NATIVO de Python (no numpy.bool_), tras el fix",
          type(sv) is bool, f"type={type(sv)}")
    try:
        json.dumps(replay_at_signal)
        json_ok = True
    except TypeError as e:
        json_ok = False
        json_err = repr(e)
    check("json.dumps(replay) no lanza TypeError (bug BOT-051.6.2 corregido)",
          json_ok, "" if json_ok else json_err)

    print("\n=== E. _weekday_from_unix() -- locale-independiente ===")
    # 2026-09-21 00:00:00 UTC es lunes (verificado con datetime.weekday() puro,
    # sin depender de configuracion regional del sistema).
    ts_monday = int(datetime(2026, 9, 21, tzinfo=timezone.utc).timestamp())
    check("2026-09-21 UTC -> Monday", sq._weekday_from_unix(ts_monday) == "Monday")
    ts_friday = int(datetime(2026, 9, 25, tzinfo=timezone.utc).timestamp())
    check("2026-09-25 UTC -> Friday", sq._weekday_from_unix(ts_friday) == "Friday")
    check("weekday enum completo son los 7 dias en ingles, sin depender de locale",
          sq.WEEKDAY_STATES == ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))

    print("\n=== F. compute_signal_quality_at_bar() -- causalidad / no usa datos futuros ===")
    n4 = 5000
    t4 = np.arange(n4, dtype=np.int64) * 300 + 1_700_000_000
    h4 = 100 + np.cumsum(rng.normal(0, 0.05, n4))
    l4 = h4 - rng.uniform(0.05, 0.3, n4)
    c4 = l4 + rng.uniform(0, 1, n4) * (h4 - l4)
    b4 = 4000
    entry4 = float(engine.ema(c4[:b4 + 1], 12)[-1])
    vec_a, diag_a = sq.compute_signal_quality_at_bar(t4, h4, l4, c4, b=b4, direction=1, entry=entry4,
                                                       ema_periods=12, periodos_htf_min=800, observed_at_bar=b4)
    # Extender el array con barras FUTURAS ficticias despues de b4 -- el
    # resultado en b4 debe ser IDENTICO (no debe usar nada con indice > b4).
    extra = 500
    t4b = np.concatenate([t4, np.arange(extra, dtype=np.int64) * 300 + t4[-1] + 300])
    h4b = np.concatenate([h4, 100 + np.cumsum(rng.normal(0, 0.05, extra)) + h4[-1]])
    l4b = np.concatenate([l4, h4b[-extra:] - 0.1])
    c4b = np.concatenate([c4, l4b[-extra:] + 0.05])
    vec_b, diag_b = sq.compute_signal_quality_at_bar(t4b, h4b, l4b, c4b, b=b4, direction=1, entry=entry4,
                                                       ema_periods=12, periodos_htf_min=800, observed_at_bar=b4)
    check("agregar barras FUTURAS despues de b no cambia el vector en b (sin lookahead)",
          vec_a.to_dict() == vec_b.to_dict(), f"a={vec_a.to_dict()}\nb={vec_b.to_dict()}")

    print("\n=== H. BOT-051.6.3 -- diagnostics JSON-safe end-to-end (arrays NumPy reales, sin fixtures presaneados) ===")
    # Recorre el mismo fixture aleatorio de la seccion F (seed fija=42, 100%
    # determinista) buscando al menos una barra donde Structure replay
    # CONFIRME la señal (structure_replay_matches_signal=True) -- el
    # escenario que exactamente rompia json.dumps() en produccion (root
    # cause de BOT-051.6.2). No se usa un valor ya sabido "limpio": se
    # recorre compute_signal_quality_at_bar() de punta a punta, con datos
    # numpy reales, igual que en produccion.
    found_true = found_false = False
    for bH in range(20, n4, 37):  # paso arbitrario, solo para variar la muestra sin recorrer las 5000 barras
        for dirH in (1, -1):
            entryH = float(engine.ema(c4[:bH + 1], 12)[-1])
            _, diagH = sq.compute_signal_quality_at_bar(
                t4, h4, l4, c4, b=bH, direction=dirH, entry=entryH,
                ema_periods=12, periodos_htf_min=800, observed_at_bar=bH,
            )
            match = diagH["structure_replay_matches_signal"]
            check(f"diagnostics(b={bH}, dir={dirH}): structure_replay_matches_signal es bool nativo",
                  type(match) is bool, f"type={type(match)} value={match!r}")
            try:
                json.dumps(diagH)
                json_okH = True
            except TypeError as e:
                json_okH = False
                json_errH = repr(e)
            check(f"diagnostics(b={bH}, dir={dirH}): json.dumps() no lanza",
                  json_okH, "" if json_okH else json_errH)
            if match:
                found_true = True
            else:
                found_false = True
        if found_true and found_false:
            break
    check("se encontro al menos un caso real con structure_replay_matches_signal=True "
          "(el escenario que faltaba cubrir, no solo el caso False)", found_true)
    check("se encontro al menos un caso real con structure_replay_matches_signal=False (contraste)", found_false)

    print("\n=== G. No-outcome-leakage (estructural) ===")
    import inspect
    forbidden = {"pnl", "pnl_r", "pnl_usd", "outcome", "win", "loss", "fill_bar",
                 "mfe", "mae", "close_reason", "tp_hit", "sl_hit", "duration", "fill"}
    sig = inspect.signature(sq.compute_signal_quality_at_bar)
    leaked = forbidden & set(sig.parameters.keys())
    check("compute_signal_quality_at_bar() no tiene ningun parametro de outcome", not leaked, f"leaked={leaked}")
    sig2 = inspect.signature(sq.produce_signal_quality_vector)
    leaked2 = forbidden & set(sig2.parameters.keys())
    check("produce_signal_quality_vector() no tiene ningun parametro de outcome", not leaked2, f"leaked={leaked2}")

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
