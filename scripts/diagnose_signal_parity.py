"""Diagnostico de paridad barra a barra entre TradingView (Pine) y el motor
de señal real del bot (strategy.live_signal.LiveSignalEngine).

SOLO LECTURA + CALCULO PURO. Este script:
  - conecta a MT5 en modo lectura (mt5.initialize(), symbol_select, copy_rates_range);
  - NO importa ni instancia execution.src.bot.LiveExecutionBot;
  - NO llama _place_order ni ninguna funcion de envio de ordenes (no existe
    ese codigo en este archivo);
  - NO toca posiciones/ordenes existentes ni el flag dry_run (no aplica --
    este script no opera, nunca coloca nada).

Usa LiveSignalEngine real (strategy/live_signal.py), el mismo que corre en
vivo -- no reimplementa EMA/HTF/armado/señal aca. Ver docs/spec-estrategia.md
#3/#4 para la especificacion de lo que imprime.

Protocolo (igual en espiritu a execution.src.bot.LiveExecutionBot.replay_startup,
pero sin ninguno de los efectos secundarios de ese metodo -- no conecta
como bot, no arma self.signal_engine de un LiveExecutionBot, no hay watchers
de ordenes/posiciones):
  1. conectar a MT5 (lectura);
  2. traer velas cerradas desde (--from - --lookback-min) hasta --to;
  3. alimentar TODAS esas velas a un LiveSignalEngine nuevo, en orden, para
     que EMA/armado/bloque HTF esten bien inicializados antes de llegar a
     --from (igual criterio de warmup que bot.py: 3 bloques HTF completos
     por default);
  4. imprimir SOLO las velas con timestamp >= --from (las de warmup no se
     muestran, existen nada mas para inicializar el estado).

Uso:
    python scripts/diagnose_signal_parity.py \
        --symbol XAUUSD --profile 5m \
        --ema-periods 12 --periodos-htf-min 800 --buf-bp 0.4 --rr 1.0 \
        --from 2026-09-03T21:15:00 --to 2026-09-03T22:45:00

    # formato CSV (para redirigir a un archivo y abrir en una planilla):
    python scripts/diagnose_signal_parity.py --from ... --to ... --csv > salida.csv

Todos los timestamps de --from/--to son UTC, formato ISO
(YYYY-MM-DDTHH:MM:SS, sin sufijo de zona -- se asume UTC siempre).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

import MetaTrader5 as mt5

from execution.src.bot import TIMEFRAME_BY_PROFILE
from execution.src.mt5_utils import connect, resolve_symbol, select_symbol
from strategy.engine import StrategyParams
from strategy.htf_session import bucket_start_utc_seconds
from strategy.live_signal import LiveSignalEngine
from strategy.profiles import normalize_profile_name

COLUMNS = [
    "timestamp_utc", "high", "low", "close", "ema",
    "resistencia", "soporte",
    "armado_venta_antes", "armado_compra_antes",
    "cruce_abajo", "cruce_arriba",
    "senal_venta", "senal_compra",
    "armado_venta_despues", "armado_compra_despues",
    "dir", "entry", "stop", "target", "valido",
]


def _parse_utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD", help="base generica o nombre exacto del broker (default: XAUUSD)")
    ap.add_argument("--profile", default="5m", choices=["1m", "5m", "M1", "M5"], help="define el timeframe base")
    ap.add_argument("--ema-periods", type=int, required=True)
    ap.add_argument("--periodos-htf-min", type=int, required=True)
    ap.add_argument("--buf-bp", type=float, required=True)
    ap.add_argument("--rr", type=float, required=True)
    ap.add_argument("--entrada-viva", action="store_true",
                     help="solo informativo: LiveSignalEngine no lo usa (es del ciclo de vida de la orden, ver bot.py)")
    ap.add_argument("--from", dest="from_ts", required=True, help="timestamp UTC ISO, inicio del rango a IMPRIMIR")
    ap.add_argument("--to", dest="to_ts", required=True, help="timestamp UTC ISO, fin del rango a IMPRIMIR")
    ap.add_argument("--lookback-min", type=int, default=None,
                     help="minutos de historia previa a --from para inicializar EMA/armado "
                          "(default: 3 bloques HTF completos, igual criterio que bot.replay_startup)")
    ap.add_argument("--csv", action="store_true", help="salida CSV en vez de tabla legible")
    return ap


def main() -> None:
    args = build_argparser().parse_args()

    profile = normalize_profile_name(args.profile)
    timeframe = TIMEFRAME_BY_PROFILE[profile]
    lookback_min = args.lookback_min if args.lookback_min is not None else 3 * args.periodos_htf_min

    from_dt = _parse_utc(args.from_ts)
    to_dt = _parse_utc(args.to_ts)
    warmup_start_dt = from_dt - timedelta(minutes=lookback_min)

    # --- conexion de SOLO LECTURA -- ver docstring del modulo ---
    connect()
    symbol = resolve_symbol(args.symbol)
    select_symbol(symbol)

    rates = mt5.copy_rates_range(symbol, timeframe, warmup_start_dt, to_dt)
    if rates is None or len(rates) == 0:
        print(f"Sin datos de {symbol} entre {warmup_start_dt} y {to_dt} -- revisa el rango o la conexion.",
              file=sys.stderr)
        sys.exit(1)

    # la ultima posicion de copy_rates_range puede ser la vela EN FORMACION
    # si `to_dt` cae dentro del timeframe actual -- mismo criterio que
    # bot.py (nunca se procesa esa vela). Si to_dt ya quedo en el pasado
    # (caso tipico de este diagnostico, rango historico) no hay vela en
    # formacion que excluir; se detecta comparando contra la hora real.
    now_utc = datetime.now(timezone.utc)
    if to_dt >= now_utc - timedelta(seconds=1):
        rates = rates[:-1]

    params = StrategyParams(
        ema_periods=args.ema_periods, periodos_htf_min=args.periodos_htf_min,
        buf_bp=args.buf_bp, rr=args.rr, entrada_viva=args.entrada_viva,
    )
    engine = LiveSignalEngine(params)

    from_ts = int(from_dt.timestamp())
    to_ts = int(to_dt.timestamp())

    rows = []
    n_warmup = 0
    for r in rates:
        t = int(r["time"])  # SIN corregir por offset -- igual que bot.py (spec-estrategia.md #3.1)
        result = engine.process_bar(t, float(r["high"]), float(r["low"]), float(r["close"]))
        if t < from_ts:
            n_warmup += 1
            continue
        if t > to_ts:
            break
        rows.append((t, r, result))

    print(f"# simbolo={symbol} profile={profile} ema_periods={args.ema_periods} "
          f"periodos_htf_min={args.periodos_htf_min} buf_bp={args.buf_bp} rr={args.rr} "
          f"entrada_viva={args.entrada_viva} (no usado por LiveSignalEngine)", file=sys.stderr)
    print(f"# warmup: {n_warmup} velas cerradas desde {warmup_start_dt} UTC hasta {from_dt} UTC", file=sys.stderr)
    print(f"# rango impreso: {from_dt} UTC -> {to_dt} UTC ({len(rows)} velas)", file=sys.stderr)

    signal_rows = [(t, res) for t, r, res in rows if res.dir is not None]
    if signal_rows:
        for t, res in signal_rows:
            print(f"#   señal en {datetime.fromtimestamp(t, tz=timezone.utc)} UTC: "
                  f"dir={res.dir:+d} entry={res.entry:.3f} stop={res.stop:.3f} "
                  f"target={res.target} valido={res.valido}", file=sys.stderr)
    else:
        print("#   sin señales en el rango impreso", file=sys.stderr)

    if args.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(COLUMNS)
        for t, r, res in rows:
            writer.writerow([
                datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                _fmt(float(r["high"])), _fmt(float(r["low"])), _fmt(float(r["close"])), _fmt(res.ema),
                _fmt(res.resistencia), _fmt(res.soporte),
                _fmt(res.armado_venta_antes), _fmt(res.armado_compra_antes),
                _fmt(res.cruce_abajo), _fmt(res.cruce_arriba),
                _fmt(res.senal_venta), _fmt(res.senal_compra),
                _fmt(res.armado_venta), _fmt(res.armado_compra),
                _fmt(res.dir), _fmt(res.entry), _fmt(res.stop), _fmt(res.target), _fmt(res.valido),
            ])
    else:
        header = (f"{'timestamp UTC':<20}{'high':>9}{'low':>9}{'close':>9}{'ema':>10}"
                  f"{'resist':>10}{'soport':>10}{'aV_ant':>7}{'aC_ant':>7}{'xAbajo':>7}{'xArriba':>8}"
                  f"{'sVenta':>7}{'sCompra':>8}{'aV_des':>7}{'aC_des':>7}{'dir':>4}{'entry':>10}"
                  f"{'stop':>10}{'target':>10}{'valido':>7}")
        print(header)
        print("-" * len(header))
        for t, r, res in rows:
            ts = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            marker = " <--" if res.dir is not None else ""
            print(f"{ts:<20}{float(r['high']):>9.3f}{float(r['low']):>9.3f}{float(r['close']):>9.3f}"
                  f"{res.ema:>10.3f}{res.resistencia:>10.3f}{res.soporte:>10.3f}"
                  f"{_fmt(res.armado_venta_antes):>7}{_fmt(res.armado_compra_antes):>7}"
                  f"{_fmt(res.cruce_abajo):>7}{_fmt(res.cruce_arriba):>8}"
                  f"{_fmt(res.senal_venta):>7}{_fmt(res.senal_compra):>8}"
                  f"{_fmt(res.armado_venta):>7}{_fmt(res.armado_compra):>7}"
                  f"{_fmt(res.dir):>4}{_fmt(res.entry):>10}{_fmt(res.stop):>10}"
                  f"{_fmt(res.target):>10}{_fmt(res.valido):>7}{marker}")


if __name__ == "__main__":
    main()
