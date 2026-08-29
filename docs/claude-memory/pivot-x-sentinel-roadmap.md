---
name: pivot-x-sentinel-roadmap
description: Proyecto bot de Oro (XAUUSD/MT5) en curso — dónde está el roadmap y la regla de trabajo de la sesión
metadata:
  node_type: memory
  type: project
  originSessionId: 2d778965-d04d-4c37-a61a-e918575298c0
  modified: 2026-08-19T04:13:11.345Z
---

Proyecto en curso: bot de trading algorítmico para Oro (XAUUSD) sobre MetaTrader 5, basado en el indicador Pine "EMA y Pivotes ZS — trade boxes", repo en `C:\Dev\Python\pivot-x-sentinel` (GitHub: omorera2488/pivot-x-sentinel).

**Regla de trabajo (fijada por el usuario):** esta sesión (Claude conversacional) se encarga de la definición, especificación, revisión y detección de problemas de cada fase del roadmap. La implementación del código corre por cuenta del usuario o de Claude Code local — no de este chat. Cada fase avanza cuando la anterior está completa según su criterio de aceptación.

**Fuente de verdad del alcance y estado:** `docs/roadmap.md` en el repo — siempre releer ese archivo al retomar el proyecto, no asumir el estado de memoria porque puede haber avanzado localmente.

Documentos de especificación producidos hasta ahora:
- `docs/spec-estrategia.md` (Fase 2) — especificación formal de la estrategia, corrige el bug de autoarmado del bloque HTF del Pine original.
- `docs/spec-backtest.md` (Fase 3) — especificación del motor de backtest con costos reales, agnóstico de bróker. Ver [[mt5-broker-offset-technique]] para el mecanismo de normalización horaria usado ahí.

Bróker de validación usado para specs con datos reales: Exness, cuenta Standard (servidor `Exness-MT5Trial11`), símbolo `XAUUSDm` — pero el diseño del bot es explícitamente agnóstico de bróker, ese es solo el caso de prueba.

**Estado al 2026-08-19:** Fases 0-2 completadas. Fase 3 (backtest): motor implementado en `/backtests`, corrido sobre 100k velas M5 reales de XAUUSDm (1.4 años) — **criterio de aceptación NO cumplido**: solo 7/3780 combinaciones con expectancy positiva (borde del rango de rr, sin tendencia limpia — compatible con ruido), ninguna sostiene expectancy positiva en los 3 sub-períodos. Detalle en `docs/spec-backtest.md` §8. Hallazgo estructural (no bug): el armado persiste indefinidamente entre bloques HTF mientras resistencia/soporte se recalculan bloque a bloque, descartando 51-64% de las señales por "stop inválido" — hipótesis de rediseño sin aplicar todavía.

El usuario pidió explícitamente NO seguir gastando en backtesting largo por ahora ("estamos en construcción del bot") — el foco pasó a tener el motor implementado y probado. Se reorganizó `/strategy` como motor único seleccionable por perfil (`get_profile("1m"|"5m")`, ver `strategy/profiles.py`), con dos correcciones de fidelidad al Pine encontradas al auditar (fórmula real de `ta.ema`, `entradaViva` implementado). Luego, a pedido explícito del usuario ("los resultados de la fase 3 no son relevantes"), se implementó **la Fase 4 igual, sin esperar parámetros validados** — motor de ejecución en vivo en `/execution` (`LiveExecutionBot`), corre en `dry_run=True` por defecto (no manda órdenes reales salvo `--live`). Probado en vivo contra la cuenta demo (connect+replay+poll) sin operar. Ver `docs/spec-live-execution.md` (nota al tope: sin edge validado, no poner `dry_run=False` sin resolver eso).

Fases 5 y 6 también completadas (2026-08-19): API local (FastAPI, `/api`, mismo proceso que el bot) y panel web (`/panel`, HTML/CSS/JS plano sin build step, servido por la misma API). Panel: sin tarjeta "shadow" (no aplica), selector de estrategia en Configuración + indicador de perfil activo en el panel principal, historial/calendario calculados con el historial real de MT5 (`GET /history`). Todo probado en vivo contra la cuenta demo.

Antes de retomar, releer `docs/roadmap.md` por si avanzó localmente. Fases 0-6 todas con algo construido y funcionando; lo que falta es decidir si/cómo validar un edge real antes de operar en serio (Fase 3 sigue sin edge confirmado, y además quedó desactualizada, ver abajo), y las Fases 7 (empaquetado .exe) y 8 (checklist a real) siguen pendientes.

**Cambio importante (2026-08-19):** a pedido explícito del usuario, se revirtió la corrección de Fase 2 del cálculo del bloque HTF. El motor (`strategy/engine.py`, `strategy/live_signal.py`) ya NO usa "bloque anterior cerrado" -- ahora replica bit a bit `usarCausal=true` del indicador real de TradingView (bloque HTF EN FORMACIÓN, auto-armado incluido), para tener paridad exacta con lo que el usuario ve en su chart. Detalle completo en [[pivot-x-sentinel-tv-reference-mismatch]]. Consecuencia: **el barrido de Fase 3 (spec-backtest.md, "sin edge robusto en M5") corrió con la lógica vieja y ya no representa lo que el bot hace en vivo** -- repetirlo con la lógica nueva es trabajo pendiente.

---

**Actualización 2026-08-26 (agregada al respaldar antes de formatear la laptop):** desde esta nota (2026-08-19) hasta la fecha del respaldo, además se agregó: `una_operacion_a_la_vez` (candado global de concurrencia, default activado — bloquea cualquier señal nueva mientras haya una operación pendiente/abierta en cualquier dirección, configurable desde el panel), columna de tipo compra/venta en las tablas de operaciones del panel, y `_watch_pending_live()` en `execution/src/bot.py` (vigila el TP/SL de las órdenes pendientes contra el tick en vivo en cada ciclo de polling de 10s, no solo al cerrar una vela de 5 min — reduce la ventana de riesgo de "hasta 5 minutos" a "hasta 10 segundos"; motivado por un caso real visto en cuenta demo el 2026-08-23). El bot estuvo operando en vivo (no dry-run) contra la cuenta demo Exness-MT5Trial11 durante este período. Ver `docs/roadmap.md` y el historial de commits de `main` para el detalle exacto y la fecha de cada cambio.
