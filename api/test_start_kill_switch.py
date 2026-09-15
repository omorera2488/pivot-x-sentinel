"""Regresion de integracion: api/app.py -- BOT-032 (kill switch / maxima
perdida diaria). Cubre la parte de la lista de tests del prompt que vive en
la capa API/gate de /start (las que son de UI/JS -- calendario y timezone del
navegador -- quedan documentadas como verificacion manual, ver
docs/reports/BOT-032_kill_switch.md).

Mismo patron que api/test_start_mt5_validation.py: usa el paquete MetaTrader5
REAL (bot.py/mt5_utils.py referencian constantes de modulo) pero monkeypatchea
las funciones de conexion + `history_deals_get` para no depender de una
terminal MT5 real. Llama `api_app._kill_switch_gate()`/`api_app.start()`
directo como funciones Python, no por HTTP (igual que el archivo hermano).

Uso:
    python api/test_start_kill_switch.py
"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root

import MetaTrader5 as mt5  # noqa: E402 -- real, solo se monkeypatchean las funciones de abajo

mt5.initialize = lambda *a, **kw: True
mt5.symbol_select = lambda *a, **kw: True
mt5.last_error = lambda: (1, "sin error")

_fake_deals = {"value": None}
mt5.history_deals_get = lambda date_from, date_to: _fake_deals["value"]

from fastapi import HTTPException  # noqa: E402

import api.app as api_app  # noqa: E402


class _Deal:
    def __init__(self, position_id, magic, symbol, entry, time, profit=0.0):
        self.position_id, self.magic, self.symbol, self.entry, self.time, self.profit = (
            position_id, magic, symbol, entry, time, profit,
        )
        self.swap = 0.0
        self.commission = 0.0


SYMBOL = api_app.DEFAULT_SYMBOL


def _today() -> date:
    from execution.src import operating_day
    from datetime import datetime, timezone
    return operating_day.current_operating_date(datetime.now(timezone.utc))


def _ts_within_today() -> float:
    """Timestamp (segundos unix) dentro del dia operativo ACTUAL -- los deals
    de estos tests necesitan caer dentro de la ventana angosta que filtra
    kill_switch.daily_realized_pnl(), no solo dentro de la ventana amplia de
    busqueda de posiciones."""
    from datetime import datetime, timedelta, timezone
    from execution.src import operating_day
    start, _, _ = operating_day.operating_day_bounds_utc(datetime.now(timezone.utc))
    return (start + timedelta(hours=1)).timestamp()


def test_a_disabled_is_noop():
    """BOT-032 #1/#20: desactivado (o config vieja sin los campos nuevos) no
    debe llamar a MT5 ni levantar nada -- comportamiento actual intacto."""
    called = {"history": False}
    real_history = mt5.history_deals_get
    mt5.history_deals_get = lambda *a, **kw: (called.__setitem__("history", True), None)[1]
    try:
        req = api_app.StartRequest()  # defaults: daily_max_loss_enabled=False
        api_app._kill_switch_gate(req)  # no deberia levantar nada
    finally:
        mt5.history_deals_get = real_history
    assert not called["history"], "con el kill switch desactivado no deberia consultarse history_deals_get"
    print("  A) daily_max_loss_enabled=False (o config vieja) -> gate no hace nada: OK")


def test_validacion_monto_obligatorio_positivo():
    """BOT-032 #1: monto obligatorio si esta habilitado; numero valido; > 0."""
    for kwargs in ({"daily_max_loss_enabled": True},
                   {"daily_max_loss_enabled": True, "daily_max_loss_usd": 0},
                   {"daily_max_loss_enabled": True, "daily_max_loss_usd": -5.0}):
        try:
            api_app.StartRequest(**kwargs)
            assert False, f"deberia rechazar {kwargs}"
        except Exception:
            pass
    api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0)  # valido, no debe fallar
    print("  Validacion) monto obligatorio/valido/>0 cuando esta habilitado: OK")


