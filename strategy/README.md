# strategy

Lógica pura de la estrategia (EMA + Pivotes ZS). Sin dependencias de MT5 ni de red — testeable de forma aislada, alimentada solo con velas (OHLC). Implementa [docs/spec-estrategia.md](../docs/spec-estrategia.md) al pie de la letra.

Un solo motor (`engine.py`), dos perfiles seleccionables (`profiles.py`) — uno por cada indicador Pine de origen en [/basecode_tradingview](../basecode_tradingview):

```python
from strategy.profiles import get_profile
from strategy.engine import run_backtest
from strategy.costs import BrokerCosts

params = get_profile("1m")                      # ema=15, bloque HTF=100min (default del Pine 1m)
params = get_profile("5m", rr=2.0)               # ema=12, bloque HTF=400min (default del Pine 5m), con override
```

## Archivos

- `engine.py` — motor **batch**: EMA, bloque HTF (corregido, sin el bug de autoarmado), armado/señal, ciclo de vida completo de la orden (pendiente→llena/expirada, abierta→TP/SL/tiempo). Opera sobre arrays completos — lo usa `/backtests`.
- `live_signal.py` — motor **incremental**: misma EMA/bloque HTF/armado que `engine.py`, pero barra a barra con estado persistente entre llamadas — no maneja el ciclo de vida de la orden (eso en vivo lo gestiona `/execution` contra el estado real del bróker, no en memoria). Validado bit a bit contra `engine.py` (`test_engine.py`, test G) — misma secuencia de barras, mismas señales.
- `costs.py` — modelo de costos (spread/comisión/swap), parámetro opcional de `run_backtest` — correrlo con costos en cero da la estrategia "pelada".
- `profiles.py` — presets `1m`/`5m` (alias `M1`/`M5`) sobre el mismo `StrategyParams`.
- `test_engine.py` — checksum mecánico (`python strategy/test_engine.py`): valida las reglas de `spec-estrategia.md` sobre datos sintéticos, la selección de perfil, `entradaViva`, y la equivalencia motor batch↔incremental. No corre contra datos reales ni MT5 — para eso ver `/backtests` y `/execution`.

Lo usan `/backtests` (`engine.py`, barrido/backtest) y `/execution` (`live_signal.py`, Fase 4 en vivo) — ambos importan de acá en vez de reimplementar la lógica.
