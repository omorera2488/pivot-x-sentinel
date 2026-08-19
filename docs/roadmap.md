# Roadmap — Bot de Oro (EMA + Pivotes ZS) sobre MT5

Este documento define las fases de desarrollo del bot de trading algorítmico para Oro (XAUUSD), basado en la lógica del indicador Pine "EMA y Pivotes ZS — trade boxes", adaptado para ejecución en vivo vía MetaTrader 5.

**Regla de trabajo:** esta sesión se encarga de la definición, especificación, revisión y detección de problemas de cada fase. La implementación del código corre por cuenta del usuario / Claude Code local. Cada fase avanza cuando la anterior está completa.

---

## Fase 0 — Fundamentos y decisiones de arquitectura ✅ COMPLETADA

Decisiones ya tomadas:

- **Arquitectura:** un solo proceso Python. Sin "shadow candidato", sin procesos paralelos ni capas extra que no aporten a la ejecución real.
- **Ejecución y datos de mercado:** paquete oficial `MetaTrader5` de Python — conecta directo a una terminal MT5 abierta, permite leer cuenta/posiciones/histórico y mandar órdenes (con SL/TP) desde el mismo proceso. Solo funciona en Windows.
- **Panel:** se toma como referencia visual el dashboard del bot "M1 Pivotes 15" (capturas ya compartidas), pero simplificado a la arquitectura de un solo proceso — sin los elementos de "shadow" u otros procesos que no correspondan.
- **Instrumento:** Oro (XAUUSD o la variante que ofrezca el bróker, ej. XAUUSDm).
- **Repositorio:** nuevo repo en GitHub, aún por crear.
- **Bug conocido a corregir:** el bloque HTF causal (no-repintante) se auto-arma en ambas direcciones en cada barra de arranque de un bloque nuevo, porque compara el máximo/mínimo del bloque contra sí mismo. Ver Fase 2.

---

## Fase 1 — Repositorio y esqueleto del proyecto ✅ COMPLETADA

**Objetivo:** tener un lugar de trabajo real donde ir completando las fases siguientes.

Repo: https://github.com/omorera2488/pivot-x-sentinel

**Pendiente del lado del usuario:**
- ~~Crear el repo vacío en GitHub (privado o público, a elección).~~ ✅ hecho.
- Confirmar la ruta local del bot "M1 Pivotes 15" si se va a usar como referencia de estructura/estilo del panel (relevante recién en Fase 6, no bloquea el avance ahora).

**Estructura de carpetas propuesta:**
```
/strategy      → lógica pura de la estrategia (sin MT5, sin red, testeable de forma aislada)
/execution     → bridge con MetaTrader5 (conexión, envío/gestión de órdenes)
/api           → servidor local que expone estado del bot al panel
/panel         → frontend del dashboard
/packaging     → script de empaquetado del .exe y ventana de control
/backtests     → motor y resultados de backtesting específico de Oro
/docs          → specs, decisiones, roadmap (este documento)
```

**Criterio de aceptación:** repo accesible con esta estructura, README explicando el propósito del proyecto y enlazando este roadmap.

---

## Fase 2 — Especificación funcional de la estrategia ✅ COMPLETADA

Especificación formal: [docs/spec-estrategia.md](spec-estrategia.md). Código Pine de referencia en [/basecode_tradingview](../basecode_tradingview).

**Objetivo:** convertir la lógica ya analizada del Pine Script en una especificación formal y corregida, independiente de lenguaje, que cualquier implementación deba seguir exactamente.

**Debe cubrir:**
- Cálculo de EMA (periodo configurable).
- Cálculo del bloque HTF **usando el bloque anterior ya cerrado** como referencia de resistencia/soporte (no el bloque que se está formando) — esto corrige a la vez el repintado del modo original y el bug de auto-armado trivial detectado.
- Reglas de armado (`armadoVenta`/`armadoCompra`) y de señal (cruce de EMA estando armado).
- Entrada como orden límite en el valor de EMA de la barra de señal.
- Cálculo del stop (extremo del bloque anterior + buffer) — buffer a recalibrar para la escala de precio del Oro (no heredar el valor pensado para forex).
- Cálculo del take profit (múltiplo R:R configurable) — R:R a validar empíricamente para Oro, no asumir los valores sugeridos para el par/timeframe original.
- Ciclo de vida completo de la orden: pendiente → llena / caducada por tiempo / invalidada por precio; abierta → TP / SL / tiempo máximo.
- Reglas de concurrencia: límite explícito de operaciones simultáneas en la misma dirección (el original no tiene límite).

**Criterio de aceptación:** la especificación es lo bastante precisa como para que dos implementaciones independientes, corriendo sobre los mismos datos, produzcan exactamente los mismos números.

---

## Fase 3 — Backtest de Oro con costos reales ❌ CRITERIO NO CUMPLIDO (M5)

Especificación: [docs/spec-backtest.md](spec-backtest.md). Motor implementado en [/backtests](../backtests), checksum mecánico pasado, barrido completo de 3.780 combinaciones corrido sobre M5 real con costos en vivo. **Resultado: sin edge robusto** — el detalle completo está en `spec-backtest.md` §8 ("Resultados del primer barrido"). No se cumple el criterio de aceptación de la fase; no se pasa a Fase 4 hasta decidir cómo seguir (redesign, otro timeframe, u otra dirección).

**Objetivo:** validar si existe una ventaja (edge) real en Oro después de costos, antes de escribir una sola línea del bot en vivo.

**Debe incluir:**
- Motor de backtest que implemente la especificación de la Fase 2 (con el bug corregido).
- Datos históricos reales de Oro, al timeframe elegido.
- Modelo de costos: spread, comisión y swap (relevante en Oro, especialmente en operaciones que quedan abiertas muchas horas).
- Barrido de parámetros (buffer, R:R, periodo del bloque HTF, periodo de EMA) específico para Oro.
- Prueba de robustez: separar la muestra en 2–3 períodos y verificar que el resultado no depende de una ventana de fechas particular.

