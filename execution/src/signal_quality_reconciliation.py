"""BOT-051.5 -- puente de reconciliacion entre Signal Quality (inmutable,
capturado en `t0`) y lo que realmente paso despues (`OutcomeObservation`).

100% read-only respecto a MT5: solo `orders_get`/`history_orders_get`/
`history_deals_get`/`symbol_info` -- nunca `order_send`/`order_remove`, nunca
modifica SL/TP/posiciones/configuracion. Seguro de correr repetidamente
(idempotente: dos corridas sin datos nuevos producen el mismo resultado) y
despues de un reinicio del bot (toda la informacion que usa vive en MT5 o en
los JSONL de `score_store`/`outcome_store`, nunca en memoria de proceso).

--------------------------------------------------------------------------
Identity (seccion 5 del enunciado de BOT-051.5)
--------------------------------------------------------------------------
Este proyecto YA demuestra, en codigo de produccion sin modificar, que:

    order_ticket (el que devuelve mt5.order_send() para la orden pendiente)
    == position.ticket (una vez que la orden se llena)
    == deal.position_id (para CADA deal -- apertura y cierre -- asociado)

Evidencia (no una suposicion nueva de esta tarea):
  - `execution/src/bot.py::_reconcile()` ya compara `self._known_orders`
    (claves = ticket de orden) contra `positions_now` buscando
    `p.ticket == ticket` para detectar "orden llenada -- ahora posicion
    abierta" -- codigo YA en produccion, sin tocar en BOT-051.5.
  - `execution/src/score_store.py` (BOT-051.4) documenta la misma
    equivalencia explicitamente en su docstring de modulo.

Por eso `signal_event_id := order_ticket` alcanza como identidad estable --
no se inventa un ID artificial nuevo. `open_deal_ticket`/`close_deal_ticket`
SI son distintos entre si y del `order_ticket` -- son el `ticket` propio de
cada deal (`DEAL_ENTRY_IN`/`DEAL_ENTRY_OUT`), obtenidos via
`mt5.history_deals_get(position=order_ticket)`.

Si algun dia un cambio de arquitectura de MT5/broker rompe esta igualdad
(ej. cuenta netting en vez de hedging), `reconcile_ticket()` lo expondria
como `order_final_state=UNKNOWN` (no encuentra el ticket en ningun lado) en
vez de fallar silenciosamente -- ver seccion "Fail-safe" abajo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from strategy.costs import BrokerCosts
from strategy.signal_quality import SCHEMA_VERSION

# --------------------------------------------------------------------------
# OOS boundary / provenance (seccion 6 del enunciado de BOT-051.5)
# --------------------------------------------------------------------------
# Momento a partir del cual una observacion de Signal Quality puede
# considerarse evidencia OOS genuina. NO es el corte general del proyecto
# (2026-09-15, usado por BOT-024.3/BOT-047.3/BOT-048.3/BOT-050.3 para sus
# datasets HISTORICOS) -- Signal Quality en vivo no pudo producir NINGUN
# snapshot antes de que BOT-051.4 se desplegara (no existia el codigo), asi
# que el corte efectivo para evidencia LIVE es el momento de ESE deploy,
# que es estrictamente posterior. Fijado al commit real, no a una fecha
# redonda -- ver reports/BOT-051.4-signal-quality-live-persistence.md.
SIGNAL_QUALITY_OOS_ACCUMULATION_START_UTC = datetime(2026, 9, 22, 0, 3, 49, tzinfo=timezone.utc)
SIGNAL_QUALITY_OOS_ACCUMULATION_START_COMMIT = "7d8c86af2fd0411e72120036b0d61eb82cb97878"  # BOT-051.4 close


def is_oos_eligible(observed_at_time_utc: str, sq_schema_version: str) -> bool:
    """Una observacion es evidencia OOS genuina ssi (a) nacio despues del
    deploy de BOT-051.4 (nunca podria haber participado en ningun discovery
    -- esos usaron el dataset historico hasta 2026-09-15, `BOT-051.3`), y
    (b) usa el schema congelado vigente (`SCHEMA_VERSION`) -- una version
    de schema distinta significaria que el contrato se reabrio, y esta
    funcion NO decide por si sola si esa hipotetica version futura sigue
    siendo comparable."""
    if sq_schema_version != SCHEMA_VERSION:
        return False
    try:
        observed = datetime.fromisoformat(observed_at_time_utc)
    except (TypeError, ValueError):
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed >= SIGNAL_QUALITY_OOS_ACCUMULATION_START_UTC

ORDER_STATE_PENDING = "PENDING"
ORDER_STATE_FILLED = "FILLED"
ORDER_STATE_CANCELED = "CANCELED"
ORDER_STATE_EXPIRED = "EXPIRED"
ORDER_STATE_REJECTED = "REJECTED"
# Ni pendiente ni en el historial de MT5 -- el ticket no existe (broker
# distinto, cuenta distinta, o un ticket que nunca fue una orden real --
# ver el hallazgo de contaminacion de esta misma tarea,
# execution/src/test_score_store.py). Nunca se inventa un estado.
ORDER_FINAL_STATE_UNKNOWN = "UNKNOWN"

_TERMINAL_STATES = {
    "ORDER_STATE_CANCELED": ORDER_STATE_CANCELED,
    "ORDER_STATE_EXPIRED": ORDER_STATE_EXPIRED,
    "ORDER_STATE_REJECTED": ORDER_STATE_REJECTED,
    "ORDER_STATE_FILLED": ORDER_STATE_FILLED,
}


def _map_order_state(mt5_module, state: int) -> str:
    for attr, label in _TERMINAL_STATES.items():
        if state == getattr(mt5_module, attr):
            return label
    return ORDER_FINAL_STATE_UNKNOWN


def _map_close_reason(mt5_module, reason: int) -> str:
    mapping = {
        "ORDER_REASON_CLIENT": "CLIENT", "ORDER_REASON_MOBILE": "MOBILE",
        "ORDER_REASON_WEB": "WEB", "ORDER_REASON_EXPERT": "EXPERT",
        "ORDER_REASON_SL": "SL", "ORDER_REASON_TP": "TP", "ORDER_REASON_SO": "STOP_OUT",
    }
    for attr, label in mapping.items():
        if reason == getattr(mt5_module, attr, object()):
            return label
    return f"REASON_{reason}"


def _empty_observation(ticket: int, symbol: str, magic: int) -> dict:
    return {
        "ticket": ticket, "symbol": symbol, "magic": magic,
        "order_final_state": ORDER_FINAL_STATE_UNKNOWN,
        "fill_time_utc": None, "position_id": None,
        "open_deal_ticket": None, "close_deal_ticket": None,
        "close_time_utc": None,
        "pnl_gross": None, "commission": None, "swap": None, "pnl_net": None,
        "realized_r": None, "close_reason": None,
        "reconciled_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _realized_r(mt5_module, symbol: str, order, open_deal, pnl_net: float, fixed_lot: float) -> float | str:
    """Misma definicion historica que `strategy/engine.py::close_open_trade()`
    (`pnl_r = pnl_usd / raw_risk`, `raw_risk = costs.price_to_usd(|stop-entry|,
    fixed_lot)`), NO una definicion nueva -- ver seccion 12 del enunciado. Se
    reusa `strategy.costs.BrokerCosts.price_to_usd()` verbatim (BOT-043, ya en
    produccion) con `tick_value`/`tick_size` reales leidos de
    `mt5.symbol_info()` (unicos campos que `price_to_usd()` usa -- ver
    docstring de esa clase, `contract_size` es solo informativo ahi).

    `raw_risk` se calcula sobre el STOP y el PRECIO DE LLENADO reales (no
    simulados) -- en principio mas exacto que la version de backtest, que
    aproxima el precio de llenado ajustando por spread. `UNAVAILABLE` si
    falta cualquier insumo (sl del order historico, precio del deal de
    apertura, o symbol_info) -- nunca se inventa un valor."""
    sl = getattr(order, "sl", None)
    fill_price = getattr(open_deal, "price", None) if open_deal is not None else None
    if not sl or not fill_price:
        return "UNAVAILABLE"
    info = mt5_module.symbol_info(symbol)
    if info is None or not getattr(info, "trade_tick_size", None):
        return "UNAVAILABLE"
    costs = BrokerCosts(
        point=info.point, contract_size=info.trade_contract_size,
        tick_value=info.trade_tick_value, tick_size=info.trade_tick_size,
        swap_long_points=0.0, swap_short_points=0.0,  # no usados por price_to_usd()
    )
    raw_risk = costs.price_to_usd(abs(fill_price - sl), fixed_lot)
    if not raw_risk or raw_risk <= 0:
        return "UNAVAILABLE"
    return pnl_net / raw_risk


def reconcile_ticket(mt5_module, symbol: str, magic: int, ticket: int, fixed_lot: float) -> dict:
    """UNA reconciliacion read-only de `ticket`. Devuelve un dict shaped como
    `OutcomeObservation` (ver `outcome_store.py`) -- no escribe nada, el
    llamador decide si persistir (ver `reconcile_signal_quality_outcomes()`).

    Fail-safe: cualquier excepcion (MT5 desconectado, symbol_info None, etc.)
    se atrapa y devuelve `order_final_state=UNKNOWN` -- nunca propaga hacia
    el loop de trading."""
    obs = _empty_observation(ticket, symbol, magic)
    try:
        pending = mt5_module.orders_get(ticket=ticket)
        if pending:
            obs["order_final_state"] = ORDER_STATE_PENDING
            return obs

        hist = mt5_module.history_orders_get(ticket=ticket)
        if not hist:
            return obs  # UNKNOWN -- ni pendiente ni en el historial
        order = hist[0]
        obs["order_final_state"] = _map_order_state(mt5_module, order.state)

        if obs["order_final_state"] != ORDER_STATE_FILLED:
            return obs  # CANCELED/EXPIRED/REJECTED -- nunca llego a posicion, sin deals que buscar

        obs["position_id"] = ticket  # identidad demostrada en el docstring del modulo
        deals = mt5_module.history_deals_get(position=ticket) or ()
        open_deal = next((d for d in deals if d.entry == mt5_module.DEAL_ENTRY_IN), None)
        close_deal = next((d for d in deals if d.entry == mt5_module.DEAL_ENTRY_OUT), None)

        if open_deal is not None:
            obs["fill_time_utc"] = datetime.fromtimestamp(int(open_deal.time), tz=timezone.utc).isoformat()
            obs["open_deal_ticket"] = int(open_deal.ticket)

        if close_deal is not None:
            obs["close_time_utc"] = datetime.fromtimestamp(int(close_deal.time), tz=timezone.utc).isoformat()
            obs["close_deal_ticket"] = int(close_deal.ticket)
            obs["close_reason"] = _map_close_reason(mt5_module, close_deal.reason)
            # pnl_net: MISMA formula que panel/app.js::closedTrades() /
            # bot.py::_aciertos_pct() -- neto YA realizado por el broker en
            # el deal de salida, no un calculo propio.
            profit = close_deal.profit or 0.0
            swap = close_deal.swap or 0.0
            commission = close_deal.commission or 0.0
            fee = getattr(close_deal, "fee", 0.0) or 0.0
            obs["pnl_gross"] = profit
            obs["swap"] = swap
            obs["commission"] = commission
            obs["pnl_net"] = profit + swap + commission + fee
            obs["realized_r"] = _realized_r(mt5_module, symbol, order, open_deal, obs["pnl_net"], fixed_lot)

        return obs
    except Exception as e:  # fail-safe -- nunca debe tumbar el loop de trading
        obs["order_final_state"] = ORDER_FINAL_STATE_UNKNOWN
        obs["reconciliation_error"] = repr(e)
        return obs


_TERMINAL_OUTCOME_STATES = {ORDER_STATE_CANCELED, ORDER_STATE_EXPIRED, ORDER_STATE_REJECTED}


def _is_final(observation: dict | None) -> bool:
    """Un OutcomeObservation ya no necesita reconciliarse de nuevo cuando:
    (a) el order termino en un estado que nunca cambia (CANCELED/EXPIRED/
    REJECTED), o (b) se llego a un close_time_utc (posicion cerrada). PENDING
    y "FILLED pero todavia abierta" SIEMPRE se re-consultan -- pueden seguir
    evolucionando."""
    if observation is None:
        return False
    state = observation.get("order_final_state")
    if state in _TERMINAL_OUTCOME_STATES:
        return True
    if state == ORDER_STATE_FILLED and observation.get("close_time_utc") is not None:
        return True
    return False


def reconcile_signal_quality_outcomes(mt5_module, symbol: str, magic: int, fixed_lot: float,
                                       sq_tickets, outcome_store, log=lambda msg: None) -> dict:
    """Reconcilia TODOS los tickets de `sq_tickets` (iterable de ints -- ver
    `score_store.load_all_signal_quality()`) que todavia no tengan un
    OutcomeObservation final. Idempotente: un ticket ya reconciliado a estado
    final no se vuelve a consultar ni se vuelve a escribir (0 escrituras
    nuevas en una segunda corrida sin cambios). Read-only respecto a
    trading -- nunca llama a order_send/order_remove.

    Devuelve un resumen {checked, reconciled, skipped_already_final, errors}
    para logging/telemetria -- nunca lanza (fail-safe interno via
    reconcile_ticket)."""
    existing = outcome_store.load_all(symbol, magic)
    summary = {"checked": 0, "reconciled": 0, "skipped_already_final": 0, "errors": 0}
    for ticket in sq_tickets:
        prior = existing.get(ticket)
        if _is_final(prior):
            summary["skipped_already_final"] += 1
            continue
        summary["checked"] += 1
        obs = reconcile_ticket(mt5_module, symbol, magic, ticket, fixed_lot)
        if obs.get("order_final_state") == ORDER_FINAL_STATE_UNKNOWN and "reconciliation_error" in obs:
            summary["errors"] += 1
        # Comparacion de idempotencia EXCLUYE 'reconciled_at_utc' a proposito:
        # ese campo es bookkeeping (cuando se corrio la reconciliacion), no
        # parte de la observacion en si -- siempre difiere entre corridas
        # aunque nada mas haya cambiado, asi que compararlo produciria una
        # idempotencia falsa/inconsistente (0 escrituras "la mayoria de las
        # veces", una escritura nueva si las dos corridas caen en
        # microsegundos distintos -- bug real encontrado y corregido en
        # BOT-051.5, ver execution/src/test_signal_quality_oos_bridge.py).
        prior_stable = {k: v for k, v in prior.items() if k != "reconciled_at_utc"} if prior else None
        obs_stable = {k: v for k, v in obs.items() if k != "reconciled_at_utc"}
        if prior_stable == obs_stable:
            continue  # sin cambios sustantivos -- no agregar una linea nueva
        outcome_store.record(symbol, magic, obs)
        summary["reconciled"] += 1
        log(f"Signal Quality OOS bridge: ticket #{ticket} -> {obs['order_final_state']}"
            + (f" (cerrado, pnl_net={obs['pnl_net']:+.2f})" if obs.get("close_time_utc") else ""))
    return summary
