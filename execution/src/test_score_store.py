"""Regresion de execution/src/score_store.py -- BOT-051.4 (agrega
`signal_quality` opcional junto al `score` existente).

Verifica explicitamente:
  - comportamiento IDENTICO al de antes de BOT-051.4 para registros que solo
    tienen `score` (backward compatibility real, no solo declarada);
  - un registro JSONL escrito por una version VIEJA del formato (sin la
    clave `signal_quality`) se lee sin error, con `signal_quality: None`;
  - un registro nuevo con ambos (`score` + `signal_quality`) se lee completo;
  - un registro con SOLO `signal_quality` (entry_score=None) tambien se
    persiste y se lee correctamente;
  - append-only / ultima linea gana si un ticket se repite.

Uso:
    python execution/src/test_score_store.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from execution.src import score_store

FAILURES: list[str] = []


def check(label: str, condition: bool, evidence: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f"\n       {evidence}" if evidence else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        score_store.DATA_DIR = Path(tmp) / "scores"

        print("=== A. Backward compatibility -- solo score (comportamiento pre-BOT-051.4) ===")
        score_store.record("XAUUSDc", 900001, 111, {"total": 2, "divergencia_score": 1})
        out = score_store.load_all("XAUUSDc", 900001)
        check("ticket 111 presente", 111 in out)
        check("campos de score quedan al nivel superior (igual que antes)", out[111]["total"] == 2 and out[111]["divergencia_score"] == 1)
        check("signal_quality == None cuando no se paso", out[111]["signal_quality"] is None)

        print("\n=== B. Registro legacy en disco SIN la clave signal_quality (simulado a mano) ===")
        legacy_path = score_store._store_path("XAUUSDc", 900001)
        with legacy_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ticket": 222, "score": {"total": -1}}) + "\n")
        out2 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 222 (linea legacy sin signal_quality) se lee sin error", 222 in out2)
        check("signal_quality == None para la linea legacy", out2[222]["signal_quality"] is None)
        check("score.total de la linea legacy sigue correcto", out2[222]["total"] == -1)

        print("\n=== C. Registro nuevo con score + signal_quality ===")
        sq_dict = {
            "schema_version": "1.0.0", "observed_at_bar": 42,
            "observed_at_time_utc": "2026-09-21T10:00:00+00:00", "direction": "LONG",
            "momentum": {"status": "AVAILABLE", "value": 0.42},
            "alignment": {"status": "AVAILABLE", "value": "ALIGNED_SINGLE"},
            "structure": {"status": "AVAILABLE", "value": 0.68},
            "context": {"status": "AVAILABLE", "value": "Friday"},
        }
        score_store.record("XAUUSDc", 900001, 333, {"total": 1}, signal_quality=sq_dict)
        out3 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 333 tiene score y signal_quality completos",
              out3[333]["total"] == 1 and out3[333]["signal_quality"] == sq_dict)

        print("\n=== D. Registro solo con signal_quality (entry_score=None) ===")
        score_store.record("XAUUSDc", 900001, 444, None, signal_quality=sq_dict)
        out4 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 444 no tiene campos de score (dict vacio + signal_quality)",
              "total" not in out4[444] and out4[444]["signal_quality"] == sq_dict)

        print("\n=== E. Ticket repetido -- ultima linea gana (comportamiento ya existente, sin cambios) ===")
        score_store.record("XAUUSDc", 900001, 111, {"total": 99})
        out5 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 111 refleja la ULTIMA escritura (total=99)", out5[111]["total"] == 99)

        print("\n=== F. Linea corrupta se ignora sin romper la lectura (comportamiento ya existente) ===")
        with legacy_path.open("a", encoding="utf-8") as f:
            f.write("{not valid json\n")
        out6 = score_store.load_all("XAUUSDc", 900001)
        check("lectura sigue funcionando pese a la linea corrupta", len(out6) == 4)

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
