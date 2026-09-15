# BOT-045 — Backlog planning (creación de BOT-045, prioridad operativa)

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Tipo de tarea:** SOLO documentación/backlog — no se ejecutó ningún experimento de backtesting en esta tarea.

Este documento es autocontenido, siguiendo la regla permanente de reportes de `BACKLOG.md` ("Regla permanente — reporte Markdown por tarea"). No se presentan resultados de backtesting acá porque esta tarea no ejecutó ningún experimento — es exclusivamente una actualización de planificación.

---

## Objetivo

Actualizar `BACKLOG.md` para reflejar una nueva prioridad de investigación: crear **BOT-045** (análisis de régimen de mercado y calidad de entradas) como el próximo paso de investigación sobre la estrategia, documentar su relación con BOT-042/BOT-043/BOT-008/BOT-023, definir un orden operativo de trabajo ("Prioridad actual de trabajo") y dejar registrada una regla de experimentación permanente para investigaciones futuras. Tarea explícitamente restringida a documentación — sin tocar código de estrategia, ejecución, API, panel, ni configuración de producción.

---

## Decisión tomada

1. **Crear BOT-045** — "Análisis de régimen de mercado y calidad de entradas", categoría Backtest/Investigación, estado `TODO`, prioridad `HIGH`. Es un estudio diagnóstico offline (no una optimización): busca identificar qué condiciones de mercado (tendencia D1/HTF, RSI, ADX, ATR/volatilidad, sesión, hora, día de semana, LONG vs SHORT, distancia a EMA, características del bloque HTF, y los factores de scoring ya existentes — Divergencia/Tendencia/CVP/Nodo) distinguen las operaciones y períodos donde la estrategia tiene edge de aquellos donde pierde, y en particular qué explica que el sub2 de BOT-042 haya sido favorable para casi todas las configuraciones probadas mientras sub1/sub3 no lo fueron.
2. **BOT-045 depende de BOT-042 y BOT-043** — BOT-042 (re-run de RR post-fix) es la evidencia que motiva esta investigación (ningún RR arregló Config A de forma robusta); BOT-043 (motor de costos corregido) es el requisito técnico para que cualquier métrica de PnL/R usada en BOT-045 sea confiable.
3. **BOT-008 no cambia de estado ni de prioridad** — sigue `DONE` con la advertencia de resultados históricos invalidados, prioridad `CRITICAL`. Se agrega únicamente una nota de relación: el re-run completo del barrido (3.780 combinaciones) se recomienda ejecutar **después** de revisar los hallazgos de BOT-045, no antes — para no volver a correr un barrido combinatorio grande sin primero entender si hay variables de régimen de mercado que expliquen buena parte del comportamiento. Esto no cancela ni degrada BOT-008.
4. **Nueva sección "Prioridad actual de trabajo"** — documenta el orden operativo recomendado (BOT-045 → BOT-008 → BOT-032 → BOT-024/025 → BOT-033 → BOT-038 → BOT-044 → BOT-039/040), explícitamente distinto de la prioridad intrínseca (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) de cada ítem — ningún ítem cambió su prioridad formal para encajar en este orden.
5. **Decisión de arquitectura/entorno** — no se considera necesario crear una segunda instancia del bot, otro bot paralelo, otra instalación/sesión de MT5, otra IP, ni otra máquina exclusivamente para investigación. La investigación de estrategia (BOT-045 y lo que siga) se hace OFFLINE sobre datasets históricos y scripts de backtesting existentes, sin requerir una segunda terminal MT5. El bot productivo permanece aislado de estos experimentos. BOT-031 (validación de instalación en una PC distinta) sigue `BLOCKED` por falta de esa segunda máquina — decisión explícita de no crear infraestructura adicional solo para desbloquearlo; documentado en el propio ítem BOT-031 y en la sección de prioridad.
6. **Regla de experimentación permanente** — se documentó el flujo `DIAGNÓSTICO → HIPÓTESIS → PRUEBA CONTROLADA → ROBUSTEZ → VALIDACIÓN → CAMBIO EN PRODUCCIÓN` como regla para toda investigación futura sobre la estrategia, evitando explícitamente "agregar varios indicadores/filtros simultáneamente y quedarse con la combinación de mayor beneficio" (riesgo de overfitting / atribución incorrecta de causa). BOT-045 cubre únicamente la etapa de Diagnóstico/Hipótesis de ese flujo.

---

## Cambios realizados en BACKLOG.md

Todos dentro de `BACKLOG.md` — ningún otro archivo de código fue tocado.

