"""Registro local de `OutcomeObservation` -- BOT-051.5.

Separado SEMANTICAMENTE de `execution/src/score_store.py` (Signal Quality,
inmutable, capturado en `t0` cuando nace la LIMIT) aunque comparte el mismo
patron de infraestructura (JSONL append-only, "ultima linea gana" por
ticket, mismo `user_data_root()`). Un `OutcomeObservation` describe que paso
DESPUES de que naciera la LIMIT -- nunca se usa para modificar el snapshot
de Signal Quality ya persistido en `score_store` (ver
`strategy/signal_quality.py`, `SignalQualityVectorV1` es `frozen=True`).

Identidad: `ticket` == el `order_ticket` que `score_store` ya usa como clave
-- ver `execution/src/signal_quality_reconciliation.py` para la evidencia de
por que ese unico valor alcanza (no se inventan IDs artificiales).

"Actualizar" un outcome (ej. de PENDING a FILLED, o de FILLED a CLOSED) es
agregar una linea NUEVA -- nunca se reescribe una linea vieja. `load_all()`
se queda con la ULTIMA linea de cada ticket, igual que `score_store`."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import user_data_root

# user_data_root(), NO app_root() -- mismo motivo que score_store.py: tiene
# que sobrevivir un upgrade del instalador.
DATA_DIR = user_data_root() / "execution" / "data" / "outcomes"

# Campos que NUNCA deben aparecer dentro de un SignalQualityVectorV1 -- ver
# strategy/test_signal_quality.py (no-outcome-leakage, lado de las features).
# Este set es la garantia estructural del lado contrario: un OutcomeObservation
# vive en su propio objeto/archivo, nunca mezclado con el snapshot de t0.
OUTCOME_ONLY_FIELDS = frozenset({
    "order_final_state", "fill_time_utc", "position_id", "close_time_utc",
    "pnl_gross", "commission", "swap", "pnl_net", "realized_r", "close_reason",
    "open_deal_ticket", "close_deal_ticket",
})


def _store_path(symbol: str, magic: int) -> Path:
    safe_symbol = "".join(c if c.isalnum() else "_" for c in symbol)
    return DATA_DIR / f"{safe_symbol}_{magic}.jsonl"


def record(symbol: str, magic: int, observation: dict) -> None:
    """Agrega una linea con el `OutcomeObservation` completo -- ver
    `signal_quality_reconciliation.py::reconcile_ticket()` para el schema
    exacto. Append-only: no hace falta (ni se permite) editar una linea
    existente."""
    if "ticket" not in observation:
        raise ValueError("OutcomeObservation necesita 'ticket'")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _store_path(symbol, magic)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(observation, ensure_ascii=False) + "\n")


def load_all(symbol: str, magic: int) -> dict[int, dict]:
    """ticket -> OutcomeObservation (el ULTIMO estado conocido). Lineas
    corruptas o incompletas se ignoran en vez de romper toda la lectura
    (mismo criterio que score_store.load_all())."""
    path = _store_path(symbol, magic)
    if not path.exists():
        return {}
    out: dict[int, dict] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                out[int(row["ticket"])] = row
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return out
