"""Regresion de integracion: api/app.py:/start no debe arrancar el motor de
trading (ni crear el thread del bot) cuando MT5 no esta listo -- y debe
devolver un 503 con el mensaje claro de MT5Readiness, no un 500 generico con
traceback (ver execution/src/mt5_validation.py, pedido original #16: "si MT5
validation == FAILED entonces Trading Engine = NOT STARTED").

Llama el handler de FastAPI (`api.app.start`) directo como funcion Python en
vez de por HTTP -- no hace falta un cliente HTTP (httpx no esta instalado en
este proyecto, ver api/requirements.txt) para probar la logica del handler;
FastAPI solo envuelve funciones normales.

Usa el paquete MetaTrader5 REAL para el import (bot.py referencia constantes
como mt5.TIMEFRAME_M1 a nivel de modulo -- un doble completo tendria que
replicar toda esa superficie, fragil e innecesario) pero MONKEYPATCHEA sus
4 funciones de conexion (initialize/terminal_info/account_info/last_error)
para no tocar una terminal MT5 real -- importante en esta maquina en
particular, que puede tener el bot real corriendo contra una cuenta real en
paralelo (ver execution/src/bot.py, run.bat).

Uso:
    python api/test_start_mt5_validation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

import MetaTrader5 as mt5  # noqa: E402 -- real, solo se monkeypatchean las 4 funciones de abajo

mt5.initialize = lambda *a, **kw: False  # "MT5 no disponible" -- lo que este test necesita
mt5.terminal_info = lambda: None
mt5.account_info = lambda: None
mt5.last_error = lambda: (-1, "fake: MT5 no disponible")

from fastapi import HTTPException  # noqa: E402

import api.app as api_app  # noqa: E402


def test_start_blocked_when_mt5_not_ready():
    assert api_app._bot is None, "precondicion: no deberia haber un bot de una corrida anterior"
    assert not api_app._bot_running()

    req = api_app.StartRequest()  # defaults: symbol=XAUUSD, profile=5m, live=True
    try:
        api_app.start(req)
        assert False, "start() deberia haber levantado HTTPException(503, ...) con MT5 no disponible"
    except HTTPException as e:
        assert e.status_code == 503, f"esperaba 503, dio {e.status_code}"
        assert "MetaTrader 5" in e.detail, f"detail no menciona MetaTrader 5: {e.detail!r}"

    # Lo que importa de verdad (pedido original #16): ningun motor de trading
    # quedo arrancado -- _bot/_thread siguen None, no hay thread corriendo.
    assert api_app._bot is None, "start() fallido NO deberia haber dejado un bot creado"
    assert not api_app._bot_running(), "start() fallido NO deberia dejar el motor corriendo"


def main():
    test_start_blocked_when_mt5_not_ready()
    print("TODO OK")


if __name__ == "__main__":
    main()