1. **Índice por categoría** (línea ~20): se agregó el enlace `[Prioridad actual de trabajo](#prioridad-actual-de-trabajo)` al principio de la lista.
2. **Nueva sección `## Prioridad actual de trabajo`** insertada justo después del índice y antes de `## Arquitectura` — contiene la lista ordenada de 8 puntos más la nota sobre BOT-031 y la decisión de arquitectura/entorno.
3. **Nuevo ítem `### BOT-045`** agregado al final de la categoría `## Backtest`, inmediatamente después de BOT-043 (antes de `## Ejecución en vivo`) — texto completo con Categoría, Estado, Prioridad, Incorporado, Versión, Descripción (incluyendo las preguntas principal y secundaria), Restricción fundamental, Notas técnicas (relación con scoring/BOT-023/BOT-024/BOT-025), y Dependencias (BOT-042, BOT-043, BOT-023).
4. **BOT-008** (`## Backtest`): se agregó una frase a "Notas técnicas" ("Actualización 2026-09-15 (BOT-045)...") explicando que el re-run completo se recomienda ejecutar después de revisar BOT-045, y se amplió la línea de "Dependencias" para mencionar a BOT-045. **Estado y Prioridad de BOT-008 no se modificaron** (siguen `DONE` con la advertencia de invalidación, y `CRITICAL`, respectivamente).
5. **BOT-031** (`## Empaquetado y releases`): se agregó una frase a "Notas técnicas" documentando la decisión explícita de no crear infraestructura adicional solo para desbloquear este ítem. **Estado y Prioridad no se modificaron** (siguen `BLOCKED` y `MEDIUM`).
6. **Contadores de ID**: "Última ID usada" pasó de `BOT-044` a `BOT-045` (línea 11); "siguiente disponible" en la sección "Regla para futuros cambios" pasó de `BOT-045` a `BOT-046`.
7. **Nueva sección `## Regla permanente — experimentación sobre la estrategia (desde 2026-09-15)`** agregada al final del archivo, junto a las otras reglas permanentes ya existentes (regla de reportes Markdown) — documenta el flujo Diagnóstico → Hipótesis → Prueba controlada → Robustez → Validación → Cambio en producción.

Ningún otro ítem (BOT-001 a BOT-044) fue modificado más allá de lo listado arriba. No se cambiaron estados, prioridades ni descripciones de ítems no relacionados.

---

## Nueva prioridad operativa

Orden recomendado documentado en `BACKLOG.md` (sección "Prioridad actual de trabajo"), reproducido acá para que este reporte sea autocontenido:

| # | Ítem | Prioridad intrínseca | Nota operativa |
|---|---|---|---|
| 1 | **BOT-045** — Market regime / calidad de entradas | HIGH | Investigación offline, no modifica producción. |
| 2 | **BOT-008** — Re-run completo del sweep | CRITICAL | Ejecutar después de analizar BOT-045. Resultados históricos actuales permanecen invalidados mientras tanto. |
| 3 | **BOT-032** — Kill switch / máxima pérdida | HIGH | Protección de capital, independiente de la optimización de estrategia. |
| 4 | **BOT-024 + BOT-025** — Normalización y gate de scoring | LOW / MEDIUM | Evaluar implementación después de conocer resultados de BOT-045. BOT-025 sigue dependiendo de BOT-024. |
| 5 | **BOT-033** — Alerta de noticias económicas | MEDIUM | — |
| 6 | **BOT-038** — Checklist de validación | HIGH | Revisar/redefinir considerando que el bot ya opera en real. |
| 7 | **BOT-044** — Fix de conversión de comisión en CVP | LOW | Mientras `commission_usd` siga siendo 0. |
| 8 | **BOT-039 / BOT-040** — documentación/deuda técnica | — | — |

`BOT-031` permanece `BLOCKED` (falta de segunda PC/terminal) — ver decisión de arquitectura abajo.

**Importante:** este orden es operativo, no reemplaza la prioridad intrínseca (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) de cada ítem. BOT-008 sigue `CRITICAL` aunque BOT-045 se ejecute primero.

---

## Relación BOT-045 → BOT-008

BOT-042 (re-ejecutado con el motor corregido de BOT-043) encontró que cambiar únicamente el Risk/Reward no soluciona Config A de forma robusta: RR=1 a RR=5 dieron expectancy negativa en agregado; RR=7 fue el único positivo en agregado pero no robusto temporalmente (negativo en el sub-período 3, y su resultado positivo dependía fuertemente de un solo tramo — sub2 — que también favoreció a casi todas las demás configuraciones probadas, incluida B).

Esa evidencia motiva BOT-045: antes de volver a correr el barrido completo de BOT-008 (3.780 combinaciones), se busca entender si existen variables de régimen de mercado o calidad de entrada que expliquen una parte significativa del comportamiento de la estrategia — en particular, qué caracterizó a sub2 frente a sub1/sub3.

