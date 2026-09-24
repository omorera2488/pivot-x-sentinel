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

BOT-051.4: agrega un campo opcional `signal_quality` (snapshot inmutable de
`strategy.signal_quality.SignalQualityVectorV1`, serializado via `.to_dict()`)
a la MISMA linea/ticket, junto al `score` ya existente -- no un archivo
aparte, no una reescritura del formato. Backward-compatible por construccion:
una linea vieja simplemente no tiene la clave `signal_quality` (`load_all()`
la completa con `None`); `record()` sigue aceptando `signal_quality=None`
(default) para cualquier llamador que no lo pase, sin cambiar el
comportamiento de `score` en absoluto.

BOT-051.6.3 (ver reports/BOT-051.6.2-* y reports/BOT-051.6.3-*): `record()`
normaliza tipos numpy escalares (`_json_safe()`, abajo) antes de serializar
-- defensa en profundidad DESPUES de corregir la causa raiz real en el
productor (`strategy/signal_quality.py`). Decision explicita: solo convierte
`numpy.bool_`/`numpy.integer`/`numpy.floating` (los tipos razonablemente
esperables desde `strategy/`), nunca objetos arbitrarios a texto -- una
estructura genuinamente invalida sigue rompiendo `json.dumps()` en vez de
persistirse silenciosamente mal."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import provenance
from .paths import user_data_root

# user_data_root(), NO app_root(): esto tiene que sobrevivir un upgrade del
# instalador (ver execution/src/paths.py -- app_root() apunta a la carpeta
# _internal que un upgrade borra y reconstruye entera).
DATA_DIR = user_data_root() / "execution" / "data" / "scores"


def _store_path(symbol: str, magic: int) -> Path:
    safe_symbol = "".join(c if c.isalnum() else "_" for c in symbol)
    return DATA_DIR / f"{safe_symbol}_{magic}.jsonl"


def _json_safe(value):
    """BOT-051.6.3 -- defensa en profundidad, NO el fix principal (ese vive
    en el productor, `strategy/signal_quality.py::_replay_armado_origin()` /
    `compute_signal_quality_at_bar()`, ver BOT-051.6.2). Convierte SOLO los
    tipos escalares de numpy razonablemente esperables desde `strategy/`
    (`numpy.bool_`, `numpy.integer`, `numpy.floating`) a su equivalente
    nativo de Python, recorriendo dicts/listas. Deliberadamente NO intenta
    convertir nada mas: un tipo no reconocido (ej. un objeto arbitrario, un
    `numpy.ndarray` completo) se devuelve TAL CUAL, para que `json.dumps()`
    siga fallando fuerte y visible en vez de ocultar una estructura invalida
    convirtiendola a texto. No reemplaza la disciplina de casteo en el
    productor -- es una red de seguridad para un futuro campo que se agregue
    sin ese cuidado, no una licencia para dejar de tenerlo."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def record(symbol: str, magic: int, ticket: int, entry_score: dict | None,
           signal_quality: dict | None = None, signal_quality_diagnostics: dict | None = None,
           hch: dict | None = None) -> None:
    """Agrega una linea {ticket, score:{...}, signal_quality:{...},
    signal_quality_diagnostics:{...}, hch:{...}} (cada clave solo si se paso)
    al archivo del symbol+magic. `entry_score` puede ser None (ej. si solo se
    pudo calcular Signal Quality) -- en ese caso la linea no lleva `score`.

    `signal_quality_diagnostics` (BOT-051.5, seccion 10): telemetria de POR
    QUE cada factor quedo UNAVAILABLE (`warmup`/`alignment_history`/
    `structure_replay_mismatch`/`market_history_fetch_error`/
    `unexpected_exception`/`other`) -- deliberadamente SEPARADA de
    `signal_quality` (nunca dentro de `SignalQualityVectorV1`, que es
    inmutable y congelado): esto es observabilidad tecnica sobre el PROCESO
    de calculo, no una feature de calidad de la señal.

    `hch` (BOT-052.2): snapshot inmutable del estado de HCH ("Lector de
    confluencias", ver `strategy/hch.py`) al nacer ESTA LIMIT --
    `hch_state`/`hch_version`/`hch_captured_at`/`hch_consumed_on_signal_bar`
    + los campos de auditoria (`hch_pivot_1/2/3`, `hch_active_level`,
    `hch_formation_bar`) que devuelve `strategy.hch.hch_state_for_signal()`.
    Vive en la MISMA linea que `signal_quality` (misma clave `ticket`) para
    que ambos snapshots queden joineables por diseño sin una segunda fuente
    de verdad -- shadow puro, nunca participa de ninguna decision de
    entrada/salida.

    Si dos tickets se repiten (no deberia pasar -- MT5 no reusa tickets), la
    lectura (load_all) se queda con la ULTIMA linea de ese ticket."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _store_path(symbol, magic)
    row: dict = {"ticket": ticket}
    if entry_score is not None:
        row["score"] = entry_score
    if signal_quality is not None:
        row["signal_quality"] = signal_quality
        # BOT-051.5 -- provenance SOLO cuando hay signal_quality que fechar
        # (no tiene sentido para una fila que es puro `score`, comportamiento
        # de antes de BOT-051.4). Fail-safe (provenance.snapshot() nunca
        # lanza) -- ver execution/src/provenance.py.
        row["provenance"] = provenance.snapshot()
    if signal_quality_diagnostics is not None:
        row["signal_quality_diagnostics"] = signal_quality_diagnostics
    if hch is not None:
        row["hch"] = hch
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_json_safe(row), ensure_ascii=False) + "\n")


