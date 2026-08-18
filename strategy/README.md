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

- `engine.py` — EMA, bloque HTF (corregido, sin el bug de autoarmado), armado/señal, ciclo de vida de la orden.
- `costs.py` — modelo de costos (spread/comisión/swap), parámetro opcional de `run_backtest` — correrlo con costos en cero da la estrategia "pelada".
- `profiles.py` — presets `1m`/`5m` (alias `M1`/`M5`) sobre el mismo `StrategyParams`.
- `test_engine.py` — checksum mecánico (`python strategy/test_engine.py`): valida las reglas de `spec-estrategia.md` sobre datos sintéticos, más la selección de perfil. No corre contra datos reales ni MT5 — para eso ver `/backtests`.

Lo usan `/backtests` (barrido/backtest) y, más adelante, `/execution` (Fase 4, vivo) — ambos importan de acá en vez de reimplementar la lógica.