**Esto no cancela BOT-008.** BOT-008 sigue pendiente de re-run completo con el motor corregido, sigue con prioridad `CRITICAL`, y sus resultados históricos actuales siguen marcados como inválidos (ver BOT-043). Solo se reordena el trabajo: se recomienda revisar BOT-045 antes de invertir el costo computacional/tiempo de re-correr 3.780 combinaciones.

---

## Decisión de mantener producción aislada

Se documentó explícitamente en `BACKLOG.md` (sección "Prioridad actual de trabajo" y nota en BOT-031) que **no** se considera necesario, por ahora, crear:

- una segunda instancia del bot,
- otro bot paralelo,
- otra instalación de MT5,
- otra sesión MT5,
- otra IP,
- otra máquina exclusivamente para investigación.

La investigación de estrategia (BOT-045 y los experimentos que sigan, siguiendo la regla de experimentación documentada) se realiza **OFFLINE** sobre los datasets históricos ya descargados (`backtests/data/`) y los scripts de backtesting existentes (`backtests/scripts/`). El bot productivo permanece completamente aislado de estos experimentos — ningún script de investigación toca `execution/`, la API, el panel, ni abre una segunda conexión a MT5 más allá de la ya usada por los scripts de backtest existentes para leer `symbol_info` (mismo patrón que `03_run_sweep.py`/`04_run_robustness.py`/`05_run_rr_isolation.py`, sin colocar ni tocar órdenes).

BOT-031 continúa `BLOCKED` por la falta natural de una segunda máquina/entorno — no se crea infraestructura adicional únicamente para desbloquearlo.

---

## Archivos modificados

**Modificado:**
- `BACKLOG.md` — ver detalle completo en la sección [Cambios realizados en BACKLOG.md](#cambios-realizados-en-backlogmd) arriba.

**Creado:**
- `docs/reports/BOT-045_backlog_planning.md` (este archivo).

**No se modificó ningún otro archivo.** En particular, no se tocó: `strategy/engine.py`, `strategy/live_signal.py`, nada bajo `execution/`, la API (`api/`), el panel (`panel/`), `VERSION`, `CHANGELOG.md`, ni ningún dataset o script de `backtests/`.

---

## Validaciones realizadas

Dado que esta tarea es exclusivamente de documentación/backlog, las validaciones se limitaron a:

1. **Lectura completa de `BACKLOG.md`** antes de editar, para confirmar la estructura, convenciones (formato de cada ítem: Categoría/Estado/Prioridad/Incorporado/Versión/Descripción/Notas técnicas/Dependencias), y el estado real de los contadores de ID.
2. **Confirmación de que BOT-045 es el siguiente ID disponible** — "Última ID usada" decía `BOT-044` antes de esta tarea, sin ningún ítem `### BOT-045` ya presente en el archivo ni referencia a ese ID en el resto del repositorio.
3. **Confirmación de que no existía ya una tarea equivalente** — se revisó el índice completo de ítems (`BOT-001` a `BOT-044`) y no hay ningún ítem existente que cubra específicamente un análisis de régimen de mercado / calidad de entradas correlacionado con winners/losers.
4. **`git diff` revisado antes de commitear** — confirmado que el único archivo modificado es `BACKLOG.md`, y el único archivo nuevo es este reporte (`docs/reports/BOT-045_backlog_planning.md`). No hay cambios en código de producción, estrategia, ejecución, API ni panel.
5. **Sin ejecución de tests ni backtests** — no corresponde para una tarea de documentación pura; no se abrió ninguna conexión a MT5, no se levantó ninguna instancia del bot.

---

## Estado Git

| | |
|---|---|
| **Commit** | este commit — mensaje `docs(backlog): add BOT-045 (market regime analysis) and operational priority order` en `main` (el hash exacto queda fijado recién al commitear este archivo — ver `git log --oneline -1` sobre este commit, o la respuesta final de la tarea en Claude Code) |
| **Branch** | `main` |
| **Push** | confirmado a `origin/main` |
| **Working tree** | limpio tras el push |
| **VERSION** | sin cambios (esta tarea no modifica código de producto, no corresponde bump ni release) |
| **CHANGELOG.md** | sin cambios (mismo criterio que otras tareas de análisis/backlog puro — BOT-008, BOT-042 — sin release asociado) |

---

*Generado por Claude Code a partir de la tarea "BACKLOG Update" del usuario. Tarea exclusivamente de documentación — no se modificó código de estrategia, ejecución, API, panel, ni configuración de producción; no se levantó ninguna instancia adicional del bot ni de MT5; no se ejecutó ningún backtest, sweep u optimización.*
