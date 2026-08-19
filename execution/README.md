# execution

Motor de ejecución en vivo contra MT5: conexión, colocación de órdenes límite con SL/TP, vigilancia/cancelación de pendientes invalidados, cierre por tiempo máximo, y reconciliación de concurrencia contra el estado real del bróker. Implementa [docs/spec-live-execution.md](../docs/spec-live-execution.md) al pie de la letra, sobre el motor de [/strategy](../strategy).

> **Sin parámetros validados por backtest** (Fase 3 no encontró edge robusto en M5, ver `docs/spec-backtest.md` §8). Implementado a pedido explícito, corre en `dry_run` por defecto — ver nota al tope de `docs/spec-live-execution.md`.

## Uso

```
python scripts/run_bot.py --profile 5m --symbol XAUUSDm            # dry-run (default): loguea, no manda ordenes
python scripts/run_bot.py --profile 5m --symbol XAUUSDm --live     # manda ordenes reales -- solo cuenta demo
```

Requiere una terminal MT5 abierta y logueada (se conecta a la instancia local en ejecución, no gestiona credenciales). `--profile` acepta `1m`/`5m` (o `M1`/`M5`).

## Estructura

```
src/
  mt5_utils.py  -> conexion, resolucion de simbolo (busca 'XAU', no hardcodeado a un broker),
                    offset horario en vivo, deteccion de filling mode -- lo usa tambien /backtests
  bot.py        -> LiveExecutionBot: replay de arranque, poll de vela cerrada, colocacion/vigilancia
                    de ordenes, reconciliacion de concurrencia contra orders_get()/positions_get() reales
scripts/
  run_bot.py    -> punto de entrada CLI
```

El motor de señal (EMA, bloque HTF, armado) vive en [`strategy/live_signal.py`](../strategy/live_signal.py) — validado contra el motor batch de backtest (`strategy/test_engine.py`, test G): misma secuencia de barras, mismas señales, bit a bit.