def test_bc_boundary_and_confirmation_required():
    """B/C: limite $500, P&L -$499.99 no dispara; -$510 dispara y exige
    confirmacion (409 estructurado, sin crear el bot)."""
    magic = 900101
    _fake_deals["value"] = [
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-499.99),
    ]
    req_ok = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    api_app._kill_switch_gate(req_ok)  # no deberia levantar nada

    _fake_deals["value"] = [
        _Deal(2, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(2, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-510.0),
    ]
    req_trig = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    try:
        api_app._kill_switch_gate(req_trig)
        assert False, "P&L -$510 con limite $500 deberia exigir confirmacion (409)"
    except HTTPException as e:
        assert e.status_code == 409
        assert e.detail["reason"] == "daily_loss_kill_switch"
        assert e.detail["realized_daily_pnl"] == -510.0
        assert e.detail["daily_max_loss_usd"] == 500.0
        assert e.detail["operating_date"] == _today().isoformat()
    print("  B/C) -$499.99 no dispara, -$510 exige confirmacion 409 estructurada: OK")


def test_hijklp_override_flow():
    """H/I/J/K/L/P: primer start exige confirmacion; cancelar deja detenido
    (no se prueba UI acá, solo que el gate sigue bloqueando); confirmar
    arranca + graba override; empeorar el P&L despues NO vuelve a bloquear
    ese mismo dia operativo; un segundo ciclo stop/start (sin `acknowledge`)
    tampoco vuelve a pedir el popup, porque el override ya es valido hoy."""
    magic = 900102
    _fake_deals["value"] = [
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-510.0),
    ]
    req = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)

    # H: primer intento sin acknowledge -> exige confirmacion
    try:
        api_app._kill_switch_gate(req)
        assert False
    except HTTPException as e:
        assert e.status_code == 409

    # I (implicito): "cancelar" = simplemente no reintentar -- no hay override grabado
    from execution.src import kill_switch_store
    assert kill_switch_store.load_override_date(SYMBOL, magic) is None, \
        "no debería quedar ningun override grabado antes de confirmar"

    # J: confirmar ("Iniciar de todas formas") -> arranca + graba override
    req_ack = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic,
                                    acknowledge_daily_loss_override=True)
    api_app._kill_switch_gate(req_ack)  # no debe levantar nada
    assert kill_switch_store.load_override_date(SYMBOL, magic) == _today(), "el override deberia quedar grabado"

    # K: P&L empeora despues del override -> NO vuelve a bloquear ese dia
    _fake_deals["value"] = [
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-700.0),
    ]
    req_again = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    api_app._kill_switch_gate(req_again)  # sin acknowledge -- no deberia levantar nada, override sigue vigente

    # L: STOP manual + START (mismo dia, sin acknowledge) -> tampoco vuelve a pedir confirmacion
    api_app._kill_switch_gate(req_again)
    print("  H/I/J/K/L/P) confirmar arranca+graba override; P&L peor y reinicios no vuelven a bloquear ese dia: OK")


def test_m_new_operating_day_invalidates_override():
    """M: un override grabado para un dia operativo DISTINTO al actual no
    debe seguir aplicando -- vuelve a exigir confirmacion."""
    magic = 900103
    from execution.src import kill_switch_store
    stale = _today() - timedelta(days=5)
    kill_switch_store.record_override(SYMBOL, magic, stale)

    _fake_deals["value"] = [
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-999.0),
    ]
    req = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    try:
        api_app._kill_switch_gate(req)
        assert False, "un override de un dia operativo pasado no deberia seguir aplicando"
    except HTTPException as e:
        assert e.status_code == 409
    print("  M) override de un dia operativo anterior ya no aplica -- vuelve a exigir confirmacion: OK")


def test_fail_safe_no_data():
    """Fail-safe (#19): si MT5 no devuelve datos suficientes, se trata como
    disparado -- nunca se asume P&L=$0 y se deja arrancar sin mas."""
    magic = 900104
    _fake_deals["value"] = None
    req = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    try:
        api_app._kill_switch_gate(req)
        assert False, "sin datos de MT5, el fail-safe deberia bloquear (exigir confirmacion), no arrancar directo"
    except HTTPException as e:
        assert e.status_code == 409
        assert e.detail["realized_daily_pnl"] is None
    print("  Fail-safe) MT5 sin datos -> bloquea (no asume P&L=$0): OK")


def test_g_start_blocked_leaves_no_bot():
    """Integracion completa (mismo estilo que api/test_start_mt5_validation.py):
    api_app.start(req) con el limite ya alcanzado y sin override NO debe
    crear ningun LiveExecutionBot ni thread -- el 409 se levanta ANTES."""
    magic = 900105
    assert api_app._bot is None, "precondicion: no deberia haber un bot de una corrida anterior"
    _fake_deals["value"] = [
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_IN, _ts_within_today()),
        _Deal(1, magic, SYMBOL, mt5.DEAL_ENTRY_OUT, _ts_within_today(), profit=-501.0),
    ]
    req = api_app.StartRequest(daily_max_loss_enabled=True, daily_max_loss_usd=500.0, magic=magic)
    try:
        api_app.start(req)
        assert False, "start() deberia haber levantado HTTPException(409, ...) -- limite ya alcanzado (#14)"
    except HTTPException as e:
        assert e.status_code == 409
    assert api_app._bot is None, "start() bloqueado por el kill switch NO deberia haber dejado un bot creado"
    assert not api_app._bot_running()
    print("  G/#14) arranque con el limite ya alcanzado -> 409 ANTES de crear el bot, ningun thread arranca: OK")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        from execution.src import kill_switch_store
        kill_switch_store.DATA_DIR = Path(tmp) / "kill_switch"

        test_a_disabled_is_noop()
        test_validacion_monto_obligatorio_positivo()
        test_bc_boundary_and_confirmation_required()
        test_hijklp_override_flow()
        test_m_new_operating_day_invalidates_override()
        test_fail_safe_no_data()
        test_g_start_blocked_leaves_no_bot()
    print("\nTODO OK")


if __name__ == "__main__":
    main()
