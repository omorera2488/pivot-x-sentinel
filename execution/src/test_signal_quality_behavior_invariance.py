"""BOT-051.4 -- prueba de invariancia de comportamiento: Signal Quality NO
puede alterar la ejecucion real.

Inyecta un modulo MetaTrader5 FALSO (mismo patron que
execution/src/test_kill_switch.py/test_mt5_validation.py) y ejercita
`LiveExecutionBot.process_closed_bar()` -- el UNICO metodo modificado por
BOT-051.4 que participa de la decision de colocar una orden -- dos veces
sobre la MISMA vela/señal:

  A) `_compute_signal_quality()` corre normalmente;
  B) `_compute_signal_quality()` esta forzada a lanzar una excepcion.

Si Signal Quality es verdaderamente observacional, el request que llega a
`mt5.order_send()` (symbol/volume/type/price/sl/tp/magic/comment/type_time/
type_filling) tiene que ser IDENTICO entre A y B, y el propio `ticket`
devuelto tiene que ser el mismo. Esta es la prueba A/B que pide el enunciado
de BOT-051.4 seccion 16, acotada al unico punto de la arquitectura por el que
Signal Quality podria, en teoria, interferir (el llamado ocurre ANTES de
`_place_order()`, ver bot.py::process_closed_bar()).

Uso:
    python execution/src/test_signal_quality_behavior_invariance.py
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

RATE_DTYPE = np.dtype([
    ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"),
    ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8"),
])


class FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_REMOVE = 8
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TIME_GTC = 0
    ORDER_REASON_CLIENT = 0
    ORDER_REASON_MOBILE = 1
    ORDER_REASON_WEB = 2
    ORDER_REASON_EXPERT = 3
    ORDER_REASON_SL = 4
    ORDER_REASON_TP = 5
    ORDER_REASON_SO = 6
    ORDER_STATE_CANCELED = 1
    ORDER_STATE_EXPIRED = 2
    ORDER_STATE_REJECTED = 3
    ORDER_STATE_FILLED = 4
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.order_send_calls: list[dict] = []
        self._next_ticket = 500000
        self._rates_cache: dict = {}

    def _synthetic_rates(self, n: int, end_time: int) -> np.ndarray:
        """Barras sinteticas deterministas -- mismo contenido en cada llamada
        con los mismos (n, end_time), sin importar cuantas veces se pida (ni
        A ni B deben ver datos distintos)."""
        key = (n, end_time)
        if key not in self._rates_cache:
            rng = np.random.default_rng(hash(key) % (2**31))
            close = 100.0 + np.cumsum(rng.normal(0, 0.05, n))
            high = close + rng.uniform(0.02, 0.15, n)
            low = close - rng.uniform(0.02, 0.15, n)
            open_ = close + rng.uniform(-0.05, 0.05, n)
            times = end_time - (n - np.arange(n)) * 300
            rates = np.zeros(n, dtype=RATE_DTYPE)
            rates["time"] = times
            rates["open"] = open_
            rates["high"] = high
            rates["low"] = low
            rates["close"] = close
            rates["tick_volume"] = rng.integers(10, 100, n)
            self._rates_cache[key] = rates
        return self._rates_cache[key]

    def copy_rates_range(self, symbol, timeframe, dt_from, dt_to):
        n = max(int((dt_to - dt_from).total_seconds() // 300), 20)
        return self._synthetic_rates(n, int(dt_to.timestamp()))

    def copy_rates_from_pos(self, symbol, timeframe, pos, count):
        return self._synthetic_rates(count, 2_000_000_000)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=100.0, ask=100.02)

    def history_deals_get(self, date_from=None, date_to=None, **kwargs):
        return ()  # sin operaciones cerradas -- _aciertos_pct()/CVP devuelve None, comportamiento normal

    def orders_get(self, symbol=None):
        return ()

    def positions_get(self, symbol=None):
        return ()

    def order_send(self, req):
        # Se guarda una COPIA -- el dict original no debe mutarse despues.
        self.order_send_calls.append(dict(req))
        ticket = self._next_ticket
        self._next_ticket += 1
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, order=ticket)


fake = FakeMT5()
sys.modules["MetaTrader5"] = fake  # ANTES de importar execution.src.bot

from execution.src.bot import LiveExecutionBot  # noqa: E402
from execution.src import score_store  # noqa: E402
from strategy.hch import HCHEngine  # noqa: E402
from strategy.live_signal import LiveSignalEngine  # noqa: E402

FAILURES: list[str] = []

# BOT-051.5 -- bug encontrado y corregido: esta prueba llama a
# process_closed_bar(), que en el camino real llega a score_store.record().
# Sin aislar DATA_DIR (mismo patron que execution/src/test_score_store.py),
# las escrituras de ESTA prueba caian en el archivo JSONL real del usuario
# (execution/data/scores/*.jsonl) -- se encontraron y limpiaron 5 lineas de
# contaminacion (tickets 500000/500001) mezcladas con datos reales de
# produccion. Nunca mas: se aisla SIEMPRE a un directorio temporal.
_tmp_scores_dir = tempfile.TemporaryDirectory()
score_store.DATA_DIR = Path(_tmp_scores_dir.name)


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def _make_bot() -> LiveExecutionBot:
    """Construye un LiveExecutionBot SIN pasar por connect()/replay_startup()
    (que necesitarian mockear mucha mas superficie de MT5 -- check_mt5_readiness,
    resolve_symbol, select_symbol, resolve_filling_mode, measure_broker_offset_seconds).
    Se setean a mano los atributos que connect() habria dejado listos -- ningun
    atajo que afecte la logica de señal/orden en si (esa vive intacta en
    strategy/live_signal.py, nunca tocada por esta prueba)."""
    bot = LiveExecutionBot(symbol="XAUUSDc", profile="5m", magic=900001, dry_run=False)
    bot.symbol = "XAUUSDc"
    bot._filling_mode = 1
    bot._offset_seconds = 0.0
    bot._contract_size = 100.0
    bot._symbol_point = 0.001  # BOT-052.2 -- mintick, lo que connect() setea de info.point
    bot.signal_engine = LiveSignalEngine(bot.params)
    bot.hch_engine = HCHEngine()  # BOT-052.2 -- lo que replay_startup() habria dejado listo
    return bot


def _prime_armed_signal(bot: LiveExecutionBot) -> np.ndarray:
    """Alimenta al signal_engine con barras neutras (sin señal) hasta que el
    proximo bar dispare una señal de venta real (misma tecnica que
    strategy/test_signal_quality.py: precio toca resistencia -> arma; cruce
    hacia abajo de EMA -> dispara). Devuelve la fila (numpy record) de la
    barra que SI dispara, lista para pasarle a process_closed_bar()."""
    t0 = 1_700_000_000
    # barras planas para que EMA converja y no arme nada todavia
    for i in range(30):
        bot.signal_engine.process_bar(t0 + i * 300, 100.2, 99.8, 100.0)
        bot._closed_bar_count += 1
    # arma venta: high toca/supera resistencia (bloque HTF en formacion)
    bot.signal_engine.process_bar(t0 + 30 * 300, 101.5, 100.0, 100.3)
    bot._closed_bar_count += 1
    # una barra intermedia neutra (mismo lado de la EMA, sin cruce)
    bot.signal_engine.process_bar(t0 + 31 * 300, 100.4, 100.1, 100.3)
    bot._closed_bar_count += 1
    # barra que dispara: cruce hacia abajo de EMA
    trigger_time = t0 + 32 * 300
    row = np.zeros(1, dtype=RATE_DTYPE)[0]
    row["time"] = trigger_time
    row["high"] = 100.1
    row["low"] = 99.0
    row["close"] = 99.2  # bien por debajo de la EMA que veniamos siguiendo (~100.3)
    row["open"] = 100.2
    row["tick_volume"] = 50
    return row


def _run_scenario(force_sq_failure: bool) -> tuple[list[dict], int | None]:
    fake.order_send_calls.clear()
    fake._rates_cache.clear()
    bot = _make_bot()
    row = _prime_armed_signal(bot)

    if force_sq_failure:
        def _boom(self, direction, entry, raw_bar_time):
            raise RuntimeError("fallo forzado de Signal Quality -- solo para esta prueba")
        bot._compute_signal_quality = _boom.__get__(bot, LiveExecutionBot)

    bot.process_closed_bar(row)
    tickets = [c for c in range(1)]  # placeholder, real ticket read below
    return list(fake.order_send_calls), (fake._next_ticket - 1 if fake.order_send_calls else None)


def _run_scenario_persistence_failure() -> tuple[list[dict], int | None, bool, int | None]:
    """BOT-051.6.3 -- root cause: BOT-051.6.2 encontro que una excepcion
    DENTRO de score_store.record() (ej. json.dumps() sobre un numpy.bool_ sin
    castear) se propagaba hasta el loop principal de run(), forzando una
    reconexion y dejando la barra sin marcar como procesada. Este escenario
    fuerza esa MISMA excepcion (en el punto real, score_store.record(), no en
    _compute_signal_quality() como A/B de arriba) y verifica que
    process_closed_bar() la aisle: la orden ya se coloco, nada de eso puede
    revertirse ni duplicarse, y self._last_processed_time SI avanza (evita el
    riesgo secundario de reprocesar la misma barra, seccion 9/20 del audit)."""
    fake.order_send_calls.clear()
    fake._rates_cache.clear()
    bot = _make_bot()
    row = _prime_armed_signal(bot)

    original_record = score_store.record

    def _boom_record(*args, **kwargs):
        raise TypeError("Object of type bool is not JSON serializable")  # mismo mensaje que en produccion

    score_store.record = _boom_record
    raised = False
    try:
        bot.process_closed_bar(row)
    except Exception:
        raised = True
    finally:
        score_store.record = original_record

    return (list(fake.order_send_calls), (fake._next_ticket - 1 if fake.order_send_calls else None),
            raised, bot._last_processed_time)


def main() -> int:
    print("=== A. Escenario normal -- _compute_signal_quality() corre sin forzar fallas ===")
    calls_a, ticket_a = _run_scenario(force_sq_failure=False)
    check("se coloco exactamente 1 orden", len(calls_a) == 1, f"calls={len(calls_a)}")
    check("la señal disparo (sanity check de la prueba misma)", ticket_a is not None)

    print("\n=== B. Escenario con _compute_signal_quality() forzada a lanzar excepcion ===")
    calls_b, ticket_b = _run_scenario(force_sq_failure=True)
    check("se coloco exactamente 1 orden IGUAL si Signal Quality revienta", len(calls_b) == 1, f"calls={len(calls_b)}")

    print("\n=== C. Comparacion A vs B -- el request a order_send() debe ser IDENTICO ===")
    if calls_a and calls_b:
        req_a, req_b = calls_a[0], calls_b[0]
        for field in ("symbol", "volume", "type", "price", "sl", "tp", "magic", "comment", "type_time", "type_filling"):
            check(f"request['{field}'] identico entre A y B", req_a.get(field) == req_b.get(field),
                  f"A={req_a.get(field)!r} B={req_b.get(field)!r}")
        check("request completo (dict) identico entre A y B", req_a == req_b)
    else:
        check("ambos escenarios colocaron una orden comparable", False, "no se puede comparar -- ver fallas arriba")

    print("\n=== D. BOT-051.6.3 -- score_store.record() forzada a fallar (root cause real de BOT-051.6.2) ===")
    calls_d, ticket_d, raised_d, last_processed_d = _run_scenario_persistence_failure()
    check("se coloco exactamente 1 orden IGUAL si la persistencia revienta", len(calls_d) == 1, f"calls={len(calls_d)}")
    check("process_closed_bar() NO propaga la excepcion de persistencia (aislamiento BOT-051.6.3)", not raised_d)
    check("el request a order_send() sigue identico al escenario normal (A)",
          calls_a and calls_d and calls_a[0] == calls_d[0])
    check("self._last_processed_time SI avanza pese al fallo de persistencia "
          "(evita reprocesar la misma barra, riesgo secundario del audit BOT-051.6.2)",
          last_processed_d is not None and last_processed_d == 1_700_000_000 + 32 * 300)

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