**Criterio de aceptación:** existe una combinación de parámetros con expectancy positiva después de costos, sobre una muestra suficientemente grande, y el resultado se sostiene entre distintos sub-períodos.

---

## Fase 4 — Motor de ejecución en vivo (MT5) ✅ IMPLEMENTADA (sin parámetros validados)

Especificación: [docs/spec-live-execution.md](spec-live-execution.md). Implementado en [/execution](../execution) sobre el motor de [/strategy](../strategy) (`strategy/live_signal.py`, validado bit a bit contra el motor batch). Probado en vivo contra la cuenta demo (conexión, replay de arranque, un ciclo de poll) en `dry_run` — sin mandar órdenes reales.

A pedido explícito del usuario, se implementó **sin esperar un resultado validado de la Fase 3** (que no encontró edge robusto en M5, `spec-backtest.md` §8). El motor corre en `dry_run=True` por defecto — pasar `--live` manda órdenes reales, y no hay base para hacerlo todavía más allá de probar que el mecanismo funciona.

**Objetivo:** la misma lógica validada en la Fase 3, corriendo en tiempo real contra el terminal MT5, en cuenta demo.

**Debe incluir:**
- Conexión vía el paquete `MetaTrader5`.
- Lectura de velas en tiempo real y replicación exacta del cálculo de bloque/armado/señal.
- Colocación de la orden límite con SL/TP adjuntos.
- Vigilancia y cancelación de la orden pendiente si se invalida antes de llenarse.
- Límite de operaciones concurrentes en la misma dirección.

**Criterio de aceptación:** corriendo contra cuenta demo, el bot opera de forma autónoma (sin intervención manual) y los resultados son consistentes con lo esperado del backtest de la Fase 3.

---

## Fase 5 — Capa de datos / API local ✅ COMPLETADA

Especificación: [docs/spec-api.md](spec-api.md). Implementada en [/api](../api) (FastAPI, mismo proceso que el bot).

**Objetivo:** exponer el estado del bot para que el panel lo consuma.

**Debe incluir:** endpoints para balance/equity, posiciones abiertas y pendientes, histórico de operaciones, log de eventos, y control de iniciar/detener el bot.

**Criterio de aceptación:** se puede consultar el estado completo del bot desde afuera (ej. con una herramienta como curl o Postman) sin necesidad de abrir el panel. ✅ Probado en vivo contra la cuenta demo: `/status`, `/start`, `/account`, `/positions`, `/orders`, `/history`, `/events`, `/stop` — los 8 endpoints responden correctamente con curl.

---

## Fase 6 — Panel web (frontend) ✅ COMPLETADA

Especificación: [docs/spec-panel.md](spec-panel.md). Implementado en [/panel](../panel) (HTML/CSS/JS planos, sin build step, servido por el mismo proceso que la API).

**Objetivo:** la interfaz visual, inspirada en las capturas de "M1 Pivotes 15" pero simplificada a un solo proceso.

**Debe incluir:** tarjetas de estado (bot, conexión MT5), métricas de cuenta, curva de capital, tabla de operaciones recientes, log de eventos, botones de iniciar/detener. Además, a pedido del usuario: sin la tarjeta de "shadow candidato" (no aplica, Fase 0), selector de estrategia en Configuración con indicador de la estrategia activa en el panel principal, historial completo y calendario de resultados calculados con el historial real de MT5.

**Criterio de aceptación:** el panel refleja en tiempo real (o casi) el estado real de la cuenta MT5. ✅ Probado en vivo (Browser) contra la API real: las 4 páginas cargan y funcionan — iniciar/detener el bot desde la UI, selector de perfil precargando defaults, balance/equity reales, eventos en vivo.

---

## Fase 7 — Empaquetado en ejecutable de Windows

**Objetivo:** un solo `.exe` que arranca todo (estrategia + API + panel) y abre una ventana de control mínima.

**Debe incluir:** script de arranque, empaquetado (ej. PyInstaller), ventana de control con opciones de abrir panel / ver logs / cerrar todo de forma segura.

**Criterio de aceptación:** doble clic en el ejecutable deja todo corriendo y el panel accesible, sin pasos manuales adicionales.

---

## Fase 8 — Validación en demo y checklist antes de pasar a real

**Objetivo:** confirmar que el sistema completo se comporta en la práctica como en el backtest, y decidir con criterios objetivos si pasa a cuenta real.

**Debe incluir:**
- Periodo mínimo de operación en demo, definido de antemano.
- Comparación cuantitativa demo vs backtest.
- Checklist de riesgo: drawdown máximo tolerado, tamaño de posición, manejo de reconexión/errores de MT5, filtros de sesión/noticias si se decide incorporarlos.

**Criterio de aceptación:** checklist cumplido con datos objetivos — no una decisión basada en sensación o en pocas operaciones.

---

## Estado actual

| Fase | Estado |
|---|---|
| 0 — Fundamentos | ✅ Completada |
| 1 — Repositorio y esqueleto | ✅ Completada |
| 2 — Especificación funcional | ✅ Completada |
| 3 — Backtest de Oro | ❌ Corrido — sin edge robusto en M5, ver spec-backtest.md §8 |
| 4 — Ejecución en vivo | ✅ Implementada, `dry_run` por defecto (sin parámetros validados de Fase 3) |
| 5 — API local | ✅ Completada |
| 6 — Panel web | ✅ Completada |
| 7 — Ejecutable Windows | ⏳ Pendiente |
| 8 — Validación y checklist a real | ⏳ Pendiente |
