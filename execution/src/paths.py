"""Resuelve la raiz de la app tanto en modo desarrollo (repo checkout) como
empaquetada (PyInstaller onedir, ver packaging/) -- unico lugar que sabe la
diferencia; todo lo demas (api/app.py, execution/src/score_store.py) le
pregunta a esto en vez de asumir `Path(__file__)..parents[N]`, que dentro del
.exe empaquetado apunta a una ruta ficticia dentro del bundle (los .py se
compilan a un archivo PYZ, no quedan como archivos sueltos en disco) y NO
coincide con la carpeta real de instalacion.

Dos raices DISTINTAS a proposito (agregado junto con el soporte de upgrades
del instalador, ver packaging/installer.iss):

  - app_root()       -> contenido de la APLICACION (panel/, VERSION):
                         reemplazable entero en cada upgrade.
  - user_data_root()  -> datos PERSISTENTES del usuario (scores, ver
                         execution/src/score_store.py): tiene que sobrevivir
                         un upgrade.

Verificado empiricamente (PyInstaller 6.x): en un build onedir, `sys.
_MEIPASS` NO es la carpeta que contiene el .exe -- es una subcarpeta
`_internal` al lado de el. packaging/installer.iss borra `_internal` entero
antes de copiar los archivos de una version nueva (para no dejar
dependencias huerfanas de la version vieja, ver su [Code]:CurStepChanged) --
si user_data_root() devolviera lo mismo que app_root() (_internal), un
upgrade se llevaria puesto el historial de scores del usuario. Por eso
user_data_root() usa `sys.executable` (la carpeta del .exe en si, HERMANA de
_internal, que el instalador nunca toca en un upgrade) en vez de _MEIPASS.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Contenido de la app -- se reemplaza entero en cada upgrade. NO usar
    para nada que el usuario genere en uso (ver user_data_root())."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]  -- ver nota de modulo: esto es {app}\_internal, no {app}
    return Path(__file__).resolve().parents[2]  # repo root en modo dev


def user_data_root() -> Path:
    """Datos persistentes del usuario -- sobrevive upgrades (packaging/
    installer.iss solo borra _internal, nunca esto). En dev es el mismo repo
    root que app_root() (no hay upgrades que atender en desarrollo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent  # {app}, hermana de _internal
    return Path(__file__).resolve().parents[2]
