"""Registro local de la calificacion (strategy.scoring.EntryScore) de cada
orden colocada por el bot -- EXCEPCION deliberada a la nota de metadatos de
bot.py (ese docstring dice que MT5 ya guarda todo lo necesario y que no hace
falta un registro local aparte -- cierto para todo lo que hay hoy, pero el
desglose de 3 factores + el motivo de cada uno no tiene ningun campo donde
vivir dentro de una orden/posicion de MT5, asi que si necesita uno).

Un archivo JSONL append-only por symbol+magic, una linea por orden colocada
(ticket -> score). Se elige JSONL en vez de reescribir un JSON completo cada
vez para que una escritura a mitad de camino (crash, corte de luz) nunca deje
el archivo entero corrupto -- a lo sumo se pierde la ultima linea.

Clave de union con el historial de MT5: el ticket que devuelve order_send()
para una orden pendiente es el mismo que MT5 usa despues como ticket de la
posicion al llenarse (bot.py:_reconcile() ya asume esto), y ese valor es el
`position_id` que trae cada deal de /history -- por eso ESTE modulo indexa
por ese mismo ticket, sin traducir nada.
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import app_root

DATA_DIR = app_root() / "execution" / "data" / "scores"


def _store_path(symbol: str, magic: int) -> Path:
    safe_symbol = "".join(c if c.isalnum() else "_" for c in symbol)
    return DATA_DIR / f"{safe_symbol}_{magic}.jsonl"


def record(symbol: str, magic: int, ticket: int, entry_score: dict) -> None:
    """Agrega una linea {ticket, score:{...}} al archivo del symbol+magic.
    Si dos tickets se repiten (no deberia pasar -- MT5 no reusa tickets), la
    lectura (load_all) se queda con la ULTIMA linea de ese ticket."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _store_path(symbol, magic)
    row = {"ticket": ticket, "score": entry_score}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_all(symbol: str, magic: int) -> dict[int, dict]:
    """ticket -> score (dict, tal cual EntryScore.to_dict()). Lineas
    corruptas o incompletas (ej. un crash a mitad de escritura) se ignoran en
    vez de romper toda la lectura -- es un registro de conveniencia para el
    panel, no una fuente critica."""
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
                out[int(row["ticket"])] = row["score"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return out
