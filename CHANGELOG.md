# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) —
versionado según [SemVer](https://semver.org/lang/es/) (`MAJOR.MINOR.PATCH`).

La sección `[Unreleased]` acumula cambios a medida que se hacen commits;
`python scripts/build_release.py` la "corta" en una sección `[X.Y.Z] - fecha`
al generar un release (ver `scripts/release_lib.py`) y deja `[Unreleased]`
vacía otra vez para lo próximo. No confundir con `RELEASE_NOTES.md`: este
archivo es el historial acumulado del PROYECTO; `RELEASE_NOTES.md` (dentro de
cada `releases/vX.Y.Z/`) describe específicamente ESE artefacto instalable.

## [Unreleased]

### Fixed

- **BOT-024** — `strategy/scoring.py`: Divergencia RSI resolvía divergencias
  bullish/bearish simultáneas con una prioridad accidental a favor de
  bullish (efecto secundario del orden del código: se evaluaba primero y
  hacía `return` sin llegar a considerar una bearish vigente, aunque esta
  fuera más reciente). Detectado en `reports/AUDIT-RSI-DIVERGENCE.md`
  (hallazgo #1). Ahora bullish y bearish se detectan de forma independiente
  (`_bullish_candidate()`/`_bearish_candidate()`) y se resuelven
  explícitamente por `confirmation_bar` más reciente
  (`resolve_divergence()`) — nunca por `pivot_bar` ni por la dirección del
  trade. Empate exacto de `confirmation_bar` → nuevo estado `CONFLICT`
  (`score=0`, distinguible de `NONE`/"sin divergencia vigente"). RSI
  Wilder(14), pivotes 5/5, `DIVERGENCE_RANGE_MIN/MAX`, `DIVERGENCE_FRESH_BARS`
  y `close[pivot_bar]` no cambiaron. `divergence_score()` mantiene su
  contrato `(score, reason)` sin cambios (wrapper compatible); la
  divergencia solo se REGISTRA (no decide entradas), así que este fix no
  cambia qué opera el bot, solo lo que queda calificado/registrado.

### Added

- **BOT-024** — `EntryScore` (`strategy/scoring.py`) gana trazabilidad de
  Divergencia RSI: `divergencia_resolved_state`, `divergencia_resolution`,
  y por lado (`bullish`/`bearish`) `_active`/`_pivot_bar`/
  `_confirmation_bar`/`_age`. Permite reconstruir después, desde
  `score_store`, qué candidato(s) y qué resolución originaron
  `divergencia_score`/`_reason` de una operación ya cerrada, sin recorrer de
  nuevo los datos de mercado. Campos aditivos — `score_store.py`, `api/
  app.py` y `panel/app.js` leen por nombre y toleran campos nuevos/ausentes,
  sin cambios necesarios en esos consumidores.
- **BOT-024** — `strategy/test_scoring.py`: pruebas I–P para solo-bullish,
  solo-bearish, ninguna, ambas (bullish más reciente / bearish más
  reciente — este último reproduce y corrige el bug de la auditoría),
  `CONFLICT`, vigencia (edad 0..10 activa, 11 expira) y causalidad
  (`pivot_bar`/`confirmation_bar`) sin cambios. `scripts/
  audit_rsi_divergence.py` actualizado (secciones 9 y 11) para validar el
  comportamiento nuevo; re-ejecutado completo: 0 fallas.

## [1.1.1] - 2026-09-15

### Fixed

- **BOT-032** — `panel/config.html`: el monto de "Máxima pérdida diaria
  (USD)" quedaba como una tarjeta independiente de "Activar máxima pérdida
  diaria" en vez de vivir dentro de la misma. Ahora el label+input del monto
  viven DENTRO de la tarjeta del checkbox, y se ocultan por completo (sin
  reservar espacio) mientras el checkbox esté desactivado — no solo
  deshabilitados como antes. Cambio puramente de presentación: no se tocó
  la persistencia ni la lógica de backend de BOT-032.

## [1.1.0] - 2026-09-15

### Added

- **BOT-032** — Kill switch / máxima pérdida diaria: protección configurable
  del motor de ejecución (`execution/src/bot.py`) que bloquea la colocación
  de **nuevas** operaciones al alcanzar la pérdida NETA realizada del día
  operativo (`daily_max_loss_usd`, activable desde Configuración en el
  panel). Nunca detiene el `run()` del bot ni toca posiciones abiertas — SL/
  TP, `orden_viva`, `caduca` y `max_bars_trade` siguen funcionando con
  normalidad. Día operativo timezone-aware (`execution/src/operating_day.py`,
  IANA `America/Costa_Rica` vía `zoneinfo`, nunca "UTC-6" hardcodeado) —
  fuente de verdad del backend, expuesta en `GET /status` y consumida por
  `panel/calendar.html` para que el calendario agrupe por el mismo día que
  usa el kill switch (antes agrupaba por hora local del navegador). P&L
  recalculado siempre desde `mt5.history_deals_get()` (nunca un contador en
  memoria), reusando la reconciliación segura de `GET /history`
  (`mt5_utils.filter_own_deals()`, extraída de `api/app.py::history()`) para
  no perder deals de cierre manual sin magic propio. Fail-safe: si MT5 no
  devuelve datos suficientes, se trata como disparado, nunca se asume P&L=$0.
  Al dispararse, `POST /start` exige una confirmación explícita
  (`acknowledge_daily_loss_override`) que arranca el bot y activa un
  override persistente (`execution/src/kill_switch_store.py`,
  `user_data_root()`, sobrevive reinicios/upgrades) válido por el resto del
  día operativo — un día operativo nuevo lo invalida automáticamente, sin
  timers. Ver `docs/spec-live-execution.md` §12, `docs/spec-api.md` §6 y
  `docs/reports/BOT-032_kill_switch.md` para el detalle completo.

### Fixed

- **BOT-043** — corregido el modelo de costos del motor de backtest
  (`strategy/costs.py`, `strategy/engine.py`): el swap se restaba con el
  signo ya invertido (se acreditaba en vez de cobrarse) y la conversión de
  precio a USD usaba `contract_size` en vez de `tick_value/tick_size`,
  subvaluando el PnL/riesgo real en precio por 100x en símbolos donde esos
  dos no coinciden (confirmado contra `mt5.order_calc_profit()`). Nuevo
  `BrokerCosts.price_to_usd()` como único punto de conversión, nuevo campo
  `BrokerCosts.tick_size`, y 9 tests nuevos en `strategy/test_costs.py` que
  antes no existían (el motor no tenía ninguna cobertura con swap≠0). **No
  afecta la ejecución en vivo** — `execution/src/bot.py` no importa
  `strategy/costs.py`, este código corre solo en `/backtests`. Invalida los
  resultados ya publicados de BOT-008 para cualquier combinación con trades
  mantenidos overnight (ver `BACKLOG.md`).

## [1.0.0] - 2026-09-04

Primer release formal — instalador distribuible, sistema de versionado, y
validación real de MT5 antes de operar.

### Added

- Instalador de Windows (`packaging/installer.iss`, Inno Setup 6 sobre un
  build onedir de PyInstaller): instala sin admin bajo `%LOCALAPPDATA%`,
  deja accesos directos en el menú Inicio, y abre el Leeme automáticamente
  al terminar.
- Ventana de control mínima (`packaging/control_window.py`): Abrir panel /
  Ver logs / Cerrar todo, con shutdown limpio del servidor.
- Soporte de **upgrade in-place** en el instalador: detecta una instalación
  previa por `AppId`, reemplaza el contenido de la app, bloquea downgrades
  accidentales (compara versiones vía registro de Windows) y avisa si ya
  está instalada la misma versión.
- Sistema formal de versionado SemVer: `/VERSION` como fuente única de
  verdad (`execution/src/version.py`), expuesta por `GET /version`, en el
  título de la ventana de control, en el panel, y en el log de arranque.
- `CHANGELOG.md` (este archivo) y plantilla de `RELEASE_NOTES.md` por
  release.
- Proceso de release reproducible: `python scripts/build_release.py`
  (`scripts/release_lib.py`) — valida SemVer, corre los tests, construye el
  instalador, genera `releases/vX.Y.Z/` con el `.exe`, `RELEASE_NOTES.md` y
  `checksums.txt` (SHA256), sin sobrescribir un release ya publicado.
- Validación real de MetaTrader 5 antes de operar
  (`execution/src/mt5_validation.py`): distingue terminal no disponible,
  terminal sin conexión al bróker, "Algo Trading" apagado, sin cuenta
  logueada, cuenta sin permiso de trading, y cuenta sin Expert Advisors
  habilitado — usando los campos reales de `terminal_info()`/
  `account_info()`, no un `try/except` genérico.

### Changed

- `execution/src/score_store.py` guarda los scores en una carpeta que
  sobrevive upgrades del instalador (`user_data_root()`, hermana de la
  carpeta reemplazable `_internal`) — antes quedaba adentro de esa misma
  carpeta reemplazable.
- `api/app.py` — `POST /start` ahora devuelve 503 con un mensaje claro si
  MT5 no está listo, en vez de un 500 genérico con traceback.

### Fixed

- `LiveExecutionBot.connect()` ya no explota con `AttributeError` cuando
  `mt5.account_info()` devuelve `None` (MT5 abierto sin ninguna cuenta
  logueada) — tanto al arrancar el bot como en cada intento de reconexión
  automática del loop en vivo.

### Technical

- `execution/src/paths.py`: separa `app_root()` (contenido reemplazable de
  la app) de `user_data_root()` (datos persistentes del usuario) — hallazgo
  al implementar upgrades: en un build onedir de PyInstaller 6,
  `sys._MEIPASS` apunta a `_internal`, NO a la carpeta del `.exe`.
- Tests agregados: `execution/src/test_mt5_validation.py` (9 casos con un MT5
  falso), `api/test_start_mt5_validation.py` (integración: `/start` no arranca
  el motor de trading si MT5 no está listo), y `scripts/test_release_lib.py`
  (SemVer, layout de `releases/`, checksums, corte de changelog) — ninguno
  depende de una terminal MT5 real.

