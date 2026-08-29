# Respaldo de la memoria local de Claude

Este directorio es un respaldo, en git, de la memoria de proyecto que Claude Code mantiene entre sesiones para `pivot-x-sentinel` — normalmente vive **solo en la máquina local**, en `~/.claude/projects/<hash-del-proyecto>/memory/` (en Windows, algo como `C:\Users\<usuario>\.claude\projects\C--Dev-Python-pivot-x-sentinel\memory\`), fuera de cualquier repositorio.

Se copió acá el 2026-08-26 antes de formatear la laptop, para no perder el contexto de decisiones tomadas durante el desarrollo (qué se acordó, por qué, y cuándo) que no está necesariamente escrito en ningún otro lado del repo.

**No es la fuente de verdad del código ni del roadmap** — eso sigue siendo `docs/roadmap.md` y las specs de `docs/`. Esto es historial de decisiones y contexto de trabajo, con fecha de cuándo se escribió cada nota.

## Archivos

- `MEMORY.md` — índice (como vivía en la carpeta original).
- `pivot-x-sentinel-roadmap.md` — estado del proyecto y regla de trabajo de la sesión.
- `pivot-x-sentinel-tv-reference-mismatch.md` — por qué el bot replica `usarCausal=true` de TradingView en vez del bloque anterior cerrado (2026-08-19).
- `mt5-broker-offset-technique.md` — la técnica de offset horario de bróker (documentada también en `docs/spec-estrategia.md` §3.1).
- `pivot-x-sentinel-no-backtest-talk.md` — preferencia del usuario sobre no mencionar el backtest de Fase 3 al hablar de resultados en vivo.

## Para restaurar en una máquina nueva

Si empezás una sesión de Claude Code nueva en este repo (por ejemplo, después de formatear), no hace falta hacer nada especial — pero si querés que Claude tenga este contexto disponible como memoria otra vez (no solo como archivo de texto en el repo), podés pedirle que lea estos archivos y los vuelva a guardar en su memoria local.
