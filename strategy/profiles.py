"""Perfiles de estrategia — un motor (engine.py), dos configuraciones.

/basecode_tradingview tiene dos indicadores Pine separados con sus propios
defaults ("1m EMA y Pivotes ZS" y "5m EMA y Pivotes ZS"), no una sola
estrategia parametrizada por timeframe. Este modulo expone esos dos perfiles
como presets seleccionables sobre el mismo StrategyParams/engine.py — ver
docs/spec-estrategia.md #2 para de donde sale cada default.

Uso:
    from strategy.profiles import get_profile

    params = get_profile("1m")                        # defaults del Pine 1m
    params = get_profile("5m", rr=2.0, buf_bp=1.0)     # defaults del Pine 5m, con overrides
"""
from __future__ import annotations

from dataclasses import replace

from .engine import StrategyParams

# emaPeriods=15, periodos(bloque HTF)=100min -- "1m EMA y Pivotes ZS — trade boxes.txt"
PERFIL_1M = StrategyParams(
    ema_periods=15,
    periodos_htf_min=100,
    buf_bp=0.4,     # default del Pine; a recalibrar para Oro, ver spec-backtest.md #3.1
    rr=1.0,         # default del Pine; ver spec-estrategia.md #1 (el "7" del comentario nunca fue un default real)
    max_concurrent_por_direccion=1,
    valid_bars=10,
    orden_viva=True,
    max_bars_trade=500,
    fixed_lot=0.01,
)

# emaPeriods=12, periodos(bloque HTF)=400min -- "5m EMA y Pivotes ZS — trade boxes.txt"
PERFIL_5M = StrategyParams(
    ema_periods=12,
    periodos_htf_min=400,
    buf_bp=0.4,
    rr=1.0,
    max_concurrent_por_direccion=1,
    valid_bars=10,
    orden_viva=True,
    max_bars_trade=500,
    fixed_lot=0.01,
)

PROFILES: dict[str, StrategyParams] = {"1m": PERFIL_1M, "5m": PERFIL_5M}

# tolera las variantes de nombre que ya se usan en el resto del repo
# (backtests/ usa "M1"/"M5" al estilo de las constantes de MT5)
_ALIASES = {"1m": "1m", "m1": "1m", "1": "1m", "5m": "5m", "m5": "5m", "5": "5m"}


def normalize_profile_name(name: str) -> str:
    """'1m'/'M1'/'1' -> '1m', '5m'/'M5'/'5' -> '5m'. Un solo lugar para el
    mapeo de alias, lo usan get_profile() y execution/ (para elegir timeframe
    de grafico)."""
    key = _ALIASES.get(name.strip().lower())
    if key is None:
        raise ValueError(f"Perfil desconocido: {name!r} (opciones: {list(_ALIASES)})")
    return key


def get_profile(name: str, **overrides) -> StrategyParams:
    """Devuelve el StrategyParams del perfil pedido ('1m'/'M1' o '5m'/'M5'),
    con overrides opcionales (ej. get_profile('5m', rr=2.0))."""
    base = PROFILES[normalize_profile_name(name)]
    return replace(base, **overrides) if overrides else base
