# releases

Artefactos de cada release, generados por `python scripts/build_release.py`
(ver [scripts/release_lib.py](../scripts/release_lib.py) y
[CHANGELOG.md](../CHANGELOG.md)) — **no se versionan en git** (ver
`.gitignore`: cada instalador pesa ~19MB, el historial de versiones ya queda
trazado por el `CHANGELOG.md` + los tags `vX.Y.Z` de git). Esta carpeta vive
solo en disco, local a cada máquina donde se generaron releases.

## Estructura

```
releases/
└── v1.0.0/
    ├── pivot-x-sentinel-setup-1.0.0.exe   -- el instalador
    ├── RELEASE_NOTES.md                    -- que trae ESTE artefacto especificamente
    └── checksums.txt                       -- SHA256 del .exe
```

Cada `vX.Y.Z/` es inmutable una vez generada: `build_release.py` se niega a
sobrescribir una que ya existe (si hace falta corregir algo, se sube el
PATCH). No se versionan en git.

## Verificar un instalador

```powershell
Get-FileHash releases\v1.0.0\pivot-x-sentinel-setup-1.0.0.exe -Algorithm SHA256
```

Comparar contra el hash de `checksums.txt` de esa misma carpeta.
