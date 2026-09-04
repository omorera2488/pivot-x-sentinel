"""Regresion de execution/src/mt5_validation.py -- valida que
check_mt5_readiness() distinga los 7 estados reales (6 de falla + listo) sin
necesitar una terminal MT5 real ni una cuenta conectada (pedido explicito:
"usar mocks/fakes para no depender de una cuenta MT5 real").

Inyecta un modulo `MetaTrader5` FALSO en sys.modules antes de importar
mt5_validation, asi el codigo bajo prueba es exactamente el mismo que corre
en produccion (import MetaTrader5 as mt5), solo que mt5 termina siendo nuestro
doble en vez del paquete real -- ver bloque de import mas abajo.

No cubre (fuera de alcance, requiere una terminal MT5 real abierta):
  - Que mt5.initialize()/terminal_info()/account_info() del paquete real
    devuelvan objetos con estos mismos campos en la práctica -- eso queda
    para un smoke test manual (ver checklist en el docstring de main()).

Uso:
    python execution/src/test_mt5_validation.py
Sale con exit code 0 y "TODO OK" si los 9 casos pasan, o levanta
AssertionError senalando cual caso fallo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, para "import execution"


class _NS:
    """Namespace minimo -- simula los namedtuples que devuelven
    terminal_info()/account_info() del paquete real (acceso por atributo)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    """Doble de todo el modulo MetaTrader5 que usa mt5_validation.py: solo
    initialize()/terminal_info()/account_info()/last_error(), configurables
    por atributo antes de cada caso."""

    def __init__(self):
        self.initialize_result = True
        self.terminal = _NS(connected=True, trade_allowed=True)
        self.account = _NS(login=12345, server="Broker-Demo", trade_mode=0,
                            trade_allowed=True, trade_expert=True)
        self.error = (1, "sin error")

    def initialize(self):
        return self.initialize_result

    def terminal_info(self):
        return self.terminal

    def account_info(self):
        return self.account

    def last_error(self):
        return self.error


fake = FakeMT5()
sys.modules["MetaTrader5"] = fake  # ANTES de importar mt5_validation -- "import MetaTrader5 as mt5" ahi adentro va a encontrar esto

from execution.src.mt5_validation import (  # noqa: E402
    MT5NotReadyError, MT5Readiness, MT5ReadinessCode, check_mt5_readiness,
)


def fresh_fake() -> FakeMT5:
    """Cada caso arranca de un estado 100% sano -- asi cada test solo prueba
    UNA condicion de falla a la vez, sin heredar configuracion de otro caso."""
    global fake
    fake = FakeMT5()
    sys.modules["MetaTrader5"] = fake
    import execution.src.mt5_validation as m
    m.mt5 = fake  # el modulo ya esta importado -- reapunta su referencia "mt5" al fake nuevo
    return fake


def check(label, fake_obj, expected_code):
    r = check_mt5_readiness()
    assert isinstance(r, MT5Readiness), f"{label}: no devolvio MT5Readiness"
    assert r.code == expected_code, f"{label}: esperaba {expected_code}, dio {r.code}"
    assert r.user_message, f"{label}: user_message vacio"
    assert r.log_detail, f"{label}: log_detail vacio"
    if expected_code == MT5ReadinessCode.READY:
        assert r.ok is True, f"{label}: .ok deberia ser True en READY"
    else:
        assert r.ok is False, f"{label}: .ok deberia ser False fuera de READY"


def main():
    # A. initialize() falla -- terminal no instalada/no corriendo
    f = fresh_fake()
    f.initialize_result = False
    check("A: initialize() falla", f, MT5ReadinessCode.NOT_AVAILABLE)

    # B. terminal_info() devuelve None (initialize() OK igual -- caso raro pero posible)
    f = fresh_fake()
    f.terminal = None
    check("B: terminal_info() None", f, MT5ReadinessCode.NOT_AVAILABLE)

    # C. terminal sin conexion al servidor del broker
    f = fresh_fake()
    f.terminal = _NS(connected=False, trade_allowed=True)
    check("C: terminal desconectada", f, MT5ReadinessCode.TERMINAL_DISCONNECTED)

    # D. "Algo Trading" apagado en la terminal
    f = fresh_fake()
    f.terminal = _NS(connected=True, trade_allowed=False)
    check("D: algo trading apagado", f, MT5ReadinessCode.ALGO_TRADING_DISABLED)

    # E. terminal lista, sin ninguna cuenta logueada -- EL BUG QUE MOTIVO ESTO:
    # antes de este modulo, bot.py leia acc.login sin chequear None y explotaba
    # con AttributeError crudo en vez de un mensaje claro.
    f = fresh_fake()
    f.account = None
    check("E: sin cuenta logueada", f, MT5ReadinessCode.NO_ACCOUNT)

    # F. cuenta logueada pero sin permiso de trading (ej. password de solo lectura)
    f = fresh_fake()
    f.account = _NS(login=1, server="s", trade_mode=0, trade_allowed=False, trade_expert=True)
    check("F: cuenta sin permiso de trading", f, MT5ReadinessCode.ACCOUNT_TRADE_DISABLED)

    # G. cuenta logueada, trading permitido, pero Expert Advisors/API no
    f = fresh_fake()
    f.account = _NS(login=1, server="s", trade_mode=0, trade_allowed=True, trade_expert=False)
    check("G: expert advisors deshabilitado", f, MT5ReadinessCode.ACCOUNT_EXPERT_DISABLED)

    # H. todo en orden -- comportamiento existente, sin cambios
    f = fresh_fake()
    check("H: todo listo", f, MT5ReadinessCode.READY)

    # I. MT5NotReadyError lleva el MT5Readiness completo (lo que atrapa api/app.py:/start)
    f = fresh_fake()
    f.account = None
    readiness = check_mt5_readiness()
    err = MT5NotReadyError(readiness)
    assert err.readiness is readiness, "I: MT5NotReadyError no conserva el MT5Readiness"
    assert err.readiness.code == MT5ReadinessCode.NO_ACCOUNT, "I: readiness incorrecto en la excepcion"
    assert str(err) == readiness.log_detail, "I: str(excepcion) deberia ser el log_detail (para logs tecnicos)"

    print("TODO OK")


if __name__ == "__main__":
    main()

"""Checklist de smoke test manual (requiere MT5 real -- no automatizable
aca):
  1. Terminal MT5 CERRADA -> /start (o LiveExecutionBot.connect()) debe
     devolver NOT_AVAILABLE, mensaje "No se pudo conectar con MetaTrader 5...".
  2. Terminal ABIERTA, SIN cuenta logueada -> NO_ACCOUNT, mensaje "...inicie
     sesión en su cuenta antes de iniciar el bot.".
  3. Terminal + cuenta logueada, boton "Algo Trading" APAGADO -> ALGO_TRADING_DISABLED.
  4. Terminal + cuenta logueada, todo prendido -> READY, el bot arranca normal.
  5. Con el bot corriendo, cerrar sesion en MT5 (o cerrar la terminal) y
     esperar al proximo ciclo de reconexion -> el log debe mostrar
     "Reconexion fallida: ..." con el MENSAJE CLARO (readiness.log_detail),
     no un AttributeError crudo.
"""
