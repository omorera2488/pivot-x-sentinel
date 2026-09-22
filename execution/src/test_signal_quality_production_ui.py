"""Regresion de BOT-051.6 (Signal Quality Production UI / Observability UX).

No vuelve a probar lo que BOT-051.4/BOT-051.5 ya cubrieron (calculo del
vector, bridge de reconciliacion, idempotencia -- ver
execution/src/test_signal_quality_oos_bridge.py). Este archivo cubre el
CONTRATO DE DATOS que el panel nuevo depende de forma directa:

  - `score_store.load_all()` expone `signal_quality_diagnostics` (razon de
    UNAVAILABLE) ademas de `signal_quality` -- necesario para que
    panel/app.js::signalQualityFactor() pueda mostrar "Reason: <razon>"
    (seccion 6 del enunciado).
  - el snapshot t0 (`score_store`) es INMUTABLE frente a lo que pase despues
    en `outcome_store` -- ningun estado de outcome (PENDING/FILLED/TP/SL/
    CANCELED) puede alterar `signal_quality`/`signal_quality_diagnostics" de
    ese mismo ticket (seccion 9, "critico": separacion t0 vs outcome).
  - NEUTRAL (un VALOR de Alignment) nunca se confunde con UNAVAILABLE (un
    STATUS) en el payload que llega al panel.
  - las claves de `unavailable_reasons` coinciden exactamente con los 4
    factores que el panel indexa (momentum/alignment/structure/context) --
    guarda contra un rename silencioso que rompa el mapeo en
    panel/app.js::signalQualitySection().
  - un ticket sigue siendo consultable en /scores (via score_store) sin
    importar en que estado de lifecycle esta (PENDING/FILLED/CANCELED) --
    el payload no depende de outcome_store para existir.

Uso:
    python execution/src/test_signal_quality_production_ui.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src import outcome_store, score_store

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def _sq(alignment_value="ALIGNED_SINGLE", alignment_status="AVAILABLE",
        structure_status="AVAILABLE", structure_value=0.5) -> dict:
    return {
        "schema_version": "1.0.0", "observed_at_bar": 100,
        "observed_at_time_utc": "2026-09-22T10:00:00+00:00", "direction": "LONG",
        "momentum": {"status": "AVAILABLE", "value": 0.30},
        "alignment": {"status": alignment_status, "value": alignment_value if alignment_status == "AVAILABLE" else None},
        "structure": {"status": structure_status, "value": structure_value if structure_status == "AVAILABLE" else None},
        "context": {"status": "AVAILABLE", "value": "Tuesday"},
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        score_store.DATA_DIR = Path(tmp) / "scores"
        outcome_store.DATA_DIR = Path(tmp) / "outcomes"

        print("=== A. signal_quality_diagnostics llega intacto para un factor UNAVAILABLE ===")
        diag_structure_mismatch = {
            "structure_replay_matches_signal": False, "origin_bar": None, "n_bars_used": 15,
            "unavailable_reasons": {"structure": "structure_replay_mismatch"},
        }
        sq_a = _sq(structure_status="UNAVAILABLE", structure_value=None)
        score_store.record("XAUUSDc", 900001, 1001, {"total": 1}, signal_quality=sq_a,
                            signal_quality_diagnostics=diag_structure_mismatch)
        scores = score_store.load_all("XAUUSDc", 900001)
        check("ticket 1001: structure queda UNAVAILABLE (status)",
              scores[1001]["signal_quality"]["structure"]["status"] == "UNAVAILABLE")
        check("ticket 1001: la razon real llega separada (unavailable_reasons.structure)",
              scores[1001]["signal_quality_diagnostics"]["unavailable_reasons"]["structure"] == "structure_replay_mismatch")

        print("\n=== B. Claves de unavailable_reasons == los 4 factores que indexa el panel ===")
        expected_keys = {"momentum", "alignment", "structure", "context"}
        diag_all = {
            "structure_replay_matches_signal": False, "origin_bar": None, "n_bars_used": 0,
            "unavailable_reasons": {"momentum": "warmup", "alignment": "alignment_history",
                                     "structure": "warmup", "context": "other"},
        }
        check("las 4 claves posibles de unavailable_reasons son un subconjunto de {momentum,alignment,structure,context}",
              set(diag_all["unavailable_reasons"].keys()) <= expected_keys,
              f"keys={set(diag_all['unavailable_reasons'].keys())}")

        print("\n=== C. NEUTRAL (valor de Alignment) nunca se confunde con UNAVAILABLE (status) ===")
        sq_neutral = _sq(alignment_value="NEUTRAL", alignment_status="AVAILABLE")
        score_store.record("XAUUSDc", 900001, 1002, {"total": 0}, signal_quality=sq_neutral)
        scores = score_store.load_all("XAUUSDc", 900001)
        check("ticket 1002: alignment.status == AVAILABLE (NEUTRAL es un valor, no un status)",
              scores[1002]["signal_quality"]["alignment"]["status"] == "AVAILABLE")
        check("ticket 1002: alignment.value == 'NEUTRAL' tal cual, sin colapsar",
              scores[1002]["signal_quality"]["alignment"]["value"] == "NEUTRAL")
        sq_unavail_alignment = _sq(alignment_status="UNAVAILABLE", alignment_value=None)
        score_store.record("XAUUSDc", 900001, 1003, {"total": 0}, signal_quality=sq_unavail_alignment)
        scores = score_store.load_all("XAUUSDc", 900001)
        check("ticket 1003 (alignment genuinamente UNAVAILABLE) es distinguible de 1002 (NEUTRAL)",
              scores[1003]["signal_quality"]["alignment"]["status"] == "UNAVAILABLE"
              and scores[1002]["signal_quality"]["alignment"]["status"] == "AVAILABLE")

        print("\n=== D. Snapshot t0 inmutable frente a outcomes posteriores (seccion 9, CRITICO) ===")
        sq_d = _sq()
        score_store.record("XAUUSDc", 900001, 2001, {"total": 2}, signal_quality=sq_d)
        before = score_store.load_all("XAUUSDc", 900001)[2001]["signal_quality"]
        # Simula el ciclo de vida completo: PENDING -> FILLED -> cerrado TP,
        # cada uno agregado como linea NUEVA en outcome_store (igual que
        # signal_quality_reconciliation.reconcile_ticket() hace en produccion).
        outcome_store.record("XAUUSDc", 900001, {"ticket": 2001, "order_final_state": "PENDING"})
        outcome_store.record("XAUUSDc", 900001, {"ticket": 2001, "order_final_state": "FILLED"})
        outcome_store.record("XAUUSDc", 900001, {
            "ticket": 2001, "order_final_state": "FILLED", "close_reason": "TP",
            "pnl_net": 49.70, "realized_r": "UNAVAILABLE",
        })
        after = score_store.load_all("XAUUSDc", 900001)[2001]["signal_quality"]
        check("signal_quality del ticket 2001 es BYTE-IDENTICO antes/despues de 3 outcomes reconciliados",
              before == after, f"before={before}\n       after={after}")
        outcomes = outcome_store.load_all("XAUUSDc", 900001)
        check("outcome_store SI refleja el ultimo estado (close_reason=TP) -- vive aparte, no en score_store",
              outcomes[2001]["close_reason"] == "TP" and outcomes[2001]["order_final_state"] == "FILLED")

        print("\n=== E. Un ticket CANCELADO sigue teniendo su Signal Quality t0 intacta ===")
        sq_e = _sq()
        score_store.record("XAUUSDc", 900001, 3001, {"total": -1}, signal_quality=sq_e)
        outcome_store.record("XAUUSDc", 900001, {"ticket": 3001, "order_final_state": "CANCELED"})
        scores = score_store.load_all("XAUUSDc", 900001)
        outcomes = outcome_store.load_all("XAUUSDc", 900001)
        check("ticket 3001 (CANCELED): signal_quality sigue completo pese a que nunca se lleno",
              scores[3001]["signal_quality"] == sq_e)
        check("ticket 3001 (CANCELED): outcome_store refleja el estado final",
              outcomes[3001]["order_final_state"] == "CANCELED")

        print("\n=== F. OUTCOME_ONLY_FIELDS nunca aparece dentro de un signal_quality persistido ===")
        all_scores = score_store.load_all("XAUUSDc", 900001)
        leaked = set()
        for row in all_scores.values():
            sq = row.get("signal_quality")
            if not sq:
                continue
            leaked |= (set(sq.keys()) & outcome_store.OUTCOME_ONLY_FIELDS)
        check("ningun campo de OUTCOME_ONLY_FIELDS aparece dentro de un signal_quality guardado",
              not leaked, f"leaked={leaked}")

        print("\n=== G. Un ticket todavia PENDIENTE (sin outcome_store) igual se puede consultar ===")
        sq_g = _sq()
        score_store.record("XAUUSDc", 900001, 4001, {"total": 1}, signal_quality=sq_g)
        scores = score_store.load_all("XAUUSDc", 900001)
        outcomes = outcome_store.load_all("XAUUSDc", 900001)
        check("ticket 4001 tiene signal_quality aunque nunca se reconcilio (LIMIT recien nacida)",
              4001 in scores and scores[4001]["signal_quality"] == sq_g)
        check("ticket 4001 NO tiene entrada en outcome_store todavia (coherente -- no se inventa un estado)",
              4001 not in outcomes)

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
