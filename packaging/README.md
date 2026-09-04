# packaging

Empaquetado del bot en un instalador de Windows -- Fase 7 ([docs/roadmap.md](../docs/roadmap.md)). Un solo `.exe` de instalacion que deja todo listo (estrategia + API + panel + ventana de control) sin pedir Python, pip, ni pasos manuales en la PC destino, con soporte de **upgrade in-place** sobre una instalacion existente.

Para generar un release completo (versionado, tests, CHANGELOG, checksums) ver **[scripts/build_release.py](../scripts/build_release.py)** y [CHANGELOG.md](../CHANGELOG.md) -- este documento es sobre las piezas de empaquetado en si, no sobre el proceso de release.

## Piezas

- **[control_window.py](control_window.py)** -- punto de entrada del `.exe`. Ventana Tk minima (stdlib, sin dependencias nuevas) que arranca `api.app:app` (uvicorn) en background y expone *Abrir panel* / *Ver logs* / *Cerrar todo*. El titulo muestra la version instalada (`execution/src/version.py`). El bot en si (arrancar/parar la estrategia) se sigue controlando desde el panel web, como hoy -- esta ventana solo gestiona el proceso.
- **[pivot_x_sentinel.spec](pivot_x_sentinel.spec)** -- spec de [PyInstaller](https://pyinstaller.org/), build **onedir** (carpeta con el `.exe` + una subcarpeta `_internal` con todo lo demas, no un solo archivo autoextraible -- arranca mas rapido y los antivirus casi no lo marcan como falso positivo, muy comun con `--onefile`).
- **[installer.iss](installer.iss)** -- script de [Inno Setup 6](https://jrsoftware.org/isinfo.php) (gratuito). Empaqueta la carpeta que genera PyInstaller en un instalador `.exe` que instala bajo `%LOCALAPPDATA%\pivot-x-sentinel` (sin admin/UAC), deja accesos directos en el menu Inicio, **abre el Leeme automaticamente al terminar**, y maneja upgrades (ver mas abajo).
- **[README_INSTALADO.txt](README_INSTALADO.txt)** -- el Leeme que ve quien instala el bot: aviso de riesgo, requisito de tener MT5 ya instalado/logueado, como usar la ventana de control, como configurar y arrancar el bot desde el panel, donde quedan los datos, como actualizar, como desinstalar.
- **[ANTES_DE_INSTALAR.txt](ANTES_DE_INSTALAR.txt)** -- nota corta que Inno Setup muestra ANTES de instalar (pantalla "Information"), para que el requisito de MT5 se vea antes de gastar tiempo instalando, no despues.
- **[build.ps1](build.ps1)** -- orquesta el pipeline de build (pip install -> PyInstaller -> Inno Setup) en un solo comando, SIN los pasos de release (tests/CHANGELOG/checksums/releases/) -- para iterar rapido en desarrollo. Para un release de verdad usar `scripts/build_release.py`, que hace lo mismo mas todo lo demas.

## Upgrade in-place (Inno Setup)

`AppId` fijo + `DefaultDirName` fijo le bastan a Inno Setup, de forma nativa, para reconocer una instalacion existente y actualizarla en el mismo lugar en vez de duplicarla -- no hay un segundo sistema de updates. Lo que agrega este proyecto encima (`installer.iss` `[Code]`):

- **Compara versiones** (via el registro de Windows, `DisplayVersion` de la instalacion existente) contra `{#MyAppVersion}` -- avisa y pide confirmacion si instalarías una version MAS VIEJA (downgrade accidental), e informa si es la MISMA version (reinstala/repara).
- **Limpia `_internal` antes de copiar** (`CurStepChanged`, `ssInstall`): PyInstaller onedir mete TODO el contenido reemplazable de la app ahi -- sin este paso, un modulo que existia en la version vieja y ya no existe en la nueva quedaria huerfano, mezclado con los archivos nuevos.

**Importante -- por que `_internal` se puede borrar entero sin perder nada del usuario:** `execution/src/paths.py` separa dos raices a proposito:

- `app_root()` -- contenido de la app (panel/, VERSION). En build congelado es `sys._MEIPASS`, que en PyInstaller 6 onedir **es la carpeta `_internal`, NO la carpeta del `.exe`** (verificado empiricamente, no esta documentado de forma obvia). Se reemplaza entero en cada upgrade.
- `user_data_root()` -- datos persistentes (`execution/src/score_store.py`). En build congelado es `Path(sys.executable).parent` -- la carpeta del `.exe`, HERMANA de `_internal`, que el upgrade nunca toca. Los logs (`control_window.py`) ya vivian ahi por separado.

Antes de este split, `score_store.DATA_DIR` colgaba de `app_root()` -- es decir, quedaba DENTRO de `_internal`. Implementar el borrado de `_internal` sin arreglar esto primero se hubiera llevado puesto el historial de scores del usuario en cada upgrade. Verificado con una instalacion + upgrade de prueba: los datos sobreviven, `_internal` se reemplaza entero.

## Build local (solo el instalador, sin proceso de release)

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Requiere [Inno Setup 6](https://jrsoftware.org/isdl.php) instalado para el ultimo paso (genera `ISCC.exe`); si no lo encuentra, el script deja igual el build de PyInstaller listo en `dist\pivot-x-sentinel\` y avisa como terminar a mano. Salida: `packaging\dist_installer\pivot-x-sentinel-setup-<version>.exe` (la version sale de `/VERSION`, no hay que pasarla).

Para generar un release real (con tests, checksums, CHANGELOG, `releases/vX.Y.Z/`) usar en cambio `python scripts/build_release.py` desde la raiz del repo -- ver [CHANGELOG.md](../CHANGELOG.md).

Verificado en esta maquina: instalacion limpia, arranque, `/status`/`/panel/`/`/version`, "Cerrar todo" (shutdown limpio de uvicorn), upgrade preservando datos de usuario, y desinstalacion -- todos probados de punta a punta. Pendiente: probar en una PC realmente distinta (sin Python instalado) con una terminal MT5 real conectada -- este dev machine no tiene una terminal MT5 propia para probar esa parte end-to-end (si tiene, en cambio, otro proceso corriendo el bot en modo desarrollo contra una cuenta real -- ver nota de seguridad mas abajo).

**Nota de seguridad al probar en esta maquina en particular:** si haces pruebas de instalador/API mientras el bot de desarrollo (`run.bat`) esta corriendo en vivo contra una cuenta real, el `.exe` de prueba simplemente va a fallar en bindear el puerto 8000 (ya ocupado) -- no interfiere con el proceso en vivo, pero conviene chequear `Get-NetTCPConnection -LocalPort 8000` antes de asumir que un test esta hablando con TU proceso.

## Icono (opcional)

Si existe `packaging/icon.ico`, el spec lo usa para el `.exe` y el instalador hereda el mismo via `UninstallDisplayIcon`. Sin ese archivo, PyInstaller usa su icono default -- no bloquea el build.
