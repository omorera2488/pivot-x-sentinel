---
name: mt5-broker-offset-technique
description: "Cómo medir el offset horario de cualquier bróker MT5 en vivo, sin conocerlo de antemano"
metadata:
  node_type: memory
  type: project
  originSessionId: 2d778965-d04d-4c37-a61a-e918575298c0
  modified: 2026-08-17T20:52:26.554Z
---

Para normalizar timestamps del servidor de un bróker MT5 a UTC sin tener que hardcodear la zona horaria de ningún bróker en particular: al conectar, pedir un tick reciente con `symbol_info_tick` (trae su propio timestamp de servidor) y compararlo contra el reloj UTC del sistema en el instante exacto de esa consulta. La diferencia es el offset horario de ESE bróker en ESE momento.

**Por qué importa:** resuelve "arrancar el bot hoy contra cualquier cuenta" sin configuración manual — funciona igual para Exness, IC Markets, o cualquier otro bróker MT5. El offset puede cambiar con el horario de verano de la zona del bróker, así que conviene re-medirlo en cada conexión, no cachearlo indefinidamente.

**Dónde se usa:** documentado en el proyecto [pivot-x-sentinel](C:\Dev\Python\pivot-x-sentinel) — `docs/spec-estrategia.md` §3.1 (alineación del bloque HTF a época UTC) y `docs/spec-backtest.md` §2.1 (normalización de timestamps al descargar historial). Aplica también a la Fase 4 (motor de ejecución en vivo) del mismo proyecto — ver [[pivot-x-sentinel-roadmap]].
