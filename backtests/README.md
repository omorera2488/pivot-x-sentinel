# backtests

Motor de backtesting y resultados específicos de Oro (XAUUSD): modelo de costos (spread, comisión, swap), barrido de parámetros y pruebas de robustez por sub-períodos.

Implementa [docs/spec-estrategia.md](../docs/spec-estrategia.md) y [docs/spec-backtest.md](../docs/spec-backtest.md) al pie de la letra. Ver ese último documento, sección "Resultados del primer barrido", para el resultado y su interpretación.

## Instalar

```
pip install -r requirements.txt
```

Requiere una terminal MT5 abierta y logueada (el motor se conecta a la instancia local en ejecución, no gestiona credenciales).

## Uso

```
python scripts/01_download_data.py XAUUSDm M5   # descarga historial por chunks a data/
python scripts/02_run_checksum.py               # valida las 4 reglas mecanicas del motor (spec #6)
python scripts/03_run_sweep.py                  # corre la malla completa de parametros (spec #4)
python scripts/04_run_robustness.py             # valida los mejores combos en 3 sub-periodos (spec #5)
```

`data/` no se versiona (se regenera con el script 01). `results/` sí — es el registro de qué se corrió y qué salió.

## Estructura

```
src/
  offset.py     -> medicion del offset horario del broker (agnostico, symbol_info_tick vs UTC)
  download.py   -> descarga de historial MT5 por chunks
  costs.py      -> modelo de costos (spread real por vela, comision, swap)
  engine.py     -> motor de backtest, implementa spec-estrategia.md al pie de la letra
  sweep.py      -> barrido de parametros
scripts/        -> puntos de entrada CLI, numerados en el orden en que se corren
results/        -> csv de cada corrida (versionado)
data/           -> historial OHLC descargado (no versionado, ver .gitignore)
```
