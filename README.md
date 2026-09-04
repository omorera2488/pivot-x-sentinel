# pivot-x-sentinel

Bot de trading algorítmico para Oro (XAUUSD) sobre MetaTrader 5, basado en la lógica del indicador Pine "EMA y Pivotes ZS — trade boxes" (cruces de EMA validados contra bloques de pivotes/soportes-resistencias en un timeframe superior), adaptado para ejecución en vivo.

Arquitectura de un solo proceso Python: estrategia, ejecución vía MT5, API local y panel web, todo en el mismo proceso — sin capas paralelas ni "shadow" processes.

## Aviso de riesgo

Este bot **opera en vivo por defecto** (manda órdenes reales) contra la cuenta que tengas conectada en tu terminal MT5, sea demo o real — esa elección se hace al loguear la cuenta, el código no la restringe ni la consulta. Trading algorítmico implica riesgo real de pérdida de capital. La estrategia implementada **no tiene un edge validado por backtest** todavía (ver [docs/spec-backtest.md §8](docs/spec-backtest.md)) — usarlo, con qué cuenta, con qué parámetros, y si operar en vivo o en modo simulado (`dry_run`) es responsabilidad de quien lo ejecuta, no de este repositorio ni de quien lo desarrolló.

## Estado del proyecto

El desarrollo avanza por fases, definidas y con criterios de aceptación explícitos, en **[docs/roadmap.md](docs/roadmap.md)**. Ese documento es la fuente de verdad del alcance y el orden de trabajo — cualquier cambio de plan se refleja ahí primero.

## Estructura

```
/strategy      → lógica pura de la estrategia (sin MT5, sin red, testeable de forma aislada)
/execution     → bridge con MetaTrader5 (conexión, envío/gestión de órdenes)
/api           → servidor local que expone estado del bot al panel
/panel         → frontend del dashboard
/packaging     → empaquetado del .exe (PyInstaller + Inno Setup) y ventana de control
/scripts       → herramientas de desarrollo y el proceso de release (build_release.py)
/backtests     → motor y resultados de backtesting específico de Oro
/docs          → specs, decisiones, roadmap
/releases      → artefactos de cada release (solo en disco local, no versionado en git)
```

## Versión y releases

La versión instalada es la única fuente de verdad en **[VERSION](VERSION)** (SemVer `MAJOR.MINOR.PATCH`, ver [execution/src/version.py](execution/src/version.py)) — expuesta por `GET /version`, en el panel, en el título de la ventana de control, y en los logs. El historial de cambios está en **[CHANGELOG.md](CHANGELOG.md)**; cada release trae su propio `RELEASE_NOTES.md` dentro de `releases/vX.Y.Z/` (generado por `python scripts/build_release.py`, ver [packaging/README.md](packaging/README.md)).
