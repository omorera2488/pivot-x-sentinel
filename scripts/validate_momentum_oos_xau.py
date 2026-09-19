"""BOT-024.3 -- Validacion OOS de Momentum en XAUUSDc (pre-flight + deteccion
de bloqueo). Subtarea de BOT-024, sucesora de BOT-024.2 (Momentum Feature
Discovery). SOLO LECTURA/AUDITORIA -- no modifica strategy/, execution/,
api/ ni panel/. No implementa MomentumScore, no asigna pesos, no activa
gating, no integra D1.

Que hace este script:
  1. Confirma, DESDE EL DATASET (no de memoria/documentacion), el timestamp
     exacto en el que termino el periodo de discovery de BOT-024.2.
  2. Busca en el repositorio cualquier dataset XAUUSDc con barras
     POSTERIORES a ese cutoff -- sin descargar nada nuevo (regla explicita
     del enunciado de BOT-024.3: "NO descargar datos automaticamente").
  3. Si no hay ninguna barra OOS, imprime `BOT-024.3 BLOCKED -- insufficient
     OOS data` con el detalle exacto y TERMINA -- no ejecuta ningun analisis
     predictivo, no recicla el periodo de discovery como si fuera OOS.
  4. Si hubiera barras OOS (no es el caso al momento de escribir este
     script -- ver reports/BOT-024.3-MOMENTUM-OOS.md), este script es el
     punto de entrada para la Parte 2 (validacion de H1-H6 con thresholds
     congelados de discovery) -- esa parte NO esta implementada todavia,
     a proposito: construirla contra datos que no existen arriesga bugs no
     detectables y trabajo especulativo: se implementa cuando haya OOS real
     que la ejercite, reusando el patron de shadow replay + paridad
     exhaustiva ya validado en scripts/discover_momentum_features_xau.py.

Uso:
    .venv/Scripts/python.exe scripts/validate_momentum_oos_xau.py \
        > reports/BOT-024.3-MOMENTUM-OOS-evidence.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "backtests" / "data"

# Dataset de discovery, congelado -- el mismo que uso BOT-024.2 (ver
# reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY.md, seccion B). No se asume
# el cutoff de memoria: se relee del archivo mas abajo.
DISCOVERY_PATH = DATA_DIR / "XAUUSDc_M5_latest.parquet"


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    print("BOT-024.3 -- Validacion OOS de Momentum, XAUUSDc -- pre-flight")
    print("SOLO LECTURA/AUDITORIA. No se modifico ningun archivo de produccion.")
    print("No se descargo ningun dato nuevo (regla explicita del enunciado).\n")

    # --- 1. Confirmar el dataset de discovery y su cutoff exacto -----------
    section("1. Dataset de discovery (BOT-024.2) -- confirmado desde el archivo, no de memoria")
    if not DISCOVERY_PATH.exists():
        print(f"[FAIL] No se encontro el dataset de discovery esperado: {DISCOVERY_PATH}")
        return 1
    df_disc = pd.read_parquet(DISCOVERY_PATH)
    n_disc = len(df_disc)
    t0 = pd.to_datetime(df_disc["time_utc"].iloc[0], unit="s", utc=True)
    t1 = pd.to_datetime(df_disc["time_utc"].iloc[-1], unit="s", utc=True)
    print(f"Archivo: {DISCOVERY_PATH.name}")
    print(f"Barras: {n_disc}")
    print(f"Timestamp inicial: {t0.isoformat()}")
    print(f"Timestamp final (CUTOFF de discovery): {t1.isoformat()}")

    # sanity check: coincide con lo documentado en BOT-024.2-MOMENTUM-FEATURE-DISCOVERY.md
    expected_n, expected_t1 = 100505, pd.Timestamp("2026-09-15 00:40:03", tz="UTC")
    match = (n_disc == expected_n) and (t1 == expected_t1)
    print(f"[{'PASS' if match else 'FAIL'}] coincide con lo documentado en BOT-024.2 "
          f"(100505 barras, cutoff 2026-09-15 00:40:03 UTC): "
          f"n_disc={n_disc}, t1={t1.isoformat()}")

    # --- 2. Buscar cualquier dataset XAU con barras posteriores al cutoff --
    section("2. Busqueda de dataset OOS (barras posteriores al cutoff, sin descargar nada)")
    candidates = sorted(DATA_DIR.glob("XAUUSD*"))
    print(f"Archivos XAUUSD* en {DATA_DIR}: {[p.name for p in candidates]}")

    oos_bars_found = 0
    oos_sources = []
    for p in candidates:
        if p.resolve() == DISCOVERY_PATH.resolve():
            continue
        try:
            df_c = pd.read_parquet(p)
        except Exception as e:
            print(f"  {p.name}: no se pudo leer ({e}) -- se ignora")
            continue
        tmax_c = pd.to_datetime(df_c["time_utc"].max(), unit="s", utc=True)
        n_after = int((df_c["time_utc"] > int(t1.timestamp())).sum())
        print(f"  {p.name}: {len(df_c)} barras, hasta {tmax_c.isoformat()}, "
              f"{n_after} barras estrictamente POSTERIORES al cutoff de discovery")
        if n_after > 0:
            oos_bars_found += n_after
            oos_sources.append(p.name)

    # Tambien verificar si el propio archivo de discovery, releido, cambio
    # (ej. si alguien lo sobreescribio con mas barras desde la ultima vez) --
    # comparamos el cutoff arriba consigo mismo, ya cubierto en la seccion 1.

    print(f"\nTotal de barras OOS encontradas en el repositorio (fuera del dataset de discovery): {oos_bars_found}")
    if oos_sources:
        print(f"Fuentes: {oos_sources}")

    # --- 3. Decision GO / BLOCKED -------------------------------------------
    section("3. Decision")
    if oos_bars_found == 0:
        print("BOT-024.3 BLOCKED -- insufficient OOS data")
        print("")
        print("Detalle exacto del bloqueo:")
        print(f"  - Los datos disponibles en el repositorio llegan exactamente hasta "
              f"{t1.isoformat()} (mismo cutoff que uso BOT-024.2 para discovery).")
        print(f"  - Barras OOS encontradas (posteriores a ese cutoff, en cualquier archivo "
              f"XAUUSD* de backtests/data/): 0.")
        print(f"  - Por lo tanto: 0 LIMITS y 0 trades OOS evaluables -- no hay universo A ni B posible.")
        print(f"  - No se reutilizo el periodo de discovery como si fuera OOS (prohibido explicitamente).")
        print(f"  - No se descargo ningun dato nuevo (prohibido sin autorizacion explicita del usuario).")
        print(f"  - Dataset adicional necesario: historial M5 real de XAUUSDc (o el simbolo que resuelva "
              f"resolve_symbol('XAUUSD') en el broker conectado) con barras estrictamente posteriores a "
              f"{t1.isoformat()}, de duracion suficiente para acumular una muestra razonable de LIMITS "
              f"(la Config A de BOT-024.2 genera aproximadamente 1 señal cada ~23 barras M5 sobre 100505 "
              f"barras -- una ventana de pocos dias produciria una muestra demasiado chica para la mayoria "
              f"de las hipotesis H1-H6, aunque igual seria un primer dato real, no simulado).")
        return 2

    print("Hay barras OOS disponibles -- Parte 2 (validacion H1-H6 con thresholds congelados de "
          "discovery) NO esta implementada en esta version del script. Implementarla reusando el "
          "patron de shadow replay + paridad exhaustiva de scripts/discover_momentum_features_xau.py, "
          "congelando los thresholds de discovery (reconstruidos desde XAUUSDc_M5_latest.parquet, "
          "nunca de qcut() sobre OOS) antes de aplicarlos a estas barras nuevas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
