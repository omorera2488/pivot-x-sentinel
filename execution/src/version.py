"""Fuente unica de verdad de la version del bot -- sistema de versionado y
releases (ver CHANGELOG.md, docs/roadmap.md, scripts/build_release.py).

El VALOR vive en un solo lugar, /VERSION (raiz del repo) -- para no tener que
tocar la version a mano en varios archivos (api/app.py, packaging/
installer.iss, panel/, logs, scripts/build_release.py, todos leen de aca en
vez de tener su propio numero copiado).

SemVer basico (MAJOR.MINOR.PATCH, sin pre-release ni build metadata -- no
hace falta mas para este proyecto por ahora).
"""
from __future__ import annotations

import re

from .paths import app_root

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def is_valid_semver(value: str) -> bool:
    """MAJOR.MINOR.PATCH, enteros no negativos, sin ceros a la izquierda
    (salvo el 0 solo). Usado tanto para validar /VERSION en runtime como
    para el gate estricto de scripts/build_release.py (ese SI debe fallar
    fuerte ante un formato invalido -- get_version() de aca abajo, no)."""
    return bool(_SEMVER_RE.match(value.strip()))


def version_file_path():
    """Ubicacion de /VERSION -- raiz del repo en modo desarrollo, junto al
    resto del contenido empaquetado en modo congelado (ver
    packaging/pivot_x_sentinel.spec: datas incluye VERSION igual que panel/,
    y app_root() ya sabe resolver ese contenido en los dos modos)."""
    return app_root() / "VERSION"


def get_version() -> str:
    """Lee /VERSION. Si falta o tiene un formato invalido, NO tumba la app
    por esto -- devuelve un valor que deja claro que algo esta mal
    ("0.0.0-unknown"/"<lo que decia>-invalid") en vez de una excepcion.
    Mostrar una version rara en el titulo de la ventana es preferible a que
    el bot no pueda arrancar por un archivo de metadata roto. Quien SI debe
    fallar fuerte ante un VERSION invalido es el proceso de release
    (scripts/release_lib.py usa is_valid_semver() directo, sin este
    fallback)."""
    path = version_file_path()
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-unknown"
    if not raw:
        return "0.0.0-unknown"
    if not is_valid_semver(raw):
        return f"{raw}-invalid"
    return raw
