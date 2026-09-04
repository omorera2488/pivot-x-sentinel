"""Mecanica reutilizable del proceso de release -- separado de
build_release.py (el CLI) para poder testearlo sin invocar PyInstaller/Inno
Setup de verdad (ver scripts/test_release_lib.py).

Fuente unica de la version: execution/src/version.py (misma que usa la app
en runtime) -- este modulo NO reimplementa el parsing de SemVer, lo importa
de ahi.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import date as _date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

import sys  # noqa: E402
sys.path.insert(0, str(REPO_ROOT))
from execution.src.version import is_valid_semver  # noqa: E402


class ReleaseError(Exception):
    """Cualquier condicion que deba abortar el release de forma segura (ver
    build_release.py: se atrapa una sola vez en el CLI, se imprime el
    mensaje, exit code != 0, y -- importante -- nada a medio escribir queda
    tirado: todas las funciones de aca son de solo-lectura o escriben recien
    al final, cuando ya se validó todo lo anterior)."""


# ---- version -----------------------------------------------------------

def version_file() -> Path:
    return REPO_ROOT / "VERSION"


def read_version() -> str:
    """A diferencia de execution.src.version.get_version() (lenient, para
    no tumbar la app en runtime por esto), ACA un VERSION faltante o
    invalido tiene que frenar el release -- no tiene sentido generar un
    instalador con una version rota."""
    path = version_file()
    if not path.exists():
        raise ReleaseError(f"No existe {path} -- no se puede generar un release sin version.")
    raw = path.read_text(encoding="utf-8").strip()
    if not is_valid_semver(raw):
        raise ReleaseError(
            f"{path} contiene {raw!r}, que no es un SemVer valido (MAJOR.MINOR.PATCH, ej. 1.2.3)."
        )
    return raw


def write_version(version: str) -> None:
    if not is_valid_semver(version):
        raise ReleaseError(f"{version!r} no es un SemVer valido (MAJOR.MINOR.PATCH, ej. 1.2.3).")
    version_file().write_text(version + "\n", encoding="utf-8")


# ---- layout de releases/ -------------------------------------------------

def releases_root() -> Path:
    return REPO_ROOT / "releases"


def release_dir(version: str) -> Path:
    return releases_root() / f"v{version}"


def installer_name(version: str) -> str:
    return f"pivot-x-sentinel-setup-{version}.exe"


# ---- checksums ------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(dir_path: Path, *artifact_paths: Path) -> Path:
    """Formato compatible con `sha256sum -c` / `certutil -hashfile` --
    '<hash>  <nombre de archivo>', una linea por artefacto."""
    lines = [f"{sha256_of_file(p)}  {p.name}" for p in artifact_paths]
    out = dir_path / "checksums.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---- CHANGELOG.md ----------------------------------------------------------

_UNRELEASED_RE = re.compile(r"(?ms)^## \[Unreleased\]\s*\n(.*?)(?=^## \[|\Z)")


def changelog_file() -> Path:
    return REPO_ROOT / "CHANGELOG.md"


def cut_changelog_release(version: str, release_date: str | None = None) -> str | None:
    """'Corta' la seccion [Unreleased] de CHANGELOG.md en una seccion
    [version] - fecha, y deja [Unreleased] vacia arriba para lo proximo
    (convencion estandar de Keep a Changelog). Devuelve el cuerpo cortado
    (para reusarlo en RELEASE_NOTES.md) o None si no habia nada acumulado
    -- en ese caso CHANGELOG.md NO se toca (nada que cortar)."""
    path = changelog_file()
    if not path.exists():
        raise ReleaseError(f"No existe {path}.")
    text = path.read_text(encoding="utf-8")
    m = _UNRELEASED_RE.search(text)
    if not m:
        raise ReleaseError(f"{path} no tiene una seccion '## [Unreleased]'.")

    body = m.group(1).strip("\n")
    if not body.strip():
        return None

    release_date = release_date or _date.today().isoformat()
    new_block = f"## [Unreleased]\n\n## [{version}] - {release_date}\n\n{body}\n\n"
    new_text = text[: m.start()] + new_block + text[m.end():]
    path.write_text(new_text, encoding="utf-8")
    return body


# ---- RELEASE_NOTES.md -------------------------------------------------------

_PLACEHOLDER_BODY = """### Added

- (completar)

### Changed

- (completar)

### Fixed

- (completar)
"""


def render_release_notes(version: str, release_date: str, changelog_body: str | None,
                          previous_version: str | None) -> str:
    body = changelog_body.strip("\n") if changelog_body else _PLACEHOLDER_BODY.strip("\n")
    compat = (
        f"- Upgrade soportado desde v{previous_version}."
        if previous_version else
        "- Primer release — no hay una versión anterior de la que migrar."
    )
    return f"""# pivot-x-sentinel v{version}

Release date: {release_date}

{body}

### Compatibility

{compat}

### Known Issues

- No hay actualizaciones automáticas por internet — instalar el nuevo .exe a mano.
"""


# ---- git (solo lectura salvo tag_release(), que es opt-in) -----------------

def git_is_clean() -> bool:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                        capture_output=True, text=True)
    return r.returncode == 0 and not r.stdout.strip()


def tag_release(version: str) -> str:
    """Crea (NO pushea) un tag anotado local -- ver build_release.py --tag.
    Devuelve el mensaje del tag para loguearlo."""
    msg = f"pivot-x-sentinel v{version}"
    subprocess.run(["git", "tag", "-a", f"v{version}", "-m", msg], cwd=REPO_ROOT, check=True)
    return msg


# ---- tests -----------------------------------------------------------------

def discover_test_scripts() -> list[Path]:
    """Scripts de test standalone del proyecto (convencion existente: cada
    uno se corre como `python archivo.py`, sale 0 y compone. No hay
    pytest/conftest en este repo -- ver strategy/test_engine.py). Se
    descubren por glob en vez de una lista a mano para no tener que acordarse
    de sumar cada test nuevo aca."""
    patterns = ["strategy/test_*.py", "execution/src/test_*.py", "scripts/test_*.py", "api/test_*.py"]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(sorted(REPO_ROOT.glob(pattern)))
    return found


def run_test_script(path: Path, python: str) -> tuple[bool, str]:
    r = subprocess.run([python, str(path)], cwd=REPO_ROOT, capture_output=True, text=True)
    output = (r.stdout or "") + (r.stderr or "")
    return r.returncode == 0, output
