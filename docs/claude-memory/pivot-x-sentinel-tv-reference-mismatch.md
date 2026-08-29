---
name: pivot-x-sentinel-tv-reference-mismatch
description: "Historial -- por qué el bot se cambió (2026-08-19) para replicar exactamente usarCausal=true del indicador de TradingView, en vez del bloque anterior cerrado"
metadata:
  node_type: memory
  type: project
  originSessionId: 4a9be3a4-3760-4292-bda7-f3cd4989af17
  modified: 2026-08-19T04:12:59.097Z
---

**Estado actual (desde 2026-08-19): el bot SÍ replica el indicador de TradingView.** `strategy/engine.py:bucket_levels()` y `strategy/live_signal.py` ahora calculan resistencia/soporte como el extremo del bloque HTF **en formación** (auto-armado incluido), igual bit a bit que `runHigh`/`runLow` con `usarCausal=true` en `basecode_tradingview/*.txt`. Para comparar el chart de TradingView contra el bot: **tildar "Niveles causales (sin repintado)"** en el indicador -- ese es el modo que el bot replica. El otro modo (`usarCausal=false`, checkbox destildado) sigue sin ser replicable: usa `request.security(..., lookahead_on)`, requiere el high/low FINAL de un bloque que todavía no terminó de formarse -- imposible en vivo.

**Por qué se cambió (contexto, ver conversación 2026-08-19):** originalmente [[pivot-x-sentinel-roadmap]] documentaba la corrección de Fase 2 como "bloque HTF ANTERIOR ya cerrado, congelado" -- eso arreglaba el auto-armado trivial de `usarCausal=true` (el bloque se compara contra sí mismo cada vez que hace un nuevo extremo) pero como consecuencia dejaba de coincidir con NINGÚN modo del indicador real que el usuario corre en TradingView. A pedido explícito del usuario ("el bot debería usar esa lógica, ya que es el mismo código que corro en TradingView"), se revirtió la corrección: se prefirió paridad exacta con el indicador visual por sobre evitar el auto-armado. Ver `docs/spec-estrategia.md` (control de cambios al tope, #3.2/#3.3) para el detalle técnico y `docs/roadmap.md` (enmienda en Fase 2, aviso en Fase 3) para el impacto en el roadmap.

**Consecuencia importante: la Fase 3 (backtest, "sin edge robusto en M5") quedó desactualizada.** Ese barrido corrió con la lógica vieja (bloque anterior cerrado) -- el bot en vivo desde el 2026-08-19 ya NO usa esa lógica. Repetir el barrido de Fase 3 con `bucket_levels()` nuevo es trabajo pendiente, no hecho todavía.

**Bug de paridad encontrado y arreglado durante el cambio:** el loop de `run_backtest()` en `strategy/engine.py` arrancaba en `i=1` (asumía que la barra 0 nunca podía tener resistencia/soporte definidos, cierto con la lógica vieja pero falso con la nueva -- ahora `resistencia[0]=high[0]` siempre). Se corrigió para arrancar en `i=0` con cruce forzado a `False` en esa barra (replica exactamente lo que ya hacía `LiveSignalEngine.process_bar`). Ver `strategy/test_engine.py::test_g_live_signal_matches_batch`, que fue el que lo detectó (batch=55 vs vivo=56 señales antes del fix).

**Dato asociado:** con `usarCausal=true` tildado, el indicador de TradingView mostró 54,19% de aciertos (cerca del 50% de equilibrio sin costos) en vez del 79,53% del modo repintante -- dirección consistente con "sin edge robusto tras costos reales" del hallazgo viejo de Fase 3, aunque ese barrido concreto ya no sea el que corre el bot.
