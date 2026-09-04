"""Resuelve la raiz de la app tanto en modo desarrollo (repo checkout) como
empaquetada (PyInstaller onedir, ver packaging/) -- unico lugar que sabe la
diferencia; todo lo demas (api/app.py, execution/src/score_store.py) le
pregunta a esto en vez de asumir `Path(__file__)..parents[N]`, que dentro del
.exe empaquetado apunta a una ruta ficticia dentro del bundle (los .py se
compilan a un archivo PYZ, no quedan como archivos sueltos en disco) y NO
coincide con la carpeta real de instalacion.

`sys._MEIPASS` es el que PyInstaller si pone correcto en ambos casos: en
onedir (el que usa este proyecto, ver packaging/pivot_x_sentinel.spec) es la
carpeta real donde vive el .exe -- persiste entre corridas, se puede escribir
ahi (data/scores) sin permisos de admin porque se instala bajo
%LOCALAPPDATA%. En onefile seria una carpeta temporal nueva cada corrida, por
eso packaging usa onedir y no onefile.
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]  # repo root en modo dev
