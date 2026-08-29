---
name: pivot-x-sentinel-no-backtest-talk
description: El usuario no quiere que se mencione el backtest de Fase 3 (sin edge / desactualizado) al hablar de resultados del bot pivot-x-sentinel
metadata:
  node_type: memory
  type: feedback
  originSessionId: bd2f9129-54b6-4778-b5a7-59c419ec6bbd
  modified: 2026-08-26T17:42:41.109Z
---

Cuando el usuario pregunta por "resultados del bot" en [[pivot-x-sentinel-roadmap]], **no mencionar el backtest de Fase 3** (ni "sin edge confirmado" ni "quedó desactualizado"). Lo pidió explícitamente y remarcó que ya lo había pedido varias veces antes en la misma conversación.

**Por qué:** no le interesa esa información para esta pregunta — el foco es la ejecución en vivo (Fase 4), no la validación estadística previa.

**Cómo aplicar:** si pregunta por resultados, dar solo los datos de la cuenta/operaciones en vivo (vía la API local del bot: `/status`, `/positions`, `/orders`, `/history`) — balance, equity, operaciones cerradas, win rate, P&L, posiciones abiertas. No traer a colación el estado de Fase 3 salvo que el usuario lo pida explícitamente.
