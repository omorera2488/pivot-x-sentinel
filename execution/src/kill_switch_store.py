"""Persistencia del OVERRIDE diario del Kill switch -- BOT-032.

A diferencia de `execution/src/score_store.py` (un log JSONL append-only,
porque ahi cada linea es un registro historico que vale la pena conservar),
aca solo importa el ULTIMO valor: si el usuario ya confirmo "Iniciar de
todas formas" para el dia operativo actual. Un JSON simple sobreescrito en
cada override es mas simple y correcto para ese caso -- no hay ningun
historico de overrides que preservar.

El P&L en si NUNCA se persiste aca (BOT-032 #12/#13): se recalcula siempre
desde MT5 (ver execution/src/kill_switch.py). Este archivo es exclusivamente
"a que fecha operativa el usuario ya autorizo continuar", para que:
  - sobreviva un reinicio de la app (#13, via user_data_root() -- el mismo
    mecanismo que score_store.py, que sobrevive upgrades del instalador
    porque packaging/installer.iss solo borra `_internal`, nunca esto);
  - un dia operativo nuevo invalide el override anterior por simple
    comparacion de fechas, sin depender de ningun timer (#11).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .paths import user_data_root

DATA_DIR = user_data_root() / "execution" / "data" / "kill_switch"


def _store_path(symbol: str, magic: int) -> Path:
    safe_symbol = "".join(c if c.isalnum() else "_" for c in symbol)
    return DATA_DIR / f"{safe_symbol}_{magic}.json"


def load_override_date(symbol: str, magic: int) -> date | None:
    """Fecha operativa (ISO) del ultimo override confirmado, o None si nunca
    se confirmo uno (o el archivo esta corrupto/incompleto -- se trata igual
    que "no hay override", nunca se asume autorizacion por un dato dudoso)."""
    path = _store_path(symbol, magic)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return date.fromisoformat(raw["override_operating_date"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
        return None


def record_override(symbol: str, magic: int, operating_date: date) -> None:
    """Idempotente: confirmar de nuevo el mismo dia operativo simplemente
    reescribe el mismo valor."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _store_path(symbol, magic)
    path.write_text(json.dumps({"override_operating_date": operating_date.isoformat()}), encoding="utf-8")
