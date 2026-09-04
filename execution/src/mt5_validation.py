"""Valida que MT5 este REALMENTE listo para operar antes de arrancar el
motor de trading -- no un try/except generico, distingue los estados reales
que la API de MetaTrader5 permite ver (ver docstring de check_mt5_readiness
para la limitacion conocida de lo que NO puede distinguir).

Usado por LiveExecutionBot.connect() (execution/src/bot.py) -- el UNICO
punto por el que pasan tanto el arranque inicial (api/app.py:/start) como
cada intento de reconexion del loop en vivo (bot.py:run(), backoff de
spec-live-execution.md #9). Arreglar la validacion ahi cubre los dos casos
con un solo cambio.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import MetaTrader5 as mt5


class MT5ReadinessCode(str, Enum):
    NOT_AVAILABLE = "not_available"                  # initialize() fallo -- terminal no instalada/no corriendo/no se pudo adjuntar
    TERMINAL_DISCONNECTED = "terminal_disconnected"   # terminal corriendo, adjuntada, pero sin conexion al servidor del broker
    ALGO_TRADING_DISABLED = "algo_trading_disabled"   # boton "Algo Trading"/"Trading automatico" apagado en la terminal
    NO_ACCOUNT = "no_account"                         # terminal lista, sin ninguna cuenta logueada
    ACCOUNT_TRADE_DISABLED = "account_trade_disabled"  # cuenta logueada sin permiso de trading (ej. password de solo lectura)
    ACCOUNT_EXPERT_DISABLED = "account_expert_disabled"  # cuenta logueada, trading permitido, pero Expert Advisors/API no
    READY = "ready"


@dataclass(frozen=True)
class MT5Readiness:
    code: MT5ReadinessCode
    user_message: str  # listo para mostrar en el panel/ventana de control -- mismo estilo que la UI existente (ver panel/index.html #mt5Detail)
    log_detail: str     # para bot._log()/logs de la ventana de control -- mas tecnico, sin datos sensibles (ver nota de modulo)

    @property
    def ok(self) -> bool:
        return self.code == MT5ReadinessCode.READY


class MT5NotReadyError(RuntimeError):
    """Se levanta en vez de dejar que un AttributeError/TypeError crudo (ej.
    mt5.account_info() devolviendo None y algo leyendo .login de eso) tumbe
    la conexion con un error criptico. Lleva el MT5Readiness estructurado
    para que quien lo atrape (api/app.py:/start) pueda mostrar
    readiness.user_message en vez de un traceback."""

    def __init__(self, readiness: MT5Readiness):
        super().__init__(readiness.log_detail)
        self.readiness = readiness


def check_mt5_readiness() -> MT5Readiness:
    """Valida en orden, deteniendose en el primer problema (no tiene sentido
    revisar la cuenta si ni siquiera hay terminal):

      1. mt5.initialize()              -> se pudo adjuntar a la terminal?
      2. terminal_info().connected     -> la terminal tiene conexion al servidor del broker?
      3. terminal_info().trade_allowed -> "Algo Trading" esta prendido en la terminal?
      4. account_info() is not None    -> hay una cuenta logueada?
      5. account_info().trade_allowed  -> la CUENTA tiene permiso de trading (no es solo-lectura)?
      6. account_info().trade_expert   -> la cuenta tiene permitido Expert Advisors/API?

    Limitacion conocida del paquete MetaTrader5 (documentada a proposito, no
    inventamos una distincion que la API no da): NO se puede diferenciar de
    forma confiable "cuenta invalida" de "cuenta que se desconecto a mitad
    de sesion" -- las dos terminan viendose igual desde aca (account_info()
    pasa a devolver None, o terminal_info().connected pasa a False). Ambas
    se reportan con el mismo codigo (NO_ACCOUNT / TERMINAL_DISCONNECTED)
    segun cual de las dos deje de responder, en vez de fabricar un tercer
    estado que no se puede confirmar.

    Los campos usados (terminal_info().connected/trade_allowed,
    account_info().trade_allowed/trade_expert) son los que documenta la API
    de MetaTrader5 -- se leen con getattr(..., None) y se tratan como "no se
    pudo determinar, no bloquear por las dudas" si algun build de la
    terminal no los expusiera, en vez de asumir que existen y romper con un
    AttributeError.
    """
    if not mt5.initialize():
        return MT5Readiness(
            MT5ReadinessCode.NOT_AVAILABLE,
            "No se pudo conectar con MetaTrader 5. Verifique que MetaTrader 5 "
            "esté instalado, abierto, y disponible en esta PC.",
            f"mt5.initialize() fallo -- last_error={mt5.last_error()!r}",
        )

    term = mt5.terminal_info()
    if term is None:
        return MT5Readiness(
            MT5ReadinessCode.NOT_AVAILABLE,
            "No se pudo leer el estado de la terminal de MetaTrader 5. "
            "Verifique que esté abierta y disponible.",
            f"mt5.terminal_info() devolvio None -- last_error={mt5.last_error()!r}",
        )
    if getattr(term, "connected", True) is False:
        return MT5Readiness(
            MT5ReadinessCode.TERMINAL_DISCONNECTED,
            "MetaTrader 5 está abierto pero no tiene conexión con el servidor "
            "del bróker. Revise su conexión a internet o el servidor elegido "
            "en MetaTrader 5.",
            "terminal_info().connected=False",
        )
    if getattr(term, "trade_allowed", True) is False:
        return MT5Readiness(
            MT5ReadinessCode.ALGO_TRADING_DISABLED,
            'El trading algorítmico está desactivado en MetaTrader 5. Active '
            'el botón "Algo Trading" / "Trading automático" en la barra de '
            'herramientas de MetaTrader 5 antes de iniciar el bot.',
            "terminal_info().trade_allowed=False",
        )

    acc = mt5.account_info()
    if acc is None:
        return MT5Readiness(
            MT5ReadinessCode.NO_ACCOUNT,
            "MetaTrader 5 no tiene una cuenta activa. Abra MetaTrader 5 e "
            "inicie sesión en su cuenta antes de iniciar el bot.",
            f"mt5.account_info() devolvio None -- last_error={mt5.last_error()!r}",
        )
    if getattr(acc, "trade_allowed", True) is False:
        return MT5Readiness(
            MT5ReadinessCode.ACCOUNT_TRADE_DISABLED,
            "La cuenta conectada en MetaTrader 5 no tiene permiso para "
            "operar (puede estar en modo solo lectura, o el bróker "
            "restringió el trading en esta cuenta).",
            f"account_info().trade_allowed=False (cuenta {acc.login}, server {acc.server!r})",
        )
    if getattr(acc, "trade_expert", True) is False:
        return MT5Readiness(
            MT5ReadinessCode.ACCOUNT_EXPERT_DISABLED,
            "La cuenta conectada en MetaTrader 5 no tiene permitido el "
            "trading automático (Expert Advisors/API). Habilítelo desde su "
            "bróker o desde MetaTrader 5 antes de iniciar el bot.",
            f"account_info().trade_expert=False (cuenta {acc.login}, server {acc.server!r})",
        )

    return MT5Readiness(
        MT5ReadinessCode.READY,
        "Conexión con MT5 verificada — cuenta autorizada para operar.",
        f"listo -- cuenta {acc.login} server {acc.server!r} trade_mode={acc.trade_mode}",
    )
