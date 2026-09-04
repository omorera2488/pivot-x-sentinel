# packaging

Empaquetado del bot en un instalador de Windows -- Fase 7 ([docs/roadmap.md](../docs/roadmap.md)). Un solo `.exe` de instalacion que deja todo listo (estrategia + API + panel + ventana de control) sin pedir Python, pip, ni pasos manuales en la PC destino.

## Piezas

- **[control_window.py](control_window.py)** -- punto de entrada del `.exe`. Ventana Tk minima (stdlib, sin dependencias nuevas) que arranca `api.app:app` (uvicorn) en background y expone *Abrir panel* / *Ver logs* / *Cerrar todo*. El bot en si (arrancar/parar la estrategia) se sigue controlando desde el panel web, como hoy -- esta ventana solo gestiona el proceso.
- **[pivot_x_sentinel.spec](pivot_x_sentinel.spec)** -- spec de [PyInstaller](https://pyinstaller.org/), build **onedir** (carpeta con el `.exe` + dependencias al lado, no un solo archivo autoextraible -- arranca mas rapido y los antivirus casi no lo marcan como falso positivo, muy comun con `--onefile`).
- **[installer.iss](installer.iss)** -- script de [Inno Setup 6](https://jrsoftware.org/isinfo.php) (gratuito). Empaqueta la carpeta que genera PyInstaller en un instalador `.exe` que instala bajo `%LOCALAPPDATA%\pivot-x-sentinel` (sin admin/UAC), deja accesos directos en el menu Inicio, y **abre el Leeme automaticamente al terminar** (`[Run] ... Flags: postinstall shellexec skipifsilent nowait`).
- **[README_INSTALADO.txt](README_INSTALADO.txt)** -- el Leeme que ve quien instala el bot: aviso de riesgo, requisito de tener MT5 ya instalado/logueado, como usar la ventana de control, como configurar y arrancar el bot desde el panel (symbol/perfil/magic/dry-run/parametros), donde quedan los datos, como desinstalar.
- **[ANTES_DE_INSTALAR.txt](ANTES_DE_INSTALAR.txt)** -- nota corta que Inno Setup muestra ANTES de instalar (pantalla "Information"), para que el requisito de MT5 se vea antes de gastar tiempo instalando, no despues.
- **[build.ps1](build.ps1)** -- orquesta todo el pipeline (pip install -> PyInstaller -> Inno Setup) en un solo comando.

## Por que hicieron falta 2 cambios fuera de `packaging/`

`api/app.py` (`_panel_dir`) y `execution/src/score_store.py` (`DATA_DIR`) resolvian su propia ubicacion con `Path(__file__).resolve().parents[N]`. Empaquetado con PyInstaller eso se rompe: los `.py` se compilan a un archivo PYZ, `__file__` de un modulo importado asi apunta a una ruta que no existe en disco. Ahora los dos usan **[execution/src/paths.py](../execution/src/paths.py):`app_root()`**, que devuelve `sys._MEIPASS` (la carpeta real del build onedir) cuando corre empaquetado, y el comportamiento de siempre (repo root) en modo desarrollo -- no cambia nada corriendo con `run.bat`.

## Build local

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Requiere [Inno Setup 6](https://jrsoftware.org/isdl.php) instalado para el ultimo paso (genera `ISCC.exe`); si no lo encuentra, el script deja igual el build de PyInstaller listo en `dist\pivot-x-sentinel\` y avisa como terminar a mano. Salida final: `packaging\dist_installer\pivot-x-sentinel-setup.exe`.

Verificado en esta maquina (2026-08-31): el build onedir arranca, sirve `/status` y `/panel/` correctamente, y "Cerrar todo" hace un shutdown limpio de uvicorn (log confirmando `Application shutdown complete.`) -- ver detalle de la corrida en la conversacion que armo este paquete. Falta correr el paso de Inno Setup end-to-end (no estaba instalado en esta maquina) y probar el instalador ya generado en una PC limpia con MT5 real.

## Actualizar version

Antes de generar un instalador para entregar, subir `#define MyAppVersion` en [installer.iss](installer.iss) -- Inno Setup lo usa para decidir si una instalacion existente se actualiza o se reinstala igual.

## Icono (opcional)

Si existe `packaging/icon.ico`, el spec lo usa para el `.exe` y el instalador hereda el mismo via `UninstallDisplayIcon`. Sin ese archivo, PyInstaller usa su icono default -- no bloquea el build.
