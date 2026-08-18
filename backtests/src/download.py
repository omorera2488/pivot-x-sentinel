"""Descarga de historial OHLC de MT5 por chunks. Ver docs/spec-backtest.md #2.3.

`copy_rates_range` en el servidor probado (Exness-MT5Trial11) devuelve como
maximo ~100.000 velas por llamada; pedir un rango mas grande no falla con un
error claro, devuelve un unico bar "fantasma" que no corresponde al rango
pedido. Por eso se descarga hacia atras en ventanas de tamano fijo y se corta
apenas una ventana devuelve <=1 vela (senal de haber llegado al limite real
de historial del servidor, no un rango vacio por fin de semana/feriado).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import MetaTrader5 as mt5

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "D1": mt5.TIMEFRAME_D1,
}

CHUNK_DAYS_BY_TF = {
    "M1": 25,
    "M5": 90,
    "M15": 300,
    "H1": 1200,
    "D1": 3650,
}


def find_gold_symbols() -> list[str]:
    """Busca simbolos que contengan 'XAU' en el broker conectado."""
    symbols = mt5.symbols_get()
    if symbols is None:
        return []
    return sorted(s.name for s in symbols if "XAU" in s.name.upper())


def download_history(symbol: str, timeframe: str, max_chunks: int = 60) -> pd.DataFrame:
    """Descarga hacia atras en chunks hasta agotar el historial real del servidor.

    Devuelve un DataFrame con columnas: time (epoch seg, server), open, high,
    low, close, tick_volume, spread (puntos), real_volume — ordenado
    ascendente por tiempo, sin duplicados.
    """
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"timeframe no soportado: {timeframe!r}")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"No se pudo seleccionar el simbolo {symbol!r}: {mt5.last_error()}")

    tf = TIMEFRAME_MAP[timeframe]
    chunk_days = CHUNK_DAYS_BY_TF[timeframe]

    now = datetime.now(timezone.utc)
    cursor = now
    frames = []
    for _ in range(max_chunks):
        start = cursor - timedelta(days=chunk_days)
        rates = mt5.copy_rates_range(symbol, tf, start, cursor)
        n = 0 if rates is None else len(rates)
        if n <= 1:
            break
        df = pd.DataFrame(rates)
        frames.append(df)
        cursor = start

    if not frames:
        raise RuntimeError(f"No se pudo descargar historial de {symbol!r} {timeframe!r}: {mt5.last_error()}")

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    return out


def save_history(df: pd.DataFrame, symbol: str, timeframe: str, data_dir: Path, offset_seconds: float) -> Path:
    """Persiste el historial crudo + una columna time_utc corregida por offset."""
    data_dir.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["time_server"] = df["time"].astype("int64")
    df["time_utc"] = (df["time_server"] - round(offset_seconds)).astype("int64")
    df.attrs["symbol"] = symbol
    df.attrs["timeframe"] = timeframe
    df.attrs["offset_seconds"] = offset_seconds

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = data_dir / f"{symbol}_{timeframe}_{stamp}.parquet"
    df.to_parquet(path, index=False)

    latest = data_dir / f"{symbol}_{timeframe}_latest.parquet"
    df.to_parquet(latest, index=False)
    return path
