"""BOT-052.2 Phase 9 -- CLI delgada. La logica real vive en
`execution/src/hch_oos_dataset.py` (modulo de libreria) -- una sola fuente de
verdad, mismo patron que `scripts/build_signal_quality_oos_dataset.py`
(BOT-051.5).

Uso:
    .venv/Scripts/python.exe scripts/build_hch_oos_dataset.py [--symbol XAUUSDc] [--magic 900001]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.src.hch_oos_dataset import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
