"""BOT-051.5 -- checksum del puente de reconciliacion OOS de Signal Quality.

Usa EXCLUSIVAMENTE un modulo MetaTrader5 FALSO y directorios JSONL
temporales (mismo patron que execution/src/test_kill_switch.py/
test_signal_quality_behavior_invariance.py) -- estos son fixtures
deterministas de TEST, nunca evidencia OOS genuina (ver seccion 17/18 del
enunciado; la evidencia real ya se valido por separado contra la cuenta MT5
real conectada -- ver reports/BOT-051.5-signal-quality-live-accumulation-oos-bridge.md).

Cubre: identity/linkage (order_ticket==position_id via deals), lifecycle
completo (non-filled/cancelled/expired/filled-abierta/filled-cerrada TP/
filled-cerrada SL), idempotencia, restart/recovery (el estado vive en
archivo, no en memoria), persistencia corrupta, NEUTRAL != UNAVAILABLE a
traves del dataset, diagnostics de structure replay mismatch, dataset con
0/parcial/completo, aislamiento de fallas del bridge.

Uso:
    python execution/src/test_signal_quality_oos_bridge.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src import outcome_store, score_store  # noqa: E402
from execution.src import signal_quality_reconciliation as bridge  # noqa: E402
from execution.src import signal_quality_oos_dataset as oos_ds  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


# ---------------------------------------------------------------------------
# Fake MT5 -- deals/orders/positions deterministas por escenario
# ---------------------------------------------------------------------------

class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeMT5:
    ORDER_STATE_CANCELED, ORDER_STATE_EXPIRED = 1, 2
    ORDER_STATE_REJECTED, ORDER_STATE_FILLED = 3, 4
    ORDER_REASON_CLIENT, ORDER_REASON_SL, ORDER_REASON_TP = 0, 4, 5
    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1

    def __init__(self):
        self.pending: dict[int, list] = {}
        self.history: dict[int, list] = {}
        self.deals: dict[int, list] = {}
        self.symbol_info_result = _Obj(point=0.01, trade_contract_size=100.0, trade_tick_value=1.0, trade_tick_size=0.01)
        self.raise_on = None  # ticket para forzar excepcion (failure isolation)

    def orders_get(self, ticket=None, symbol=None):
        if self.raise_on is not None and ticket == self.raise_on:
            raise RuntimeError("fallo forzado de MT5 (orders_get) -- solo para test")
        return self.pending.get(ticket, [])

    def history_orders_get(self, ticket=None):
        return self.history.get(ticket, [])

    def history_deals_get(self, position=None):
        return self.deals.get(position, [])

    def symbol_info(self, symbol):
        return self.symbol_info_result


def _setup_non_filled(mt5f, ticket):
    mt5f.pending[ticket] = [_Obj(ticket=ticket)]


def _setup_cancelled(mt5f, ticket):
    mt5f.history[ticket] = [_Obj(ticket=ticket, state=mt5f.ORDER_STATE_CANCELED, sl=0.0, tp=0.0)]


def _setup_expired(mt5f, ticket):
    mt5f.history[ticket] = [_Obj(ticket=ticket, state=mt5f.ORDER_STATE_EXPIRED, sl=0.0, tp=0.0)]


def _setup_filled_open(mt5f, ticket, entry=100.0, sl=99.0):
    mt5f.history[ticket] = [_Obj(ticket=ticket, state=mt5f.ORDER_STATE_FILLED, sl=sl, tp=101.0)]
    mt5f.deals[ticket] = [_Obj(ticket=ticket * 10 + 1, order=ticket, entry=mt5f.DEAL_ENTRY_IN,
                                time=1_700_000_000, price=entry, profit=0.0, swap=0.0, commission=0.0, fee=0.0,
                                reason=mt5f.ORDER_REASON_CLIENT, position_id=ticket)]


def _setup_filled_closed(mt5f, ticket, entry=100.0, sl=99.0, exit_price=99.0, reason=None, profit=-100.0):
    reason = mt5f.ORDER_REASON_SL if reason is None else reason
    mt5f.history[ticket] = [_Obj(ticket=ticket, state=mt5f.ORDER_STATE_FILLED, sl=sl, tp=101.0)]
    mt5f.deals[ticket] = [
        _Obj(ticket=ticket * 10 + 1, order=ticket, entry=mt5f.DEAL_ENTRY_IN, time=1_700_000_000,
             price=entry, profit=0.0, swap=0.0, commission=0.0, fee=0.0,
             reason=mt5f.ORDER_REASON_CLIENT, position_id=ticket),
        _Obj(ticket=ticket * 10 + 2, order=0, entry=mt5f.DEAL_ENTRY_OUT, time=1_700_003_600,
             price=exit_price, profit=profit, swap=-0.5, commission=-0.2, fee=0.0,
             reason=reason, position_id=ticket),
    ]


def main() -> int:
    print("=== A. Identity/linkage + lifecycle (fixtures deterministas) ===")
    mt5f = FakeMT5()
    _setup_non_filled(mt5f, 1001)
    _setup_cancelled(mt5f, 1002)
    _setup_expired(mt5f, 1003)
    _setup_filled_open(mt5f, 1004)
    _setup_filled_closed(mt5f, 1005, entry=100.0, sl=99.0, exit_price=99.0, reason=mt5f.ORDER_REASON_SL, profit=-100.0)
    _setup_filled_closed(mt5f, 1006, entry=100.0, sl=99.0, exit_price=101.0, reason=mt5f.ORDER_REASON_TP, profit=100.0)

    obs_pending = bridge.reconcile_ticket(mt5f, "TEST", 1, 1001, 0.1)
    check("non-filled -> PENDING", obs_pending["order_final_state"] == "PENDING")

    obs_cancel = bridge.reconcile_ticket(mt5f, "TEST", 1, 1002, 0.1)
    check("cancelled -> CANCELED, sin deals que buscar", obs_cancel["order_final_state"] == "CANCELED" and obs_cancel["position_id"] is None)

    obs_expired = bridge.reconcile_ticket(mt5f, "TEST", 1, 1003, 0.1)
    check("expired -> EXPIRED", obs_expired["order_final_state"] == "EXPIRED")

    obs_open = bridge.reconcile_ticket(mt5f, "TEST", 1, 1004, 0.1)
    check("filled, todavia abierta -> FILLED, sin close_time", obs_open["order_final_state"] == "FILLED" and obs_open["close_time_utc"] is None)
    check("identity: position_id == order_ticket (demostrado, no asumido)", obs_open["position_id"] == 1004)

    obs_sl = bridge.reconcile_ticket(mt5f, "TEST", 1, 1005, 0.1)
    check("closed TP/SL -- reason=SL, pnl_net correcto (profit+swap+commission+fee)",
          obs_sl["close_reason"] == "SL" and abs(obs_sl["pnl_net"] - (-100.0 - 0.5 - 0.2)) < 1e-9)
    check("open_deal_ticket != close_deal_ticket != order_ticket (identidad de deal distinta, demostrado)",
          len({obs_sl["open_deal_ticket"], obs_sl["close_deal_ticket"], obs_sl["ticket"]}) == 3)
    check("realized_r calculado (sl/fill/symbol_info disponibles en el fixture)",
          isinstance(obs_sl["realized_r"], float) and obs_sl["realized_r"] < 0)

    obs_tp = bridge.reconcile_ticket(mt5f, "TEST", 1, 1006, 0.1)
    check("closed TP -- reason=TP, pnl_net positivo", obs_tp["close_reason"] == "TP" and obs_tp["pnl_net"] > 0)

    print("\n=== B. Ticket inexistente -- UNKNOWN, nunca inventado (mismo caso que la contaminacion encontrada) ===")
    obs_unknown = bridge.reconcile_ticket(mt5f, "TEST", 1, 999999, 0.1)
    check("ticket sin rastro en MT5 -> UNKNOWN", obs_unknown["order_final_state"] == "UNKNOWN")

    print("\n=== C. Idempotencia ===")
    with tempfile.TemporaryDirectory() as tmp:
        outcome_store.DATA_DIR = Path(tmp)
        tickets = [1001, 1002, 1003, 1004, 1005, 1006]
        s1 = bridge.reconcile_signal_quality_outcomes(mt5f, "TEST", 1, 0.1, tickets, outcome_store)
        check("primera corrida reconcilia todos", s1["reconciled"] == 6 and s1["skipped_already_final"] == 0)
        s2 = bridge.reconcile_signal_quality_outcomes(mt5f, "TEST", 1, 0.1, tickets, outcome_store)
        check("segunda corrida -- 0 escrituras nuevas para los terminales (CANCELED/EXPIRED/closed)",
              s2["reconciled"] == 0, f"s2={s2}")
        check("segunda corrida -- PENDING y FILLED-abierta se siguen consultando (no son terminales)",
              s2["checked"] == 2, f"s2={s2}")  # 1001 (pending) + 1004 (filled abierta)

        print("\n=== D. Restart/recovery -- el estado vive en archivo, no en memoria ===")
        # "Reinicio": nueva referencia de proceso, mismo DATA_DIR -- debe leer
        # exactamente el mismo estado ya persistido, sin recalcular desde MT5
        # lo que ya es terminal.
        all_after = outcome_store.load_all("TEST", 1)
        check("6 outcomes sobreviven el 'reinicio' (load_all fresco)", len(all_after) == 6)
        check("closed SL sigue con pnl_net correcto tras 'reinicio'",
              abs(all_after[1005]["pnl_net"] - (-100.7)) < 1e-9)

        print("\n=== E. Persistencia corrupta -- no rompe la lectura ===")
        path = outcome_store._store_path("TEST", 1)
        with path.open("a", encoding="utf-8") as f:
            f.write("{not valid json\n")
        all_with_corrupt = outcome_store.load_all("TEST", 1)
        check("linea corrupta se ignora, resto sigue legible", len(all_with_corrupt) == 6)

    print("\n=== F. Aislamiento de fallas del bridge (failure isolation, seccion 16) ===")
    mt5_fail = FakeMT5()
    _setup_non_filled(mt5_fail, 2001)
    mt5_fail.raise_on = 2001
    with tempfile.TemporaryDirectory() as tmp2:
        outcome_store.DATA_DIR = Path(tmp2)
        summary = bridge.reconcile_signal_quality_outcomes(mt5_fail, "TEST", 1, 0.1, [2001], outcome_store)
        check("una excepcion de MT5 no propaga -- reconcile_signal_quality_outcomes no lanza",
              summary["errors"] == 1 and summary["checked"] == 1)
        check("el ticket fallido queda UNKNOWN, no crashea ni inventa un estado",
              outcome_store.load_all("TEST", 1)[2001]["order_final_state"] == "UNKNOWN")

    print("\n=== G. OOS eligibility (boundary) ===")
    check("timestamp antes del freeze -> no elegible",
          not bridge.is_oos_eligible("2026-09-20T00:00:00+00:00", "1.0.0"))
    check("timestamp despues del freeze, schema vigente -> elegible",
          bridge.is_oos_eligible("2026-09-22T01:00:00+00:00", "1.0.0"))
    check("schema distinto -> no elegible (aunque la fecha sea posterior)",
          not bridge.is_oos_eligible("2026-09-22T01:00:00+00:00", "0.9.0"))

    print("\n=== H. Dataset builder -- 0 / parcial / completo, NEUTRAL != UNAVAILABLE, Universe A conserva non-filled ===")
    with tempfile.TemporaryDirectory() as tmp3:
        score_store.DATA_DIR = Path(tmp3) / "scores"
        outcome_store.DATA_DIR = Path(tmp3) / "outcomes"

        df_empty = oos_ds.build_dataset("SYM0", 1)
        check("0 snapshots -> dataset vacio, no crashea", len(df_empty) == 0)
        rd_empty = oos_ds.readiness(df_empty)
        check("readiness con 0 datos -> NO_DATA en los 4 factores",
              all(v == oos_ds.READY_NO_DATA for v in rd_empty.values()), f"{rd_empty}")

        sq_neutral = {
            "schema_version": "1.0.0", "observed_at_bar": 1,
            "observed_at_time_utc": "2026-09-22T10:00:00+00:00", "direction": "LONG",
            "momentum": {"status": "AVAILABLE", "value": 0.1},
            "alignment": {"status": "AVAILABLE", "value": "NEUTRAL"},
            "structure": {"status": "UNAVAILABLE", "value": None},
            "context": {"status": "AVAILABLE", "value": "Monday"},
        }
        score_store.record("SYM0", 1, 5001, {"total": 0}, signal_quality=sq_neutral,
                            signal_quality_diagnostics={"structure_replay_matches_signal": False,
                                                         "unavailable_reasons": {"structure": "structure_replay_mismatch"}})
        # ticket 5002: cancelado, nunca llena -- Universe A debe conservarlo
        score_store.record("SYM0", 1, 5002, {"total": 0}, signal_quality={**sq_neutral, "direction": "SHORT"})

        df_partial = oos_ds.build_dataset("SYM0", 1)
        check("2 snapshots sin outcome reconciliado -> filled=False para ambos (non-filled se conserva)",
              len(df_partial) == 2 and not df_partial["filled"].any())
        row5001 = df_partial[df_partial["order_ticket"] == 5001].iloc[0]
        check("NEUTRAL (alignment) se preserva tal cual -- nunca colapsado a UNAVAILABLE",
              row5001["alignment_status"] == "AVAILABLE" and row5001["alignment"] == "NEUTRAL")
        check("structure UNAVAILABLE con razon structure_replay_mismatch preservada en diagnostic_reason",
              row5001["structure_status"] == "UNAVAILABLE" and "structure_replay_mismatch" in str(row5001["diagnostic_reason"]))
        check("sq_complete False cuando algun factor esta UNAVAILABLE", row5001["sq_complete"] == False)  # noqa: E712

        outcome_store.record("SYM0", 1, {
            "ticket": 5002, "symbol": "SYM0", "magic": 1, "order_final_state": "CANCELED",
            "fill_time_utc": None, "position_id": None, "close_time_utc": None,
            "pnl_gross": None, "commission": None, "swap": None, "pnl_net": None,
            "realized_r": None, "close_reason": None, "open_deal_ticket": None, "close_deal_ticket": None,
        })
        df_with_outcome = oos_ds.build_dataset("SYM0", 1)
        row5002 = df_with_outcome[df_with_outcome["order_ticket"] == 5002].iloc[0]
        check("Universe A conserva el ticket cancelado (non-filled) -- no se elimina por falta de P&L",
              row5002["order_final_state"] == "CANCELED" and not row5002["filled"] and not row5002["closed"])

        check("dataset determinista -- misma llamada, mismo resultado", oos_ds.build_dataset("SYM0", 1).equals(df_with_outcome))

    print("\n=== I. LiveExecutionBot._run_signal_quality_oos_bridge() -- resguardo defensivo (seccion 16) ===")
    # No se re-construye un LiveExecutionBot completo aca (eso ya lo cubre
    # execution/src/test_signal_quality_behavior_invariance.py, con MT5
    # falso inyectado) -- esta prueba verifica puntualmente que el metodo
    # atrapa CUALQUIER excepcion del bridge sin propagar, usando el bot ya
    # importado por ese otro archivo de test para no duplicar el fixture de
    # LiveExecutionBot.
    import execution.src.test_signal_quality_behavior_invariance as bi_test
    bot = bi_test._make_bot()
    # sq_tickets debe ser no-vacio para que _run_signal_quality_oos_bridge()
    # llegue a llamar al bridge (si no hay ningun snapshot, el metodo
    # retorna temprano SIN llamarlo -- ver bot.py, comportamiento correcto
    # pero que dejaria esta prueba sin ejercitar nada). bi_test ya dejo
    # score_store.DATA_DIR apuntando a un tempdir aislado (import a nivel de
    # modulo de ese archivo) -- se reusa, no se toca el store real.
    score_store.record(bot.symbol, bot.magic, 700001, None, signal_quality={
        "schema_version": "1.0.0", "observed_at_bar": 1,
        "observed_at_time_utc": "2026-09-22T09:00:00+00:00", "direction": "LONG",
        "momentum": {"status": "AVAILABLE", "value": 0.1},
        "alignment": {"status": "AVAILABLE", "value": "NEUTRAL"},
        "structure": {"status": "AVAILABLE", "value": 0.1},
        "context": {"status": "AVAILABLE", "value": "Monday"},
    })

    def _boom(*a, **kw):
        raise RuntimeError("fallo forzado del bridge OOS -- solo para esta prueba")

    # `bridge` (este archivo) y `execution.src.bot.sq_bridge` son el MISMO
    # objeto modulo (Python cachea modulos) -- parchear el atributo aca lo
    # cambia para cualquier referencia, incluida la de bot.py.
    real_bridge_fn = bridge.reconcile_signal_quality_outcomes
    bridge.reconcile_signal_quality_outcomes = _boom
    try:
        bot._run_signal_quality_oos_bridge()  # no debe lanzar
        check("_run_signal_quality_oos_bridge() no propaga una excepcion del bridge", True)
    except Exception as e:
        check("_run_signal_quality_oos_bridge() no propaga una excepcion del bridge", False, f"propago: {e!r}")
    finally:
        bridge.reconcile_signal_quality_outcomes = real_bridge_fn

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
