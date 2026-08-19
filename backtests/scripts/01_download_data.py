"""Descarga el historial de XAUUSDm M5 desde la terminal MT5 conectada.
Ver docs/spec-backtest.md #2.

Uso:
    python scripts/01_download_data.py [SIMBOLO] [TIMEFRAME]
Default: XAUUSDm M5
"""
import sys
from pathlib import Path

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backtests/, para "import src"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repo root, para "import execution"

from src.download import download_history, save_history
from execution.src.mt5_utils import find_gold_symbols, measure_broker_offset_seconds

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSDm"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "M5"

    ok = mt5.initialize()
    if not ok:
        print("No se pudo conectar a MT5:", mt5.last_error())
        sys.exit(1)

    acc = mt5.account_info()
    print(f"Conectado: cuenta {acc.login} server {acc.server}")

    gold = find_gold_symbols()
    print(f"Simbolos con 'XAU' disponibles: {gold}")
    if symbol not in gold:
        print(f"AVISO: {symbol!r} no aparece entre los simbolos disponibles; se intenta igual.")

    offset_s = measure_broker_offset_seconds(symbol)
    print(f"Offset del servidor vs UTC: {offset_s:+.2f} s")

    print(f"Descargando {symbol} {timeframe} por chunks...")
    df = download_history(symbol, timeframe)
    print(f"Total velas descargadas: {len(df)}")
    if len(df):
        import datetime as _dt
        first = _dt.datetime.utcfromtimestamp(int(df['time'].iloc[0]))
        last = _dt.datetime.utcfromtimestamp(int(df['time'].iloc[-1]))
        print(f"Rango: {first} .. {last}")

    path = save_history(df, symbol, timeframe, DATA_DIR, offset_s)
    print(f"Guardado en: {path}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
