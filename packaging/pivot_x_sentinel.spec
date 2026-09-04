# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller -- Fase 7 (docs/roadmap.md). Genera un build ONEDIR
(carpeta con el .exe + dependencias al lado, NO un solo .exe autoextraible):
arranca mas rapido y los antivirus casi no lo marcan como falso positivo,
a diferencia de --onefile (ver discusion en packaging/README.md).

Uso (normalmente via packaging/build.ps1, que hace todo el pipeline):
    pyinstaller packaging/pivot_x_sentinel.spec --noconfirm --clean

Salida: dist/pivot-x-sentinel/pivot-x-sentinel.exe (+ carpeta _internal con
todo lo demas). packaging/installer.iss empaqueta ESA carpeta entera.
"""
from pathlib import Path

block_cipher = None

REPO_ROOT = Path(SPECPATH).resolve().parent

# Modulos que uvicorn[standard] resuelve en runtime via importlib segun que
# haya instalado (auto-deteccion de la implementacion mas rapida disponible:
# httptools vs h11, etc.) -- el analisis estatico de PyInstaller no los seria
# sin esto y el .exe explota al arrancar el servidor con "ModuleNotFoundError".
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "email.mime.multipart",  # dependencia transitiva de starlette/fastapi (formularios)
]

a = Analysis(
    ["control_window.py"],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        # Panel estatico (html/css/js planos, sin build step -- ver api/app.py
        # _panel_dir): NO son .py, PyInstaller no los sigue solo por import
        # analysis, hay que copiarlos a mano.
        (str(REPO_ROOT / "panel"), "panel"),
        # Fuente unica de la version (execution/src/version.py:get_version())
        # -- mismo motivo, un archivo de texto plano no lo trae el analisis
        # de imports.
        (str(REPO_ROOT / "VERSION"), "."),
    ],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # nada de esto hace falta para correr el bot en vivo -- afuera para
        # que el instalador no pese de mas.
        "matplotlib", "pandas", "scipy", "numpy.testing", "pytest",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pivot-x-sentinel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX comprime el .exe pero dispara MUCHOS mas falsos positivos de antivirus -- no vale la pena por el espacio que ahorra
    console=False,  # ventana Tk propia (control_window.py) -- sin consola aparte; stdout/stderr van a un log en disco (ver _install_log_redirection)
    icon=str(REPO_ROOT / "packaging" / "icon.ico") if (REPO_ROOT / "packaging" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="pivot-x-sentinel",
)
