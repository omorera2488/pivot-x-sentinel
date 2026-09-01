"""Motor de ejecucion en vivo — docs/spec-live-execution.md.

Un LiveExecutionBot por simbolo+perfil. El bucle principal (`run`) detecta
velas cerradas nuevas por polling, las procesa una a una a traves del motor
de señal incremental (strategy.live_signal), coloca ordenes limite reales
con SL/TP adjuntos, vigila y cancela pendientes invalidados, cierra
posiciones por tiempo maximo, y calcula el limite de concurrencia contra
ordenes/posiciones REALES del broker — nunca contra una copia en memoria
(docs/spec-live-execution.md #1).

Vigilancia de pendientes en DOS frecuencias (agregado 2026-08-23, ver
`_watch_pending_live`): tpAntes/muerto (spec-estrategia.md #5.2) se evaluan
por TICK en vivo en cada ciclo de `run()` (`poll_interval_s`, 10s tipico) y
tambien por vela CERRADA (`_watch_pending`, hasta `bar_seconds`, 5min en el
perfil 5m -- mas lento, pero es el unico que ademas cubre `caduca`/
`maxBarsTrade`, que depende de conteo de barras, no de precio). El chequeo
por tick existe para cerrar una ventana real: sin el, el precio podia tocar
el TP dentro de la vela en formacion sin llenar la orden, devolverse, y
llenarla de verdad en el broker -- todo antes de que `_watch_pending`
llegara a cancelarla (visto en cuenta demo el 2026-08-23).

Nota sobre metadatos: a diferencia de lo que asumia el borrador de la spec
(#6), MT5 SI guarda todo lo que hace falta directamente en la orden/posicion
(`time_setup`/`time` = born/open, `sl`, `tp`, `price_open`, `type` = direccion)
— no hace falta un registro local aparte. El `comment` se usa solo como
etiqueta legible en el terminal, no se reconstruye nada critico a partir de
el. OJO: `time_setup`/`time` son tiempo de RELOJ, no el `bar_index` de Pine
-- `maxBarsTrade`/`validBars` cuentan barras REALMENTE formadas (no avanzan
con el mercado cerrado), asi que `_bars_between()` consulta el historial
real via `copy_rates_range` en vez de dividir tiempo transcurrido por la
duracion nominal de la barra (eso sobre-contaria cualquier fin de semana).

dry_run: si True, calcula todo (señales, timeouts, concurrencia) pero solo
loguea lo que haria en vez de llamar a order_send/order_remove -- util para
validar una configuracion nueva antes de confiarle dinero real. Default
False: opera de una. Que cuenta (demo o real) y si corre en dry_run o en
vivo es una decision de quien conecta la cuenta a MT5 y arranca el bot, no
del codigo -- no hay ningun chequeo aca que distinga demo de real. Quien
opera este bot asume el riesgo (ver disclaimer en README.md).
"""
from __future__ import annotations

import threading
import time as time_mod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

from strategy.engine import StrategyParams
from strategy.live_signal import LiveSignalEngine
from strategy.profiles import get_profile, normalize_profile_name
from strategy import scoring

from .mt5_utils import connect, select_symbol, resolve_symbol, measure_broker_offset_seconds, resolve_filling_mode, mt5_lock
from . import score_store

