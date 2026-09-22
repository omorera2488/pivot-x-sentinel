"""BOT-051.5 -- provenance (bot_version/git_commit) de cada registro nuevo
de score_store -- seccion 6 del enunciado: "Esta metadata es provenance, no
un factor de calidad". Nunca entra a SignalQualityVectorV1; solo acompaña la
fila persistida para poder responder despues "¿esta observacion nacio
despues del freeze, y con que version de codigo?".

Fail-safe por diseño: si `/VERSION` o `git` no estan disponibles (ej. un
build empaquetado sin repo git), ambas funciones devuelven `None` en vez de
lanzar -- la captura de provenance nunca debe poder bloquear
`score_store.record()` ni, por extension, la colocacion de una orden."""
from __future__ import annotations

import subprocess
from pathlib import Path

_git_commit_cache: str | None | object = "_unset"


def bot_version() -> str | None:
    try:
        from .version import get_version
        return get_version()
    except Exception:
        return None


def git_commit() -> str | None:
    """`git rev-parse HEAD` sobre el repo, cacheado tras la primera llamada
    (el commit no cambia durante la vida del proceso). `None` si no hay repo
    git disponible (ej. build empaquetado) o si git no esta instalado."""
    global _git_commit_cache
    if _git_commit_cache != "_unset":
        return _git_commit_cache  # type: ignore[return-value]
    try:
        repo_root = Path(__file__).resolve().parents[2]
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=5,
        )
        _git_commit_cache = res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None
    except Exception:
        _git_commit_cache = None
    return _git_commit_cache  # type: ignore[return-value]


def snapshot() -> dict:
    """{"bot_version": ..., "git_commit": ...} -- lo que
    score_store.record() adjunta a cada fila nueva como `provenance`."""
    return {"bot_version": bot_version(), "git_commit": git_commit()}
