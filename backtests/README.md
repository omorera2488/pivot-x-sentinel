# backtests

Backtesting específico de Oro (XAUUSD) sobre el motor de [/strategy](../strategy): modelo de costos (spread, comisión, swap), barrido de parámetros y pruebas de robustez por sub-períodos, uno por cada perfil (`1m`/`5m`, ver `strategy/profiles.py`).

Implementa [docs/spec-backtest.md](../docs/spec-backtest.md) al pie de la letra. Ver ese documento, sección "Resultados", para los resultados y su interpretación (por ahora: perfil 5m corrido, sin edge robusto — §8; perfil 1m sin correr todavía).

## Instalar

```
pip install -r requirements.txt
```

Requiere una terminal MT5 abierta y logueada (el motor se conecta a la instancia local en ejecución, no gestiona credenciales).

## Uso

```
python scripts/01_download_data.py XAUUSDm M5      # descarga historial por chunks a data/
python ../strategy/test_engine.py                  # valida las reglas mecanicas del motor (spec #6) — vive en /strategy
python scripts/03_run_sweep.py M5                   # corre la malla del perfil (spec #4) -- M1 o M5
python scripts/04_run_robustness.py M5              # valida los top del barrido en sub-periodos (spec #5)
```

`data/` no se versiona (se regenera con el script 01). `results/` sí — es el registro de qué se corrió y qué salió, con sufijo de perfil (`sweep_full_M5.csv`, etc.).

## Estructura

```
src/
  offset.py     -> medicion del offset horario del broker (agnostico, symbol_info_tick vs UTC)
  download.py   -> descarga de historial MT5 por chunks
  sweep.py      -> barrido de parametros por perfil (grid_1m/grid_5m), usa strategy.engine/strategy.costs
scripts/        -> puntos de entrada CLI, numerados en el orden en que se corren
results/        -> csv de cada corrida (versionado)
data/           -> historial OHLC descargado (no versionado, ver .gitignore)
```

El motor (`engine.py`), el modelo de costos (`costs.py`) y los perfiles (`profiles.py`) viven en [/strategy](../strategy), no acá — este directorio es solo la capa de backtesting sobre esa lógica.
