"""Proceso de release reproducible -- Fase 7.1 (versionado y releases, ver
CHANGELOG.md, scripts/release_lib.py).

Uso:
    python scripts/build_release.py            # usa la version de /VERSION tal cual
    python scripts/build_release.py 1.1.0       # escribe 1.1.0 en /VERSION primero, despues sigue igual
    python scripts/build_release.py --strict    # aborta si el working tree de git tiene cambios sin commitear
    python scripts/build_release.py --tag       # si todo sale bien, crea (LOCAL, sin push) el tag anotado v<version>

Que hace, en orden (aborta en el primer problema, sin dejar nada a medio
escribir -- ver scripts/release_lib.py:ReleaseError):
    1. Lee (o escribe, si se paso un argumento) /VERSION.
    2. Valida que sea un SemVer valido.
    3. Valida que no exista ya releases/v<version>/.
    4. (opcional) valida que el working tree de git este limpio (--strict).
    5. Corre todos los tests standalone del repo (strategy/test_*.py,
       execution/src/test_*.py, scripts/test_*.py) -- si alguno falla, listo, no sigue.
    6. Construye el .exe con PyInstaller (packaging/pivot_x_sentinel.spec).
    7. Compila el instalador con Inno Setup (packaging/installer.iss) --
       el .iss lee la version de /VERSION solo, no hace falta pasarsela.
    8. Crea releases/v<version>/, copia el instalador ahi.
    9. "Corta" CHANGELOG.md ([Unreleased] -> [version] - fecha de hoy) y usa
       ese contenido para generar RELEASE_NOTES.md.
    10. Genera checksums.txt (SHA256) del instalador.
    11. Imprime el comando exacto de `git tag` (o lo corre, con --tag).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_lib
from release_lib import REPO_ROOT, ReleaseError


def _find_python() -> str:
    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


def _find_iscc() -> str | None:
    """Misma busqueda que packaging/build.ps1 -- PATH primero, despues las
    dos ubicaciones tipicas de instalacion (por-usuario y machine-wide)."""
    on_path = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if on_path:
        return on_path
    import os
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _previous_version(current: str) -> str | None:
    """El release publicado mas reciente ANTES de este -- para el
    "Compatibility: Upgrade soportado desde vX" de RELEASE_NOTES.md. Se
    infiere de que carpetas ya existen en releases/, no de CHANGELOG.md (ese
    ya se corto para la version actual antes de llegar aca)."""
    existing = sorted(
        (p.name[1:] for p in release_lib.releases_root().glob("v*") if p.is_dir() and p.name != f"v{current}"),
        key=lambda v: tuple(int(x) for x in v.split(".")) if v.replace(".", "").isdigit() else (0, 0, 0),
    )
    return existing[-1] if existing else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", nargs="?", help="Version a liberar (ej. 1.1.0) -- si se omite, usa /VERSION tal cual.")
    ap.add_argument("--strict", action="store_true", help="Abortar si el working tree de git tiene cambios sin commitear.")
    ap.add_argument("--tag", action="store_true", help="Crear (local, sin push) el tag anotado v<version> si todo sale bien.")
    args = ap.parse_args()

    try:
        if args.version:
            release_lib.write_version(args.version)
        version = release_lib.read_version()
        print(f"== Release pivot-x-sentinel v{version} ==")

        rdir = release_lib.release_dir(version)
        if rdir.exists():
            raise ReleaseError(
                f"Ya existe {rdir} -- una version publicada no se reemplaza. "
                "Si hay que corregir algo, subi el PATCH (ej. escribi la version siguiente en /VERSION)."
            )

        if not release_lib.git_is_clean():
            msg = "El working tree de git tiene cambios sin commitear."
            if args.strict:
                raise ReleaseError(msg + " (--strict pedido, abortando)")
            print(f"AVISO: {msg} Este release no va a corresponder exactamente a un commit. Segui con --strict para que esto frene.")

        print("-- corriendo tests --")
        python = _find_python()
        scripts = release_lib.discover_test_scripts()
        failed = []
        for script in scripts:
            ok, output = release_lib.run_test_script(script, python)
            rel = script.relative_to(REPO_ROOT)
            print(f"  [{'OK' if ok else 'FALLO'}] {rel}")
            if not ok:
                failed.append((rel, output))
        if failed:
            for rel, output in failed:
                print(f"\n--- {rel} ---\n{output}")
            raise ReleaseError(f"{len(failed)} test(s) fallaron -- release abortado, no se genero ningun artefacto.")

        print("-- PyInstaller (onedir) --")
        r = subprocess.run(
            [python, "-m", "PyInstaller", "packaging/pivot_x_sentinel.spec", "--noconfirm", "--clean"],
            cwd=REPO_ROOT,
        )
        if r.returncode != 0:
            raise ReleaseError("PyInstaller fallo -- ver el log de arriba.")

        exe_path = REPO_ROOT / "dist" / "pivot-x-sentinel" / "pivot-x-sentinel.exe"
        if not exe_path.exists():
            raise ReleaseError(f"PyInstaller termino pero no aparecio {exe_path}.")

        print("-- Inno Setup --")
        iscc = _find_iscc()
        if not iscc:
            raise ReleaseError(
                "No se encontro ISCC.exe (Inno Setup 6). Instalalo (https://jrsoftware.org/isdl.php) y corre de nuevo."
            )
        r = subprocess.run([iscc, "packaging/installer.iss"], cwd=REPO_ROOT)
        if r.returncode != 0:
            raise ReleaseError("ISCC (Inno Setup) fallo -- ver el log de arriba.")

        installer_src = REPO_ROOT / "packaging" / "dist_installer" / release_lib.installer_name(version)
        if not installer_src.exists():
            raise ReleaseError(
                f"Inno Setup termino pero no aparecio {installer_src} -- revisar OutputBaseFilename en installer.iss."
            )

        print(f"-- generando {rdir} --")
        rdir.mkdir(parents=True)
        installer_dst = rdir / installer_src.name
        shutil.copy2(installer_src, installer_dst)

        changelog_body = release_lib.cut_changelog_release(version)
        if changelog_body is None:
            print("AVISO: CHANGELOG.md no tenia nada en [Unreleased] -- RELEASE_NOTES.md queda con una plantilla para completar a mano.")

        from datetime import date
        today = date.today().isoformat()
        prev = _previous_version(version)
        notes = release_lib.render_release_notes(version, today, changelog_body, prev)
        (rdir / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")

        release_lib.write_checksums(rdir, installer_dst)

        print(f"\nListo: {rdir}")
        for f in sorted(rdir.iterdir()):
            print(f"  - {f.name}")

        tag_cmd = f'git tag -a v{version} -m "pivot-x-sentinel v{version}"'
        if args.tag:
            if not release_lib.git_is_clean():
                print(f"\nNo se creo el tag: hay cambios sin commitear (VERSION/CHANGELOG.md incluidos).\n"
                      f"Commiteá esos cambios y despues corré:\n  {tag_cmd}")
            else:
                release_lib.tag_release(version)
                print(f"\nTag creado localmente: v{version} (no se hizo push)")
        else:
            print(f"\nPara asociar este release a un commit de git (no se ejecuta automaticamente):\n"
                  f"  git add VERSION CHANGELOG.md\n"
                  f'  git commit -m "release: v{version}"\n'
                  f"  {tag_cmd}")

    except ReleaseError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
