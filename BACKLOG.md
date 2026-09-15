# Backlog — pivot-x-sentinel

Fuente única de verdad de tareas, mejoras, bugs y funcionalidades — pendientes y ya resueltas — de todo el proyecto. Reemplaza el tener esto disperso entre `docs/roadmap.md`, comentarios de código, y la memoria de las sesiones de Claude.

**Relación con otros documentos:**
- **[docs/roadmap.md](docs/roadmap.md)** sigue siendo la fuente de verdad del *alcance y orden de las fases* (Fase 0 → Fase 8). Este backlog es más granular: cada tarea concreta dentro (o fuera) de esas fases tiene acá su propio ítem con estado y prioridad.
- **[CHANGELOG.md](CHANGELOG.md)** documenta qué cambió en cada *versión publicada*. Este backlog documenta qué existe, qué se está haciendo, y qué falta — independientemente de si ya se publicó una versión con eso o no.

**Regla de trabajo (ver también el pie de este archivo):** antes de implementar algo importante, buscar o crear su ID acá, pasarlo a `IN PROGRESS`, implementar, correr los tests, y recién pasarlo a `DONE` con la versión donde quedó. Nunca borrar un ítem — si se cancela, pasa a `CANCELLED` con el motivo.

**IDs:** secuenciales, nunca se reutilizan aunque el ítem se cancele. Última ID usada: **BOT-045**.

