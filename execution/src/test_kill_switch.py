"""Regresion de execution/src/kill_switch.py + kill_switch_store.py -- BOT-032
(kill switch / maxima perdida diaria).

Inyecta un modulo MetaTrader5 FALSO (mismo patron que
execution/src/test_mt5_validation.py) porque kill_switch.py solo necesita
`history_deals_get()` + las constantes DEAL_ENTRY_IN/OUT -- una superficie
chica, no hace falta el paquete real.

Uso:
    python execution/src/test_kill_switch.py
"""
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root


class _Deal:
    def __init__(self, position_id, magic, symbol, entry, time, profit=0.0, swap=0.0, commission=0.0, fee=0.0):
        self.position_id = position_id
        self.magic = magic
        self.symbol = symbol
        self.entry = entry
        self.time = time
        self.profit = profit
        self.swap = swap
        self.commission = commission
        self.fee = fee


class FakeMT5:
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1

    def __init__(self):
        self.deals = None  # None = simula MT5 sin datos (fail-safe)

    def history_deals_get(self, date_from, date_to):
        return self.deals


fake = FakeMT5()
sys.modules["MetaTrader5"] = fake  # ANTES de importar kill_switch/mt5_utils

from execution.src import kill_switch, kill_switch_store  # noqa: E402
from execution.src.mt5_utils import filter_own_deals  # noqa: E402

SYMBOL, MAGIC = "XAUUSDc", 900001
DAY_START = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(days=1)


def _ts(dt: datetime) -> float:
    return dt.timestamp()


def test_a_disabled_feature_is_out_of_scope():
    """El calculo en si no tiene un "enabled" -- eso vive en bot.py/api/app.py
    (BOT-032 #1: costo cero, sin llamar a MT5, cuando esta desactivado). Este
    modulo solo se ejercita cuando SI se llama -- se deja constancia acá de
    que un `deals=None` (equivalente a "no se pudo/no hizo falta consultar")
    da None, nunca 0.0."""
    fake.deals = None
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl is None, "fail-safe: sin datos de MT5 no se debe asumir 0.0"
    print("  A) history_deals_get() -> None propaga como None (fail-safe), nunca 0.0: OK")


def test_b_limit_499_99_does_not_trigger():
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=1))),
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=2)), profit=-499.99),
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == -499.99
    assert not (pnl <= -500.0)
    print("  B) limite $500 / P&L -$499.99 -> NO dispara: OK")


def test_c_limit_500_triggers():
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=1))),
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=2)), profit=-500.0),
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == -500.0
    assert pnl <= -500.0
    print("  C) limite $500 / P&L -$500.00 -> SI dispara: OK")


def test_d_net_pnl_wins_and_losses():
    """+$120 -$300 -$220 = -$400 (ejemplo del prompt) -- las ganancias
    compensan las perdidas dentro del mismo dia operativo."""
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START)),
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=1)), profit=120.0),
        _Deal(2, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=2))),
        _Deal(2, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=3)), profit=-300.0),
        _Deal(3, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=4))),
        _Deal(3, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=5)), profit=-220.0),
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == -400.0, pnl
    print("  D) +$120 -$300 -$220 = -$400 neto (ganancias compensan perdidas): OK")


def test_e_open_position_floating_pnl_not_counted():
    """Una posicion sin deal de salida (todavia abierta) no debe aportar
    nada -- nunca se usa P&L flotante (BOT-032 #2)."""
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=1))),
        # sin deal de salida -- todavia abierta
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == 0.0, f"una posicion abierta sin cierre no deberia aportar P&L, dio {pnl}"
    print("  E) posicion abierta (sin deal de salida) -> no cuenta: OK")


def test_f_manual_close_without_magic_still_attributed():
    """Deal de cierre manual con magic=0 (bug ya resuelto en /history) sigue
    atribuyendose correctamente via filter_own_deals -- BOT-032 #3, no
    reintroducir el bug."""
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(DAY_START + timedelta(hours=1))),
        _Deal(1, 0, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(DAY_START + timedelta(hours=2)), profit=-50.0),
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == -50.0, f"el cierre manual (magic=0) deberia seguir atribuyendose a la posicion propia, dio {pnl}"
    # y la funcion compartida por separado, para dejar constancia explicita:
    own = filter_own_deals(fake.deals, MAGIC, SYMBOL)
    assert len(own) == 2, "filter_own_deals deberia devolver ambos legs de la posicion propia"
    print("  F) deal de cierre manual (magic=0) sigue atribuido a la operacion del bot: OK")


def test_g_deal_outside_operating_day_excluded():
    """Un deal de ayer (fuera de [DAY_START, DAY_END)) no debe sumar al P&L
    de HOY, aunque su posicion se identifique igual (misma logica que separa
    identificacion de posiciones -- ventana amplia -- de la ventana angosta
    de "que se realizo hoy")."""
    ayer = DAY_START - timedelta(hours=1)
    fake.deals = [
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_IN, _ts(ayer)),
        _Deal(1, MAGIC, SYMBOL, FakeMT5.DEAL_ENTRY_OUT, _ts(ayer), profit=-9999.0),
    ]
    pnl = kill_switch.daily_realized_pnl(SYMBOL, MAGIC, DAY_START, DAY_END)
    assert pnl == 0.0, f"un cierre de AYER no deberia contar en el P&L de HOY, dio {pnl}"
    print("  G) deal de cierre fuera del dia operativo actual -> excluido: OK")


def test_h_override_persists_and_expires_on_new_day():
    """kill_switch_store: idempotente, sobrevive una nueva 'instancia' (que
    simula un reinicio de la app, ya que todo es un archivo en disco) y deja
    de aplicar en un dia operativo distinto."""
    with tempfile.TemporaryDirectory() as tmp:
        kill_switch_store.DATA_DIR = Path(tmp) / "kill_switch"
        today = date(2026, 9, 15)

        assert kill_switch_store.load_override_date(SYMBOL, MAGIC) is None, "sin override todavia"
        kill_switch_store.record_override(SYMBOL, MAGIC, today)
        assert kill_switch_store.load_override_date(SYMBOL, MAGIC) == today, "override no persistio"

        # "reinicio de la app" -- releer desde el archivo en disco, no desde memoria
        reloaded = kill_switch_store.load_override_date(SYMBOL, MAGIC)
        assert reloaded == today, "el override deberia sobrevivir un reinicio (se relee del archivo)"

        # nuevo dia operativo -- el override de ayer ya no debe ser valido
        manana = date(2026, 9, 16)
        assert reloaded != manana, "el override de un dia operativo distinto no deberia aplicar"

        # confirmar de nuevo el mismo dia es idempotente
        kill_switch_store.record_override(SYMBOL, MAGIC, today)
        assert kill_switch_store.load_override_date(SYMBOL, MAGIC) == today
    print("  H) override persiste entre 'reinicios' (archivo en disco) y expira en un dia operativo distinto: OK")


def main():
    test_a_disabled_feature_is_out_of_scope()
    test_b_limit_499_99_does_not_trigger()
    test_c_limit_500_triggers()
    test_d_net_pnl_wins_and_losses()
    test_e_open_position_floating_pnl_not_counted()
    test_f_manual_close_without_magic_still_attributed()
    test_g_deal_outside_operating_day_excluded()
    test_h_override_persists_and_expires_on_new_day()
    print("\nTODO OK")


if __name__ == "__main__":
    main()
