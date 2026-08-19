# execution

Motor de ejecución en vivo contra MT5: conexión, colocación de órdenes límite con SL/TP, vigilancia/cancelación de pendientes invalidados, cierre por tiempo máximo, y reconciliación de concurrencia contra el estado real del bróker. Implementa [docs/spec-live-execution.md](../docs/spec-live-execution.md) al pie de la letra, sobre el motor de [/strategy](../strategy).

> **Sin parámetros validados por backtest** (Fase 3 no encontró edge robusto en M5, ver `docs/spec-backtest.md` §8) — opera igual, a pedido explícito del usuario. Qué cuenta conectar (demo o real) es decisión de quien loguea la terminal MT5, no del código — ver nota al tope de `docs/spec-live-execution.md` y el disclaimer en el README raíz.

## Uso

```
python scripts/run_bot.py --profile 5m --symbol XAUUSDm              # opera de una (default) contra la cuenta conectada
python scripts/run_bot.py --profile 5m --symbol XAUUSDm --dry-run    # solo calcula y loguea, no manda ordenes
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