**Convenciones:**
- Estados: `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `CANCELLED`
- Prioridades: `CRITICAL` · `HIGH` · `MEDIUM` · `LOW`
- "Versión objetivo" solo se completa si ya está decidido — la mayoría de lo pendiente todavía no tiene versión asignada.

---

## Índice por categoría

- [Arquitectura](#arquitectura) · [Estrategia](#estrategia) · [Backtest](#backtest) · [Ejecución en vivo](#ejecución-en-vivo) · [API](#api) · [Panel](#panel) · [Scoring de entradas](#scoring-de-entradas) · [Empaquetado y releases](#empaquetado-y-releases) · [Gestión de riesgo](#gestión-de-riesgo) · [Noticias económicas](#noticias-económicas) · [Validación y salida a real](#validación-y-salida-a-real) · [Deuda técnica y documentación](#deuda-técnica-y-documentación)

---

## Arquitectura

### BOT-001 — Arquitectura de proceso único
- **Categoría:** Arquitectura
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Un solo proceso Python corre estrategia + ejecución MT5 + API + panel — sin "shadow process" ni capas paralelas (decisión de Fase 0, `docs/roadmap.md`).
- **Notas técnicas:** Confirmado en `api/app.py` (el bot corre en un thread del mismo proceso uvicorn, protegido por `mt5_lock`).
- **Dependencias:** ninguna.

---

## Estrategia

### BOT-002 — Especificación funcional formal de la estrategia
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `docs/spec-estrategia.md` — especificación independiente de lenguaje de EMA, bloque HTF, armado/señal, ciclo de vida de la orden y concurrencia, derivada del Pine original.
- **Notas técnicas:** Documento vivo — tiene 2 enmiendas registradas (ver BOT-004, BOT-005) con control de cambios al tope.
- **Dependencias:** ninguna.

### BOT-003 — Motor batch + motor incremental con paridad validada
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `strategy/engine.py` (motor batch, usado por `/backtests`) y `strategy/live_signal.py` (motor incremental, usado por `/execution`) implementan exactamente la misma lógica — validado bit a bit, no solo por inspección.
- **Notas técnicas:** Verificado corriendo `strategy/test_engine.py` (test G: 56 señales comparadas, motor batch == incremental) — **pasa** (confirmado en esta sesión).
- **Dependencias:** BOT-002.

### BOT-004 — Bloque HTF alineado a sesión (no a época Unix)
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** CRITICAL
- **Incorporado:** 2026-09-03
- **Versión objetivo/alcanzada:** 1.0.0 (⚠️ no documentado en `CHANGELOG.md` — ver BOT-039)
- **Descripción:** Se detectó por prueba directa contra TradingView que el bloque HTF NO se calcula como `floor(minutos_unix / periodos)` (bloques fijos desde época Unix) sino trocheado por sesión (ancla medida en 22:00 UTC, día de sesión de 1440min, último bloque del día truncado). La fórmula vieja llegó a desfasar el bot ~2hs respecto a TradingView. Implementado en `strategy/htf_session.py`, compartido bit a bit entre `engine.bucket_levels` y `LiveSignalEngine`.
- **Notas técnicas:** `docs/spec-estrategia.md` §3.1 tiene la evidencia medida (2-4 sept 2026) y la fórmula nueva. **Supuestos aún sin validar** (ver BOT-005 relacionados): el ancla de sesión (22:00 UTC) no se probó todavía contra un cambio de DST real (EEUU cambia el 1-nov-2026), y se midió solo contra el feed TVC de TradingView, no de forma independiente contra el feed nativo de MT5. Verificado con `strategy/test_htf_session.py` — **pasa** (confirmado en esta sesión: paridad batch/incremental cruzando 3 límites reales de bloque, 360 barras).
- **Dependencias:** BOT-002, BOT-003.

### BOT-005 — Réplica exacta de `usarCausal=true` (paridad visual con TradingView)
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-19
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** A pedido explícito del usuario, el motor reproduce el bloque HTF **en formación** (con auto-armado incluido) en vez del "bloque anterior cerrado" que corregía ese comportamiento — para tener paridad exacta con lo que el indicador real muestra en TradingView, la única variante que se puede ejecutar en vivo.
- **Notas técnicas:** `docs/spec-estrategia.md` §3.2/§3.3. Esta decisión es la que dejó desactualizado el barrido de Fase 3 (ver BOT-008).
- **Dependencias:** BOT-002.

### BOT-006 — Campos de diagnóstico de paridad barra a barra
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-03
- **Versión objetivo/alcanzada:** 1.0.0 (⚠️ no documentado en `CHANGELOG.md` — ver BOT-039)
- **Descripción:** `BarSignal` expone campos adicionales puramente informativos (`armado_*_antes`, `cruce_*`, `senal_*`) para poder comparar bar-a-bar el motor contra lo que muestra TradingView, sin tocar el resultado real de la señal. Complementado por `scripts/diagnose_signal_parity.py` (solo lectura, no manda órdenes).
- **Notas técnicas:** Verificado con `strategy/test_diagnostics.py` — **pasa** (confirmado en esta sesión): consistencia interna de los campos nuevos + resultado idéntico al motor batch.
- **Dependencias:** BOT-003, BOT-004.

### BOT-007 — Modelo de costos reales (spread, comisión, swap)
- **Categoría:** Estrategia
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `strategy/costs.py` — spread real por vela, comisión explícita, swap por rollover (con día triple configurable). Parámetro opcional del motor batch; con costos en cero da la estrategia "pelada".
- **Dependencias:** ninguna.

---

## Backtest

### BOT-008 — Re-ejecutar el barrido de Fase 3 con la lógica HTF actual
- **Categoría:** Backtest
- **Estado:** TODO
- **Prioridad:** CRITICAL
- **Incorporado:** 2026-08-19 (ampliado 2026-09-03)
- **Versión objetivo:** sin definir
- **Descripción:** El único barrido de backtest que existe (`docs/spec-backtest.md` §8, 3.780 combinaciones sobre M5 real) corrió contra la lógica HTF **vieja** — reemplazada DOS VECES desde entonces: primero por "bloque en formación" (BOT-005, 2026-08-19) y después por "alineado a sesión" (BOT-004, 2026-09-03). El bot opera en vivo con capital real (`execution/README.md`, `docs/spec-live-execution.md`) sin que exista ningún backtest que refleje la lógica que realmente corre hoy.
- **Notas técnicas:** El motor de backtest en sí (`/backtests`, `engine.py`) no necesita cambios — solo hay que volver a correr el barrido (`backtests/scripts/03_run_sweep.py`/`04_run_robustness.py`) con datos frescos, ya que `bucket_levels`/`htf_session.py` ya están actualizados. `backtests/` no tuvo cambios desde 2026-08-30 (solo la resolución de símbolo).
- **Dependencias:** BOT-004, BOT-005.

### BOT-009 — Motor de backtest con costos reales (implementación)
- **Categoría:** Backtest
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Motor implementado en `/backtests`, corrido sobre datos reales de XAUUSDm M5 (1.4 años, 100k velas). El *motor* está terminado y probado; el *resultado* de ese barrido específico está obsoleto (ver BOT-008).
- **Notas técnicas:** `docs/spec-backtest.md` §8 documenta el resultado del barrido viejo (sin edge robusto — hallazgo estructural del armado persistente, no un bug).
- **Dependencias:** ninguna.

---

## Ejecución en vivo

### BOT-010 — Motor de ejecución en vivo (LiveExecutionBot)
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-18
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Conexión a MT5, replay de arranque (reconstruye armado/EMA sobre historial reciente), polling de vela cerrada, colocación de orden límite con SL/TP, vigilancia y cancelación de pendientes, cierre por tiempo máximo, reconciliación de concurrencia contra el estado real del bróker.
- **Notas técnicas:** `execution/src/bot.py`, especificado en `docs/spec-live-execution.md`.
- **Dependencias:** BOT-003.

### BOT-011 — Resolución automática de símbolo (agnóstico de bróker/cuenta)
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-30
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `resolve_symbol()` acepta la base genérica (`XAUUSD`, `BTCUSD`) o el nombre exacto, y resuelve al nombre real que usa el bróker conectado (`XAUUSDm`, `XAUUSDc`, etc.) — sin hardcodear ningún bróker. Si hay más de un candidato ambiguo (ej. `BTCUSDc` vs `BTCUSDTc`), falla explícito en vez de adivinar con plata real.
- **Notas técnicas:** `execution/src/mt5_utils.py`. Motivado por el bot dejando de conectar al cambiar de cuenta demo (`XAUUSDm`) a cuenta real (`XAUUSDc`) en un bróker distinto.
- **Dependencias:** ninguna.

### BOT-012 — Vigilancia de pendientes por tick en vivo
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-23
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `_watch_pending_live()` evalúa tpAntes/muerto contra el tick en vivo en cada ciclo de polling (~10s), no solo al cerrar una vela de 5 min — reduce la ventana de riesgo de "hasta 5 minutos" a "hasta 10 segundos". Motivado por un caso real visto en cuenta demo donde el precio llenaba una orden que ya debería haber sido inválida.
- **Dependencias:** BOT-010.

### BOT-013 — Auditoría de órdenes/posiciones (reconciliación externa)
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-31
- **Versión objetivo/alcanzada:** 1.0.0 (⚠️ no documentado en `CHANGELOG.md` — ver BOT-039)
- **Descripción:** `_reconcile()` compara en cada ciclo lo que el bot sabía contra el estado real de MT5 — cualquier orden/posición propia (mismo magic) que desaparece se loguea leyendo el motivo real del historial de MT5 (cancelada, llenada, cerrada por SL/TP/stop-out, o cerrada a mano desde el terminal). Antes, un cierre manual no dejaba ningún rastro en el log del bot.
- **Notas técnicas:** `execution/src/bot.py`. A pedido explícito del usuario: "fue abierta por el bot, se audita pase lo que pase" — no depende de que haya sido el propio proceso quien hizo el cambio.
- **Dependencias:** BOT-010.

### BOT-014 — Candado "una operación a la vez"
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-19
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Config `una_operacion_a_la_vez` (default `true`) — bloquea cualquier señal nueva (venta o compra) mientras haya una operación pendiente o abierta en cualquier dirección. Desactivable para volver al límite por dirección de siempre (`max_concurrent_por_direccion`).
- **Dependencias:** ninguna.

### BOT-015 — Validación real de MT5 antes de operar
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `execution/src/mt5_validation.py` distingue terminal no disponible, terminal sin conexión al bróker, "Algo Trading" apagado, sin cuenta logueada, cuenta sin permiso de trading, y cuenta sin Expert Advisors habilitado — usando campos reales de `terminal_info()`/`account_info()`, no un `try/except` genérico. Es la precondición de arranque tanto en `/start` como en cada reconexión automática.
- **Notas técnicas:** Verificado con `execution/src/test_mt5_validation.py` (9 casos con un MT5 falso) y `api/test_start_mt5_validation.py` — **ambos pasan** (confirmado en esta sesión).
- **Dependencias:** ninguna.

### BOT-016 — Reconexión automática con backoff
- **Categoría:** Ejecución
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-18
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** El loop principal reintenta con backoff creciente (5s, 15s, 60s, 300s) ante cualquier excepción, y `stop()` puede despertarlo al instante en vez de esperar el timeout completo.
- **Notas técnicas:** `execution/src/bot.py::run()`.
- **Dependencias:** ninguna.

---

## API

### BOT-017 — API local (FastAPI)
- **Categoría:** API
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-18
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `/status`, `/start`, `/stop`, `/account`, `/positions`, `/orders`, `/history`, `/events`, `/profiles`, `/version`, `/scores` — expone el estado completo del bot sobre HTTP, en el mismo proceso.
- **Dependencias:** BOT-010.

### BOT-018 — Fix: `/history` excluía cierres manuales de la posición
- **Categoría:** API
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-31
- **Versión objetivo/alcanzada:** 1.0.0 (⚠️ no documentado en `CHANGELOG.md` — ver BOT-039)
- **Descripción:** El deal de cierre de una posición cerrada a mano desde el terminal MT5 llega con `magic=0` (no hereda el magic del bot). Filtrar cada deal individualmente por `magic` descartaba esa mitad del par y la operación desaparecía de la tabla del panel aunque la apertura sí tuviera el magic correcto. Ahora se identifican las posiciones propias por el deal de apertura y se devuelven todos los deals de esas posiciones sin importar el magic de cada leg.
- **Dependencias:** BOT-013.

### BOT-019 — `/start` devuelve error claro si MT5 no está listo
- **Categoría:** API
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `POST /start` responde 503 con un mensaje claro (usando BOT-015) en vez de un 500 genérico con traceback cuando MT5 no está listo.
- **Dependencias:** BOT-015.

---

## Panel

### BOT-020 — Panel web (dashboard)
- **Categoría:** Panel
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-18
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** HTML/CSS/JS planos sin build step, servidos por el mismo proceso de la API. Tarjetas de estado, métricas de cuenta, historial de operaciones, log de eventos, botones iniciar/detener.
- **Dependencias:** BOT-017.

### BOT-021 — Selector de estrategia + indicador de perfil activo
- **Categoría:** Panel
- **Estado:** DONE
- **Prioridad:** LOW
- **Incorporado:** 2026-08-19
- **Versión objetivo/alcanzada:** 1.0.0
- **Dependencias:** BOT-020.

### BOT-022 — Historial completo y calendario de resultados
- **Categoría:** Panel
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-18
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Calculados con el historial real de MT5 (`/history`), no con un registro local aparte. `panel/history.html`, `panel/calendar.html`.
- **Dependencias:** BOT-017.

---

## Scoring de entradas

### BOT-023 — Cálculo y registro de score de cada entrada (4 factores)
- **Categoría:** Scoring
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-31
- **Versión objetivo/alcanzada:** 1.0.0 (⚠️ no documentado en `CHANGELOG.md` — ver BOT-039)
- **Descripción:** `strategy/scoring.py` — 4 factores: **Divergencia** (RSI 14 + pivotes, ±1), **Tendencia** (mismo `bucket_levels` en dos ventanas de tiempo distintas sobre la misma serie, ±1), **CVP** (aciertos% real medido de operaciones ya cerradas vs breakeven neto de la entrada, +1/0, nunca bloquea), **Nodo** (perfil de volumen de rango fijo del bloque HTF, si el camino a TP cruza la zona de mayor volumen resta -1, agregado 2026-08-31). Es una capa puramente aditiva — no altera si se opera ni el volumen.
- **Notas técnicas:** Guardado vía `execution/src/score_store.py` (sobrevive upgrades del instalador — carpeta de datos de usuario, no la reemplazable). Verificado con `strategy/test_scoring.py` — **pasa** (confirmado en esta sesión, 8 casos). Corresponde exactamente al pedido original del usuario de "mejorar la calificación de las entradas" con divergencia/tendencia/CVP + "otros factores técnicos" (Nodo).
- **Dependencias:** BOT-003, BOT-004.

### BOT-024 — Normalizar el score a escala 0–100
- **Categoría:** Scoring
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Hoy el score es aditivo (`total=+2`, `-1`, etc., suma de los 4 factores ±1). El pedido original es una escala tipo `Signal Score: 82/100`. Definir la fórmula de normalización (y si cada factor pesa igual) antes de implementar.
- **Dependencias:** BOT-023.

### BOT-025 — Gate configurable `minimum_entry_score`
- **Categoría:** Scoring
- **Estado:** TODO
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Permitir rechazar una entrada si su score queda por debajo de un umbral configurable (`minimum_entry_score = 70`, por ejemplo). El diseño de `scoring.py` ya contempla esto para el factor CVP específicamente ("el gate... está descripto en el diseño pero deliberadamente desactivado en esta primera pasada") — falta generalizarlo al score total y exponerlo como configuración.
- **Notas técnicas:** Debe seguir siendo una capa que se pueda desactivar — no reemplazar la lógica base de señales (`engine.py`/`live_signal.py`).
- **Dependencias:** BOT-023, BOT-024 (para que el umbral tenga una escala estable antes de fijar un default razonable).

---

## Empaquetado y releases

### BOT-026 — Empaquetado en instalador de Windows
- **Categoría:** Packaging
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-03
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** PyInstaller (build onedir) + Inno Setup 6. Instala sin admin bajo `%LOCALAPPDATA%`, ventana de control mínima (Tk) con Abrir panel / Ver logs / Cerrar todo.
- **Notas técnicas:** `packaging/`. Probado de punta a punta en la máquina de desarrollo (instalar, arrancar, panel, cerrar, desinstalar).
- **Dependencias:** BOT-020.

### BOT-027 — Upgrade in-place preservando datos de usuario
- **Categoría:** Packaging
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** El instalador detecta una instalación previa (mismo `AppId`), bloquea downgrades accidentales, avisa si ya está la misma versión, y reemplaza solo el contenido de la app (`_internal`) sin tocar los datos persistentes del usuario (scores, logs).
- **Notas técnicas:** `execution/src/paths.py` separa `app_root()` (reemplazable) de `user_data_root()` (persistente) — hallazgo clave: en PyInstaller 6 onedir, `sys._MEIPASS` apunta a `_internal`, no a la carpeta del `.exe`. Verificado con una instalación + upgrade de prueba real.
- **Dependencias:** BOT-026.

### BOT-028 — Versionado SemVer con fuente única de verdad
- **Categoría:** Packaging
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `/VERSION` en la raíz, leído por `execution/src/version.py` — expuesto en `GET /version`, panel, ventana de control y logs. Nadie más duplica el número.
- **Dependencias:** ninguna.

### BOT-029 — CHANGELOG.md + RELEASE_NOTES.md por release
- **Categoría:** Packaging
- **Estado:** DONE (con hueco de contenido — ver BOT-039)
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `CHANGELOG.md` como historial acumulado del proyecto (formato Keep a Changelog); cada `releases/vX.Y.Z/` trae su propio `RELEASE_NOTES.md` describiendo específicamente ese artefacto.
- **Dependencias:** BOT-028.

### BOT-030 — Proceso de release reproducible
- **Categoría:** Packaging
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-04
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** `python scripts/build_release.py` valida SemVer, corre los tests, construye el instalador, genera `releases/vX.Y.Z/` con `.exe` + `RELEASE_NOTES.md` + `checksums.txt` (SHA256), y se niega a sobrescribir un release ya publicado. `--tag` crea (local, sin push) el tag anotado `vX.Y.Z`.
- **Notas técnicas:** Verificado con `scripts/test_release_lib.py` — **pasa** (confirmado en esta sesión: SemVer, layout de `releases/`, checksums, corte de changelog). Tag `v1.0.0` existe en el repo.
- **Dependencias:** BOT-028, BOT-029.

### BOT-031 — Validar instalación end-to-end en una PC realmente distinta
- **Categoría:** Packaging
- **Estado:** BLOCKED
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-03
- **Versión objetivo:** sin definir
- **Descripción:** Todo lo de empaquetado (BOT-026 a BOT-030) se probó de punta a punta en la máquina de desarrollo, que ya tiene Python y una terminal MT5 propia operando en vivo. Falta un smoke test real en una PC sin Python preinstalado y con una terminal MT5 distinta.
- **Notas técnicas:** Bloqueado por no tener acceso a una segunda máquina/terminal MT5 para probar — no es un problema de código conocido, es falta de entorno de prueba. Ver nota de seguridad en `packaging/README.md` (dev machine con el bot corriendo en vivo contra cuenta real durante las pruebas de instalador).
- **Dependencias:** BOT-026, BOT-027.

---

## Gestión de riesgo

### BOT-032 — Kill switch: máxima pérdida configurable
- **Categoría:** Riesgo
- **Estado:** TODO
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Mecanismo configurable (`max_loss = 500`, por ejemplo) que, al alcanzar la pérdida acumulada definida, impida abrir nuevas operaciones, detenga el trading automático, cambie el estado visible del bot, y muestre un mensaje claro ("Maximum loss reached. Trading has been stopped."). La reactivación debe requerir una acción explícita/manual — no debe levantarse solo.
- **Notas técnicas:** Sin código relacionado en el repo todavía (verificado: no hay ninguna mención de "kill switch"/"max_loss"/"drawdown máximo" en el código). Pendiente de diseño: (1) cómo se mide la "pérdida acumulada" — ¿por día, por sesión, desde que arrancó el bot, acumulado histórico?; (2) si las operaciones ya abiertas al momento de disparar el kill switch se siguen gestionando con normalidad (SL/TP/timeout) o se cierran de inmediato — el pedido explícita que "debe evaluarse posteriormente"; (3) dónde vive la config (perfil, panel) y cómo se expone el estado "detenido por kill switch" en `/status` y el panel, distinto de un `/stop` manual.
- **Dependencias:** BOT-010 (el motor de ejecución en vivo), BOT-017 (para exponer el estado nuevo por API).

---

## Noticias económicas

### BOT-033 — Alerta de noticia económica próxima (primera etapa)
- **Categoría:** Noticias
- **Estado:** TODO
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Primera etapa únicamente: mostrar una alerta cuando se aproxime una noticia/evento económico relevante. No bloquear entradas todavía (ver BOT-036).
- **Notas técnicas:** Sin ningún código relacionado en el repo (verificado). Requiere definir de dónde sale el calendario económico (fuente de datos externa — no hay ninguna integración de terceros en el proyecto hoy) antes de poder implementar nada.
- **Dependencias:** ninguna directa, pero conceptualmente es la base de BOT-034/035/036.

### BOT-034 — Clasificación de noticias por impacto
- **Categoría:** Noticias
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Etapa posterior a BOT-033 — no implementar todavía (a pedido explícito del usuario).
- **Dependencias:** BOT-033.

### BOT-035 — Configuración del tiempo de anticipación de la alerta
- **Categoría:** Noticias
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Etapa posterior a BOT-033 — no implementar todavía.
- **Dependencias:** BOT-033.

### BOT-036 — Identificación de noticias relevantes específicas para XAUUSD
- **Categoría:** Noticias
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Etapa posterior a BOT-033 — no implementar todavía.
- **Dependencias:** BOT-033.

### BOT-037 — Bloqueo opcional de entradas alrededor de noticias de alto impacto
- **Categoría:** Noticias
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Bloquear nuevas entradas X minutos antes y después de una noticia de alto impacto, configurable. Etapa posterior a BOT-033/034 — no implementar todavía.
- **Dependencias:** BOT-033, BOT-034, BOT-035.

---

## Validación y salida a real

### BOT-038 — Fase 8: checklist de validación en demo antes de pasar a real
- **Categoría:** Validación
- **Estado:** TODO
- **Prioridad:** HIGH
- **Incorporado:** 2026-08-17 (Fase 8 del roadmap original)
- **Versión objetivo:** sin definir
- **Descripción:** Periodo mínimo de operación en demo definido de antemano, comparación cuantitativa demo vs backtest, checklist de riesgo (drawdown máximo tolerado, tamaño de posición, manejo de reconexión/errores, filtros de sesión/noticias si se deciden incorporar). Criterio de aceptación: checklist cumplido con datos objetivos, no una decisión "a sensación".
- **Notas técnicas:** Nota de estado real: el bot ya opera contra una cuenta **real** (no demo) desde antes de esta sesión — esta fase, tal como está descrita en `docs/roadmap.md`, técnicamente ya fue superada por la práctica sin haberse cumplido su criterio formal. Vale la pena revisar si esta fase se redefine (checklist retroactivo) o se reemplaza por otra cosa.
- **Dependencias:** BOT-008 (backtest actualizado), BOT-032 (kill switch, parte natural del checklist de riesgo).

---

## Deuda técnica y documentación

### BOT-039 — CHANGELOG.md incompleto para lo ya shippeado en 1.0.0
- **Categoría:** Documentación
- **Estado:** TODO
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir (retroactivo a 1.0.0)
- **Descripción:** La sección `[1.0.0]` de `CHANGELOG.md` documenta el instalador/versionado/validación de MT5, pero **no menciona** varios cambios reales que el `git log` confirma que entraron en esa misma versión: BOT-004 (bloque HTF alineado a sesión), BOT-006 (campos de diagnóstico), BOT-013 (auditoría de órdenes/posiciones), BOT-018 (fix de `/history`), BOT-023 (scoring de 4 factores). `[Unreleased]` está vacío.
- **Notas técnicas:** No se modifica el `CHANGELOG.md` en esta tarea (se pidió explícitamente no implementar/tocar funcionalidad, solo consolidar el backlog) — queda registrado acá para resolverlo como tarea aparte.
- **Dependencias:** ninguna.

### BOT-040 — `execution/README.md` con ejemplo de uso desactualizado
- **Categoría:** Documentación
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** El ejemplo de uso todavía muestra `--symbol XAUUSDm` (nombre específico de un bróker), aunque desde BOT-011 el default recomendado es el símbolo genérico `XAUUSD` (se resuelve solo). No es incorrecto (`XAUUSDm` sigue funcionando como nombre exacto), pero es confuso/desactualizado respecto a la forma recomendada actual.
- **Dependencias:** BOT-011.

### BOT-041 — Backlog único centralizado (esta tarea)
- **Categoría:** Documentación
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo/alcanzada:** sin versión de release asociada (documento de proceso)
- **Descripción:** Este mismo archivo — consolidación de todo lo disperso en `docs/roadmap.md`, `CHANGELOG.md`, comentarios de código y memoria de sesiones anteriores en una única fuente de verdad de tareas.
- **Dependencias:** ninguna.

---

## Regla para futuros cambios

Antes de implementar cualquier funcionalidad nueva importante:

1. Revisar este `BACKLOG.md`.
2. Crear o identificar el ID correspondiente (siguiente disponible: **BOT-042**).
3. Cambiarlo a `IN PROGRESS` al comenzar.
4. Implementar.
5. Correr los tests correspondientes (ver los scripts `test_*.py` de cada módulo — no hay `pytest` instalado en el entorno, se corren como script plano: `python strategy/test_engine.py`, etc.).
6. Cambiarlo a `DONE` únicamente cuando esté realmente validado (no por aparecer mencionado en un doc).
7. Registrar la versión correspondiente.
8. Si corresponde a una release, reflejar el cambio también en `CHANGELOG.md`.

Si durante el desarrollo aparece un bug, deuda técnica, o mejora nueva: agregarla acá con su propio ID en vez de dejarla como comentario suelto en el código.
