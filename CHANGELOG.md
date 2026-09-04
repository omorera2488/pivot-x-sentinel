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

