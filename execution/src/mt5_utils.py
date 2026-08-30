"""Utilidades compartidas de la capa de conexion a MT5 (agnostico de broker).

Usado por /execution (motor en vivo, Fase 4) y por /backtests (ingesta de
historial, Fase 3) — vive aca porque es "bridge con MetaTrader5", no logica
de estrategia (eso es /strategy).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import MetaTrader5 as mt5

# El paquete MetaTrader5 no garantiza ser thread-safe si dos llamadas pisan
# el canal de comunicacion con la terminal al mismo tiempo. Desde la Fase 5
# hay dos threads potencialmente golpeando MT5 a la vez (el loop del bot y
# los handlers de la API, que corren en el mismo proceso -- decision de
# Fase 0). Un lock global simple evita que se pisen; no es una API de alta
# concurrencia, no hace falta nada mas fino.
mt5_lock = threading.Lock()


def connect() -> None:
    """Conecta a la terminal MT5 ya abierta/logueada en esta maquina. No
    gestiona credenciales — mt5.initialize() sin argumentos adjunta a la
    instancia corriendo."""
    if not mt5.initialize():
        raise RuntimeError(f"No se pudo conectar a MT5: {mt5.last_error()}")


def find_symbols(base: str) -> list[str]:
    """Busca simbolos que contengan `base` (ej. 'XAUUSD', 'BTCUSD') en el
    broker conectado — nunca se hardcodea un nombre de simbolo completo, cada
    broker le agrega su propio prefijo/sufijo ('XAUUSDm', 'BTCUSDc', ...)."""
    symbols = mt5.symbols_get()
    if symbols is None:
        return []
    base_up = base.upper()
    return sorted(s.name for s in symbols if base_up in s.name.upper())


def find_gold_symbols() -> list[str]:
    """Alias historico de find_symbols('XAU') — lo siguen usando los scripts
    de /backtests."""
    return find_symbols("XAU")


# Bases de instrumento conocidas por el bot, para poder pasar "XAUUSD" o
# "BTCUSD" sin saber de antemano como los nombra el broker conectado. Agregar
# aca cualquier instrumento nuevo que el bot deba soportar.
KNOWN_BASES = ("XAUUSD", "BTCUSD")


def resolve_symbol(requested: str) -> str:
    """Devuelve el nombre de simbolo REAL del broker conectado a partir de lo
    que pidio el usuario ('XAUUSD', 'XAUUSDm', 'BTCUSD', ...) — agnostico de
    broker y de si la cuenta es demo o real (eso solo cambia como se llama el
    simbolo, no la logica de la estrategia, ver strategy/costs.py).

    1. Si `requested` ya es un nombre exacto que el broker reconoce, se usa
       tal cual (permite seguir pasando el nombre completo si se prefiere).
    2. Si no, se extrae la base conocida (KNOWN_BASES) contenida en
       `requested` y se buscan simbolos del broker que la contengan.
       - Exactamente un candidato -> se usa ese.
       - Cero o mas de uno -> error explicito con la lista de candidatos,
         para no operar el instrumento equivocado con plata real.
    """
    if mt5.symbol_select(requested, True):
        return requested

    req_up = requested.upper()
    base = next((b for b in KNOWN_BASES if b in req_up), req_up)
    candidates = find_symbols(base)

    if len(candidates) == 1:
        chosen = candidates[0]
        if not mt5.symbol_select(chosen, True):
            raise RuntimeError(f"No se pudo seleccionar el simbolo resuelto {chosen!r}: {mt5.last_error()}")
        return chosen

    if not candidates:
        raise RuntimeError(
            f"No se pudo seleccionar {requested!r} y no hay ningun simbolo con {base!r} "
            f"en el broker conectado: {mt5.last_error()}"
        )

    raise RuntimeError(
        f"{requested!r} es ambiguo en este broker -- candidatos encontrados: {candidates}. "
        "Especifica el nombre exacto en la config (symbol) para no operar el instrumento equivocado."
    )


def select_symbol(symbol: str):
    """Selecciona el simbolo en Market Watch y devuelve su symbol_info."""
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar el simbolo {symbol!r}: {mt5.last_error()}")
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol!r}) devolvio None: {mt5.last_error()}")
    return info


def measure_broker_offset_seconds(symbol: str, samples: int = 3) -> float:
    """Devuelve el offset (segundos) del servidor del broker respecto a UTC.

    offset > 0  => el reloj del servidor va ADELANTADO respecto a UTC.
    offset < 0  => el reloj del servidor va ATRASADO respecto a UTC.

    Se promedian varias muestras para amortiguar el jitter de red/latencia
    entre la consulta y la respuesta. Ver docs/spec-estrategia.md #3.1.
    """
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar el simbolo {symbol!r}: {mt5.last_error()}")

    offsets = []
    for _ in range(samples):
        t0 = datetime.now(timezone.utc).timestamp()
        tick = mt5.symbol_info_tick(symbol)
        t1 = datetime.now(timezone.utc).timestamp()
        if tick is None:
            continue
        local_mid = (t0 + t1) / 2.0
        offsets.append(tick.time - local_mid)

    if not offsets:
        raise RuntimeError(f"No se pudo obtener ningun tick de {symbol!r} para medir el offset: {mt5.last_error()}")

    return sum(offsets) / len(offsets)


def resolve_filling_mode(symbol: str) -> int:
    """Detecta en tiempo de ejecucion que modo de filling acepta el simbolo
    (spec-live-execution.md #11.3) — no se asume ORDER_FILLING_IOC/FOK/RETURN
    a priori, varia por broker/simbolo.

    El paquete MetaTrader5 de Python NO expone las constantes
    SYMBOL_FILLING_FOK/IOC (solo las ORDER_FILLING_* para armar el request);
    la mascara de symbol_info().filling_mode usa los mismos valores que MQL5
    (FOK=1, IOC=2), asi que se comparan como enteros crudos. Preferencia:
    IOC > FOK > RETURN (fallback si el broker no marca ninguno de los dos
    bits, caso comun en cuentas de tipo netting/hedging con ordenes pendientes)."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol!r}) devolvio None: {mt5.last_error()}")
    modes = info.filling_mode
    FOK, IOC = 1, 2
    if modes & IOC:
        return mt5.ORDER_FILLING_IOC
    if modes & FOK:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN
