"""Regresion de scripts/release_lib.py -- SemVer, layout de releases/,
checksums, y el corte de CHANGELOG.md ([Unreleased] -> [version] - fecha).

Todo corre contra directorios temporales (tempfile) -- nunca toca el
VERSION/CHANGELOG.md/releases/ reales del repo (se logra reapuntando
release_lib.REPO_ROOT a un directorio temporal antes de cada caso, y
restaurandolo al original al final).

Fuera de alcance (no es apropiado para unit testing, ver pedido original
#18 -- "documentar que debe validarse mediante smoke test/manual"):
  - git_is_clean() contra un repo git real con commits/cambios de verdad
    (se prueba solo el caso trivial: directorio que no es un repo git).
  - tag_release() -- crea un tag de git real, no se ejecuta en el test
    (probarlo manualmente: `python scripts/build_release.py --tag` en un
    repo de prueba, y confirmar con `git tag -l`).
  - Todo el pipeline de build (PyInstaller + ISCC) -- son herramientas
    externas pesadas, cubierto por packaging/build.ps1 + smoke test manual
    (instalar/actualizar/desinstalar), no por este archivo.

Uso:
    python scripts/test_release_lib.py
"""
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_lib
from release_lib import ReleaseError

_REAL_REPO_ROOT = release_lib.REPO_ROOT  # restaurado al final -- ver main()
_tmp_dirs: list[Path] = []


def fresh_tmp_repo() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="pxs_release_test_"))
    _tmp_dirs.append(tmp)
    release_lib.REPO_ROOT = tmp
    return tmp


def test_semver_validation():
    from execution.src.version import is_valid_semver
    for good in ("1.0.0", "0.0.1", "12.34.56", "0.0.0"):
        assert is_valid_semver(good), f"deberia ser valido: {good!r}"
    for bad in ("1.0", "1.0.0.0", "v1.0.0", "1.0.0-beta", "01.0.0", "", "1.0.x", "1..0"):
        assert not is_valid_semver(bad), f"deberia ser invalido: {bad!r}"


def test_read_write_version():
    fresh_tmp_repo()

    # A. sin VERSION todavia -> error claro, no un FileNotFoundError crudo
    try:
        release_lib.read_version()
        assert False, "deberia haber fallado sin VERSION"
    except ReleaseError:
        pass

    # B. write_version con formato invalido -> error, NO escribe el archivo
    try:
        release_lib.write_version("no-es-semver")
        assert False, "deberia haber rechazado un SemVer invalido"
    except ReleaseError:
        pass
    assert not release_lib.version_file().exists(), "write_version invalido no deberia crear el archivo"

    # C. round-trip normal
    release_lib.write_version("1.2.3")
    assert release_lib.read_version() == "1.2.3"

    # D. contenido invalido escrito a mano en VERSION -> read_version lo rechaza
    release_lib.version_file().write_text("no-es-semver\n", encoding="utf-8")
    try:
        release_lib.read_version()
        assert False, "deberia haber rechazado contenido invalido en VERSION"
    except ReleaseError:
        pass


def test_release_dir_layout():
    fresh_tmp_repo()
    d = release_lib.release_dir("1.4.0")
    assert d == release_lib.releases_root() / "v1.4.0"
    assert not d.exists()
    d.mkdir(parents=True)
    assert release_lib.release_dir("1.4.0").exists()  # lo que build_release.py chequea antes de generar nada


def test_checksums():
    tmp = fresh_tmp_repo()
    f1 = tmp / "a.txt"
    f2 = tmp / "b.txt"
    f1.write_bytes(b"contenido de prueba A")
    f2.write_bytes(b"otro contenido, mas largo, para variar el tamano del archivo B")

    expected1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    expected2 = hashlib.sha256(f2.read_bytes()).hexdigest()
    assert release_lib.sha256_of_file(f1) == expected1
    assert release_lib.sha256_of_file(f2) == expected2

    out = release_lib.write_checksums(tmp, f1, f2)
    assert out.name == "checksums.txt"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines == [f"{expected1}  a.txt", f"{expected2}  b.txt"]


_CHANGELOG_TEMPLATE = """# Changelog

## [Unreleased]

### Added

- Cosa nueva A.
- Cosa nueva B.

## [0.9.0] - 2026-01-01

### Added

- Version vieja, no debe tocarse.
"""


def test_cut_changelog_with_content():
    tmp = fresh_tmp_repo()
    release_lib.changelog_file().write_text(_CHANGELOG_TEMPLATE, encoding="utf-8")

    body = release_lib.cut_changelog_release("1.0.0", release_date="2026-06-01")
    assert body is not None
    assert "Cosa nueva A." in body
    assert "Cosa nueva B." in body

    new_text = release_lib.changelog_file().read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [1.0.0] - 2026-06-01" in new_text
    assert "Cosa nueva A." in new_text
    assert "## [0.9.0] - 2026-01-01" in new_text  # la seccion vieja no se toca
    assert "Version vieja, no debe tocarse." in new_text

    # cortar nada dos veces seguidas: la segunda vez [Unreleased] ya esta vacia
    body2 = release_lib.cut_changelog_release("1.0.1", release_date="2026-06-02")
    assert body2 is None


def test_cut_changelog_empty_unreleased():
    tmp = fresh_tmp_repo()
    release_lib.changelog_file().write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.9.0] - 2026-01-01\n\nvieja\n",
        encoding="utf-8",
    )
    body = release_lib.cut_changelog_release("1.0.0")
    assert body is None
    # no debe haber modificado el archivo si no habia nada que cortar
    text = release_lib.changelog_file().read_text(encoding="utf-8")
    assert "## [1.0.0]" not in text


def test_cut_changelog_missing_section():
    fresh_tmp_repo()
    release_lib.changelog_file().write_text("# Changelog\n\nsin seccion Unreleased\n", encoding="utf-8")
    try:
        release_lib.cut_changelog_release("1.0.0")
        assert False, "deberia haber fallado sin seccion [Unreleased]"
    except ReleaseError:
        pass


def test_cut_changelog_unreleased_is_last_section():
    fresh_tmp_repo()
    release_lib.changelog_file().write_text(
        "# Changelog\n\n## [Unreleased]\n\n- Unica cosa.\n",
        encoding="utf-8",
    )
    body = release_lib.cut_changelog_release("2.0.0", release_date="2026-07-01")
    assert body is not None and "Unica cosa." in body
    text = release_lib.changelog_file().read_text(encoding="utf-8")
    assert "## [2.0.0] - 2026-07-01" in text


def test_render_release_notes():
    notes_first = release_lib.render_release_notes(
        "1.0.0", "2026-06-01", changelog_body="### Added\n\n- Algo nuevo.\n", previous_version=None,
    )
    assert "v1.0.0" in notes_first
    assert "2026-06-01" in notes_first
    assert "Algo nuevo." in notes_first
    assert "Primer release" in notes_first

    notes_upgrade = release_lib.render_release_notes(
        "1.1.0", "2026-07-01", changelog_body=None, previous_version="1.0.0",
    )
    assert "Upgrade soportado desde v1.0.0." in notes_upgrade
    assert "(completar)" in notes_upgrade  # sin changelog_body -> plantilla


def test_git_is_clean_non_repo():
    tmp = fresh_tmp_repo()
    # tmp no es un repo git -- `git status` falla, no debe crashear ni dar falso "limpio"
    assert release_lib.git_is_clean() is False


def test_discover_test_scripts_finds_self():
    release_lib.REPO_ROOT = _REAL_REPO_ROOT  # este chequeo SI es contra el repo real
    found = release_lib.discover_test_scripts()
    names = {p.relative_to(_REAL_REPO_ROOT).as_posix() for p in found}
    for expected in ("strategy/test_engine.py", "execution/src/test_mt5_validation.py", "scripts/test_release_lib.py"):
        assert expected in names, f"discover_test_scripts() no encontro {expected}"


def main():
    try:
        test_semver_validation()
        test_read_write_version()
        test_release_dir_layout()
        test_checksums()
        test_cut_changelog_with_content()
        test_cut_changelog_empty_unreleased()
        test_cut_changelog_missing_section()
        test_cut_changelog_unreleased_is_last_section()
        test_render_release_notes()
        test_git_is_clean_non_repo()
        test_discover_test_scripts_finds_self()
    finally:
        release_lib.REPO_ROOT = _REAL_REPO_ROOT
        for d in _tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    print("TODO OK")


if __name__ == "__main__":
    main()
