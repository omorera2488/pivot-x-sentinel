"""BOT-051.5 -- CLI delgada. La logica real vive en
`execution/src/signal_quality_oos_dataset.py` (modulo de libreria, tambien
usado por `api/app.py::GET /signal-quality/oos-status`) -- una sola fuente
de verdad, sin duplicar el generador de dataset/coverage/readiness.

Uso:
    .venv/Scripts/python.exe scripts/build_signal_quality_oos_dataset.py [--symbol XAUUSDc] [--magic 900001]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.src.signal_quality_oos_dataset import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
