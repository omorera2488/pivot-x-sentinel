"""BOT-008 -- etapa 3: sensibilidad local (vecindad) de los finalistas que
pasaron la etapa de robustez temporal (11_bot008_robustness_candidates.py).

Analisis puro sobre datos ya calculados -- NO corre backtests nuevos, solo
busca en `sweep_full_M5_post_BOT-043.csv` (las 3.780 filas ya generadas) los
vecinos inmediatos de cada finalista en cada una de las 5 dimensiones del
espacio de parametros (ema_periods, periodos_htf_min, buf_bp, rr,
max_concurrent_por_direccion), variando una dimension por vez y dejando las
otras 4 fijas -- hasta 10 vecinos por candidato (2 por dimension, cuando
existen en la malla).

Clasifica cada finalista como:
  - MESETA: la mayoria de sus vecinos inmediatos tambien tienen
    expectancy_r > 0 (umbral: >=60% de los vecinos existentes).
  - PICO AISLADO: la mayoria de sus vecinos tienen expectancy_r <= 0 --
    senal fuerte de posible overfitting a esa combinacion puntual.

"Finalista" para este script = cualquier fila de
`bot008_robustness_candidates_post_BOT-043_M5.csv` con
`positive_subperiods >= 2` y `full_expectancy_r > 0` (no re-define el
criterio de la etapa 2, solo filtra sobre su resultado ya guardado).

Uso:
    python backtests/scripts/12_bot008_neighborhood_analysis.py [M5]
"""
import sys
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

GRID_VALUES = {
    "ema_periods": [8, 11, 14, 17, 20, 23],
    "periodos_htf_min": [200, 350, 500, 650, 800],
    "buf_bp": [0.2, 0.7, 1.2, 1.7, 2.2, 2.7, 3.2],
    "rr": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    "max_concurrent_por_direccion": [1, 2, 3],
}


def neighbors_of(row: dict) -> list[dict]:
    out = []
    for dim, values in GRID_VALUES.items():
        cur = row[dim]
        # tolerancia de float para buf_bp/rr (linspace_count redondea a 6 decimales)
        idx_matches = [i for i, v in enumerate(values) if abs(v - cur) < 1e-6]
        if not idx_matches:
            continue
        idx = idx_matches[0]
        for delta in (-1, 1):
            j = idx + delta
            if 0 <= j < len(values):
                neighbor = dict(row)
                neighbor[dim] = values[j]
                out.append(neighbor)
    return out


def find_row(sweep: pd.DataFrame, params: dict):
    mask = (
        (sweep["ema_periods"] == params["ema_periods"])
        & (sweep["periodos_htf_min"] == params["periodos_htf_min"])
        & (abs(sweep["buf_bp"] - params["buf_bp"]) < 1e-6)
        & (abs(sweep["rr"] - params["rr"]) < 1e-6)
        & (sweep["max_concurrent_por_direccion"] == params["max_concurrent_por_direccion"])
    )
    matched = sweep[mask]
    return matched.iloc[0] if len(matched) else None


def main():
    tf = "M5"
    sweep = pd.read_csv(RESULTS_DIR / f"sweep_full_{tf}_post_BOT-043.csv")
    cand_path = RESULTS_DIR / f"bot008_robustness_candidates_post_BOT-043_{tf}.csv"
    cand = pd.read_csv(cand_path)

    finalists = cand[(cand["positive_subperiods"] >= 2) & (cand["full_expectancy_r"] > 0)
                      & (cand["cfg_id"] != "ConfigA_referencia")].copy()
    print(f"Finalistas (positive_subperiods>=2 AND full_expectancy_r>0): {len(finalists)}/{len(cand)-1} candidatos")

    rows = []
    for _, f in finalists.iterrows():
        base = {"ema_periods": f["ema_periods"], "periodos_htf_min": f["periodos_htf_min"],
                "buf_bp": f["buf_bp"], "rr": f["rr"],
                "max_concurrent_por_direccion": f["max_concurrent_por_direccion"]}
        neigh_params = neighbors_of(base)
        neigh_exp = []
        neigh_detail = []
        for np_ in neigh_params:
            r = find_row(sweep, np_)
            if r is not None:
                neigh_exp.append(float(r["expectancy_r"]))
                neigh_detail.append({**np_, "n_trades": int(r["n_trades"]), "expectancy_r": float(r["expectancy_r"]),
                                      "profit_factor": float(r["profit_factor"])})
        n_neighbors = len(neigh_exp)
        n_positive = sum(1 for e in neigh_exp if e > 0)
        frac_positive = n_positive / n_neighbors if n_neighbors else float("nan")
        mean_neighbor_exp = sum(neigh_exp) / n_neighbors if n_neighbors else float("nan")
        classification = "MESETA" if (n_neighbors > 0 and frac_positive >= 0.6) else "PICO_AISLADO"
        rows.append({
            "cfg_id": f["cfg_id"], "ema_periods": f["ema_periods"], "periodos_htf_min": f["periodos_htf_min"],
            "buf_bp": f["buf_bp"], "rr": f["rr"], "max_concurrent_por_direccion": f["max_concurrent_por_direccion"],
            "full_expectancy_r": f["full_expectancy_r"], "full_pf": f["full_pf"],
            "positive_subperiods": f["positive_subperiods"],
            "n_neighbors_found": n_neighbors, "n_neighbors_positive": n_positive,
            "frac_neighbors_positive": frac_positive, "mean_neighbor_expectancy_r": mean_neighbor_exp,
            "classification": classification,
        })
        print(f"{f['cfg_id']}: expR={f['full_expectancy_r']:.4f} vecinos={n_neighbors} "
              f"positivos={n_positive} ({frac_positive:.0%}) -> {classification}")

    out = pd.DataFrame(rows)
    out_path = RESULTS_DIR / f"bot008_neighborhood_analysis_post_BOT-043_{tf}.csv"
    out.to_csv(out_path, index=False)
    print(f"\nGuardado: {out_path} ({len(out)} finalistas analizados)")


if __name__ == "__main__":
    main()
