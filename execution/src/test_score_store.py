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

import numpy as np

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

        print("\n=== G. signal_quality_diagnostics (BOT-051.6) -- razon de UNAVAILABLE llega al panel ===")
        diag = {
            "structure_replay_matches_signal": False, "origin_bar": None, "n_bars_used": 20,
            "unavailable_reasons": {"structure": "structure_replay_mismatch"},
        }
        score_store.record("XAUUSDc", 900001, 555, {"total": 0}, signal_quality=sq_dict, signal_quality_diagnostics=diag)
        out7 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 555 trae signal_quality_diagnostics completo",
              out7[555]["signal_quality_diagnostics"] == diag)
        check("ticket 333 (sin diagnostics, seccion C) sigue en None -- backward compatible",
              out7[333]["signal_quality_diagnostics"] is None)
        check("linea legacy sin la clave (ticket 222) tambien queda en None, no rompe la lectura",
              out7[222]["signal_quality_diagnostics"] is None)

        print("\n=== H. BOT-051.6.3 -- numpy.bool_ real en diagnostics: record()/load_all() end-to-end ===")
        # Root cause de BOT-051.6.2: json.dumps() SIEMPRE falla sobre un
        # numpy.bool_ (confirmado empiricamente con el numpy real del
        # proyecto). Esta prueba NO mockea el punto que se esta probando --
        # pasa un numpy.bool_ REAL (no un bool de Python que simule serlo) a
        # traves de record() tal cual lo haria execution/src/bot.py si el fix
        # de strategy/signal_quality.py fallara o si un campo futuro se
        # olvidara de castear -- ejercitando la defensa en profundidad de
        # score_store.py::_json_safe(), no el fix del productor.
        diag_numpy = {
            "structure_replay_matches_signal": np.bool_(True),
            "origin_bar": np.int64(7), "n_bars_used": 30,
            "unavailable_reasons": {},
        }
        check("precondicion: structure_replay_matches_signal es numpy.bool_ real (no simulado)",
              type(diag_numpy["structure_replay_matches_signal"]) is np.bool_)
        score_store.record("XAUUSDc", 900001, 666, {"total": 0}, signal_quality=sq_dict,
                            signal_quality_diagnostics=diag_numpy)
        out8 = score_store.load_all("XAUUSDc", 900001)
        check("record() con numpy.bool_/numpy.int64 real NO lanza (defensa en profundidad activa)", 666 in out8)
        persisted_diag = out8[666]["signal_quality_diagnostics"]
        check("structure_replay_matches_signal persistido es bool NATIVO de Python tras leer del disco",
              type(persisted_diag["structure_replay_matches_signal"]) is bool
              and persisted_diag["structure_replay_matches_signal"] is True)
        check("origin_bar persistido es int NATIVO de Python tras leer del disco",
              type(persisted_diag["origin_bar"]) is int and persisted_diag["origin_bar"] == 7)
        # Confirma que la linea escrita en disco es JSON valido de verdad, no
        # solo que load_all() "arregla" algo en memoria -- lee el archivo raw.
        raw_path = score_store._store_path("XAUUSDc", 900001)
        with raw_path.open("r", encoding="utf-8") as f:
            last_line = f.readlines()[-1]
        try:
            json.loads(last_line)
            raw_json_ok = True
        except json.JSONDecodeError:
            raw_json_ok = False
        check("la linea escrita en disco es JSON valido (no quedo a medio escribir)", raw_json_ok)

        print("\n=== I. BOT-052.2 -- hch (snapshot HCH) viaja en la MISMA linea, joineable con signal_quality ===")
        hch_dict = {
            "hch_state": "HCH", "hch_version": "1.0.0",
            "hch_captured_at": "2026-09-24T10:00:00+00:00",
            "hch_consumed_on_signal_bar": 42,
            "hch_pivot_1": 4300.5, "hch_pivot_2": 4310.2, "hch_pivot_3": 4298.1,
            "hch_active_level": 4300.5, "hch_formation_bar": 39,
        }
        score_store.record("XAUUSDc", 900001, 777, {"total": 1}, signal_quality=sq_dict, hch=hch_dict)
        out9 = score_store.load_all("XAUUSDc", 900001)
        check("ticket 777 trae hch completo, byte-identico a lo que se paso", out9[777]["hch"] == hch_dict)
        check("ticket 777 sigue trayendo signal_quality (misma linea, ambos joineables por `ticket`)",
              out9[777]["signal_quality"] == sq_dict)
        check("ticket 333 (sin hch, secciones previas) sigue en None -- backward compatible",
              out9[333]["hch"] is None)
        check("linea legacy sin la clave (ticket 222) tambien queda en None, no rompe la lectura",
              out9[222]["hch"] is None)
        # hch=None (default) no debe agregar la clave -- comportamiento identico
        # al de antes de BOT-052.2 para cualquier llamador que no lo pase.
        score_store.record("XAUUSDc", 900001, 888, {"total": 0}, signal_quality=sq_dict)
        out10 = score_store.load_all("XAUUSDc", 900001)
        check("record() sin pasar hch sigue funcionando igual que antes (hch=None)", out10[888]["hch"] is None)

    print(f"\n{len(FAILURES)} failing checks" if FAILURES else "\nALL CHECKS PASS")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAILED: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
