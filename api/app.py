"""API local — Fase 5. Expone el estado del bot de Fase 4 por HTTP: balance/
equity, posiciones abiertas y pendientes, historico de operaciones, log de
eventos, y control de iniciar/detener. Ver docs/spec-api.md.

Corre en el MISMO proceso que el bot (decision de Fase 0: sin procesos
paralelos, sin "shadow"): el loop del bot (`execution/src/bot.py`) corre en
un thread de background que esta API arranca/para. Todo acceso a MT5 (desde
el thread del bot y desde los handlers de esta API) pasa por el mismo lock
(`execution.src.mt5_utils.mt5_lock`) para no pisarse.

Uso:
    uvicorn api.app:app --host 127.0.0.1 --port 8000

Solo bindea a localhost por default -- es un panel/API personal para correr
en la misma maquina que la terminal MT5, no un servicio expuesto a otras
maquinas (no hay autenticacion, ver docs/spec-api.md #6).
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

import MetaTrader5 as mt5
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from execution.src.bot import LiveExecutionBot
from execution.src.mt5_utils import mt5_lock
from strategy.profiles import PROFILES

app = FastAPI(title="pivot-x-sentinel API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)  # el panel (Fase 6) puede correr en otro puerto/origen en dev; la API igual
   # solo escucha en localhost por default (ver nota del modulo)

DEFAULT_SYMBOL = "XAUUSDm"
DEFAULT_MAGIC = 900001

_bot: LiveExecutionBot | None = None
_thread: threading.Thread | None = None
_started_at: datetime | None = None
_lock = threading.Lock()  # protege _bot/_thread/_started_at contra /start y /stop concurrentes


class StartRequest(BaseModel):
    symbol: str = DEFAULT_SYMBOL
    profile: str = "5m"
    magic: int = DEFAULT_MAGIC
    poll_interval_s: int = 10
    live: bool = True  # opera de una contra la cuenta conectada (demo o real -- decision de quien
                        # loguea la cuenta en MT5, no de esta API). False = dry-run: calcula todo,
                        # solo loguea, no manda ordenes -- util para validar una config nueva.
    # overrides opcionales sobre el perfil elegido (strategy/profiles.py) --
    # None = usar el default del perfil, sin tocarlo. El panel (Fase 6) los
    # manda solo si el usuario los edito en Configuracion.
    ema_periods: int | None = None
    periodos_htf_min: int | None = None
    buf_bp: float | None = None
    rr: float | None = None
    max_concurrent_por_direccion: int | None = None
    valid_bars: int | None = None
    orden_viva: bool | None = None
    max_bars_trade: int | None = None
    fixed_lot: float | None = None
    entrada_viva: bool | None = None

    def overrides(self) -> dict:
        fields = ("ema_periods", "periodos_htf_min", "buf_bp", "rr",
                   "max_concurrent_por_direccion", "valid_bars", "orden_viva",
                   "max_bars_trade", "fixed_lot", "entrada_viva")
        return {f: v for f in fields if (v := getattr(self, f)) is not None}


def _bot_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _require_mt5():
    with mt5_lock:
        if not mt5.initialize():
            raise HTTPException(503, f"No se pudo conectar a MT5: {mt5.last_error()}")


# ---- control del bot ------------------------------------------------------

@app.get("/status")
def status():
    return {
        "running": _bot_running(),
        "symbol": _bot.symbol if _bot else None,
        "profile": _bot.profile_name if _bot else None,
        "magic": _bot.magic if _bot else None,
        "dry_run": _bot.dry_run if _bot else None,
        "params": _bot.params.__dict__ if _bot else None,
        "started_at": _started_at.isoformat() if _started_at else None,
    }


@app.post("/start")
def start(req: StartRequest):
    global _bot, _thread, _started_at
    with _lock:
        if _bot_running():
            raise HTTPException(409, "El bot ya esta corriendo -- llama a /stop primero")

        bot = LiveExecutionBot(
            symbol=req.symbol, profile=req.profile, magic=req.magic,
            poll_interval_s=req.poll_interval_s, dry_run=not req.live,
            **req.overrides(),
        )
        with mt5_lock:
            bot.connect()
            bot.replay_startup()

        thread = threading.Thread(target=bot.run, daemon=True, name="pxs-bot")
        thread.start()

        _bot, _thread, _started_at = bot, thread, datetime.now(timezone.utc)
    return status()


@app.post("/stop")
def stop():
    global _thread
    with _lock:
        if not _bot_running():
            raise HTTPException(409, "El bot no esta corriendo")
        _bot.stop()
        thread, _thread = _thread, None
    # bot.stop() ahora despierta el loop al instante via threading.Event
    # (ver execution/src/bot.py) en vez de esperar a que expire el sleep del
    # ciclo o del backoff de error (antes, hasta 300s) -- este timeout solo
    # cubre una llamada a MT5 en curso bajo mt5_lock, no un sleep completo.
    thread.join(timeout=10)
    return status()


@app.get("/events")
def events(limit: int = Query(200, ge=1, le=1000)):
    if _bot is None:
        return []
    return list(_bot.events)[-limit:]


@app.get("/profiles")
def profiles():
    """Defaults de cada perfil (strategy/profiles.py) -- una sola fuente de
    verdad, el panel de Configuracion los usa para precargar el formulario
    sin tener los numeros duplicados en el frontend."""
    return {name: params.__dict__ for name, params in PROFILES.items()}


# ---- estado del broker (no depende de que el bot este corriendo) ----------

@app.get("/account")
def account():
    _require_mt5()
    with mt5_lock:
        info = mt5.account_info()
    if info is None:
        raise HTTPException(503, f"No se pudo leer account_info: {mt5.last_error()}")
    return info._asdict()


@app.get("/positions")
def positions(symbol: str = DEFAULT_SYMBOL, magic: int = DEFAULT_MAGIC):
    _require_mt5()
    with mt5_lock:
        rows = mt5.positions_get(symbol=symbol) or ()
    return [p._asdict() for p in rows if p.magic == magic]


@app.get("/orders")
def orders(symbol: str = DEFAULT_SYMBOL, magic: int = DEFAULT_MAGIC):
    _require_mt5()
    with mt5_lock:
        rows = mt5.orders_get(symbol=symbol) or ()
    return [o._asdict() for o in rows if o.magic == magic]


@app.get("/history")
def history(symbol: str = DEFAULT_SYMBOL, magic: int = DEFAULT_MAGIC,
            days: int = Query(30, ge=1, le=3650)):
    _require_mt5()
    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)
    with mt5_lock:
        deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        return []
    return [d._asdict() for d in deals if d.magic == magic and d.symbol == symbol]


# ---- panel estatico (Fase 6) -----------------------------------------------
# Servido por el mismo proceso -- sin build step, HTML/CSS/JS planos que
# consumen esta misma API por fetch(). Montado al final a proposito: si se
# monta antes, StaticFiles puede interceptar rutas antes que las de la API.
_panel_dir = Path(__file__).resolve().parents[1] / "panel"
if _panel_dir.exists():
    app.mount("/panel", StaticFiles(directory=_panel_dir, html=True), name="panel")