TIMEFRAME_BY_PROFILE = {"1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5}
SECONDS_BY_PROFILE = {"1m": 60, "5m": 300}
MAX_EVENTS = 1000  # tope del log en memoria -- ver Fase 5 (api/app.py lee esto)

# Cuantas velas base (bar_seconds) se piden hacia atras para calificar cada
# entrada (strategy.scoring) -- suficiente para la ventana de tendencia mas
# larga (240min/4h del perfil 5m, ~3 bloques cerrados) y para el rango de
# divergencia RSI (hasta 60 velas) con margen de sobra.
SCORE_LOOKBACK_BARS = 500

# Operaciones cerradas minimas de ESTE bot (symbol+magic) antes de confiar en
# un aciertos% real para el CVP -- ver strategy.scoring.cvp_score.
AGE_LOOKBACK_DAYS_FOR_ACIERTOS = 365

# Etiquetas legibles para el motivo real que MT5 guarda en su propio historial
# -- se usan en la auditoria de _reconcile() (agregada 2026-08-31: una orden/
# posicion propia del bot -- mismo magic -- se audita pase lo que pase, la haya
# cancelado/cerrado este proceso, el broker (SL/TP/stop-out) u otra persona a
# mano en el terminal).
_REASON_LABEL = {
    mt5.ORDER_REASON_CLIENT: "manual (terminal)",
    mt5.ORDER_REASON_MOBILE: "manual (app movil)",
    mt5.ORDER_REASON_WEB: "manual (web)",
    mt5.ORDER_REASON_EXPERT: "programa/API",
    mt5.ORDER_REASON_SL: "stop loss",
    mt5.ORDER_REASON_TP: "take profit",
    mt5.ORDER_REASON_SO: "stop out (margen)",
}
_ORDER_STATE_LABEL = {
    mt5.ORDER_STATE_CANCELED: "cancelada",
    mt5.ORDER_STATE_EXPIRED: "expirada",
    mt5.ORDER_STATE_REJECTED: "rechazada",
    mt5.ORDER_STATE_FILLED: "llenada",
}


class LiveExecutionBot:
    def __init__(self, symbol: str, profile: str, magic: int,
                 poll_interval_s: int = 10, lookback_buckets: int = 3,
                 dry_run: bool = False, **param_overrides):
        self.symbol = symbol
        self.profile_name = normalize_profile_name(profile)
        self.magic = magic
        self.poll_interval_s = poll_interval_s
        self.lookback_buckets = lookback_buckets
        self.dry_run = dry_run

        self.params: StrategyParams = get_profile(self.profile_name, **param_overrides)
        self.timeframe = TIMEFRAME_BY_PROFILE[self.profile_name]
        self.bar_seconds = SECONDS_BY_PROFILE[self.profile_name]

        self.signal_engine: LiveSignalEngine | None = None
        self._last_processed_time: int | None = None
        self._filling_mode: int | None = None
        self._offset_seconds: float = 0.0
        self._contract_size: float | None = None
        self._running = False

        # auditoria de ordenes/posiciones propias (ver _reconcile) -- ticket ->
        # "venta"/"compra", tal como estaban al final del ciclo anterior.
        self._known_orders: dict[int, str] = {}
        self._known_positions: dict[int, str] = {}
        # tickets que un watcher (_watch_pending/_watch_pending_live/_watch_open)
        # ya reporto en ESTE ciclo -- _reconcile no los vuelve a loguear, solo
        # actualiza su snapshot. Se limpia al principio de cada vuelta de run().
        self._reported_this_cycle: set[int] = set()
        # usado en vez de time.sleep() dentro de run() -- permite que stop()
        # despierte el loop al instante, incluso si esta en medio de un
        # backoff de error de hasta 300s (ver docstring de run()).
        self._stop_event = threading.Event()

        # log de eventos en memoria -- Fase 5 (api/app.py) lo expone por HTTP
        # sin necesitar que el bot escriba a disco (el proceso de la API y el
        # del bot son el mismo, decision de Fase 0).
        self.events: deque = deque(maxlen=MAX_EVENTS)

    def _log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc)
        print(f"[{ts:%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)
        self.events.append({"time": ts.isoformat(), "msg": msg})

    # ---- arranque -----------------------------------------------------

    def connect(self) -> None:
        connect()
        requested = self.symbol
        self.symbol = resolve_symbol(self.symbol)  # 'XAUUSD'/'BTCUSD' -> nombre real del broker
        if self.symbol != requested:
            self._log(f"Simbolo {requested!r} resuelto a {self.symbol!r} en este broker")
        info = select_symbol(self.symbol)
        self._filling_mode = resolve_filling_mode(self.symbol)
        self._offset_seconds = measure_broker_offset_seconds(self.symbol)
        self._contract_size = info.trade_contract_size
        acc = mt5.account_info()
        self._log(f"Conectado: cuenta {acc.login} server {acc.server} simbolo {self.symbol} "
                  f"perfil {self.profile_name} magic {self.magic} dry_run={self.dry_run}")
        self._log(f"Offset servidor vs UTC: {self._offset_seconds:+.2f}s | "
                  f"digits={info.digits} point={info.point} filling_mode={self._filling_mode}")
        self._seed_known_state()

    def _order_label(self, o) -> str:
        return "venta" if o.type == mt5.ORDER_TYPE_SELL_LIMIT else "compra"

    def _position_label(self, p) -> str:
        return "venta" if p.type == mt5.POSITION_TYPE_SELL else "compra"

    def _seed_known_state(self) -> None:
        """Snapshot inicial al conectar -- lo que YA exista en la cuenta (de
        una sesion anterior del bot) no debe reportarse como recien
        desaparecido en el primer ciclo de _reconcile()."""
        self._known_orders = {o.ticket: self._order_label(o) for o in self.my_orders()}
        self._known_positions = {p.ticket: self._position_label(p) for p in self.my_positions()}

    def replay_startup(self) -> None:
        """Reconstruye armado/bloque HTF sobre historial reciente, SIN
        colocar ninguna orden (spec-live-execution.md #4)."""
        lookback_min = self.lookback_buckets * self.params.periodos_htf_min
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=lookback_min + 2 * self.bar_seconds / 60)
        rates = mt5.copy_rates_range(self.symbol, self.timeframe, start, now)
        if rates is None or len(rates) < 2:
            self._log("Replay: historial insuficiente para el lookback pedido -- arranca en calentamiento (igual que backtest).")
            self.signal_engine = LiveSignalEngine(self.params)
            return

        closed = rates[:-1]  # la ultima posicion es la vela en formacion -- nunca se usa
        self.signal_engine = LiveSignalEngine(self.params)
        for r in closed:
            self.signal_engine.process_bar(int(r["time"]) - round(self._offset_seconds),
                                            float(r["high"]), float(r["low"]), float(r["close"]))
        self._last_processed_time = int(closed[-1]["time"])
        self._log(f"Replay: {len(closed)} velas cerradas procesadas ({lookback_min}min de lookback). "
             f"armadoVenta={self.signal_engine.armado_venta} armadoCompra={self.signal_engine.armado_compra}")

    # ---- estado real del broker ----------------------------------------

    def my_orders(self):
        orders = mt5.orders_get(symbol=self.symbol) or ()
        return [o for o in orders if o.magic == self.magic]

    def my_positions(self):
        positions = mt5.positions_get(symbol=self.symbol) or ()
        return [p for p in positions if p.magic == self.magic]

    def _concurrency_count(self, direction: int) -> int:
        order_type_for_dir = mt5.ORDER_TYPE_SELL_LIMIT if direction < 0 else mt5.ORDER_TYPE_BUY_LIMIT
        pos_type_for_dir = mt5.POSITION_TYPE_SELL if direction < 0 else mt5.POSITION_TYPE_BUY
        n_pend = sum(1 for o in self.my_orders() if o.type == order_type_for_dir)
        n_open = sum(1 for p in self.my_positions() if p.type == pos_type_for_dir)
        return n_pend + n_open

    def _effective_concurrency(self, direction: int) -> tuple[int, int]:
        """(activos, limite) segun params.una_operacion_a_la_vez -- ver
        spec-estrategia.md #6. Default: cuenta pendientes+abiertas en
        CUALQUIER direccion contra este magic, tope 1. Desactivado, vuelve
        al limite de siempre por direccion (max_concurrent_por_direccion)."""
        if self.params.una_operacion_a_la_vez:
            return len(self.my_orders()) + len(self.my_positions()), 1
        return self._concurrency_count(direction), self.params.max_concurrent_por_direccion

    # ---- vigilancia de pendientes / abiertas ----------------------------

    def _bars_between(self, t_from_server: int, t_to_server: int) -> int:
        """Cuenta velas REALMENTE formadas entre t_from y t_to (bar_index en
        Pine, no minutos de reloj). t_from/t_to en hora de SERVIDOR sin
        corregir -- mismo sistema que time_setup/time de las ordenes/
        posiciones de MT5 y que copy_rates_range, asi que se comparan
        directamente sin tocar el offset.

        Reemplaza a proposito un calculo por tiempo de reloj (elapsed /
        duracion nominal de la barra): ese calculo sobre-cuenta cualquier
        fin de semana/feriado de por medio (el mercado no genera velas
        cuando esta cerrado, pero el reloj sigue corriendo) y dispararia
        `caduca`/`tooLong` mucho antes de lo que pretende spec-estrategia.md
        #5.2/#5.4 -- ahi `bar_index` es el contador nativo de Pine, que solo
        avanza cuando se forma una vela nueva. Consultar el historial real
        via copy_rates_range da exactamente ese conteo: si el mercado estuvo
        cerrado, MT5 simplemente no devuelve barras para ese lapso."""
        if t_to_server <= t_from_server:
            return 0
        dt_from = datetime.fromtimestamp(t_from_server, tz=timezone.utc)
        dt_to = datetime.fromtimestamp(t_to_server, tz=timezone.utc)
        rates = mt5.copy_rates_range(self.symbol, self.timeframe, dt_from, dt_to)
        if rates is None or len(rates) == 0:
            return 0
        return max(0, len(rates) - 1)  # rates[0] es la barra "from" misma -- no cuenta como barra transcurrida

    def _watch_pending(self, bar_high: float, bar_low: float, raw_bar_time: int) -> None:
        for o in self.my_orders():
            d = -1 if o.type == mt5.ORDER_TYPE_SELL_LIMIT else 1
            stop, target = o.sl, o.tp
            tp_antes = bar_low <= target if d < 0 else bar_high >= target
            expired, reason = False, ""
            if tp_antes:
                expired, reason = True, "target alcanzado sin llenarse"
            elif self.params.orden_viva:
                muerto = bar_high >= stop if d < 0 else bar_low <= stop
                bars_since_born = self._bars_between(int(o.time_setup), raw_bar_time)
                caduca = bars_since_born >= self.params.max_bars_trade
                if muerto:
                    expired, reason = True, "precio alcanzo el stop sin llenarse (invalidada)"
                elif caduca:
                    expired, reason = True, f"caduco por tiempo ({bars_since_born} barras reales)"
            else:
                bars_since_born = self._bars_between(int(o.time_setup), raw_bar_time)
                if bars_since_born >= self.params.valid_bars:
                    expired, reason = True, f"caduco por validBars ({bars_since_born} barras reales)"

            if expired:
                self._log(f"Pendiente #{o.ticket} ({'venta' if d < 0 else 'compra'}) expirada: {reason}")
                self._cancel_order(o.ticket)
                self._reported_this_cycle.add(o.ticket)

    def _watch_pending_live(self) -> None:
        """Igual que `_watch_pending` (tpAntes/muerto, spec-estrategia.md
        #5.2) pero contra el TICK EN VIVO en vez de la vela cerrada, corrida
        en CADA ciclo de `run()` (`poll_interval_s`, 10s tipico) en vez de
        solo cuando cierra una vela nueva (hasta `bar_seconds`, 5min en el
        perfil 5m).

        Motivo (visto en cuenta demo el 2026-08-23): sin esto, el precio
        puede tocar el TP dentro de la vela en formacion sin que la orden
        limite se haya llenado, devolverse, y llenar esa orden de verdad en
        el broker -- todo antes de que `_watch_pending` llegue a cancelarla
        por "target alcanzado sin llenarse", porque esa funcion solo corre
        al cerrar la vela. Esto reduce la ventana de exposicion de "hasta
        bar_seconds" a "hasta poll_interval_s".

        Usa `tick.bid` nada mas (no mezcla bid/ask nuevo aca: copy_rates_*
        de MT5, que alimenta `_watch_pending`, ya es una serie de bid).
        No evalua `caduca`/`maxBarsTrade`: eso depende de conteo de barras
        reales (`_bars_between`), no de precio en vivo -- sigue siendo
        exclusivo de `_watch_pending` en cada vela cerrada, que ademas queda
        como red de seguridad redundante si un ciclo de poll se salta o
        `symbol_info_tick` falla momentaneamente. Sin duplicacion posible:
        en cuanto una orden se cancela, `orders_get()` deja de devolverla,
        asi que el otro chequeo simplemente no la vuelve a encontrar."""
        orders = self.my_orders()
        if not orders:
            return
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            self._log(f"AVISO: no se pudo leer symbol_info_tick({self.symbol}) para vigilancia en vivo: {mt5.last_error()}")
            return
        for o in orders:
            d = -1 if o.type == mt5.ORDER_TYPE_SELL_LIMIT else 1
            stop, target = o.sl, o.tp
            tp_antes = tick.bid <= target if d < 0 else tick.bid >= target
            expired, reason = False, ""
            if tp_antes:
                expired, reason = True, "target alcanzado sin llenarse"
            elif self.params.orden_viva:
                muerto = tick.bid >= stop if d < 0 else tick.bid <= stop
                if muerto:
                    expired, reason = True, "precio alcanzo el stop sin llenarse (invalidada)"

            if expired:
                self._log(f"Pendiente #{o.ticket} ({'venta' if d < 0 else 'compra'}) expirada: {reason}")
                self._cancel_order(o.ticket)
                self._reported_this_cycle.add(o.ticket)

    def _watch_open(self, raw_bar_time: int) -> None:
        for p in self.my_positions():
            bars_since_open = self._bars_between(int(p.time), raw_bar_time)
            if bars_since_open >= self.params.max_bars_trade:
                self._log(f"Posicion #{p.ticket} cerrada por tiempo maximo ({bars_since_open} barras reales)")
                self._close_position(p)
                self._reported_this_cycle.add(p.ticket)

    def _reconcile(self) -> None:
        """Auditoria: compara lo que el bot sabia que tenia (fin del ciclo
        anterior) contra lo que MT5 tiene AHORA. Toda orden/posicion propia
        (mismo magic) que desapareció se loguea, leyendo el motivo REAL del
        historial de MT5 -- sin importar si la cerro/cancelo este mismo
        proceso, el broker (SL/TP/stop-out), u otra persona a mano en el
        terminal. Fue abierta por el bot: se audita pase lo que pase (a
        pedido del usuario, 2026-08-31 -- antes una posicion cerrada a mano
        no dejaba ningun rastro en el log).

        Los watchers (_watch_pending/_watch_pending_live/_watch_open) ya
        loguean con mas detalle las cancelaciones/cierres que ELLOS mismos
        deciden en este mismo ciclo -- esos tickets quedan en
        _reported_this_cycle y aca no se repiten, solo se actualiza el
        snapshot."""
        positions_now = self.my_positions()
        cur_orders = {o.ticket: self._order_label(o) for o in self.my_orders()}
        cur_positions = {p.ticket: self._position_label(p) for p in positions_now}

        for ticket, tipo in self._known_orders.items():
            if ticket in cur_orders or ticket in self._reported_this_cycle:
                continue
            pos = next((p for p in positions_now if p.ticket == ticket), None)
            if pos is not None:
                self._log(f"Orden #{ticket} ({tipo}) llenada -- ahora posicion abierta @ {pos.price_open:.3f}")
            else:
                self._log_order_vanished(ticket, tipo)

        for ticket, tipo in self._known_positions.items():
            if ticket in cur_positions or ticket in self._reported_this_cycle:
                continue
            self._log_position_vanished(ticket, tipo)

        self._known_orders = cur_orders
        self._known_positions = cur_positions

    def _log_order_vanished(self, ticket: int, tipo: str) -> None:
        rows = mt5.history_orders_get(ticket=ticket) or ()
        o = rows[0] if rows else None
        if o is None:
            self._log(f"AVISO: orden #{ticket} ({tipo}) desaparecio de MT5 sin rastro en el historial")
            return
        estado = _ORDER_STATE_LABEL.get(o.state, f"estado {o.state}")
        motivo = _REASON_LABEL.get(o.reason, f"motivo {o.reason}")
        self._log(f"Orden #{ticket} ({tipo}) {estado} -- {motivo}")

    def _log_position_vanished(self, ticket: int, tipo: str) -> None:
        deals = mt5.history_deals_get(position=ticket) or ()
        salida = next((d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT), None)
        if salida is None:
            self._log(f"AVISO: posicion #{ticket} ({tipo}) desaparecio de MT5 sin rastro en el historial")
            return
        motivo = _REASON_LABEL.get(salida.reason, f"motivo {salida.reason}")
        self._log(f"Posicion #{ticket} ({tipo}) cerrada -- {motivo} @ {salida.price:.3f} P&L={salida.profit:+.2f}")

    # ---- envio de ordenes reales (o simuladas si dry_run) ---------------

    def _cancel_order(self, ticket: int) -> None:
        if self.dry_run:
            self._log(f"[dry_run] cancelaria orden #{ticket}")
            return
        res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            self._log(f"AVISO: no se pudo cancelar #{ticket}: {res}")

    def _close_position(self, p) -> None:
        if self.dry_run:
            self._log(f"[dry_run] cerraria posicion #{p.ticket} a mercado")
            return
        tick = mt5.symbol_info_tick(self.symbol)
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol, "volume": p.volume,
               "type": close_type, "position": p.ticket, "price": price,
               "magic": self.magic, "type_filling": self._filling_mode,
               "comment": "pxs|timeout"}
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            self._log(f"AVISO: no se pudo cerrar #{p.ticket}: {res}")

    def _aciertos_pct(self) -> float | None:
        """Aciertos% REAL, medido de las operaciones ya cerradas por ESTE bot
        (mismo symbol+magic) en los ultimos AGE_LOOKBACK_DAYS_FOR_ACIERTOS
        dias -- nunca de un backtest (ver strategy.scoring, docstring del
        modulo). Mismo filtro/formula que closedTrades()/tradeStats() en
        panel/app.js: deal de salida (DEAL_ENTRY_OUT), neto = profit+swap+
        comision+fee. None si no hay MT5, o si hay menos de
        scoring.CVP_MIN_SAMPLE operaciones cerradas -- no tiene sentido
        confiar en un aciertos% medido sobre una muestra chica."""
        date_to = datetime.now(timezone.utc)
        date_from = date_to - timedelta(days=AGE_LOOKBACK_DAYS_FOR_ACIERTOS)
        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return None
        closed = [d for d in deals
                  if d.magic == self.magic and d.symbol == self.symbol and d.entry == mt5.DEAL_ENTRY_OUT]
        if len(closed) < scoring.CVP_MIN_SAMPLE:
            return None
        nets = [(d.profit or 0.0) + (d.swap or 0.0) + (d.commission or 0.0) + getattr(d, "fee", 0.0)
                for d in closed]
        wins = sum(1 for n in nets if n > 0)
        losses = sum(1 for n in nets if n < 0)
        if wins + losses == 0:
            return None
        return wins / (wins + losses) * 100.0

    def _score_entry(self, direction: int, entry: float, stop: float, target: float,
                      raw_bar_time: int) -> scoring.EntryScore | None:
        """Califica la entrada (Divergencia + Tendencia + CVP, ver
        strategy/scoring.py) SOLO para registrarla -- no decide si se opera
        ni cambia el volumen (self.params.fixed_lot no se toca). Cualquier
        falla aca (MT5, historial insuficiente) se loguea y se devuelve
        None -- la orden se coloca igual, sin calificacion, nunca al reves."""
        try:
            dt_to = datetime.fromtimestamp(raw_bar_time, tz=timezone.utc)
            dt_from = dt_to - timedelta(seconds=self.bar_seconds * SCORE_LOOKBACK_BARS)
            rates = mt5.copy_rates_range(self.symbol, self.timeframe, dt_from, dt_to)
            if rates is None or len(rates) < 20:
                self._log("AVISO: historial insuficiente para calificar la entrada -- se coloca sin calificacion.")
                return None

            time_utc = rates["time"].astype("int64") - round(self._offset_seconds)
            high = rates["high"].astype(float)
            low = rates["low"].astype(float)
            close = rates["close"].astype(float)
            # tick_volume: proxy de volumen que ya trae copy_rates_range (CFD/OTC,
            # sin real_volume de bolsa -- mismo criterio que usa TradingView en
            # este simbolo). Alimenta el perfil de volumen del score de "Nodo".
            volume = rates["tick_volume"].astype(float)

            tick = mt5.symbol_info_tick(self.symbol)
            spread_price = (tick.ask - tick.bid) if tick is not None else 0.0

            return scoring.score_entry(
                direction=direction, profile_name=self.profile_name,
                entry=entry, stop=stop, target=target,
                time_utc=time_utc, high=high, low=low, close=close,
                volume=volume, periodos_htf_min=self.params.periodos_htf_min,
                spread_price=spread_price,
                commission_usd=0.0,  # no hay commission_per_lot configurado en el bot en vivo todavia
                fixed_lot=self.params.fixed_lot, contract_size=self._contract_size or 1.0,
                aciertos_pct=self._aciertos_pct(),
            )
        except Exception as e:
            self._log(f"AVISO: no se pudo calificar la entrada ({e!r}) -- se coloca sin calificacion.")
            return None

    def _place_order(self, direction: int, entry: float, stop: float, target: float) -> int | None:
        """Devuelve el ticket de la orden colocada (None si fue dry_run o si
        el broker la rechazo) -- lo usa process_closed_bar() para asociarle
        la calificacion de entrada (score_store), si hubo una."""
        tipo = "venta" if direction < 0 else "compra"
        if self.dry_run:
            self._log(f"[dry_run] colocaria {tipo} limite: entry={entry:.3f} sl={stop:.3f} tp={target:.3f}")
            return None
        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": self.symbol,
            "volume": self.params.fixed_lot,
            "type": mt5.ORDER_TYPE_SELL_LIMIT if direction < 0 else mt5.ORDER_TYPE_BUY_LIMIT,
            "price": entry,
            "sl": stop,
            "tp": target,
            "magic": self.magic,
            "comment": f"pxs|{self.profile_name}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode,
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            self._log(f"AVISO: orden {tipo} rechazada: {res}")
            return None
        self._log(f"Orden {tipo} colocada: #{res.order} entry={entry:.3f} sl={stop:.3f} tp={target:.3f}")
        return res.order

    # ---- deteccion de vela cerrada + procesamiento por barra ------------

    def _fetch_new_closed_bars(self):
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, 5)
        if rates is None or len(rates) < 2:
            return []
        closed = rates[:-1]  # nunca se procesa la vela en formacion (rates[-1])
        if self._last_processed_time is None:
            return closed[-1:]
        return [r for r in closed if int(r["time"]) > self._last_processed_time]

    def process_closed_bar(self, r) -> None:
        raw_time = int(r["time"])                          # hora de SERVIDOR sin corregir
        t = raw_time - round(self._offset_seconds)         # UTC corregido -- solo para el bloque HTF (motor de señal)
        high, low, close = float(r["high"]), float(r["low"]), float(r["close"])

        # _watch_open/_watch_pending cuentan barras REALES via copy_rates_range
        # (mismo sistema de tiempo que time_setup/time de MT5: hora de servidor,
        # no corregida) -- ver _bars_between. El offset solo importa para
        # alinear el bloque HTF con la epoca UTC, no para esto.
        self._watch_open(raw_time)
        self._watch_pending(high, low, raw_time)

        signal = self.signal_engine.process_bar(t, high, low, close)
        if signal.dir is not None:
            if not signal.valido:
                self._log(f"Señal descartada: stop del lado incorrecto (dir={signal.dir})")
            else:
                activos, limite = self._effective_concurrency(signal.dir)
                if activos >= limite:
                    self._log(f"Señal descartada: limite de concurrencia ({activos}/{limite})")
                else:
                    entry_score = self._score_entry(signal.dir, signal.entry, signal.stop, signal.target, raw_time)
                    if entry_score is not None:
                        self._log(
                            f"Calificacion de la entrada: total={entry_score.total:+d} "
                            f"(divergencia={entry_score.divergencia_score:+d} '{entry_score.divergencia_reason}', "
                            f"tendencia={entry_score.tendencia_score:+d} '{entry_score.tendencia_reason}', "
                            f"cvp={entry_score.cvp_score:+d} '{entry_score.cvp_reason}', "
                            f"nodo={entry_score.nodo_score:+d} '{entry_score.nodo_reason}') -- "
                            f"solo se registra, el volumen sigue en fixed_lot."
                        )
                    ticket = self._place_order(signal.dir, signal.entry, signal.stop, signal.target)
                    if ticket is not None and entry_score is not None:
                        score_store.record(self.symbol, self.magic, ticket, entry_score.to_dict())

        self._last_processed_time = int(r["time"])

    def poll_once(self) -> int:
        """Procesa todas las velas cerradas nuevas desde el ultimo poll, EN
        ORDEN. Devuelve cuantas proceso."""
        nuevas = self._fetch_new_closed_bars()
        for r in nuevas:
            self.process_closed_bar(r)
        return len(nuevas)

    def run(self) -> None:
        """Bucle principal. Usa self._stop_event.wait(timeout) en vez de
        time.sleep(): duerme lo mismo, pero stop() puede despertarlo al
        instante en vez de esperar a que el timeout expire por su cuenta --
        importante sobre todo en el backoff de error, que puede llegar a
        300s (5 min) y antes dejaba a stop() sin efecto hasta que terminara."""
        self._running = True
        self._stop_event.clear()
        backoff = [5, 15, 60, 300]
        bi = 0
        while self._running:
            try:
                self._reported_this_cycle = set()
                with mt5_lock:  # serializa contra la API (Fase 5), mismo proceso
                    n = self.poll_once()
                    self._watch_pending_live()  # tick en vivo, cada ciclo -- ver docstring
                    self._reconcile()  # auditoria: cualquier orden/posicion propia que
                                        # desaparecio sin que un watcher de arriba la reportara
                if n:
                    self._log(f"Procesadas {n} vela(s) nueva(s).")
                bi = 0
                if self._stop_event.wait(self.poll_interval_s):
                    break
            except KeyboardInterrupt:
                self._log("Detenido por el usuario.")
                break
            except Exception as e:  # reconexion con backoff, spec #9
                wait = backoff[min(bi, len(backoff) - 1)]
                self._log(f"Error en el ciclo ({e!r}), reintentando en {wait}s...")
                if self._stop_event.wait(wait):
                    break
                bi += 1
                try:
                    self.connect()
                except Exception as e2:
                    self._log(f"Reconexion fallida: {e2!r}")
        self._running = False
        self._log("Detenido.")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
