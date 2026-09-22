"""BOT-051.3/BOT-051.4 -- SignalQualityVectorV1 producer, thin re-export.

BOT-051.4 promoted the canonical schema/types/assembly function to
`strategy/signal_quality.py` (the production module -- it needed to live
under `strategy/` so `execution/src/bot.py` could import it, and the task
explicitly asked for a single source of truth rather than two independent
copies of the same dataclasses). This module now only re-exports those names
so the offline research scripts written during BOT-051.1/.2/.3
(`scripts/reconstruct_signal_quality_vector_v1_xau.py`,
`scripts/reconstruct_signal_quality_vector_full_universe_xau.py`,
`scripts/test_signal_quality_vector.py`) keep working unchanged -- backward
compatible by construction, not by coincidence.

`produce_from_row()` stays here (not moved): it is offline-script-specific
convenience (builds a vector from a pandas row shaped like the CSV audit
artifacts), not part of the frozen production contract.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from strategy.signal_quality import (  # noqa: E402,F401 -- re-exported for backward compatibility
    SCHEMA_VERSION, ALIGNMENT_STATES, WEEKDAY_STATES,
    FactorObservation, SignalQualityVectorV1, produce_signal_quality_vector,
)


def produce_from_row(row) -> SignalQualityVectorV1:
    """Convenience constructor from a pandas Series / dict-like row shaped
    like reports/BOT-051.3-signal-quality-vector-shadow-xau.csv."""
    import pandas as pd
    return produce_signal_quality_vector(
        observed_at_bar=int(row["limit_created_bar"]),
        observed_at_time_utc=pd.Timestamp(row["limit_created_time_utc"]).to_pydatetime(),
        direction=row["direction"],
        roc_atr_3=row["roc_atr_3"] if pd.notna(row["roc_atr_3"]) else None,
        alignment_consensus_state=row["alignment"],
        origin_dist_atr=row["origin_dist_atr"] if pd.notna(row["origin_dist_atr"]) else None,
        weekday=row["weekday"] if pd.notna(row["weekday"]) else None,
    )