def load_all(symbol: str, magic: int) -> dict[int, dict]:
    """ticket -> {**score_fields, "signal_quality": {...} | None,
    "signal_quality_diagnostics": {...} | None}. Los campos de `score` (tal
    cual EntryScore.to_dict()) siguen quedando al nivel superior --
    comportamiento IDENTICO al de antes de BOT-051.4 para cualquier lector
    existente de esos campos (ej. panel/app.js::scoreBadge()). `signal_quality`
    es una clave nueva, siempre presente (None para registros que no lo
    tienen -- viejos, o nuevos donde solo se pudo calificar la entrada).
    `signal_quality_diagnostics` (BOT-051.6): mismo trato -- siempre presente,
    None si el registro no la tiene (viejos, o `signal_quality` completo sin
    ningun factor UNAVAILABLE que justifique una razon) -- el panel la usa
    para mostrar "Reason: <razon real>" junto a cada factor UNAVAILABLE (ver
    signalQualityFactor() en panel/app.js), nunca para alterar el vector
    congelado en si. `hch` (BOT-052.2): mismo trato -- siempre presente, None
    si el registro no la tiene (anterior a BOT-052.2). Lineas corruptas o
    incompletas (ej. un crash a mitad de escritura) se ignoran en vez de
    romper toda la lectura -- es un registro de conveniencia para el panel,
    no una fuente critica."""
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
                ticket = int(row["ticket"])
                out[ticket] = {
                    **row.get("score", {}),
                    "signal_quality": row.get("signal_quality"),
                    "signal_quality_diagnostics": row.get("signal_quality_diagnostics"),
                    "hch": row.get("hch"),
                }
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return out


def load_all_raw(symbol: str, magic: int) -> dict[int, dict]:
    """BOT-051.5 -- ticket -> fila COMPLETA tal cual se persistio (`ticket`,
    `score`, `signal_quality`, `signal_quality_diagnostics`, `hch` --
    BOT-052.2 --, cada una presente solo si se guardo). Usado por el
    generador de dataset OOS y por
    la matriz de coverage (scripts/build_signal_quality_oos_dataset.py) --
    necesitan las tres piezas juntas sin la mezcla de `load_all()` (pensada
    para el panel) ni el filtro exclusivo de `load_all_signal_quality()`."""
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


def load_all_signal_quality(symbol: str, magic: int) -> dict[int, dict]:
    """BOT-051.5 -- ticket -> signal_quality dict RAW (tal cual se persistio,
    sin mezclar con los campos de `score`), solo para tickets que SI tienen
    la clave. Usado por el bridge de reconciliacion OOS
    (execution/src/signal_quality_reconciliation.py) para enumerar que
    snapshots existen sin ambiguedad de nombres de campo -- `load_all()`
    sigue siendo la fuente para el panel (necesita `score` al nivel
    superior, ver docstring de esa funcion)."""
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
                if "signal_quality" not in row or row["signal_quality"] is None:
                    continue
                out[int(row["ticket"])] = row["signal_quality"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return out
