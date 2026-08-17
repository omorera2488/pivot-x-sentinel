# pivot-x-sentinel

Bot de trading algorítmico para Oro (XAUUSD) sobre MetaTrader 5, basado en la lógica del indicador Pine "EMA y Pivotes ZS — trade boxes" (cruces de EMA validados contra bloques de pivotes/soportes-resistencias en un timeframe superior), adaptado para ejecución en vivo.

Arquitectura de un solo proceso Python: estrategia, ejecución vía MT5, API local y panel web, todo en el mismo proceso — sin capas paralelas ni "shadow" processes.

## Estado del proyecto

El desarrollo avanza por fases, definidas y con criterios de aceptación explícitos, en **[docs/roadmap.md](docs/roadmap.md)**. Ese documento es la fuente de verdad del alcance y el orden de trabajo — cualquier cambio de plan se refleja ahí primero.

## Estructura

```
/strategy      → lógica pura de la estrategia (sin MT5, sin red, testeable de forma aislada)
/execution     → bridge con MetaTrader5 (conexión, envío/gestión de órdenes)
/api           → servidor local que expone estado del bot al panel
/panel         → frontend del dashboard
/packaging     → script de empaquetado del .exe y ventana de control
/backtests     → motor y resultados de backtesting específico de Oro
/docs          → specs, decisiones, roadmap
```
