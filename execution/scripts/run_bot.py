"""Arranca el motor de ejecucion en vivo — docs/spec-live-execution.md.

Opera de una contra lo que tengas conectado en la terminal MT5 (demo o real
-- esa decision es de quien loguea la cuenta, no de este script). Pasar
--dry-run si queres que calcule todo y solo loguee lo que haria, sin mandar
ordenes -- util para validar una configuracion nueva antes de arriesgar
capital real.

Uso:
    python scripts/run_bot.py [--profile 1m|5m] [--symbol XAUUSDm]
                               [--magic 900001] [--poll 10] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src.bot import LiveExecutionBot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="5m", choices=["1m", "5m", "M1", "M5"])
    ap.add_argument("--symbol", default="XAUUSDm")
    ap.add_argument("--magic", type=int, default=900001)
    ap.add_argument("--poll", type=int, default=10, help="segundos entre sondeos")
    ap.add_argument("--lookback-buckets", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true",
                     help="no manda ordenes reales, solo loguea que haria (default: opera de una)")
    args = ap.parse_args()

    bot = LiveExecutionBot(
        symbol=args.symbol, profile=args.profile, magic=args.magic,
        poll_interval_s=args.poll, lookback_buckets=args.lookback_buckets,
        dry_run=args.dry_run,
    )
    bot.connect()
    bot.replay_startup()
    bot.run()


if __name__ == "__main__":
    main()
