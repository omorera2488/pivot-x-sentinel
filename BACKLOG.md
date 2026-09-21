# Backlog — pivot-x-sentinel

Fuente única de verdad de tareas, mejoras, bugs y funcionalidades — pendientes y ya resueltas — de todo el proyecto. Reemplaza el tener esto disperso entre `docs/roadmap.md`, comentarios de código, y la memoria de las sesiones de Claude.

**Relación con otros documentos:**
- **[docs/roadmap.md](docs/roadmap.md)** sigue siendo la fuente de verdad del *alcance y orden de las fases* (Fase 0 → Fase 8). Este backlog es más granular: cada tarea concreta dentro (o fuera) de esas fases tiene acá su propio ítem con estado y prioridad.
- **[CHANGELOG.md](CHANGELOG.md)** documenta qué cambió en cada *versión publicada*. Este backlog documenta qué existe, qué se está haciendo, y qué falta — independientemente de si ya se publicó una versión con eso o no.

**Regla de trabajo (ver también el pie de este archivo):** antes de implementar algo importante, buscar o crear su ID acá, pasarlo a `IN PROGRESS`, implementar, correr los tests, y recién pasarlo a `DONE` con la versión donde quedó. Nunca borrar un ítem — si se cancela, pasa a `CANCELLED` con el motivo.

**IDs:** secuenciales, nunca se reutilizan aunque el ítem se cancele. Última ID **principal** usada: **BOT-051**. Siguiente disponible: **BOT-052**. Los IDs decimales (`BOT-XXX.1`, `.2`, `.3`, ...) no consumen IDs principales nuevos — ver "Convención para features experimentales" más abajo.

**Convenciones:**
- Estados: `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `CANCELLED`
- Prioridades: `CRITICAL` · `HIGH` · `MEDIUM` · `LOW`
- "Versión objetivo" solo se completa si ya está decidido — la mayoría de lo pendiente todavía no tiene versión asignada.
- Features experimentales que requieren discovery estadístico usan la subestructura `BOT-XXX.1/.2/.3` (Feature Discovery / Definition Freeze / OOS Validation) — ver "Convención para features experimentales" más abajo. No es obligatoria para bugs, fixes, UI, infraestructura, packaging, documentación u otras tareas ya claramente definidas.

---

## Índice por categoría

- [Prioridad actual de trabajo](#prioridad-actual-de-trabajo) · [Arquitectura](#arquitectura) · [Estrategia](#estrategia) · [Backtest](#backtest) · [Ejecución en vivo](#ejecución-en-vivo) · [API](#api) · [Panel](#panel) · [Scoring de entradas](#scoring-de-entradas) · [Empaquetado y releases](#empaquetado-y-releases) · [Gestión de riesgo](#gestión-de-riesgo) · [Noticias económicas](#noticias-económicas) · [Validación y salida a real](#validación-y-salida-a-real) · [Deuda técnica y documentación](#deuda-técnica-y-documentación)

---

## Prioridad actual de trabajo

*(Última actualización: 2026-09-21, ver BOT-024.2/BOT-024.3/BOT-024.4/BOT-047/BOT-047.1/BOT-047.2/BOT-047.3/BOT-048/BOT-048.1/BOT-048.2/BOT-049/BOT-049.1/BOT-049.2/BOT-049.3/BOT-050/BOT-051/BOT-051.1/BOT-051.2.)* Esta sección representa el **orden operativo recomendado** — puede diferir de la prioridad intrínseca (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) de cada ítem, que no se modifica solo para coincidir con este orden.

1. **BOT-024 — Signal Quality** (línea de investigación activa, `HIGH`): ~~**BOT-024.1** — Evaluación predictiva de Divergencia RSI~~ `DONE`. ~~**BOT-024.2** — Momentum Feature Discovery XAU~~ `DONE` — ver `reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY.md`. **BOT-024.3** — Momentum Out-of-Sample Validation `BLOCKED — waiting for genuine OOS` (no existe histórico posterior al 2026-09-15 en el repositorio, ver `reports/BOT-024.3-MOMENTUM-OOS.md`). **BOT-047 — D1 Alignment** (feature padre, `IN PROGRESS / RESEARCH`): ~~**BOT-047.1 — D1 Alignment Feature Discovery**~~ `DONE` — ver `reports/BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md`. ~~**BOT-047.2 — D1 Alignment Definition Freeze**~~ `DONE` — resultado **`PROVISIONAL`** (no `FREEZE_READY`), ver `reports/BOT-047.2-ALIGNMENT-DEFINITION-FREEZE.md`. `closed_ema200_slope` se trata provisionalmente como **D1 Regime / Trend Strength**, no como definición final de Alignment. ~~**BOT-047.2.1 — Structural Alignment Definition & Legacy Decomposition**~~ `DONE` — resultado **`PROVISIONAL`**, ver `reports/BOT-047.2.1-STRUCTURAL-ALIGNMENT-DEFINITION.md`. ~~**BOT-047.2.2 — D1 Structural Boundary Validation**~~ `DONE` — resultado **`PROVISIONAL`**, ver `reports/BOT-047.2.2-D1-STRUCTURAL-BOUNDARY-VALIDATION.md`. ~~**BOT-047.2.3 — Structural Alignment Consensus Definition Freeze**~~ `DONE` — resultado **`FREEZE_READY`** (definición congelada, no validada), ver `reports/BOT-047.2.3-STRUCTURAL-ALIGNMENT-CONSENSUS-FREEZE.md`. **BOT-047.3 — D1 Alignment OOS Validation** `READY / WAITING FOR OOS` — la decisión metodológica ya está tomada (Structural Alignment Consensus, congelado en `BOT-047.2.3`), pero sigue sin ejecutarse porque no existe histórico posterior al 2026-09-15 en el repositorio (mismo motivo que `BOT-024.3`). **BOT-048 — Structure** (feature padre, `IN PROGRESS / RESEARCH`): ~~**BOT-048.1 — Structure Feature Discovery**~~ `DONE` — ver `reports/BOT-048.1-STRUCTURE-FEATURE-DISCOVERY.md`. ~~**BOT-048.2 — Structure Definition Freeze**~~ `DONE` — resultado **`ORIGIN_ONLY_FREEZE`** (contrato RAW continuo sobre `origin_dist_atr`; Swing y Forward-Space evaluados y rechazados, Structural Consensus rechazado por falta de frontera defendible, `origin_retracement_frac` clasificado `CROSS_FACTOR_ONLY`), ver `reports/BOT-048.2-STRUCTURE-DEFINITION-FREEZE.md`. **BOT-048.3 — Structure OOS Validation** `PENDING / WAITING OOS` — contrato pre-registrado en `BOT-048.2`, sigue sin ejecutarse porque no existe histórico posterior al 2026-09-15 en el repositorio (mismo motivo que `BOT-024.3`/`BOT-047.3`). **Roadmap acordado para completar Signal Quality** (formalizado 2026-09-20): **BOT-049 — Economics** → **BOT-050 — Context** → **BOT-051 — Signal Quality Integration** → **BOT-025** (gate/decisión de ejecución, downstream). ~~**BOT-049.1 — Economics Feature Discovery**~~ `DONE` (2026-09-21) — ver `reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY.md`. ~~**BOT-049.2 — Economics Definition Freeze**~~ `DONE` (2026-09-21) — resultado **`NO_VALID_ECONOMICS_FREEZE`**: bajo Config A y el diseño actual de la estrategia, ninguna candidata de Economics sobrevive con ownership propio — `risk_atr` es casi idéntico algebraicamente a `origin_dist_atr` de Structure (ρ=0.976–0.982, verificado exhaustivamente sobre las 3.207 filas, `REJECT_REDUNDANT`), la fricción de spread (`spread_over_risk`/`breakeven_pct`/`rr_effective_net`) es la MISMA cantidad que el término de costo de `cvp_score()` (verificado bit-exacto sobre las 3.207 filas, ownership asignado a CVP), `distance_to_limit_atr` se reclasificó como execution/fill-quality (no Economics), `origin_retracement_frac` reconfirmado `CROSS_FACTOR_ONLY` (sin error nuevo encontrado), y `rr_nominal/rr_geometric` siguen `REJECTED` (degenerados). Ver `reports/BOT-049.2-ECONOMICS-DEFINITION-FREEZE.md`. **`BOT-049` (feature padre) pasa a `DONE — NO_VALID_ECONOMICS_FREEZE`** — no queda ninguna dimensión Economics independiente para validar OOS bajo la evidencia actual; `BOT-049.3` pasa a `TODO — NO CONTRACT TO VALIDATE` (no hay definición congelada que validar, distinto de estar bloqueada por falta de datos OOS). ~~**BOT-050.1** — Context Feature Discovery~~ `DONE` (2026-09-21) — ver `reports/BOT-050.1-CONTEXT-FEATURE-DISCOVERY.md`. ~~**BOT-050.2** — Context Definition Freeze~~ `DONE` (2026-09-21) — resultado **`TEMPORAL_ONLY_FREEZE`**: solo `weekday`/efecto Viernes sobrevive ownership independiente frente a Momentum/Alignment/Structure (verificado con un modelo diagnóstico conjunto, no solo condicionamiento uno-a-la-vez); `atr_ratio_short_long` (volatilidad relativa ATR14/160, ligada al mecanismo HTF de Config A) queda `CROSS_FACTOR_ONLY` pese a evidencia causal/semántica sólida, por perder esa contribución marginal en el modelo conjunto; `session_utc`/Asia queda `CROSS_FACTOR_ONLY` (limitación DST). Ver `reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE.md`. **`BOT-050` (feature padre) pasa a `DONE — TEMPORAL_ONLY_FREEZE`**; `BOT-050.3` pasa a `TODO — BLOCKED_WAITING_GENUINE_NEW_DATA` (contrato congelado, esperando histórico genuinamente posterior a 2026-09-15). ~~**BOT-051.1 — Signal Quality Integration Design / Contract Discovery**~~ `DONE` (2026-09-21) — decisión **`VECTOR_FIRST`**: vector de 4 slots (Momentum/Alignment/Structure/Context, con `direction` como metadato adjunto), de los cuales 3 tenían contrato congelado y reconstruible ese día (Alignment `FREEZE_READY`, Structure `ORIGIN_ONLY_FREEZE`, Context `TEMPORAL_ONLY_FREEZE`) y 1 quedó **`PENDING_DEFINITION`** (Momentum — único factor sin Definition Freeze propio, gap detectado explícitamente en esta tarea). Economics confirmado excluido (`EXCLUDED_ABSORBED`, no pendiente). Ver `reports/BOT-051.1-signal-quality-integration-design.md`. ~~**BOT-024.4 — Momentum Definition Freeze**~~ `DONE` (2026-09-21, sesión separada del usuario) — cerró ese gap: **`FREEZE_READY`**, canónica `roc_atr_3` (RAW continua), ver `reports/BOT-024.4-MOMENTUM-DEFINITION-FREEZE.md`. ~~**BOT-051.2 — Signal Quality Definition Freeze**~~ `DONE` (2026-09-21) — decisión **`SIGNAL_QUALITY_VECTOR_V1_FREEZE`**: esquema tipado `SignalQualityVectorV1` congelado (los 4 slots ya poblables, ninguno OOS-validado), reconstrucción causal 2.474/2.474 exitosa (universo acotado por el artefacto de Alignment, N=2.474, no por contrato), 2.456/2.474 eventos con los 4 factores `AVAILABLE`, 17 invariantes congelados, sin redundancia fuerte entre los 4 contratos. Ver `reports/BOT-051.2-signal-quality-definition-freeze.md` y `reports/BOT-051.2-signal-quality-contract.json`. **`BOT-051` (feature padre) permanece `IN PROGRESS / RESEARCH`**; `BOT-051.3` pasa a **`TODO — NEXT ACTIVE`** (Shadow Reconstruction / Observability, sin score, sin gate). BOT-024 en sí (definición formal de Signal Quality 0–100) permanece `TODO`, no se implementa nada de esto todavía.
2. ~~**BOT-045** — Market regime / calidad de entradas~~ `DONE`. ~~**BOT-046** — Dirección/D1 + robustez temporal~~ `DONE` — recomendación: RESULTADO 2 (más historial), ver `docs/reports/BOT-046_direction_d1_temporal_robustness.md`. No se abre todavía una Prueba controlada de filtro/scoring; su continuación conceptual para la dimensión Alignment de Signal Quality es la secuencia **BOT-047.1 → BOT-047.2 → BOT-047.3** dentro de la feature padre `BOT-047` (ID nueva, no una reapertura de BOT-046 — ver esas entradas).
3. ~~**BOT-008** — Re-run completo del sweep~~ `DONE` — re-ejecutado con el motor corregido: ESCENARIO A marginal (edge real pero delgado, PF~1.05, dos configuraciones — `cfg_1260`/`cfg_1278` — positivas en USD en los 3 sub-períodos), ver `docs/reports/BOT-008_rerun_post_BOT043.md`. Próximo paso recomendado (no ejecutado): validación Out-of-Sample genuina sobre esas dos configuraciones, mismo criterio que `VALIDATION-D1-OOS` — no se abre automáticamente otro sweep ni se cambia producción.

   **Con BOT-008 cerrado, la línea de investigación/optimización sobre este espacio de parámetros queda CERRADA** (ver "DECISIÓN — Cierre temporal de optimización histórica" al final del archivo) — `cfg_1260`/`cfg_1278` y la hipótesis D1 quedan congeladas para `VALIDATION-CONFIG-OOS`/`VALIDATION-D1-OOS` (futuro, con datos OOS posteriores al 2026-09-15, no ejecutar todavía — misma barrera de datos que bloquea BOT-024.3). El proyecto retoma la secuencia funcional/operativa ya acordada — **próxima US activa: BOT-032** (punto 4 abajo).
4. ~~**BOT-032** — Kill switch / máxima pérdida~~ `DONE` (v1.1.0) — protección de capital, mejora independiente de la optimización de estrategia. Ver detalle en "Gestión de riesgo" abajo y `docs/reports/BOT-032_kill_switch.md`.
5. **BOT-025** — Gate configurable de scoring (`MEDIUM`) — sigue dependiendo de que BOT-024 defina una escala estable (todavía en investigación, ver punto 1).
6. **BOT-033** — Alerta de noticias económicas (`MEDIUM`).
7. **BOT-038** — Checklist de validación (`HIGH`) — revisar/redefinir considerando que el bot ya está operando en real.
8. **BOT-044** — Fix de conversión de comisión en CVP (`LOW` mientras `commission_usd` siga siendo 0).
9. **BOT-039 / BOT-040** — documentación/deuda técnica.

BOT-031 permanece `BLOCKED` porque actualmente no existe una segunda PC/terminal disponible para esa validación — decisión explícita de no crear infraestructura adicional (segunda instancia del bot/MT5, otra máquina, otra IP) solo para desbloquearlo; ver nota en el propio ítem. La investigación de estrategia (BOT-045 y lo que siga) se hace OFFLINE sobre datasets históricos y scripts de backtesting, sin necesitar una segunda sesión de MT5, y el bot productivo permanece aislado de estos experimentos.

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
- **Estado:** DONE — re-ejecutado 2026-09-15 con el motor corregido (BOT-043). Los resultados de las corridas anteriores (2026-08-18 y 2026-09-15 pre-BOT-043) quedan como evidencia histórica INVALIDADA, sin sobrescribir — ver actualización más abajo para el resultado válido.
- **Prioridad:** CRITICAL
- **Incorporado:** 2026-08-19 (ampliado 2026-09-03)
- **Versión objetivo/alcanzada:** sin release asociado (resultado de barrido, no cambio de código de producto)
- **Descripción:** El único barrido de backtest que existía (`docs/spec-backtest.md` §8, 3.780 combinaciones sobre M5 real) había corrido contra la lógica HTF **vieja** — reemplazada dos veces desde entonces: "bloque en formación" (BOT-005, 2026-08-19) y "alineado a sesión" (BOT-004, 2026-09-03). Re-ejecutado el 2026-09-15: datos frescos descargados (100.505 velas M5, `XAUUSDc`, 2025-04-14 a 2026-09-15), barrido completo (`03_run_sweep.py`) y prueba de robustez en 3 sub-períodos (`04_run_robustness.py`) — ambos corriendo ya contra `htf_session.py` (BOT-004).
- **Notas técnicas:** `backtests/scripts/03_run_sweep.py` y `04_run_robustness.py` tenían `SYMBOL = "XAUUSDm"` hardcodeado (bróker/cuenta vieja) — corregido para usar `resolve_symbol("XAUUSD")` (mismo mecanismo que BOT-011), resuelto en runtime antes de conectar, no como constante de import. Resultados en `backtests/results/sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv` — a pedido explícito del usuario, el contenido/interpretación del resultado no se documenta ni se discute acá (ver `docs/claude-memory/pivot-x-sentinel-no-backtest-talk.md`); el ítem se cierra por haberse *ejecutado*, no por el resultado obtenido. **Actualización 2026-09-15 (BOT-043):** el motor con el que corrió este barrido tenía el bug de costos de BOT-043 (swap acreditado en vez de cobrado + precio→USD subvaluado 100x). La corrida de control de BOT-043 sobre Config A con params idénticos confirma el impacto: mismo `n_trades`/`win_rate` (2.474 / 49.37%, esos no dependen de USD), pero Net R pasa de **+588.44 a −114.22** y Profit Factor de **1.476 a 0.912** con el motor corregido — es decir, este barrido (`sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv`) está corrido con el motor viejo y sus resultados **no son confiables** para ninguna combinación con trades `nights_held>0` (la gran mayoría de las 3.780). Este ítem se mantiene DONE porque el trabajo de *ejecutarlo* está hecho y no se re-abre solo, pero cualquier decisión que dependa de sus números debe esperar un re-run explícito con el motor corregido (fuera de alcance de BOT-043, ver nota de BOT-042). **Actualización 2026-09-15 (BOT-045):** el re-run completo de este barrido (3.780 combinaciones) queda pendiente pero se recomienda ejecutarlo **después** de revisar los hallazgos de BOT-045 (análisis de régimen de mercado/calidad de entrada) — antes de volver a correr 3.780 combinaciones, conviene entender si hay variables de régimen de mercado que expliquen buena parte del comportamiento de la estrategia. Esto no cancela ni degrada la prioridad de BOT-008 (sigue CRITICAL, sus resultados siguen invalidados) — solo ordena el trabajo operativo, ver "Prioridad actual de trabajo" más abajo. **Actualización 2026-09-15 (BOT-045 completado):** BOT-045 ya está `DONE` (ver ese ítem y `docs/reports/BOT-045_market_regime_analysis.md`) — encontró evidencia consistente (dirección LONG/SHORT, alineación con tendencia D1) pero ningún filtro fue implementado, es diagnóstico puro. El re-run completo de BOT-008 sigue pendiente y puede retomarse ahora que se revisó BOT-045. **Actualización 2026-09-15 (re-run completo con motor corregido):** ejecutadas las 3.780 combinaciones originales (`backtests/scripts/10_bot008_full_sweep_rerun.py`, commit base `a0e32f6`+) — **hallazgo metodológico:** el espacio efectivamente único es 1.260, no 3.780 (`max_concurrent_por_direccion` no tiene ningún efecto mientras `una_operacion_a_la_vez=True`, el default de producción). **71/1.260 (5.6%) configuraciones únicas tienen expectancy positiva** — la gran mayoría del espacio sigue sin edge. Existe una región concreta (EMA≈14-17, HTF=200, Buffer bajo, **RR=0.5**) que pasa la mayoría de los filtros de robustez pre-definidos: MESETA en vecindad (9/11 finalistas), y **dos configuraciones específicas (`cfg_1260`: EMA=14/HTF=200/Buf=0.2/RR=0.5 y `cfg_1278`: EMA=14/HTF=200/Buf=0.7/RR=0.5) positivas en USD en los 3 sub-períodos** — aunque solo 2/3 en R (única R-3/3 de las 1.260, `cfg_2250`, resultó perdedora neta en USD — hallazgo que subraya por qué se verificaron ambas métricas). **Clasificación: ESCENARIO A marginal** — edge real pero delgado (PF~1.05), no listo para producción, requiere validación Out-of-Sample genuina antes de cualquier cambio real (mismo criterio que `VALIDATION-D1-OOS`). Ningún parámetro de producción fue modificado; ningún filtro/config nueva se implementó automáticamente. **Reporte completo (documento maestro, autocontenido):** `docs/reports/BOT-008_rerun_post_BOT043.md`.

**Resumen breve del resultado válido (post-BOT-043, confirmado 2026-09-15):**
- Sweep original: 3.780 combinaciones definidas (`docs/spec-backtest.md` §4.1, sin modificar).
- 1.260 configuraciones efectivamente únicas (`max_concurrent_por_direccion` resultó inerte).
- 71/1.260 (5.6%) con expectancy positiva después de costos.
- Región favorable identificada: EMA 14–17, HTF 200, RR 0.5, Buffer bajo.
- `cfg_1260` (EMA=14/HTF=200/Buf=0.2/RR=0.5) y `cfg_1278` (EMA=14/HTF=200/Buf=0.7/RR=0.5) quedaron como principales candidatos — únicos positivos en USD en los 3 sub-períodos.
- Resultado clasificado como **ESCENARIO A marginal**.
- **Ninguna configuración pasa a producción todavía.**
- **La optimización histórica de este espacio de parámetros (EMA/HTF/Buffer/RR sobre este mismo dataset) queda CERRADA** — no se vuelve a barrer, expandir rangos, ni re-analizar sin una hipótesis nueva claramente justificada (ver "DECISIÓN — Cierre temporal de optimización histórica" al final del archivo).
- Próxima validación de `cfg_1260`/`cfg_1278`: con datos OOS genuinos posteriores al 2026-09-15 — ver `VALIDATION-CONFIG-OOS` al final del archivo. No ejecutar todavía.
- **Dependencias:** BOT-004, BOT-005. Ver BOT-043 (bug de costos, ya corregido — motor usado para este re-run), BOT-042 (re-run parcial ya hecho, aislado en RR) y BOT-045/BOT-046 (revisados antes del re-run completo del barrido, hipótesis congeladas, no incorporadas acá).

### BOT-009 — Motor de backtest con costos reales (implementación)
- **Categoría:** Backtest
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-08-17
- **Versión objetivo/alcanzada:** 1.0.0
- **Descripción:** Motor implementado en `/backtests`, corrido sobre datos reales de XAUUSDm M5 (1.4 años, 100k velas). El *motor* está terminado y probado; el *resultado* de ese barrido específico está obsoleto (ver BOT-008).
- **Notas técnicas:** `docs/spec-backtest.md` §8 documenta el resultado del barrido viejo (sin edge robusto — hallazgo estructural del armado persistente, no un bug).
- **Dependencias:** ninguna.

### BOT-042 — Comparación A/B controlada y optimización aislada de RR sobre Config A
- **Categoría:** Backtest
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo/alcanzada:** sin release asociado (análisis, no cambio de código de producto)
- **Descripción:** Análisis puntual a pedido del usuario, en dos partes: (1) comparación A/B controlada entre la config real del bot (EMA=12, HTF=800, Buffer=0.4, RR=1.0) y la ganadora de BOT-008 (EMA=17, HTF=800, Buffer=2.2, RR=3.0); (2) aislar el efecto de RR sobre Config A manteniendo EMA/HTF/Buffer fijos y variando solo RR∈{1,2,3,4,5,7}, B únicamente como referencia. Corrida original (2026-09-14) con el motor contaminado por BOT-043 — invalidada. **Re-ejecutada 2026-09-15 con el motor ya corregido** (commit `a0e32f6`), cerrando el ítem.
- **Notas técnicas:** Re-run completo: dataset `backtests/data/XAUUSDc_M5_latest.parquet` (100.505 velas M5, 2025-04-14 a 2026-09-15, mismo dataset que BOT-008/la corrida original), Config A fija (EMA=12/HTF=800/Buffer=0.4) con RR∈{1,2,3,4,5,7}, cada una corrida además sobre los mismos 3 sub-períodos que `04_run_robustness.py`, más Config B como referencia opcional (motor corregido, no forma parte del experimento principal). Verificación previa (branch `main`, `strategy/costs.py::price_to_usd()`, signo de swap, y los tests `test_costs.py`/`test_engine.py`/`test_diagnostics.py`) documentada y pasada antes de correr. **Conclusión: cambiar únicamente RR NO arregla Config A de forma robusta.** RR=1 a 5 dan expectancy negativa; RR=7 es el único positivo en el agregado (Exp R=+0.0425, PF=1.049, Net R=+36.99) pero **no se sostiene en los 3 sub-períodos** (positivo en sub1/sub2, negativo en sub3) y depende de un tramo (sub2) que favorece a TODAS las configuraciones probadas, incluida B — evidencia de régimen de mercado, no de edge de RR=7 específicamente. Clasificado INTERESANTE, no CANDIDATO. B (referencia, motor corregido) también da negativo en el agregado y en los 3 sub-períodos — su ventaja aparente en el barrido original de BOT-008 era en gran parte artefacto del bug. Script nuevo y versionado: `backtests/scripts/05_run_rr_isolation.py`. Resultados en `backtests/results/rr_summary_post_BOT-043_M5.csv`, `rr_subperiods_post_BOT-043_M5.csv`, `rr_loss_streaks_post_BOT-043_M5.csv`, `rr_cost_and_r_dist_post_BOT-043_M5.csv`, `rr_isolation_post_BOT-043_M5.json` (sufijo `post_BOT-043` para no pisar los CSV contaminados de la corrida original, que se dejan intactos como referencia histórica). **Reporte completo (documento maestro de esta tarea, autocontenido):** `docs/reports/BOT-042_rerun_RR_post_BOT-043.md`.
- **Dependencias:** BOT-008 (resultado histórico contaminado, sigue sin re-correrse — este ítem solo re-corrió Config A aislada en RR, no el barrido completo de 3.780 combinaciones), BOT-043 (resuelto, motor usado para este re-run).

### BOT-043 — Bug: signo invertido del swap + escala de riesgo (1R) inconsistente en el motor de backtest
- **Categoría:** Backtest
- **Estado:** DONE
- **Prioridad:** CRITICAL
- **Incorporado:** 2026-09-14
- **Versión objetivo/alcanzada:** ver `CHANGELOG.md`/`VERSION` (corrección del motor de backtest, no de la estrategia live)
- **Descripción:** Encontrado durante BOT-042 al validar el cálculo de R a pedido del usuario. Dos causas raíz confirmadas, ambas en `strategy/engine.py` / `strategy/costs.py`:
  1. **Signo del swap invertido.** `close_open_trade()` hacía `pnl_usd -= costs.swap_total_usd(...)`, pero `swap_total_usd()` ya devuelve el monto CON signo (negativo = costo real, ej. `swap_long=-533.9` en XAUUSDc). Restar un número ya negativo lo acreditaba al trade en vez de cobrárselo.
  2. **Precio→USD vía `contract_size` en vez de `tick_value/tick_size`.** `risk_usd()` y el cálculo de `pnl_usd` multiplicaban `price_diff * contract_size * fixed_lot`. Validado contra `mt5.order_calc_profit()` (referencia de la propia plataforma, ver `strategy/test_costs.py::test_i_live_order_calc_profit_cross_check`): para XAUUSDc de esta cuenta (símbolo en la categoría `Cent\Forex\XAUUSDc` del bróker), `contract_size=1.0` pero `tick_value/tick_size=100` — la fórmula vieja infravaloraba el PnL/riesgo real en precio por **exactamente 100x**, confirmado en múltiples combinaciones de lote/movimiento de precio contra `order_calc_profit()`. Este era el origen real de que el swap pareciera "demasiado grande" frente a 1R: no era que el swap estuviera mal escalado, era que el riesgo en precio estaba subvaluado 100x mientras el swap (que ya usaba `tick_value` directamente) no.
- **Fix:** Nuevo método único de conversión `BrokerCosts.price_to_usd(price_diff, lot)` (`price_diff / tick_size * tick_value * lot`), usado tanto para `raw_risk` como para el PnL de precio — un solo punto de verdad. `swap_usd_per_lot_per_night()` reescrito para pasar por la misma conversión (antes coincidía con la fórmula correcta solo porque `tick_size==point` en XAUUSDc; ahora es general). `close_open_trade()`: `pnl_usd += costs.swap_total_usd(...)` (antes `-=`). Campo nuevo `BrokerCosts.tick_size`; `contract_size` se conserva en el dataclass solo a título informativo, ya no se usa para convertir precio→USD.
- **Archivos modificados:** `strategy/costs.py` (campo `tick_size`, método `price_to_usd()`, `swap_usd_per_lot_per_night()` reescrito, docstrings), `strategy/engine.py` (`risk_usd()` y `close_open_trade()` usan `price_to_usd()`, signo de swap corregido), `backtests/scripts/03_run_sweep.py` y `04_run_robustness.py` (pasan `tick_size=si.trade_tick_size` al construir `BrokerCosts`), `strategy/test_engine.py` y `strategy/test_diagnostics.py` (`ZERO_COST` con `tick_size=1.0`).
- **Archivo nuevo:** `strategy/test_costs.py` — 9 tests: (A) `price_to_usd()` contra valores de referencia de `mt5.order_calc_profit()` capturados en vivo + no regresión en un símbolo "estándar" sintético; (B) swap_long negativo da costo negativo; (C) swap_short usa el campo correcto (dirección); (D) `nights_held=0` → `swap_total_usd()==0.0` exacto; (E) día de triple swap cobrado 3x, resto 1x; (F/G) cadena completa de PnL (bruto→spread→swap firmado→comisión→neto→1R→R realizado) para un ganador y un perdedor, contra cálculo manual independiente, corrida end-to-end por `run_backtest`; (H) swap negativo reduce el PnL de un LONG overnight frente al mismo trade sin swap; (I) cross-check en vivo contra `mt5.order_calc_profit()` (se salta sola si no hay MT5 conectado, no bloquea la suite).
- **Tests — resultado de la suite completa (9 scripts, los 8 preexistentes + el nuevo):** `strategy/test_engine.py`, `strategy/test_htf_session.py`, `strategy/test_diagnostics.py`, `strategy/test_scoring.py`, `strategy/test_costs.py`, `execution/src/test_mt5_validation.py`, `execution/src/test_timestamp_offset.py`, `api/test_start_mt5_validation.py`, `scripts/test_release_lib.py` — **TODOS OK**, sin fallos, corridos antes y después del fix (los 8 preexistentes no cambiaron su resultado, cero regresiones).
- **Evidencia de la corrección — corrida de control (Config A: EMA=12, HTF=800, Buffer=0.4, RR=1, mismo dataset `XAUUSDc_M5_latest.parquet`):**

  | Métrica | Motor anterior (con bug) | Motor corregido |
  |---|---:|---:|
  | Trades | 2,474 | 2,474 |
  | Win Rate | 49.37% | 49.37% |
  | Net R | 588.44 | **−114.22** |
  | Expectancy R/trade | 0.238 | **−0.046** |
  | Profit Factor | 1.476 | **0.912** |
  | Max Drawdown (R) | 27.93 | 140.66 |
  | Recovery Factor | 21.07 | **−0.81** |
  | Max Losing Streak | 10 | 10 (sin cambio — depende solo de outcome win/loss, no de USD) |
  | % trades overnight | 6.8% | 6.8% (sin cambio — no depende de USD) |

  Con el motor corregido, Config A (la configuración real del bot) da **expectancy negativa** sobre este dataset — el resultado positivo reportado antes era en gran parte artefacto del bug. Trades/WR/% overnight no cambian (no dependen de USD); todo lo que sí depende de la conversión precio→USD o del swap cambia sustancialmente.
- **Impacto conocido:** No afecta la cuenta real / ejecución en vivo (el swap ahí lo aplica el bróker directamente, este código solo corre en `/backtests`). Sí invalida los resultados ya publicados de BOT-008 (`sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv`) para cualquier combinación con trades `nights_held>0` — BOT-008 actualizado con esta nota, marcado como requiere re-run. BOT-042 (comparación A/B + Etapa 1 de RR) sigue BLOCKED — el motor ya está corregido pero ese experimento específico no se re-ejecutó en esta tarea (fuera de alcance explícito, ver notas de BOT-042).
- **Revisión adicional (pedida explícitamente antes de cerrar):** se re-examinó el comportamiento ya documentado "stop del lado incorrecto / stop recalculado dentro del bloque HTF" (`docs/spec-backtest.md` §4.4) para descartar que también invalidara matemáticamente `realized_r`. Conclusión: **no lo hace** — con `entrada_viva=False` (el caso de A y B), entry/stop/target quedan congelados en el momento de la señal, ambos derivados de la misma barra `i` (mismo `resistencia[i]`/`soporte[i]`/`ema_line[i]`); `raw_risk` y `pnl_r` son internamente consistentes con esos valores congelados. Ese comportamiento es una característica de diseño de la estrategia (por qué algunas señales quedan descartadas por `n_skip_stop`), no un defecto de contabilidad — no se creó un BOT-XXX nuevo para esto. Corrección de una atribución anterior: en el análisis de BOT-042 se había atribuido parte de los "loss" con R positivo de Config B a este comportamiento — con la evidencia de esta tarea, ese patrón se explica enteramente por el bug de signo de swap (punto 1 arriba), no por el stop del lado incorrecto.
- **Hallazgo independiente NO corregido acá (ver BOT-044):** `strategy/scoring.py::cvp_score()` usa el mismo patrón `commission_usd/(contract_size*fixed_lot)` para convertir comisión a precio — mismo problema de fondo, pero en código que corre en VIVO (`execution/src/bot.py`), fuera de alcance de esta tarea (que se restringió a "exclusivamente el modelo/cálculo del backtest"). Actualmente sin impacto real porque `execution/src/bot.py` pasa `commission_usd=0.0` hardcodeado. Ver BOT-044.
- **Dependencias:** BOT-007, BOT-009. Desbloqueaba BOT-042 (parcialmente — ver nota de BOT-042) y reabre BOT-008.

### BOT-045 — Análisis de régimen de mercado y calidad de entradas
- **Categoría:** Backtest / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-15
- **Versión objetivo/alcanzada:** sin release asociado (estudio diagnóstico offline, no cambio de código de producto)
- **Descripción:** Análisis OFFLINE sobre las operaciones históricas de la estrategia (motor de backtesting corregido post BOT-043) para identificar qué condiciones de mercado están asociadas con operaciones ganadoras y perdedoras. El objetivo **no** es optimizar parámetros todavía ni agregar indicadores directamente a la estrategia — es generar evidencia que permita formular hipótesis antes de plantear nuevos sweeps u optimizaciones. Debe estudiar, como mínimo: tendencia diaria D1, dirección/tendencia HTF, relación de la entrada con la tendencia diaria, RSI, ADX, ATR/régimen de volatilidad, sesión de mercado, hora de entrada, día de semana, LONG vs SHORT, distancia del precio respecto a la EMA, características del bloque HTF, y los factores existentes de scoring cuando sea posible (Divergencia, Tendencia, CVP, Nodo — ver BOT-023). Debe comparar estas características entre: winners vs losers; sub1 vs sub2 vs sub3 de BOT-042; LONG vs SHORT; diferentes sesiones/horarios; diferentes regímenes de tendencia y volatilidad.
  - **Pregunta principal:** ¿qué condiciones de mercado distinguen los períodos y operaciones donde la estrategia tiene edge de aquellos donde pierde?
  - **Pregunta secundaria (especialmente importante):** ¿qué características tuvo sub2 — favorable para varias configuraciones en BOT-042 (único sub-período positivo en casi todas las variantes de RR probadas, incluida B) — que no estuvieron presentes de la misma manera en sub1 y sub3?
- **Restricción fundamental:** debe ser explícitamente un estudio diagnóstico. NO debe: modificar la estrategia; agregar filtros al live bot; cambiar EMA/Buffer/HTF/RR/scoring; bloquear operaciones; optimizar combinaciones; seleccionar automáticamente una nueva configuración; modificar producción. Siempre que sea técnicamente correcto, los indicadores de temporalidades superiores deben derivarse de los datos históricos disponibles sin requerir una segunda instancia de MT5 (ver también la decisión de arquitectura documentada en "Prioridad actual de trabajo" más abajo). Debe evitar look-ahead bias explícitamente — por ejemplo, cualquier indicador D1 usado para evaluar una entrada M5 debe usar exclusivamente información que habría estado disponible en el momento de esa entrada. Si para alguna variable no existe información histórica suficiente, la limitación debe documentarse en vez de aproximar o inventar datos en silencio.
- **Notas técnicas:** Sobre scoring — BOT-023 ya contiene información potencialmente útil (Divergencia, Tendencia, CVP, Nodo). BOT-045 debe revisar si esos factores tienen poder explicativo sobre winners/losers **antes** de decidir si BOT-024/BOT-025 deben usarse para filtrar operaciones; no debe asumirse que un score mayor implica mejor performance — debe comprobarse estadísticamente. Sigue la regla de experimentación documentada más abajo (Diagnóstico → Hipótesis → Prueba controlada → Robustez → Validación → Cambio en producción) — este ítem cubre únicamente la etapa de Diagnóstico/Hipótesis, no las posteriores.
- **Dependencias:** BOT-042 (encontró que cambiar únicamente RR no solucionó Config A de forma robusta — RR=1 a RR=5 negativos en agregado, RR=7 el único positivo en agregado pero no robusto temporalmente, negativo en sub3 — BOT-045 investiga si existe una explicación de régimen de mercado/calidad de entrada antes de seguir modificando parámetros), BOT-043 (motor de costos corregido, requisito para que cualquier métrica de PnL/R de este análisis sea confiable), BOT-023 (factores de scoring a evaluar).
- **Resultado (2026-09-15):** dataset enriquecido de 2.474 operaciones (Config A congelada) con 14 categorías de variables de régimen calculadas de forma causal (RSI, ADX y ATR nuevos -- no existían en `/strategy`, agregados solo en los scripts de este análisis; el resto reusa `strategy/scoring.py` sin modificarlo). Hallazgos de mayor confianza (evidencia A, consistente en los 3 sub-períodos): **dirección** (SHORT expectancy +0.004R vs LONG −0.100R) y **alineación con la tendencia D1** (alineado +0.067R vs en contra −0.183R, cubre 26% de la muestra). ADX (relación inversa) y sesión (Asia peor) quedan en evidencia B. Distancia a EMA, el factor "Tendencia" de scoring y CVP (sin variación a RR=1) quedan sin evidencia útil (D). `sub2` se explica parcialmente por volatilidad relativa (ATR%) sustancialmente más alta que `sub1`/`sub3` y una mezcla direccional más favorable (más SHORT, D1 menos bajista) -- ninguna variable lo explica por completo, y la alineación con D1 específicamente **no** lo explica (sub2 tiene más operaciones en contra de D1, no menos). Ningún filtro fue implementado -- estudio 100% diagnóstico, cubre solo la etapa Diagnóstico/Hipótesis de la regla de experimentación. **Reporte completo (documento maestro de esta tarea, autocontenido):** `docs/reports/BOT-045_market_regime_analysis.md`. Scripts nuevos: `backtests/scripts/07_bot045_regime_dataset.py`, `backtests/scripts/08_bot045_analysis.py`. Seguido inmediatamente por **BOT-046** (validación de robustez temporal de estas dos hipótesis).

### BOT-046 — Dirección/D1 + robustez temporal (validación de las hipótesis de BOT-045)
- **Categoría:** Backtest / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-15
- **Versión objetivo/alcanzada:** sin release asociado (estudio diagnóstico offline, no cambio de código de producto)
- **Descripción:** Sometió las dos hipótesis de mayor confianza de BOT-045 (H1 dirección LONG/SHORT, H2 alineación con D1) a mayor resolución temporal (sextiles T1-T6, rolling windows de 3 meses con avance mensual), un split cronológico pseudo-OOS 70/30 (development/holdout) y bootstrap de bloques (moving block bootstrap, 10.000 resamples, largo de bloque `round(√N)`) sobre la diferencia de expectancy entre grupos. Reutilizó el dataset enriquecido de BOT-045 tal cual (sin recalcular ningún indicador), con un sanity check previo que reprodujo exactamente los números de BOT-045. Config A permaneció completamente congelada.
- **Resultado:** ninguna hipótesis fue refutada. **H2 (alineación D1) resultó la más robusta: evidencia A** -- signo positivo (alineado > contra) en el 100% de los cortes evaluados (3 sub-períodos, 6 sextiles, 16 ventanas rolling válidas), aunque el bootstrap deja de excluir cero en `sub3`/`holdout` por menor tamaño de muestra (no por reversión). **H1 (dirección) resultó prometedora pero más frágil: evidencia B** -- positivo en 17/18 ventanas rolling pero sin significancia estadística en `sub1`/`sub2`/`development`, solo significativo en el agregado completo y en el tramo más reciente (`sub3`/`holdout`) -- el efecto parece emerger/fortalecerse con el tiempo, no estar presente desde el inicio. **H3 (interacción):** hallazgo más nítido -- `LONG+contra D1` es catastrófico y consistente en los 6 cortes evaluados (−0.25R a −0.55R); `SHORT+alineado D1` es el mejor grupo, también consistente en los 6 cortes (+0.10R a +0.28R); pero `LONG+alineado D1` NO es consistentemente malo (positivo hasta `sub2`, negativo recién en `sub3`/`holdout`) y `SHORT+contra D1` nunca es claramente positivo -- el efecto no es aditivo. Dato adicional: LONG tiene proporcionalmente MÁS operaciones alineadas con D1 que SHORT (16.2% vs 10.0%), así que la ventaja de SHORT no se explica por una mezcla de D1 más favorable -- sugiere que Dirección aporta información al menos parcialmente independiente de D1. **Recomendación: RESULTADO 2 -- más historial**, ni se descarta (RESULTADO 3) ni se justifica todavía abrir una Prueba controlada de filtro/scoring (RESULTADO 1). Ningún filtro fue implementado. **Reporte completo (documento maestro de esta tarea, autocontenido):** `docs/reports/BOT-046_direction_d1_temporal_robustness.md`. Script nuevo: `backtests/scripts/09_bot046_direction_d1_robustness.py`.
- **Dependencias:** BOT-045 (hipótesis de origen, dataset reutilizado sin recalcular).

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

### BOT-024 — Signal Quality: evolucionar el scoring aditivo hacia una escala 0–100
- **Categoría:** Scoring
- **Estado:** TODO
- **Prioridad:** LOW
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** El pedido original era simplemente normalizar el score aditivo actual (`total=+2`, `-1`, etc.) a una escala tipo `Signal Score: 82/100`. El diseño evolucionó desde entonces (ver subtareas abajo): **antes de definir cualquier fórmula de normalización o peso, primero se está investigando qué dimensiones tienen evidencia suficiente para formar el futuro `Signal Quality`.** La arquitectura conceptual actualmente considerada (todavía diseño/investigación, nada implementado) es:
  - **Momentum** — velocidad/persistencia/aceleración del movimiento de precio en `limit_created_bar` (BOT-024.2/BOT-024.3).
  - **Alignment** — si la dirección del trade está a favor o en contra del contexto direccional de mayor plazo (D1) (BOT-047, feature padre, sucesora conceptual de BOT-045/BOT-046).
  - **Structure** — ubicación estructural del `LIMIT` dentro de la estructura M5 reciente del precio (swings, rango, origen de la ruptura que armó la señal) — distinta de Alignment D1 pese al nombre parecido (BOT-048, feature padre).
  - **Economics** — geometría económica del setup disponible causalmente al crear el LIMIT: RR, costos, spread, stop (`BOT-049`, feature padre, `DONE — NO_VALID_ECONOMICS_FREEZE`: bajo Config A y el diseño actual de la estrategia, la escala de riesgo (`risk_atr`) resultó casi idéntica a Structure (`origin_dist_atr`) y la fricción de spread resultó la misma cantidad que el factor CVP de BOT-023 — no queda ninguna representación numérica propia de Economics, ver `BOT-049.2`).
  - **Context** — condiciones ambientales/de mercado alrededor de la señal: sesión, hora, régimen, volatilidad (`BOT-050`, feature padre, `DONE — TEMPORAL_ONLY_FREEZE`: de los candidatos evaluados, solo `weekday`/efecto Viernes sobrevivió ownership independiente frente a Momentum/Alignment/Structure bajo un modelo diagnóstico conjunto; la volatilidad relativa —`atr_ratio_short_long`— y la sesión Asia quedaron `CROSS_FACTOR_ONLY`, ver `BOT-050.2`).

  No se asignan pesos ni se implementa ninguna de estas dimensiones en esta entrada — es únicamente el marco conceptual que están llenando las subtareas de investigación. Roadmap acordado (formalizado 2026-09-20) para completar las 5 dimensiones e integrarlas: `BOT-049` (Economics) → `BOT-050` (Context) → `BOT-051` (Signal Quality Integration) → `BOT-025` (gate/decisión de ejecución, downstream — ver esas entradas). `BOT-049` y `BOT-050` ya cerraron (ver esas entradas); esta actualización de la descripción refleja ese cierre.
- **Dependencias:** BOT-023.
- **Subtareas/experimentos:**
  - `BOT-024.1` `DONE` — auditoría y evaluación predictiva de Divergencia RSI (insumo de diagnóstico, no es Momentum en sí).
  - `BOT-024.2` `DONE` — Momentum Feature Discovery XAU (BTC bloqueado).
  - `BOT-024.3` `BLOCKED` — Momentum Out-of-Sample Validation (esperando histórico genuinamente nuevo; ahora tiene un contrato congelado que validar, ver `BOT-024.4`).
  - `BOT-024.4` `DONE` — Momentum Definition Freeze (resultado `FREEZE_READY`: canónica `roc_atr_3`, RAW continua; cierra el gap identificado por `BOT-051.1`).
  - `BOT-047` `IN PROGRESS / RESEARCH` — D1 Alignment (feature padre, ver "Convención para features experimentales" más abajo):
    - `BOT-047.1` `DONE` — D1 Alignment Feature Discovery.
    - `BOT-047.2` `DONE` — D1 Alignment Definition Freeze (resultado `PROVISIONAL`).
    - `BOT-047.2.1` `DONE` — Structural Alignment Definition & Legacy Decomposition (subtarea experimental interna de `BOT-047.2`, resultado `PROVISIONAL`).
    - `BOT-047.2.2` `DONE` — D1 Structural Boundary Validation (subtarea experimental interna de `BOT-047.2`, resultado `PROVISIONAL`).
    - `BOT-047.2.3` `DONE` — Structural Alignment Consensus Definition Freeze (subtarea experimental interna de `BOT-047.2`, resultado `FREEZE_READY`).
    - `BOT-047.3` `READY / WAITING FOR OOS` — D1 Alignment Out-of-Sample Validation (definición congelada por `BOT-047.2.3`; espera histórico genuinamente posterior al 2026-09-15).
  - `BOT-048` `IN PROGRESS / RESEARCH` — Structure (feature padre, ver "Convención para features experimentales" más abajo):
    - `BOT-048.1` `DONE` — Structure Feature Discovery.
    - `BOT-048.2` `DONE` — Structure Definition Freeze (resultado `ORIGIN_ONLY_FREEZE`).
    - `BOT-048.3` `PENDING / WAITING OOS` — Structure OOS Validation (contrato congelado por `BOT-048.2`; espera histórico genuinamente posterior al 2026-09-15).
  - `BOT-049` `DONE — NO_VALID_ECONOMICS_FREEZE` — Economics (feature padre, ver "Convención para features experimentales" más abajo):
    - `BOT-049.1` `DONE` — Economics Feature Discovery.
    - `BOT-049.2` `DONE` — Economics Definition Freeze (resultado `NO_VALID_ECONOMICS_FREEZE` — ninguna candidata sobrevive con ownership propio bajo Config A/diseño actual, ver esa entrada).
    - `BOT-049.3` `TODO — NO CONTRACT TO VALIDATE` — Economics OOS Validation (no aplica: no hay definición congelada que validar, distinto de estar bloqueada por falta de histórico OOS).
  - `BOT-050` `DONE — TEMPORAL_ONLY_FREEZE` — Context (feature padre, ver "Convención para features experimentales" más abajo):
    - `BOT-050.1` `DONE` — Context Feature Discovery.
    - `BOT-050.2` `DONE` — Context Definition Freeze (resultado `TEMPORAL_ONLY_FREEZE` — solo `weekday`/Viernes sobrevive ownership independiente, ver esa entrada).
    - `BOT-050.3` `TODO — BLOCKED_WAITING_GENUINE_NEW_DATA` — Context OOS Validation (contrato congelado por `BOT-050.2`; espera histórico genuinamente posterior al 2026-09-15).
  - `BOT-051` `IN PROGRESS / RESEARCH` — Signal Quality Integration (feature padre; adopta subestructura `.1/.2/.3` — ver esa entrada):
    - `BOT-051.1` `DONE` — Signal Quality Integration Design / Contract Discovery (decisión: `VECTOR_FIRST`, ver `reports/BOT-051.1-signal-quality-integration-design.md`).
    - `BOT-051.2` `DONE` — Signal Quality Definition Freeze (decisión: `SIGNAL_QUALITY_VECTOR_V1_FREEZE`, ver `reports/BOT-051.2-signal-quality-definition-freeze.md`).
    - `BOT-051.3` `TODO — NEXT ACTIVE` — Signal Quality Vector Shadow Reconstruction / Observability.

  BOT-024 en sí (la definición formal de Signal Quality 0–100) sigue `TODO` — no se cierra hasta tener evidencia suficientemente validada (OOS) de al menos Momentum y Alignment. Su continuación pasa ahora por `BOT-051.3`, próximo trabajo activo del proyecto tras el cierre de `BOT-051.2`.

### BOT-024.1 — Evaluación predictiva A/B de Divergencia RSI
- **Categoría:** Scoring
- **Estado:** DONE
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-19
- **Versión objetivo:** N/A (experimento/diagnóstico, no cambia producción)
- **Descripción:** Subtarea trazable de `BOT-024` (Signal Quality). Encadena tres auditorías 100% READ-ONLY sobre `strategy/scoring.py` (ninguna modificó producción): (1) auditoría de la implementación de Divergencia RSI (`reports/AUDIT-RSI-DIVERGENCE.md`) — causal, RSI Wilder correcto, encontró y luego se corrigió (commit aparte) una prioridad accidental bullish-sobre-bearish en divergencias simultáneas; (2) auditoría A/B de fuente de precio, `close` (actual) vs. `low`/`high` (`reports/AUDIT-RSI-PRICE-SOURCE.md`) — ambas definiciones detectan conjuntos de divergencias materialmente distintos (3.4% de discrepancia sobre 100 474 barras reales), sin relación de subconjunto en ninguna dirección; (3) esta evaluación predictiva (`reports/BOT-024.1-RSI-DIVERGENCE-PREDICTIVE.md`) — sobre los 2474 trades cerrados/evaluables que `strategy.engine.run_backtest` genera con "Config A" (mismo dataset y configuración que BOT-042/043/045), congelando Divergencia A/B causalmente en `limit_created_bar` (verificado exhaustivamente contra `divergence_detail()` real de producción, 0 discrepancias en 2474/2474).
- **Resultado (2026-09-19):** la cohorte `OPPOSED` (divergencia en contra de la dirección del trade) es la más informativa: expectancy negativa con intervalo de confianza bootstrap 95% que excluye cero (por-trade y por-evento, clustering mínimo — máx. 2 trades por evento), consistente en signo en los 3 subperíodos cronológicos y en LONG/SHORT, aunque solo alcanza significancia estadística aislada dentro de LONG (N=55/52). Hallazgo no anticipado: el agregado `ALIGNED` es casi neutro frente al baseline, pero esconde dos efectos opuestos que se cancelan — dentro de LONG, `ALIGNED` rinde **peor** que el baseline de LONG (IC95% excluye cero, contrario a la intuición de "señal a favor"), mientras que dentro de SHORT rinde mejor (sin significancia). A y B (`close` vs. `low`/`high`) muestran comportamiento cualitativamente muy similar — A con un efecto `OPPOSED` levemente más marcado. Ningún patrón se clasificó por encima de `PROMISING` (ver tabla de clasificación en el reporte); ninguno se convirtió en peso de scoring. No se implementó Momentum, no se integró D1, no se activó ningún gate. **Reporte completo:** `reports/BOT-024.1-RSI-DIVERGENCE-PREDICTIVE.md`. Script: `scripts/evaluate_rsi_divergence_predictive.py`. Dataset por trade: `reports/BOT-024.1-RSI-DIVERGENCE-PREDICTIVE.csv`.
- **Notas técnicas:** Reusa `strategy.engine.run_backtest`/`strategy.scoring.*` sin modificarlos. Universo de trades fijo entre A y B (feature attribution, no gating) — deliberadamente NO se corrió "bot filtrando con A" vs. "bot filtrando con B" (eso mezclaría calidad de señal con cambio de universo de operaciones; queda para un experimento separado si la evidencia lo justifica).
- **Siguiente paso planificado dentro de BOT-024 (ya ejecutado, ver abajo):** Momentum — definir qué papel merece Divergencia RSI ahí, considerando en particular el hallazgo de `OPPOSED` y la interacción con la dirección del trade. Continuado en `BOT-024.2` (Momentum Feature Discovery), que reconfirmó la interacción `OPPOSED` × Momentum como hipótesis de agotamiento (N pequeño, no validada) — ver esa entrada.
- **Dependencias:** BOT-023 (factores de scoring existentes).

### BOT-024.2 — Momentum Feature Discovery XAU + BTC
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-19
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-024` (Signal Quality), sucesora directa de `BOT-024.1`. Estudio 100% offline, causal y read-only respecto a producción, congelado en `limit_created_bar` (`== signal_bar == born_bar`, mismo punto de congelación validado en BOT-024.1) — sin construir `MomentumScore`, sin asignar pesos, sin activar gating. Objetivo: identificar qué propiedades observables del movimiento de precio (velocidad/ROC, pendiente de EMA, persistencia/eficiencia, aceleración, RSI extendido, volatilidad ATR) muestran evidencia de Momentum predictivo, separando explícitamente Universo A (todos los LIMITS creados, para probabilidad de fill) de Universo B (trades filled/cerrados, para desempeño condicional).
  - **Decisión de activo prioritario (permanente, ver también más abajo):** XAUUSD es el activo prioritario del bot para diseño, investigación y validación. La estrategia nació originalmente para BTC (que el bot puede seguir operando ocasionalmente), pero ninguna decisión de scoring/estrategia debe degradarse para forzar simetría con BTC.
  - **Estado BTC en esta tarea:** bloqueado y documentado, no inventado. Verificado en vivo (solo lectura, sin órdenes) contra la cuenta conectada: `BTCUSD` resuelve ambiguamente a dos símbolos (`BTCUSDc` / `BTCUSDTc`), no existe dataset histórico BTC validado en el repositorio, y no existe ninguna configuración de estrategia BTC equivalente a "Config A". Por esto BOT-024.2 continuó correctamente solo con XAU (activo prioritario).
  - **Universos:** Universo A = 3.207 LIMITS creados; Universo B = 2.474 trades filled + cerrados (mismo universo exacto que BOT-024.1/BOT-045, mismo motor/dataset/Config A). Paridad del "shadow replay" (reconstruye el detalle de LIMITS que `run_backtest()` no retiene) contra `strategy.engine.run_backtest()` real: **exhaustiva, 0 discrepancias** (8/8 counters, 2.474/2.474 trades en todos sus campos).
  - **Hallazgos principales (sin exagerar el alcance — discovery, no validación):**
    1. Momentum favorable al trade en `limit_created_bar` mostró una relación fuerte y monotónica con **menor** probabilidad de fill del LIMIT (el hallazgo más robusto del estudio).
    2. Condicionado a que la operación efectivamente hiciera fill, ciertas medidas de momentum de corto plazo mostraron una relación potencial con mejores resultados — más débil y menos consistente que el hallazgo de fill rate.
    3. `P(fill | momentum)` y `P(outcome | filled, momentum)` son fenómenos distintos que no deben mezclarse automáticamente en un futuro diseño de Momentum.
    4. `roc_atr_3` quedó como candidato principal de impulso de muy corto plazo.
    5. `rsi_delta_3` resultó altamente redundante con `roc_atr_3` (ρ≈0.935) — se conserva principalmente como control de redundancia, no como feature independiente.
    6. `ema_slope_atr_5` quedó como candidato independiente a validar (patrón parcialmente contraintuitivo, requiere entender la causa).
    7. `atr_pct` quedó como candidato de contexto de volatilidad — no se trata como componente de Momentum en sí.
    8. La interacción `Divergence OPPOSED × Momentum fuerte` mostró un resultado potencialmente desfavorable (peor que `OPPOSED × Momentum débil`), pero con N pequeño (36 vs. 59) — requiere validación, no es hallazgo confirmado.
    9. RSI extremo (>70/<30) prácticamente no existe en `limit_created_bar` para esta estrategia sobre XAU (0/2.474 en Universo B, 8/3.207 en Universo A) — hallazgo estructural del mecanismo de señal, no quedó como candidato útil para Momentum en XAU.
  - **Ninguno de estos hallazgos se implementó como score, peso, filtro ni cambio de producción.**
- **Notas técnicas:** Reusa sin modificar `strategy.engine.ema()`/`bucket_levels()` y `strategy.scoring.rsi()`/`find_confirmed_pivots()`/`resolve_divergence()`/`divergence_detail()`. ATR Wilder (no existe en `/strategy`) reusado verbatim de `backtests/scripts/07_bot045_regime_dataset.py::atr_wilder`. **Reporte completo:** `reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY.md`. Script: `scripts/discover_momentum_features_xau.py`. Evidence log: `reports/BOT-024.2-MOMENTUM-FEATURE-DISCOVERY-EVIDENCE.log`. Datasets: `reports/BOT-024.2-momentum-limits-xau.csv` (Universo A), `reports/BOT-024.2-momentum-trades-xau.csv` (Universo B).
- **Siguiente paso planificado dentro de BOT-024 (ya ejecutado, ver `BOT-024.4`):** definir formalmente qué candidato de esta shortlist es Momentum (ownership, no solo performance) antes de integrarlo a Signal Quality — ejecutado en `BOT-024.4` (`FREEZE_READY`, canónica `roc_atr_3`). La validación OOS de esa definición sigue siendo `BOT-024.3` (`BLOCKED`, sin cambios).
- **Dependencias:** BOT-024.1 (evidencia de entrada sobre Divergencia RSI, no reinterpretada acá).

### BOT-024.3 — Momentum Out-of-Sample Validation
- **Categoría:** Scoring / Investigación / Validación
- **Estado:** BLOCKED
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-19
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-024`, sucesora de `BOT-024.2`. Objetivo: validar Out-of-Sample (con datos que nunca participaron en el discovery) las hipótesis congeladas de BOT-024.2 (H1 `roc_atr_3` → Fill Rate; H2 `roc_atr_3` → resultado condicional al fill; H3 redundancia `roc_atr_3` ↔ `rsi_delta_3`; H4 `ema_slope_atr_5`; H5 `atr_pct`; H6 `Divergence OPPOSED` × Momentum), con thresholds/quintiles congelados desde discovery (nunca recalculados sobre OOS), sin feature discovery nuevo, sin optimizar parámetros.
- **Motivo del bloqueo:** BOT-024.2 utilizó todo el histórico XAU local disponible, confirmado directamente desde el dataset (no de memoria): `backtests/data/XAUUSDc_M5_latest.parquet`, 100.505 barras, hasta exactamente **2026-09-15T00:40:03 UTC**. Al ejecutar el pre-flight de esta tarea (2026-09-19) se verificó que **no existe ninguna barra en el repositorio posterior a ese cutoff** — el único otro archivo `XAUUSDc_M5_*.parquet` resultó ser el mismo dataset (idéntico byte a byte, no un segundo archivo). No se descargó ningún dato nuevo (requiere autorización explícita del usuario, no asumida en esta tarea) y no se reutilizó el período de discovery como si fuera OOS (prohibido explícitamente). Con la fecha actual, quedarían disponibles como mucho ~4 días (~1.150 barras M5) si se descargaran — insuficiente para una validación OOS estadísticamente razonable de la mayoría de las hipótesis H1-H6.
- **Regla al desbloquear (congelada, no modificar cuando haya datos):** mismos thresholds/quintiles de discovery (reconstruidos desde `XAUUSDc_M5_latest.parquet`, nunca recalculados sobre OOS); mismos Universo A/Universo B; misma separación causal en `limit_created_bar`; separar LONG/SHORT; separar `P(fill | momentum)` de `P(outcome | filled, momentum)`; sin feature fishing (nada de ROC2/4/6, ATR/EMA period nuevos, thresholds alternativos u optimizar LONG/SHORT por separado); paridad exhaustiva (shadow replay, 0 discrepancias) contra `strategy.engine.run_backtest()` antes de interpretar cualquier resultado.
- **Notas técnicas:** `scripts/validate_momentum_oos_xau.py` ya implementa la detección automática del cutoff de discovery y la búsqueda de barras OOS — re-ejecutarlo sin cambios es suficiente para saber si esta tarea puede desbloquearse. **Reporte completo:** `reports/BOT-024.3-MOMENTUM-OOS.md`. Evidence log: `reports/BOT-024.3-MOMENTUM-OOS-evidence.txt`. No se generaron CSVs de Universo A/B (no obligatorio en caso de bloqueo).
- **Actualización 2026-09-21 (`BOT-024.4`):** el objeto de validación ya no son 6 hipótesis sueltas — `BOT-024.4` congeló el contrato canónico de Momentum (`roc_atr_3`, RAW, `FREEZE_READY`), con `rsi_delta_3` como control de redundancia y `ema_slope_atr_5`/`atr_pct` explícitamente fuera del contrato v1 (ver esa entrada). `BOT-024.3` debe validar ese contrato congelado cuando exista OOS, no recalcular thresholds ni reabrir ownership. Sigue `BLOCKED` por la misma falta de histórico — sin cambios en el motivo del bloqueo.
- **Dependencias:** BOT-024.2 (hipótesis y thresholds a validar, no reinterpretados acá), BOT-024.4 (contrato congelado a validar).

### BOT-024.4 — Momentum Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-21
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-024`, cierra el gap identificado por `BOT-051.1` ("Momentum es la única de las cinco líneas que nunca ejecutó un paso de Definition Freeze"). Tarea de **definición/verificación, no discovery**: reusa exclusivamente los artefactos ya congelados de `BOT-024.2` (Momentum), `BOT-047.2.3` (Alignment), `BOT-048.2`/`BOT-048.1` (Structure), `BOT-049.2` (Economics) y `BOT-050.2`/`BOT-050.1` (Context) — cero features nuevas, cero ventanas nuevas, cero grid search, cero recalculo de discovery. El único cómputo permitido fue verificación determinista: reproducir números ya publicados de `BOT-024.2` desde el CSV congelado (0 discrepancias) y llenar correlaciones cruzadas no reportadas explícitamente antes (`roc_atr_3` vs `ema_slope_atr_5`/`atr_pct`/`origin_dist_atr`/Alignment Consensus/`weekday`).
- **Resultado (2026-09-21):** **`FREEZE_READY`**. Definición: *"Momentum = impulso direccional de muy corto plazo (3 barras M5/15min) en `limit_created_bar`, normalizado por ATR14, signado por dirección."* Canónica: **`roc_atr_3`** (RAW continua, sin estados/bins/thresholds). `rsi_delta_3` → `CONTROL_ONLY` (redundante, ρ=+0.935, no vota dos veces el mismo fenómeno). `ema_slope_atr_5` → `UNRESOLVED`/`MOMENTUM-SECONDARY` (no redundante, ρ=−0.526, pero patrón sin mecanismo explicado — no promovido a v1). `atr_pct` → `OWNED_BY_OTHER_FACTOR` (Context/Volatilidad — gap documentado: el contrato de Context, `BOT-050.2`, no lo incluye explícitamente). Divergencia (`NONE/ALIGNED/OPPOSED`) → `CROSS_FACTOR_ONLY` (identidad propia de `BOT-023`, interactúa vía `OPPOSED`×momentum sin folding). **`P(fill | momentum)` → `OWNED_BY_OTHER_FACTOR` (`execution/fill-quality`)** — mismo dominio que `BOT-049.2` ya usó para `distance_to_limit_atr`, mismo razonamiento (predice ejecución, no calidad direccional del resultado). Sin redundancia fuerte (`|ρ|≥0.8`) de `roc_atr_3` contra ningún contrato ya congelado de otra dimensión (Structure ρ=+0.317; sin patrón fuerte descriptivo vs Alignment Consensus ni `weekday`). LONG/SHORT: fórmula simétrica por construcción (verificado, medias/std del mismo orden en ambas direcciones), pero el efecto observado es asimétrico (Q1 Exp$=−3.10 en LONG vs −0.21 en SHORT) — no se calibra por dirección, se documenta la asimetría. XAU único activo evaluado; BTC permanece `BLOCKED` sin cambios. **`BOT-024.3` sigue `BLOCKED`** — este freeze define QUÉ es Momentum, no lo valida OOS; no autoriza score, peso ni gating. **Reporte completo:** `reports/BOT-024.4-MOMENTUM-DEFINITION-FREEZE.md`. Script: `scripts/freeze_momentum_definition_xau.py`. Evidence log: `reports/BOT-024.4-MOMENTUM-DEFINITION-FREEZE-EVIDENCE.log`.
- **Siguiente paso planificado dentro de BOT-024:** `BOT-024.3` (OOS del contrato ahora congelado, sigue esperando histórico) y `BOT-051.2` (puede poblar el slot `momentum` del vector de Signal Quality con `roc_atr_3` en vez de `PENDING_DEFINITION` — ver esa entrada).
- **Dependencias:** BOT-024.2 (evidencia de origen, no reinterpretada), BOT-047.2.3/BOT-048.2/BOT-049.2/BOT-050.2 (contratos ya congelados de las otras dimensiones, usados solo para verificación cruzada de redundancia), BOT-051.1 (identificó el gap que esta tarea cierra).

### BOT-025 — Gate configurable `minimum_entry_score`
- **Categoría:** Scoring
- **Estado:** TODO
- **Prioridad:** MEDIUM
- **Incorporado:** 2026-09-14
- **Versión objetivo:** sin definir
- **Descripción:** Permitir rechazar una entrada si su score queda por debajo de un umbral configurable (`minimum_entry_score = 70`, por ejemplo). El diseño de `scoring.py` ya contempla esto para el factor CVP específicamente ("el gate... está descripto en el diseño pero deliberadamente desactivado en esta primera pasada") — falta generalizarlo al score total y exponerlo como configuración.
- **Estado downstream (actualizado 2026-09-20, ver roadmap en `BOT-024`):** permanece explícitamente **pendiente/downstream** de la secuencia `BOT-047/048/049/050` (Discovery/Freeze por dimensión) → `BOT-051` (Signal Quality Integration) → `BOT-025`. No se cierra, no se cancela ni se reinterpreta aquí — su diseño concreto (qué escala, qué umbral, si aplica sobre el 0–100 integrado de `BOT-051` o sobre otra representación) puede cambiar según lo que `BOT-051` produzca.
- **Notas técnicas:** Debe seguir siendo una capa que se pueda desactivar — no reemplazar la lógica base de señales (`engine.py`/`live_signal.py`).
- **Dependencias:** BOT-023, BOT-024 (para que el umbral tenga una escala estable antes de fijar un default razonable) — en la práctica, esa escala estable depende ahora de que `BOT-051` complete la integración de las 5 dimensiones.

### BOT-047 — D1 Alignment
- **Categoría:** Scoring / Investigación
- **Estado:** IN PROGRESS / RESEARCH (feature padre — refleja el estado agregado de sus subtareas, ver abajo; no se marca `DONE` hasta tener OOS validado)
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-19
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Feature padre de `BOT-024` (Signal Quality), dimensión `Alignment` — **¿la dirección propuesta por el trade está alineada o en contra del contexto direccional de mayor plazo?** — explícitamente independiente de Momentum (`BOT-024.2`/`BOT-024.3`, que responde una pregunta distinta: ¿con qué fuerza se está moviendo el mercado alrededor del nacimiento del LIMIT?). D1 NO debe utilizarse para modificar ni "mejorar" Momentum. Ambas siguen siendo dimensiones independientes de `Signal Quality = Momentum + Alignment + Structure + Economics + Context`.
  - **Relación con BOT-045/BOT-046:** reutiliza esos hallazgos como antecedente/contexto histórico (no se reinterpretan ni se descartan), pero **no asume** que la definición anterior de `aligned_with_d1` (BOT-045/046) sea necesariamente la definición final de la dimensión Alignment de Signal Quality. BOT-045/046 preguntaban "¿la hipótesis D1 tiene robustez?"; BOT-047 amplía la pregunta a "¿cómo debemos representar formalmente Alignment?". **`BOT-046` permanece `DONE` sin cambios — esta es una ID nueva, no una reapertura ni un `BOT-046.1`.**
  - **Estructura interna (convención de features experimentales, ver regla permanente más abajo):** esta es la primera feature organizada bajo la subestructura `.1/.2/.3` — ver `BOT-047.1`, `BOT-047.2`, `BOT-047.3` a continuación. `BOT-047.2.1`, `BOT-047.2.2` y `BOT-047.2.3` son subtareas experimentales **internas** de `BOT-047.2` (no consumen un ID principal ni un `.3`/`.4` nuevo — ver "Convención de IDs" en cada una más abajo).
- **Dependencias:** BOT-045, BOT-046 (antecedentes, reutilizados como contexto, no reinterpretados).
- **Subtareas:**
  - `BOT-047.1` `DONE` — Feature Discovery.
  - `BOT-047.2` `DONE` — Definition Freeze (resultado `PROVISIONAL`, no `FREEZE_READY`).
  - `BOT-047.2.1` `DONE` — Structural Alignment Definition & Legacy Decomposition (resultado `PROVISIONAL`).
  - `BOT-047.2.2` `DONE` — D1 Structural Boundary Validation (resultado `PROVISIONAL`).
  - `BOT-047.2.3` `DONE` — Structural Alignment Consensus Definition Freeze (resultado `FREEZE_READY`).
  - `BOT-047.3` `READY / WAITING FOR OOS` — definición congelada por `BOT-047.2.3`; espera histórico genuinamente posterior al 2026-09-15 (no se ejecuta con el histórico actual).

### BOT-047.1 — D1 Alignment Feature Discovery
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-19
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-047` (D1 Alignment). Objetivo: descubrir qué variables observables de temporalidad D1 representan de forma útil y causal el concepto de Alignment, separando explícitamente `D1_CLOSED`/`D1_FORMING` y RAW/trade-relative, sin asumir de antemano reglas tipo "precio > EMA200 D1 = bullish". Reusa sin modificar el motor de producción (`strategy.engine.run_backtest`, validado vía shadow replay exhaustivo, 0 discrepancias) y funciones ya existentes (`strategy.engine.ema()`, `strategy.scoring.rsi()`/`find_confirmed_pivots()`/`divergence_detail()`).
- **Resultado (2026-09-20):** Universo A = 3.207 LIMITS creados (LONG=1.534, SHORT=1.673), Universo B = 2.474 trades filled+cerrados (idéntico a Universo A/B de BOT-024.2, mismo motor/dataset/Config A). Causalidad de `D1_FORMING` verificada tanto constructivamente como empíricamente (re-slice de 41 eventos truncando el histórico a `[:limit_created_bar+1]`, 0 discrepancias). **Hallazgos principales:** (1) la familia distancia/pendiente de EMA D1 (20/50/200, normalizada por ATR) es la más fuerte y estable del screening (ρ Spearman ≈0.10–0.15 vs `pnl_r`, la más alta de todas las features estudiadas), con relación aproximadamente monotónica en los bins y razonablemente estable entre sub-períodos; (2) `D1_CLOSED` y `D1_FORMING` resultaron **casi indistinguibles** para las mismas features (ρ entre ambas representaciones 0.85–0.99) — FORMING no mostró ventaja clara sobre CLOSED en los pares comparados; (3) las versiones **trade-relative** (`aligned_*`) de esas mismas features RAW **pierden casi toda la correlación** con `pnl_r` (hallazgo no anticipado — sugiere que la señal fuerte de EMA/RSI D1 podría ser más una variable de régimen/volatilidad que de "alineación direccional" en sentido estricto); (4) fuerte redundancia (ρ>0.95) entre distancia a EMA, pendiente de EMA y RSI14 D1 — probablemente la misma señal subyacente, no features independientes; (5) Estructura D1 (HH/HL vs LH/LL, vía `find_confirmed_pivots()` sobre la serie D1_CLOSED, solo resuelta para CLOSED por diseño causal) mostró diferencia direccional consistente pero débil (~3-5pp WR); (6) comparación descriptiva contra `aligned_with_d1` histórico (BOT-045/046, metodología sin modificar) reprodujo el mismo signo ya documentado (alineado ExpR=+0.073 vs en contra ExpR=-0.178). Ningún hallazgo se convirtió en score, peso, filtro ni cambio de producción — discovery puro. **Reporte completo:** `reports/BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY.md`. Script: `scripts/discover_d1_alignment_features_xau.py`. Evidence log: `reports/BOT-047.1-D1-ALIGNMENT-FEATURE-DISCOVERY-EVIDENCE.log`. Datasets: `reports/BOT-047.1-d1-alignment-limits-xau.csv` (Universo A), `reports/BOT-047.1-d1-alignment-trades-xau.csv` (Universo B).
- **Siguiente paso planificado dentro de BOT-047 (ya ejecutado, ver `BOT-047.2`):** revisión de estos candidatos y freeze de una definición — completado en `BOT-047.2` con resultado `PROVISIONAL`.
- **Dependencias:** BOT-047 (feature padre), BOT-045, BOT-046 (antecedentes, reutilizados como contexto, no reinterpretados).

### BOT-047.2 — D1 Alignment Definition Freeze
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Sucesora de `BOT-047.1` dentro de la feature padre `BOT-047`. Objetivo: usar exclusivamente la evidencia del discovery de BOT-047.1 (no una búsqueda nueva) para definir y congelar formalmente una hipótesis candidata de Alignment, investigando explícitamente por qué las versiones RAW de las features D1 correlacionan con `pnl_r` mientras sus versiones trade-relative (`aligned_*`) pierden esa señal, y tratando la asimetría LONG/SHORT como hipótesis explícita en vez de asumirla. Reusa exclusivamente los datasets ya causales de BOT-047.1 (sin re-ejecutar el motor de producción ni MT5).
- **Resultado (2026-09-20):** **Explicación RAW vs `aligned_*` (confirmada en los 6 candidatos principales, sin excepción):** la pendiente OLS de `pnl_r ~ feature` tiene el MISMO signo en LONG y en SHORT — comportamiento de variable de RÉGIMEN (fuerza/persistencia de la tendencia D1), no de ALINEACIÓN direccional. Al multiplicar por `direction_sign` (Modelo C, signed trade-relative), la pendiente de SHORT se invierte artificialmente y cancela gran parte de la correlación agregada — explica matemática y empíricamente el colapso de señal ya observado en BOT-047.1. **LONG vs SHORT:** aunque la correlación agregada es de magnitud similar en ambas direcciones, el resultado económico y la estabilidad temporal NO lo son — SHORT llega a expectancy positiva en el régimen favorable y es temporalmente `STABLE` (mismo signo en los 3 sub-períodos) en 4/6 candidatos; LONG nunca cruza a expectancy positiva en ningún corte y nunca alcanza `STABLE` (`UNSTABLE` en 2/6 candidatos incluido el elegido como PRIMARY, `PARTIALLY_STABLE` en los otros 4). **`D1_CLOSED` vs `D1_FORMING`:** decisión `D1_CLOSED_ONLY` — CLOSED es igual o mejor que FORMING en los 8/8 pares comparados. **Redundancia:** PRIMARY = `closed_ema200_slope` (mayor `|ρ|` vs `pnl_r` = +0.149); `closed_ema50_slope`/`closed_dist_ema200_atr`/`closed_dist_ema50_atr` clasificados `REDUNDANT` (`|ρ|≥0.8` con PRIMARY); `closed_ema20_slope`/`closed_ret_10d`/`closed_rsi14` `SECONDARY/ORTHOGONAL` pero ningún composite sin pesos optimizados (Modelo D) mejoró sobre PRIMARY solo, así que no se incluyen en la definición congelada. **4 modelos comparados:** A (RAW regime) es el único que sobrevive sin objeciones; B (direction-conditioned, terciles propios por dirección) resultó cualitativamente equivalente a A; C (signed trade-relative) descartado; D (composite mínimo) no mejoró sobre A. **Legacy `aligned_with_d1` (BOT-045/046):** NO redundante con el PRIMARY elegido (`ρ=-0.099`, prácticamente sin correlación) — sigue separando outcomes dentro de cada tercil de `closed_ema200_slope`, con un split notablemente más fuerte para LONG específicamente (LONG "en contra" ExpR=-0.342) que el que logra el PRIMARY continuo — queda documentado como pregunta abierta, no se combina ni se reemplaza. **ALIGNMENT DEFINITION FREEZE:** PRIMARY=`closed_ema200_slope`, boundary=`D1_CLOSED`, sin transformación por dirección (RAW, reportado siempre separado LONG/SHORT), sin composite. **Resultado: `PROVISIONAL`** (no `FREEZE_READY`) — hay señal real, causal y redundancia-controlada, pero LONG nunca es económicamente positivo y es temporalmente inestable, y existe evidencia de que legacy captura información directional relevante (especialmente para LONG) que el PRIMARY continuo no captura. Ningún score, peso, gate ni cambio de producción implementado. **Reporte completo:** `reports/BOT-047.2-ALIGNMENT-DEFINITION-FREEZE.md`. Script: `scripts/analyze_d1_alignment_definition_xau.py`. Evidence log: `reports/BOT-047.2-ALIGNMENT-DEFINITION-FREEZE-EVIDENCE.log`. CSVs: `reports/BOT-047.2-alignment-candidates-xau.csv`, `reports/BOT-047.2-alignment-directional-analysis-xau.csv`.
- **Bug encontrado y corregido durante el pre-flight de esta tarea (no producción):** `scripts/discover_d1_alignment_features_xau.py` (BOT-047.1) escribía los CSV de Universo A/B ANTES de calcular `legacy_aligned_with_d1` — la columna quedaba en `None`/NaN en disco aunque el log impreso (y por lo tanto el reporte de BOT-047.1, que cita el log, no el CSV) mostraba los números correctos. Fix: se movió la escritura de los CSV a después del cálculo de `legacy_aligned_with_d1`; se re-ejecutó el script completo (único cambio en el evidence log: el orden de las líneas "CSV escrito", ningún número ni hallazgo cambió) y se regeneraron los CSV de `BOT-047.1` en `reports/`, ahora correctos. El reporte de `BOT-047.1` no necesitó ningún cambio.
- **Siguiente paso planificado dentro de BOT-047 (ejecutado, ver `BOT-047.2.1`):** revisión humana explícita del resultado `PROVISIONAL` sigue pendiente — `BOT-047.2.1` amplía la evidencia (decomposición del legacy) pero no reemplaza la necesidad de esa revisión; `BOT-047.3` sigue sin desbloquearse automáticamente.
- **Dependencias:** BOT-047.1.

### BOT-047.2.1 — Structural Alignment Definition & Legacy Decomposition
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Convención de IDs:** subtarea experimental **interna** de `BOT-047.2` (no `BOT-047.3`/`BOT-047.4`, no consume un ID principal nuevo). La última ID principal sigue siendo `BOT-047`; el siguiente ID principal disponible sigue siendo `BOT-048`.
- **Descripción:** `BOT-047.2` encontró que `closed_ema200_slope` (PRIMARY congelado) se comporta como D1 Regime/Trend Strength, no como Alignment direccional, y que `legacy_aligned_with_d1` (BOT-045/046) aporta información incremental (`ρ≈-0.099` con PRIMARY) pero con cobertura limitada (26%). Esta tarea decompone exactamente la implementación legacy real (sin modificarla), audita su causalidad respecto a `limit_created_bar`, explica la cobertura del 26%, y evalúa si existe una definición de mayor cobertura sin threshold mining.
- **Resultado (2026-09-20):** **Legacy exacto localizado y auditado** (`backtests/scripts/07_bot045_regime_dataset.py::precompute_closed_blocks` + `strategy/scoring.py::_classify_sequence`, `TREND_LOOKBACK_BLOCKS=3`) — causalidad confirmada exhaustivamente (prueba constructiva + replay empírico de 60 eventos truncando el histórico, 0 discrepancias). **Hallazgo crítico:** la detección de "bloque D1 cerrado" que usa el legacy real (heredado de BOT-045, también presente en `strategy/scoring.py::_closed_blocks` de producción) usa `time_utc // 86400` (partición de día-calendario UTC), **no** el ancla de sesión 22:00 UTC documentada y usada en el resto del proyecto (`bucket_start_utc_seconds`) — verificado empíricamente (367 transiciones true-anchor vs 443 naive, índices de barra no coincidentes). Es 100% causal (no hay fuga de información futura), pero es una discrepancia semántica entre lo documentado y lo realmente ejecutado — no se modifica ni `strategy/scoring.py` ni el script de BOT-045 (fuera de alcance, código ya congelado/producción). **Cobertura del 26% explicada:** de los 1.830 "None", sólo 18 (1%) son warm-up real (`insufficient_blocks`); el 99% restante (1.812) son casos con 3+ bloques cerrados pero sin secuencia HH/HL o LH/LL estricta (`mixed_sequence`) — la limitación es de la regla (exigir monotonicidad estricta en 3 bloques es estructuralmente rara), no del tamaño del dataset. **Coverage bias:** el subconjunto covered (26%) no luce marcadamente distinto del uncovered en WR/ExpR/PF/distribución LONG-SHORT/distribución temporal/Regime — sin evidencia de sesgo de selección grosero. **5 candidatos de mayor cobertura evaluados simétricamente** (legacy exacto 26%, misma regla con ancla corregida 22:00 UTC 36.9%, lookback=2 75.4%, lookback=4 17.1%, pivot-based `find_confirmed_pivots` 58.6%): ampliar cobertura degrada sistemáticamente la separación ALIGNED/AGAINST; ningún candidato de mayor cobertura preserva la fuerza del legacy exacto; el candidato pivot-based (mayor cobertura) resulta con signo invertido para SHORT y estabilidad `UNSTABLE`/`INSUFFICIENT_N`. **Hallazgo robusto y convergente:** `LONG + estructura en contra de D1` es, en las 5 variantes evaluadas (independiente del ancla o de la regla exacta), una de las combinaciones más negativas (ExpR entre -0.18 y -0.34) — la evidencia individual más sólida de la tarea. **Estabilidad temporal:** el legacy exacto (ancla naive) es `STABLE` en ALL/LONG/SHORT; la versión con ancla corregida es `PARTIALLY_STABLE`/`STABLE`; el candidato pivot-based es `UNSTABLE`/`INSUFFICIENT_N`. **Decisión semántica:** se confirma que `closed_ema200_slope` debe seguir tratándose como D1 Regime, no Alignment (redundancia baja confirmada con evidencia adicional). **Resultado: `PROVISIONAL`** (no `FREEZE_READY`, no `INSUFFICIENT_EVIDENCE`) — hay evidencia causal real de una señal de Structural Alignment, pero la variante con más evidencia (legacy exacto) depende de un boundary no documentado, la variante con el boundary correcto es más débil, y ningún candidato de mayor cobertura es viable todavía. Ningún score, peso, gate ni cambio de producción implementado. **Reporte completo:** `reports/BOT-047.2.1-STRUCTURAL-ALIGNMENT-DEFINITION.md`. Script: `scripts/analyze_d1_structural_alignment_xau.py`. Evidence log: `reports/BOT-047.2.1-STRUCTURAL-ALIGNMENT-EVIDENCE.log`. CSVs: `reports/BOT-047.2.1-legacy-decomposition-xau.csv`, `reports/BOT-047.2.1-model-comparison-xau.csv`, `reports/BOT-047.2.1-coverage-reasons-xau.csv`.
- **Siguiente paso planificado dentro de BOT-047 (ejecutado, ver `BOT-047.2.2`):** cuantificar cuánto del efecto de `BOT-047.2.1` depende específicamente del boundary 00:00 UTC vs. el boundary documentado 22:00 UTC.
- **Dependencias:** BOT-047.2.

### BOT-047.2.2 — D1 Structural Boundary Validation
- **Categoría:** Scoring / Investigación / Validación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Convención de IDs:** subtarea experimental **interna** de `BOT-047.2` (no `BOT-047.3`/`BOT-047.4`, no consume un ID principal nuevo). La última ID principal sigue siendo `BOT-047`; el siguiente ID principal disponible sigue siendo `BOT-048`.
- **Descripción:** Sucesora directa de `BOT-047.2.1`. Objetivo: determinar si el edge estructural (`S0`/`B0`, legacy exacto, boundary 00:00 UTC) pertenece genuinamente a la estructura D1 o depende específicamente del corte artificial 00:00 UTC heredado del legacy, comparando exactamente B0 (00:00 UTC) contra B1 (22:00 UTC, boundary documentado) evento por evento — manteniendo fija la regla estructural (`_classify_sequence`, `TREND_LOOKBACK_BLOCKS=3`), sin boundary mining (no se recorrieron otras horas, sin grid search). Reusa sin modificar las funciones de partición de bloques de `BOT-047.2.1`.
- **Resultado (2026-09-20):** **B2 (día del bróker) considerado y excluido** antes de mirar cualquier resultado de performance: para este dataset/bróker el offset `time_server - time_utc` es de sólo -3 segundos (no una diferencia de zona horaria real), la partición resultante coincide 100% con B0 — no aporta un punto de comparación independiente. **Transition analysis:** cero transiciones directas `ALIGNED↔AGAINST` en la matriz B0→B1 — el boundary nunca invierte el signo de la clasificación, sólo mueve eventos hacia/desde `NEUTRAL_MIXED` (36.0% de los 2.474 eventos cambian de clasificación, ninguno invierte signo). **Structural anatomy:** el mecanismo es agregación de ventana horaria (qué 2 horas de precio cerca de la medianoche UTC "cuentan" para el día anterior vs. el siguiente al construir el high/low de cada bloque), no una diferencia de información disponible ni de causalidad. **Hallazgo central — cohortes LONG+AGAINST por acuerdo entre boundaries:** el subconjunto donde **ambos** boundaries coinciden en clasificar el evento como AGAINST (N=48) tiene ExpR=-0.452 — **más negativo que B0 solo (-0.342) o B1 solo (-0.202)** — con monotonicidad clara entre "against en ambos" → "against en solo uno" → "against en ninguno" (ExpR se acerca a la baseline a medida que decrece el acuerdo). Esto es evidencia directa de que el efecto LONG+AGAINST **no es puramente un artefacto del boundary 00:00 UTC** — el núcleo de acuerdo entre boundaries es más fuerte, no más débil, que cualquiera de las dos definiciones por separado. **Causalidad:** `PASS`, 0/60 discrepancias en replay empírico con muestra independiente; reconstrucción B0/B1 coincide 100% (2.474/2.474) con `BOT-047.2.1`. **Estabilidad/coverage/redundancia con Regime:** reconfirmados de forma independiente, idénticos a `BOT-047.2.1` (B0 `STABLE` en ALL/LONG/SHORT, B1 `PARTIALLY_STABLE`/`STABLE`/`PARTIALLY_STABLE`; `rho` vs `closed_ema200_slope` baja en ambos boundaries). **Resultado: `PROVISIONAL`** (no `BOUNDARY_FREEZE_READY`, no `INSUFFICIENT_EVIDENCE`) — hay evidencia real de un núcleo de señal estructural robusto al boundary (cohorte "against en ambos"), pero ni B0 (fuerte, no documentado) ni B1 (documentado, más débil) domina en los cuatro planos (estadística/causalidad/semántica/robustez) simultáneamente como para congelar un boundary único. Ningún score, peso, gate ni cambio de producción implementado. **Reporte completo:** `reports/BOT-047.2.2-D1-STRUCTURAL-BOUNDARY-VALIDATION.md`. Script: `scripts/analyze_d1_structural_boundary_xau.py`. Evidence log: `reports/BOT-047.2.2-D1-STRUCTURAL-BOUNDARY-EVIDENCE.log`. CSVs: `reports/BOT-047.2.2-boundary-event-comparison-xau.csv`, `reports/BOT-047.2.2-boundary-transition-matrix-xau.csv`, `reports/BOT-047.2.2-boundary-performance-xau.csv`.
- **Siguiente paso planificado dentro de BOT-047 (ejecutado, ver `BOT-047.2.3`):** decidir formalmente, sin discovery adicional, qué definición de Structural Alignment congelar como hipótesis pre-OOS — resuelto en `BOT-047.2.3`.
- **Dependencias:** BOT-047.2.1.

### BOT-047.2.3 — Structural Alignment Consensus Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Convención de IDs:** subtarea experimental **interna** de `BOT-047.2` (no `BOT-047.3`/`BOT-047.4`, no consume un ID principal nuevo). La última ID principal sigue siendo `BOT-047`; el siguiente ID principal disponible sigue siendo `BOT-048`.
- **Descripción:** `DEFINITION FREEZE / DOCUMENTATION / CONTRACT` — explícitamente **no es discovery**. Toma exclusivamente la evidencia ya producida por `BOT-047.2.1`/`BOT-047.2.2` y decide, sin generar variantes nuevas ni buscar mejor performance, entre dos familias conceptuales: **Canonical-only** (Alignment = sólo B1, boundary 22:00 UTC documentado) vs. **Structural Consensus** (Alignment = grado de acuerdo entre B0 00:00 UTC y B1 22:00 UTC, las dos particiones ya estudiadas). Único cómputo nuevo: una re-etiquetación determinista de las columnas `B0_alignment`/`B1_alignment` ya generadas y auditadas por `BOT-047.2.2` (`reports/BOT-047.2.2-boundary-event-comparison-xau.csv`) — ningún bloque D1 se recalculó, ningún boundary/lookback/regla nueva se probó.
- **Resultado (2026-09-20):** **Decisión: `STRUCTURAL_CONSENSUS`** — justificada por semántica/causalidad/interpretabilidad/reproducibilidad/robustez ya observada/capacidad de freeze limpio (no por performance; ver reporte sección 4 para la comparación explícita de los 6 criterios). Contrato de 6 estados congelado: `AGAINST_CONFIRMED` (B0=B1=AGAINST, N=164, 6.6%), `AGAINST_SINGLE` (N=451, 18.2%), `NEUTRAL` (B0=B1=NEUTRAL_MIXED, N=1.234, 49.9%), `ALIGNED_SINGLE` (N=438, 17.7%), `ALIGNED_CONFIRMED` (B0=B1=ALIGNED, N=169, 6.8%), `UNAVAILABLE` (B0 o B1 sin historia suficiente, N=18, 0.7% — regla de prioridad documentada explícitamente). **Invariante crítico reverificado:** 0/2.474 transiciones directas `ALIGNED↔AGAINST` (confirma, de forma independiente, el hallazgo de `BOT-047.2.2` — condición que hace bien-definida la escala de 6 estados). **Cross-check exacto:** `AGAINST_CONFIRMED` LONG reproduce exactamente la cohorte "against en ambos boundaries" de `BOT-047.2.2` (N=48, ExpR=-0.452, idéntico por sub-período). **Hallazgo honesto no simétrico (documentado explícitamente, no ocultado):** H1 (más evidencia AGAINST → peor resultado) se sostiene con claridad en LONG (`AGAINST_CONFIRMED` es el peor estado en los 3 sub-períodos, sin excepción) pero **NO se sostiene en SHORT** (`AGAINST_CONFIRMED` es de los mejores estados para SHORT, ExpR=+0.061 agregado, positivo en 2/3 sub-períodos) — el contrato preserva esta asimetría sin forzar una interpretación simétrica ni asignar score/peso. **Contrato técnico completo congelado** (semantic_name, purpose, evaluation_time=`limit_created_bar`, inputs, boundaries, structural_rule, direction_handling, output_states, unavailable_behavior, causal_guarantee, regime_separation, scoring=NONE, gating=NONE, production_effect=NONE) — ver reporte sección 7. **5 hipótesis pre-registradas para BOT-047.3** (H1 Structural ordering, H2 Consensus strength, H3 Directional asymmetry, H4 LONG+AGAINST, H5 Regime independence) y métricas OOS mínimas a medir (N, coverage, WR, ExpR, PF, LONG/SHORT, por estado, vs. baseline OOS) — sin declarar éxito solo por P&L absoluto, sin thresholds estadísticos nuevos. **Resultado: `FREEZE_READY`** (no `PROVISIONAL`, no `INSUFFICIENT_EVIDENCE`) — la definición es exacta, causal, interpretable y pre-registrable; esto NO significa que la feature esté validada, sólo que la hipótesis está lista para someterse a datos nuevos. Ningún score, peso, gate ni cambio de producción implementado. **Reporte completo:** `reports/BOT-047.2.3-STRUCTURAL-ALIGNMENT-CONSENSUS-FREEZE.md` (incluye el contrato formal completo). Evidence log: `reports/BOT-047.2.3-STRUCTURAL-ALIGNMENT-CONSENSUS-EVIDENCE.log`.
- **Impacto sobre BOT-047.3:** pasa de `BLOCKED` a `READY / WAITING FOR OOS` — la decisión metodológica ya está tomada y documentada; sigue sin poder ejecutarse porque no existe histórico genuinamente posterior al 2026-09-15 en el repositorio (mismo motivo que bloquea `BOT-024.3`), no por una decisión humana pendiente.
- **Dependencias:** BOT-047.2.1, BOT-047.2.2.

### BOT-047.3 — D1 Alignment Out-of-Sample Validation
- **Categoría:** Scoring / Investigación / Validación
- **Estado:** READY / WAITING FOR OOS
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Motivo del estado actual:** `BOT-047.2.3` congeló formalmente la definición de Structural Alignment (`STRUCTURAL_CONSENSUS`, resultado `FREEZE_READY`) — la decisión metodológica que mantenía esta tarea `BLOCKED` (qué boundary/definición usar) ya está resuelta y documentada (contrato completo, hipótesis H1–H5 pre-registradas, métricas OOS mínimas definidas). `BOT-047.3` **no se ejecuta todavía** porque no existe histórico genuinamente posterior al 2026-09-15 en el repositorio — el mismo motivo que mantiene `BOT-024.3` en espera. No se usa el histórico actual como sustituto de OOS.
- **Descripción:** Validar exclusivamente el contrato congelado en `BOT-047.2.3` (Structural Alignment Consensus: B0 00:00 UTC + B1 22:00 UTC, `TREND_LOOKBACK_BLOCKS=3`, 6 estados) sobre datos que NO participaron en `BOT-047.1`/`BOT-047.2.1`/`BOT-047.2.2` (discovery, definición de boundaries, diseño del contrato). No recalcular thresholds usando OOS, no agregar estados nuevos, no eliminar features porque fallen, no cambiar boundaries/lookback después de observar resultados, no hacer feature fishing, no redefinir Structural Alignment utilizando los resultados OOS. Evaluar explícitamente las hipótesis H1–H5 de `BOT-047.2.3`, siempre separado LONG/SHORT. Si la hipótesis falla, debe documentarse como resultado válido — cualquier modificación posterior es una hipótesis/versión nueva que requiere nueva validación (ej. `BOT-047.4` si la evidencia lo justifica).
  - **Relación con `VALIDATION-D1-OOS` (no se fusionan, son experimentos distintos):** `VALIDATION-D1-OOS` valida exclusivamente la hipótesis histórica ya congelada de BOT-045/BOT-046 (`aligned_with_d1`, sin modificar esa definición). `BOT-047.3` valida la definición **nueva** y formal de Alignment que resulte de BOT-047.1 → BOT-047.2 → BOT-047.2.1 → BOT-047.2.2 → BOT-047.2.3. Ambos tickets coexisten de forma independiente; ver nota cruzada equivalente en `VALIDATION-D1-OOS` más abajo.
- **Dependencias:** BOT-047.2.3.

### BOT-048 — Structure
- **Categoría:** Scoring / Investigación
- **Estado:** IN PROGRESS / RESEARCH (feature padre — refleja el estado agregado de sus subtareas, ver abajo; no se marca `DONE` hasta tener OOS validado)
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Feature padre de `BOT-024` (Signal Quality), dimensión `Structure` — **¿dónde está ubicada físicamente esta entrada dentro de la estructura reciente observable del precio (M5)?** — explícitamente independiente de Momentum (`BOT-024.2`/`BOT-024.3`, velocidad/impulso) y de Alignment (`BOT-047`, dirección D1). A pesar del nombre parecido a "Structural Alignment" (`BOT-047.2.1`/`.2.2`/`.2.3`), Structure (esta feature) NO es un concepto direccional de D1 — es un concepto de ubicación dentro de la estructura M5 reciente (swings, rango, origen de la ruptura que armó la señal). Ninguna de las dos reinterpreta ni sustituye a la otra.
  - **Estructura interna (convención de features experimentales, ver regla permanente más abajo):** sigue la misma subestructura `.1/.2/.3` que `BOT-047` — ver `BOT-048.1` a continuación.
- **Dependencias:** BOT-024 (marco conceptual de Signal Quality).
- **Subtareas:**
  - `BOT-048.1` `DONE` — Feature Discovery.
  - `BOT-048.2` `DONE` — Definition Freeze (resultado `ORIGIN_ONLY_FREEZE`, contrato RAW continuo sobre `origin_dist_atr`).
  - `BOT-048.3` `PENDING / WAITING OOS` — OOS Validation (contrato pre-registrado por `BOT-048.2`; bloqueada por falta de histórico genuinamente posterior al 2026-09-15, mismo motivo que `BOT-024.3`/`BOT-047.3`).

### BOT-048.1 — Structure Feature Discovery
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-048` (Structure). Objetivo: descubrir qué variables estructurales M5 observables y causales existen en `limit_created_bar` y describen la ubicación de la entrada dentro de la estructura reciente del precio, sin asumir de antemano que estar cerca de soporte/resistencia, un retest, o HH/HL, sea "mejor". Reusa sin modificar el motor de producción (`strategy.engine.run_backtest`, validado vía shadow replay exhaustivo, 0 discrepancias) y funciones ya existentes (`strategy.engine.bucket_levels()`, `strategy.scoring.find_confirmed_pivots()` — esta última, nunca antes aplicada a precio M5, solo a RSI para Divergencia y a OHLC D1 en `BOT-047.1`). Extiende el shadow replay con un mecanismo nuevo (rastreo causal del "origen de armado": qué ruptura de nivel HTF disparó por última vez `armado_venta`/`armado_compra` antes de que la señal EMA dispare), verificado tanto constructiva como empíricamente (re-slice de 41 eventos truncando el histórico a `[:limit_created_bar+1]`, 0 discrepancias, tanto para el origen de armado como para los swings M5).
- **Resultado (2026-09-20):** Universo A = 3.207 LIMITS creados (LONG=1.534, SHORT=1.673), Universo B = 2.474 trades filled+cerrados — idéntico al Universo A/B de `BOT-024.2`/`BOT-047.1` (mismo motor/dataset/Config A, verificado). 29 features en 9 familias (A–I), todas clasificadas `CAUSAL`. **Hallazgos principales:** (1) la familia F, nueva de esta tarea ("Entry Relative to Signal Origin" — distancia/edad/retroceso entre la entrada y el nivel HTF que armó la señal), es la más fuerte de todo el discovery: `origin_retracement_frac` (ρ Spearman=+0.387 vs `pnl_r`) y `origin_dist_atr` (ρ=+0.261) superan a la mejor feature de Momentum (`roc_atr_10`, ρ=-0.077 en este mismo universo) y son comparables a la mejor de Alignment (`closed_ema200_slope`, ρ=+0.149); (2) `origin_retracement_frac`, pese a tener la correlación más alta, tiene una limitación importante — 97.6% de los eventos caen en una banda casi constante (0.45–0.55), consistente con un artefacto mecánico de `RR=1.0` (Config A) — se clasifica `CROSS-FACTOR` con Economics, no `STRUCTURE-PRIMARY` limpia; `origin_dist_atr` (distribución continua, no degenerada, consistentemente peor en el quintil superior en ALL/LONG/SHORT y en los 3 sub-períodos) es la candidata más defendible; (3) las tres definiciones de "posición en el rango" (`range_pos_htf`/`range_pos_roll60`/`range_pos_roll288`) mostraron correlación prácticamente nula (`|ρ|<=0.022`) — resultado descriptivo válido, no una falla; (4) una hipótesis pre-registrada explícitamente en el código antes de ejecutar (`n_obstacles_to_sl` "casi tautológico, ~100% en cero" por construcción del SL) resultó **refutada** por la evidencia (97.2% con >=1 obstáculo) — documentado como ejemplo explícito de hipótesis intuitiva incorrecta; (5) redundancia fuerte confirmada entre las familias G (espacio estructural) y H (obstáculos hacia TP), `ρ=0.991` entre sus representantes; (6) sin evidencia de que Structure esté remidiendo Momentum con otro nombre (`|ρ|<=0.10` en todas las interacciones cruzadas evaluadas). Ningún hallazgo se convirtió en score, peso, filtro ni cambio de producción — discovery puro. **Reporte completo:** `reports/BOT-048.1-STRUCTURE-FEATURE-DISCOVERY.md`. Script: `scripts/discover_structure_features_xau.py`. Evidence log: `reports/BOT-048.1-STRUCTURE-FEATURE-DISCOVERY-EVIDENCE.log`. Datasets: `reports/BOT-048.1-structure-limits-xau.csv` (Universo A), `reports/BOT-048.1-structure-trades-xau.csv` (Universo B).
- **Siguiente paso planificado dentro de BOT-048 (ya ejecutado, ver `BOT-048.2`):** revisión humana de estos candidatos y freeze de una definición — completado en `BOT-048.2` con resultado `ORIGIN_ONLY_FREEZE`.
- **Dependencias:** BOT-048 (feature padre).

### BOT-048.2 — Structure Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** `DEFINITION / COMPARISON / FREEZE` — explícitamente **no es discovery**. Sucesora de `BOT-048.1`, reusa exclusivamente esos datasets ya causales (sin recalcular ninguna feature desde cero, salvo combinaciones deterministas fila a fila de columnas ya congeladas: `market_swing_state`/`swing_trade_relation`, derivadas de `swing_high_seq`/`swing_low_seq` siguiendo el mismo patrón conceptual que `pivot_state()` de `BOT-047.2.1` pero en M5, no D1). Compara explícitamente 4 alternativas (Origin, Swing, Forward-Space, Structural Consensus) con bootstrap/Wilson CI 95% (rigor no aplicado en `BOT-048.1`), matriz cualitativa (no numérica) de 11 criterios, y resuelve explícitamente la clasificación de `origin_retracement_frac` (obligatoria por enunciado).
- **Resultado (2026-09-20):** **Decisión: `ORIGIN_ONLY_FREEZE`** (contrato RAW continuo, sin thresholds/estados) sobre `origin_dist_atr` — justificada por semántica/causalidad/interpretabilidad/reproducibilidad/no-redundancia/robustez, **no** por performance histórica (ver reporte sección 15 para la comparación explícita). **Swing rechazado:** `market_swing_state`/`swing_trade_relation` (combinación nueva de esta tarea, `BULLISH`/`BEARISH`/`MIXED`/`UNAVAILABLE`, invariantes verificados por assertion) muestra una asimetría LONG/SHORT que **invierte de signo** (`MIXED` es significativamente malo para LONG, `ExpR=-0.168 [-0.265,-0.075]` IC 95%, pero el mejor estado — no significativo — para SHORT) sin explicación estructural clara. **Forward-Space rechazado:** tras colapsar la redundancia G/H (`ρ=1.000` entre `space_to_next_swing_atr` y `dist_first_obstacle_tp_atr`, reconfirmado) y elegir la representación geométrica limpia (`space_to_next_swing_atr`, independiente de TP/RR), la señal sigue siendo prácticamente nula (`ρ=+0.026` vs `pnl_r`). **Structural Consensus rechazado:** exigiría umbralizar `origin_dist_atr` sin una frontera geométrica defendible (los quintiles del análisis son descriptivos, no congelables) — aplicada la cláusula explícita de rechazo del enunciado. **`origin_retracement_frac` clasificado `CROSS_FACTOR_ONLY`** (obligatorio por enunciado): pese a tener el mayor `|ρ|` individual de todo `BOT-048.1` (+0.387), 97.6% de los eventos caen en una banda de 0.10 de ancho — dependencia mecánica confirmada de `RR=1.0`, no se promueve a Structure, queda documentado como candidata explícita para una futura dimensión Economics (no iniciada). **Hallazgo nuevo no reportado en `BOT-048.1`:** `ρ(origin_dist_atr, momentum_roc_atr_10)=-0.214` — moderada, la mayor entre las candidatas limpias de Economics, documentada sin ocultar (muy por debajo del umbral de redundancia fuerte `|ρ|>=0.8` del proyecto, pero es una reserva explícita para `BOT-048.3`). **Efecto de `origin_dist_atr` con IC (bootstrap 95%/Wilson 95%, nuevo en esta tarea):** estadísticamente distinguible de cero en ALL (Q5 `ExpR=-0.116 [-0.201,-0.027]`) y en LONG (patrón en U: Q1 `-0.204 [-0.329,-0.073]`, Q5 `-0.180 [-0.302,-0.056]`), pero **no** en SHORT ni en cada sub-período individual por separado (N insuficiente por bucket) — dirección consistente en 3/3 sub-períodos, documentado sin sobre-afirmar significancia donde no la hay. **Corrección menor a `BOT-048.1`:** la cobertura de `origin_dist_atr` es 99.97% (3.206/3.207), no 100.0% como esa tarea había redondeado — 1 evento de warm-up de ATR, no cambia ninguna conclusión. Ningún score, peso, gate ni cambio de producción implementado. **Reporte completo:** `reports/BOT-048.2-STRUCTURE-DEFINITION-FREEZE.md` (incluye el contrato formal completo). Script: `scripts/freeze_structure_definition_xau.py`. Evidence log: `reports/BOT-048.2-STRUCTURE-DEFINITION-FREEZE-EVIDENCE.log`.
- **Impacto sobre BOT-048.3:** pasa a `PENDING / WAITING OOS` — el contrato completo (definición, inputs, invariantes, métricas de validación, criterios de éxito/fallo explícitamente distintos de `P&L>0`) queda pre-registrado en el reporte sección 21; sigue sin poder ejecutarse porque no existe histórico genuinamente posterior al 2026-09-15 en el repositorio (mismo motivo que `BOT-024.3`/`BOT-047.3`).
- **Dependencias:** BOT-048.1.

### BOT-049 — Economics
- **Categoría:** Scoring / Investigación
- **Estado:** DONE — `NO_VALID_ECONOMICS_FREEZE` (feature padre — refleja el estado agregado de sus subtareas, ver abajo; se cierra porque `BOT-049.2` concluyó que no queda ninguna dimensión Economics independiente bajo la evidencia actual, no porque haya una definición validada OOS — ver esa entrada para por qué esto no requiere `BOT-049.3`)
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Feature padre de `BOT-024` (Signal Quality), dimensión `Economics` — **¿qué geometría económica del setup existe, de forma observable, causal y reproducible, en el momento de creación del LIMIT?** (RR, costos, spread, distancia a SL/TP, y cualquier variable derivada que describa el "diseño económico" de la oportunidad) — explícitamente independiente de Momentum (`BOT-024.2`/`BOT-024.3`), Alignment (`BOT-047`), Structure (`BOT-048`, `ORIGIN_ONLY_FREEZE`) y Context (`BOT-050`). No debe duplicar ninguna de esas dimensiones.
  - **Candidata conocida de entrada:** `origin_retracement_frac` — `BOT-048.2` la clasificó `CROSS_FACTOR_ONLY` y la excluyó explícitamente de Structure porque mezcla `origin_level` (Structure) con `target`/RR (Economics); evaluada desde cero en `BOT-049.1`, reconfirmada `CROSS_FACTOR_ONLY` en `BOT-049.2`.
  - **Relación con el factor CVP existente (BOT-023/`scoring.py::cvp_score()`):** resuelta en `BOT-049.2` — CVP y la candidata de fricción de Economics resultaron ser la MISMA cantidad (verificado bit-exacto), ownership asignado a CVP.
  - **Estructura interna (convención de features experimentales, ver regla permanente más abajo):** sigue la misma subestructura `.1/.2/.3` que `BOT-047`/`BOT-048` — ver `BOT-049.1`/`BOT-049.2` a continuación.
  - **Resultado final (2026-09-21):** bajo Config A y el diseño actual de la estrategia, Economics **no tiene ninguna representación numérica propia** — su escala de riesgo (`risk_atr`) es un proxy casi exacto de Structure (`origin_dist_atr`) por cómo esta estrategia ata el stop al nivel de origen HTF, y su fricción de costos es la misma cantidad que ya calcula CVP. Esto es un resultado de **ownership conceptual**, no de falta de señal estadística — ver `BOT-049.2` para el detalle completo y para qué escenario futuro (rediseño del stop, o exposición de un CVP continuo) podría reabrir la pregunta con una ID nueva.
- **Dependencias:** BOT-024 (marco conceptual de Signal Quality), BOT-048.2 (candidata `origin_retracement_frac`, sin reinterpretar su clasificación en Structure).
- **Subtareas:**
  - `BOT-049.1` `DONE` — Economics Feature Discovery.
  - `BOT-049.2` `DONE` — Economics Definition Freeze (resultado `NO_VALID_ECONOMICS_FREEZE`).
  - `BOT-049.3` `TODO — NO CONTRACT TO VALIDATE` — Economics OOS Validation (no aplica: no hay definición congelada que validar).

### BOT-049.1 — Economics Feature Discovery
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-049` (Economics). Pregunta central: **¿qué variables económicas observables, causales y reproducibles existen en el momento de creación del LIMIT y describen la geometría económica de la oportunidad?** `OFFLINE / DISCOVERY / NO PRODUCTION CHANGES / NO SCORE / NO GATE` — mismo tipo de disciplina que `BOT-048.1` (shadow replay exhaustivo + verificación causal antes de interpretar cualquier resultado), aplicada a Economics.
- **Resultado (2026-09-21):** Universo A = 3.207 LIMITS creados (LONG=1.534, SHORT=1.673), Universo B = 2.474 trades filled+cerrados — idéntico al Universo A/B de `BOT-024.2`/`BOT-047.1`/`BOT-048.1` (mismo motor/dataset/Config A, shadow replay exhaustivo, 0 discrepancias en 8/8 counters y 2.474/2.474 trades; re-slice causal empírico de 41 eventos, 0 discrepancias). **Hallazgo metodológico central:** bajo Config A, `rr` es un parámetro FIJO (rr=1.0 para el 100% de los eventos, identidad algebraica `rr_geometric==rr_nominal`) — esto colapsa las familias "LIMIT→SL" y "LIMIT→TP" del enunciado en una sola (`reward_price==risk_price` exacto) y hace que `breakeven_pct`/`rr_effective_net`/`cost_frac_of_target`/`spread_over_risk` sean la MISMA cantidad (`|ρ|=1.000` entre todas) — bajo esta config, Economics tiene solo DOS grados de libertad genuinos en `limit_created_bar`: **escala absoluta del setup** (`risk_atr`, ρ=+0.258 vs `pnl_r`) y **ratio de fricción de spread** (`spread_over_risk`, ρ=−0.448 vs `pnl_r`, la señal más fuerte de la tarea). **`origin_retracement_frac`** (candidata obligatoria) reconstruida desde cero de forma independiente: banda [0.45,0.55] en 97.3% de eventos (BOT-048.1 reportó ~97.6%, consistente), explicación algebraica completa de la dependencia mecánica de RR=1, ρ=+0.387/+0.362/+0.432 (ALL/LONG/SHORT, sin inversión de signo, la relación más estable temporalmente de la tarea) pero redundante fuerte (ρ≈−0.9) con la familia de fricción — **confirma `CROSS_FACTOR_ONLY`** de `BOT-048.2`, no se reabre. **`distance_to_limit_atr`** (sección obligatoria del enunciado, `|close[b]-entry|/ATR`): predictor fuerte y causal de fill rate (ρ=−0.401, fill rate 95.6%→47.4% del quintil más cercano al más lejano) pero predictor débil del resultado condicionado al fill (ρ=+0.062) — replica el patrón `P(fill|X)`≠`P(outcome|filled,X)` ya documentado en `BOT-024.2` para Momentum; `time_to_fill_bars|filled` reportado como distribución pura (mediana=1 barra, 80.4% en 1 barra, 92.6% en ≤3 barras) sin convertir "3 barras" en gate/threshold. **Redundancia cruzada (hallazgo importante, pendiente para BOT-049.2):** `risk_atr` es casi redundante (ρ=+0.981) con `origin_dist_atr`, el representante congelado de Structure (`BOT-048.2`, `ORIGIN_ONLY_FREEZE`) — ambas miden esencialmente la misma distancia HTF/ATR bajo esta estrategia, cuestión que `BOT-049.2` debe resolver explícitamente antes de congelar una definición. Redundancia con Momentum (`roc_atr_3`) y Alignment (`closed_ema200_slope`) baja en todas las candidatas (`|ρ|≤0.46`). **CVP:** `cvp_score()` calcula el breakeven neto con la MISMA fórmula exacta que `breakeven_pct` de esta tarea (ρ=+1.000 verificado) — Economics no la reintroduce, aporta la escala continua y la fricción continua que CVP no expone (CVP es un +1/0/-1 discreto gateado por ≥10 trades cerrados). **LONG/SHORT:** ninguna candidata invierte de signo (cambios de forma/magnitud sí, especialmente en fricción de spread y `distance_to_limit_atr`). **Estabilidad temporal:** `origin_retracement_frac` la más estable; el resto con signo consistente pero IC bootstrap que no siempre excluye 0 en los 3 sub-períodos. **Clasificación de discovery:** `risk_atr` y `spread_over_risk` `PRIMARY_CANDIDATE` (el segundo con reserva de redundancia con Structure), `distance_to_limit_atr` `SECONDARY_CANDIDATE` (pregunta distinta: fricción de ejecución, no diseño económico), `origin_retracement_frac` `CROSS_FACTOR_ONLY` (confirmado), `rr_nominal/rr_geometric` `REJECTED` (sin variación), `swap_1night_estimate_usd` `CONTEXT_ONLY`/`INSUFFICIENT_EVIDENCE` (constante por dirección en esta cuenta). Ningún score/peso/gate implementado — discovery puro, cero cambios de producción (verificado por `git diff --stat`, único archivo modificado del repo es `BACKLOG.md`; 9/9 tests de la suite existente OK). **Reporte completo (documento maestro, autocontenido):** `reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY.md`. Script: `scripts/discover_economics_features_xau.py`. Evidence log: `reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY-EVIDENCE.log`. Datasets: `reports/BOT-049.1-economics-limits-xau.csv` (Universo A), `reports/BOT-049.1-economics-trades-xau.csv` (Universo B).
- **Siguiente paso planificado dentro de BOT-049 (ejecutado, ver `BOT-049.2`):** resolver la redundancia `risk_atr`↔`origin_dist_atr` (Structure) y decidir si congelar formalmente escala/fricción como definición de Economics — resuelto con resultado `NO_VALID_ECONOMICS_FREEZE`.
- **Dependencias:** BOT-049 (feature padre), BOT-048.2 (candidata `origin_retracement_frac`, reconfirmada `CROSS_FACTOR_ONLY`, no reinterpretada).

### BOT-049.2 — Economics Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-049`, sucesora de `BOT-049.1`. `DEFINITION/FREEZE`, explícitamente no discovery — decide ownership semántico de las candidatas ya evaluadas en `BOT-049.1` frente a Structure, CVP y execution/fill, sin buscar performance ni recalcular features desde cero (reusa los CSV ya congelados de `BOT-049.1`/`BOT-048.1` y la función real `strategy.scoring.cvp_score()`, sin modificarla).
- **Resultado (2026-09-21):** **`NO_VALID_ECONOMICS_FREEZE`** — bajo Config A y el diseño actual de la estrategia, ninguna candidata de `BOT-049.1` sobrevive con ownership propio de Economics. **`risk_atr` → `REJECT_REDUNDANT`** (propiedad de Structure): derivación algebraica desde `strategy/engine.py` (`stop = resistencia[b]·(1+buf)` o `soporte[b]·(1-buf)`, `buf_bp=0.4` mínimo) muestra que `risk_price ≈ |origin_level − entry| + nivel·buf` — la MISMA distancia que `origin_dist_atr` (Structure, `BOT-048.2` `ORIGIN_ONLY_FREEZE`) más un offset minúsculo; verificado exhaustivamente sobre las 3.207 filas de Universo A (no una muestra): `ρ_Pearson=0.982`, `ρ_Spearman=0.976`, 94.7% de eventos con `|risk_atr−origin_dist_atr|≤0.10 ATR` (frente a una escala típica ~1.75-1.79 ATR), 0/3.207 eventos con `origin_dist_atr≤0` (confirma la condición necesaria de la identidad). Es una consecuencia mecánica de que ESTA estrategia ata el stop al mismo nivel HTF que originó la señal — no una ley general de Economics vs. Structure; si un futuro rediseño desacoplara el stop del nivel de origen, la pregunta debería reabrirse con una ID nueva. **Fricción de spread (`spread_over_risk`/`breakeven_pct`/`rr_effective_net`) → ownership asignado a CVP, sin freeze propio de Economics:** bajo RR=1 fijo las tres son la misma cantidad (`BOT-049.1`); se verificó exhaustivamente (las 3.207 filas, no muestra) que `breakeven_pct` es la MISMA fórmula que el término de costo de `strategy.scoring.cvp_score()` (`cvp_margin + breakeven_pct == aciertos_pct` constante, `std=2.7e-15`, error de punto flotante puro). CVP (BOT-023, en producción) retiene ownership del juicio costo-vs-aciertos%; Economics no recrea una segunda representación de la misma fórmula bajo otro nombre. **`distance_to_limit_atr` → reclasificado `execution/fill quality` (order lifecycle / Time-to-Fill), NO Economics:** predice fuertemente `P(fill)` (ρ=−0.401) pero débilmente `pnl_r|filled` (ρ=+0.062) — responde una pregunta de ejecución, no de diseño económico del trade. **`origin_retracement_frac` → `CROSS_FACTOR_ONLY` reconfirmado**, sin error nuevo encontrado (se revisó explícitamente buscando uno, ver reporte). **`rr_nominal`/`rr_geometric` → `REJECT_OTHER`** (degenerados, sin variación bajo Config A, ya establecido en `BOT-049.1`). **`ATR_short/ATR_long`** confirmado reservado para `BOT-050.1` (Context), sin tocar. Ningún score, peso, gate ni cambio de producción — cero cambios en `strategy/`/`execution/`/`api/`/`panel/` (verificado por `git diff --stat`), 9/9 tests de la suite existente OK. **Backlog revisado íntegramente** (ver reporte sección "Backlog Review") — corrigió una referencia obsoleta en el bloque agregado de `BOT-024` (subtareas de `BOT-049` seguían marcadas `TODO`/`NEXT ACTIVE` pese a que `BOT-049.1` ya estaba `DONE` desde el cierre de esa tarea). **Reporte completo (documento maestro, autocontenido):** `reports/BOT-049.2-ECONOMICS-DEFINITION-FREEZE.md`. Script de verificación determinística: `scripts/freeze_economics_definition_xau.py`. Evidence log: `reports/BOT-049.2-ECONOMICS-DEFINITION-FREEZE-EVIDENCE.log`.
- **Siguiente paso planificado dentro de BOT-049 (no aplica, ver `BOT-049.3`):** con `NO_VALID_ECONOMICS_FREEZE`, no hay contrato que validar OOS — `BOT-051` debe integrar Signal Quality tratando Economics como una dimensión sin representación numérica propia bajo la evidencia actual, no como una dimensión pendiente.
- **Dependencias:** BOT-049.1, BOT-048.2 (`origin_dist_atr`, Structure, reconfirmado sin modificar), BOT-023 (`cvp_score()`, reconfirmado sin modificar).

### BOT-049.3 — Economics Out-of-Sample Validation
- **Categoría:** Scoring / Investigación / Validación
- **Estado:** TODO — NO CONTRACT TO VALIDATE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-049`, sucesora de `BOT-049.2`. `BOT-049.2` concluyó `NO_VALID_ECONOMICS_FREEZE` — no existe ninguna definición congelada de Economics para validar Out-of-Sample. Este ítem se distingue explícitamente de `BOT-024.3`/`BOT-047.3`/`BOT-048.3` (que sí tienen un contrato congelado y esperan únicamente histórico genuinamente posterior al 2026-09-15): aquí la ausencia de OOS **no** es el motivo de que la tarea no avance — el motivo es que no hay definición que someter a datos nuevos. Permanece abierta únicamente como registro de que, si una futura tarea (nueva ID, ej. `BOT-049.4`) redefine Economics tras un cambio de diseño de estrategia o una exposición continua de CVP, esa nueva definición sí deberá pasar por esta validación antes de integrarse a `BOT-051`.
- **Dependencias:** BOT-049.2 (resultado `NO_VALID_ECONOMICS_FREEZE`, sin contrato que heredar).

### BOT-050 — Context
- **Categoría:** Scoring / Investigación
- **Estado:** DONE — `TEMPORAL_ONLY_FREEZE` (feature padre — se cierra porque `BOT-050.2` produjo un contrato congelado válido, aunque parcial; `BOT-050.3` queda `BLOCKED_WAITING_GENUINE_NEW_DATA`, no bloquea el cierre del feature padre — mismo criterio que `BOT-047`/`BOT-048`)
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Feature padre de `BOT-024` (Signal Quality), dimensión `Context` — condiciones ambientales/de mercado alrededor de la señal, separadas explícitamente de Momentum, Alignment, Structure y Economics.
  - **Candidatos futuros a evaluar en `BOT-050.1`** (mencionados aquí solo como referencia, ninguno promovido automáticamente — el discovery deberá clasificarlos): datos ya estudiados descriptivamente en `BOT-045` — sesión, hora/día, ATR/volatilidad, ADX, RSI (cuando corresponda semánticamente a Context y no ya cubierto por Momentum/Alignment), distancia a EMA, régimen, contexto condicional LONG/SHORT, y otras variables ambientales causales. `BOT-045` en sí permanece `DONE` sin cambios — `BOT-050.1` no reabre ni reinterpreta ese hallazgo, solo puede reutilizarlo como antecedente.
  - **Candidata explícita registrada por `BOT-049.1` (2026-09-21):** **Relative Volatility / Volatility Compression-Expansion** — ratio causal `ATR_short / ATR_long`, con períodos short/long a definir mediante diseño disciplinado en `BOT-050.1` (no optimizados por grid search ni elegidos en `BOT-049.1`, que la excluyó explícitamente de Economics por describir régimen/compresión-expansión ambiental, no geometría económica intrínseca del setup — ver `reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY.md` sección 11.4).
  - **Estructura interna:** sigue la misma subestructura `.1/.2/.3` — ver `BOT-050.1` a continuación.
  - **Resultado final (2026-09-21):** `TEMPORAL_ONLY_FREEZE` — únicamente `weekday`(efecto Friday) se congela como factor Context propio; `atr_ratio_short_long` (volatilidad relativa) queda `CROSS_FACTOR_ONLY` pese a evidencia causal/semántica sólida, por perder ownership independiente en un modelo diagnóstico conjunto (ver `BOT-050.2`); `session_utc`/Asia queda `CROSS_FACTOR_ONLY` (limitación DST + no significativo en el modelo conjunto).
- **Dependencias:** BOT-024 (marco conceptual de Signal Quality), BOT-045 (antecedente descriptivo, reutilizado sin reinterpretar).
- **Subtareas:**
  - `BOT-050.1` `DONE` — Context Feature Discovery.
  - `BOT-050.2` `DONE` — Context Definition Freeze (resultado `TEMPORAL_ONLY_FREEZE`).
  - `BOT-050.3` `TODO — BLOCKED_WAITING_GENUINE_NEW_DATA` — Context OOS Validation (contrato de `weekday`/Friday pre-registrado, esperando histórico genuinamente posterior a 2026-09-15).

### BOT-050.1 — Context Feature Discovery
- **Categoría:** Scoring / Investigación
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline
- **Descripción:** Subtarea de `BOT-050` (Context). Investigó qué variables ambientales/de mercado observables, causales y reproducibles existen en el momento de creación del LIMIT (ver candidatos de referencia en `BOT-050`, incluida `ATR_short/ATR_long` reservada explícitamente por `BOT-049.1`/`BOT-049.2`). `OFFLINE / DISCOVERY / NO PRODUCTION CHANGES / NO SCORE / NO GATE` — mismo tipo de disciplina que `BOT-048.1`/`BOT-049.1` (shadow replay exhaustivo + verificación causal empírica antes de interpretar cualquier resultado).
- **Resultado (2026-09-21):** Universo A = 3.207 LIMITS creados (LONG=1.534, SHORT=1.673), Universo B = 2.474 trades filled+cerrados — idéntico al Universo A/B de `BOT-024.2`/`BOT-047.1`/`BOT-048.1`/`BOT-049.1` (mismo motor/dataset/Config A, shadow replay exhaustivo, 0 discrepancias en 8/8 counters y 2.474/2.474 trades; re-slice causal empírico de 41 eventos sobre TODOS los indicadores nuevos —ATR short/long, ADX, RSI, EMA—, 0 discrepancias). **Hallazgo metodológico central:** dos familias mínimas obligatorias del enunciado (RSI, y en parte volatilidad ATR-normalizada) ya habían sido calculadas, sin congelar, dentro del propio discovery de Momentum (`BOT-024.2`) — `rsi_now` (idéntico bit-a-bit a `rsi_level_m5` de esta tarea, ρ=+1.000) y `atr_pct`/`atr14`/`atr5_atr20_ratio` (familia relacionada con `atr_ratio_short_long`, ρ=+0.44 a +0.67); `BOT-024.3` incluso etiquetó `atr_pct` explícitamente como "contexto de volatilidad" — evidencia independiente de que el backlog acertó al reservar esa familia para Context. **7 familias de candidatos evaluadas:** volatilidad relativa (`atr_ratio_short_long` = ATR(14)/ATR(160), primario, y variante de robustez ATR(14)/ATR(288), ambos períodos reusados de constantes YA canónicas del proyecto —`periodos_htf_min`/5 y `D1_WINDOW_MIN`/5—, sin grid search), sesión (`SESSION_BOUNDS_UTC` reusado verbatim), hora del día (continua + codificación cíclica), día de semana, ADX(14) M5 (fuerza de tendencia, no direccional), distancia a la EMA de señal M5 (`dist_ema_m5_atr`) y nivel de RSI(14) M5. **Clasificación final:** `atr_ratio_short_long` y `weekday`(Viernes) `ADVANCE_TO_FREEZE_REVIEW` (evidencia moderada, consistente en 2/3 sub-períodos, sin inversión LONG/SHORT, redundancia cruzada máxima +0.38-0.46 muy por debajo del umbral fuerte del proyecto); `session_utc`(Asia) `CROSS_FACTOR_ONLY` (se solapa temporalmente con el efecto de Viernes, deep-dive conjunto pendiente en `BOT-050.2`); `atr_regime_bucket`/`atr_pct_rank_causal` `CROSS_FACTOR_ONLY` (representaciones secundarias del mismo `atr_ratio_short_long`, ρ≥0.96); `dist_ema_m5_atr` `EXECUTION_FILL_QUALITY`/`REJECT_REDUNDANT` (predictor fuerte de fill —ρ=−0.40— pero débil de outcome —ρ=+0.06—, correlación moderada +0.46 con Momentum `roc_atr_3`); `adx_m5` `REJECT_UNSTABLE` (el efecto solo sobrevive en el agregado ALL, desaparece al partir LONG/SHORT); `rsi_level_m5` `REJECT_REDUNDANT` (identidad exacta ρ=+1.000 con `rsi_now` de Momentum, ya calculada sin congelar; patrón que se invierte de qué extremo de la distribución es peor entre sub1/sub3); `hour_utc_cont`/cíclico `REJECT_UNSTABLE` (screening prácticamente nulo). Ningún score/peso/gate implementado — discovery puro, cero cambios de producción (verificado por `git diff --stat`; 12/12 tests de la suite existente OK). **No se congela ningún contrato** — `BOT-050.2` debe decidir con el mismo rigor de `BOT-047.2`/`BOT-048.2`/`BOT-049.2` si `atr_ratio_short_long` y/o `weekday` sobreviven una revisión más profunda, siendo válido que concluya `NO_VALID_CONTEXT_FREEZE`. **Reporte completo (documento maestro, autocontenido):** `reports/BOT-050.1-CONTEXT-FEATURE-DISCOVERY.md`. Script: `scripts/discover_context_features_xau.py`. Evidence log: `reports/BOT-050.1-CONTEXT-FEATURE-DISCOVERY-EVIDENCE.log`. Evidencia de comandos/checksums: `reports/BOT-050.1-context-evidence.txt`. Datasets: `reports/BOT-050.1-context-limits-xau.csv` (Universo A), `reports/BOT-050.1-context-trades-xau.csv` (Universo B).
- **Siguiente paso planificado dentro de BOT-050 (ejecutado, ver `BOT-050.2`):** revisión humana/formal de `atr_ratio_short_long` y `weekday`(Viernes) — completado con resultado `TEMPORAL_ONLY_FREEZE`.
- **Dependencias:** BOT-050 (feature padre), BOT-045 (antecedente), BOT-024.2 (redundancia cruzada, `rsi_now`/`atr_pct`/`atr14`/`atr5_atr20_ratio` ya calculadas sin congelar), BOT-048.2 (`origin_dist_atr`, Structure, reconfirmado sin modificar), BOT-047.1 (`closed_ema200_slope`, Alignment, reconfirmado sin modificar).

### BOT-050.2 — Context Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-050`, sucesora de `BOT-050.1`. `DEFINITION/FREEZE`, explícitamente no discovery — decidió, sobre el candidate set cerrado de `BOT-050.1` (`atr_ratio_short_long`/`atr_ratio_short_long_alt`, `weekday`/Viernes, `session_utc`/Asia solo para ownership), si existe un contrato Context defendible. 100% reusa los CSV ya causales de `BOT-050.1`/`BOT-024.2`/`BOT-047.1`/`BOT-048.1` (sin recalcular ninguna feature, sin MT5).
- **Resultado (2026-09-21):** **`TEMPORAL_ONLY_FREEZE`.** **Hallazgo central (no anticipado en `BOT-050.1`):** un modelo diagnóstico conjunto único (`pnl_r ~ atr_ratio_short_long + is_friday + is_asia + is_long + roc_atr_3 + closed_ema200_slope + origin_dist_atr`, OLS simple, N=2.371) mostró que `atr_ratio_short_long` tiene coeficiente prácticamente nulo (`−0.0007`, `p=0.9918`) al controlar SIMULTÁNEAMENTE por las 3 dimensiones ya congeladas + Friday + dirección — pese a que sus correlaciones parciales UNO-A-LA-VEZ (controlando cada dimensión por separado) se mantenían estables (`ρ` entre `+0.20` y `+0.29`, similar a la RAW `+0.277`); la colinealidad par-a-par es moderada (máx `|r|=0.333` con `origin_dist_atr`, muy por debajo del umbral fuerte `0.8` del proyecto), por lo que la caída **no es un artefacto de un par casi-duplicado**. `weekday`/Viernes, en cambio, **sobrevive** la misma prueba conjunta (`coef=−0.1461`, `p=0.0078`). Como "ownership independiente" es la prioridad #3 del criterio de decisión (por encima de estabilidad/robustez/asociación con outcome, #6/#7/#9), esto pesa más que la significancia marginal por quintiles de `atr_ratio_short_long` (Q5 excluye cero en ALL/LONG, pero **no sobrevive corrección BH-FDR**, `q=0.088`). **`atr_ratio_short_long` (+ variante `/288`) → `RELATIVE_VOLATILITY_CROSS_FACTOR_ONLY`** (causal, semánticamente ligada al mecanismo HTF de la propia estrategia —`ATR14/160`, `160=periodos_htf_min/5`—, sin redundancia par-a-par fuerte, pero sin ownership independiente pleno). **`weekday`/Viernes → `CALENDAR_CONTEXT_FREEZE`**: Friday peor fuera de sesión Asia (`ExpR=−0.181 [−0.301,−0.061]`, N=264, excluye cero), solo 35.1% de los trades Friday caen en Asia (no es Asia con otro nombre), sin diferencia composicional en Momentum/Alignment/Structure/Volatilidad, efecto persistente en 9/9 estratos (3 controles × 3 terciles), 2/3 sub-períodos significativos del mismo signo (sub2 sin evidencia, no invertido), asimetría direccional real y documentada (fuerte en LONG, ausente en SHORT). **`session_utc`/Asia → `TEMPORAL_CONTEXT_CROSS_FACTOR_ONLY`** (limitación DST no corregida, ya documentada en `BOT-050.1`, más `p=0.309` en el modelo conjunto). **Contrato formal congelado** (RAW categórico por día de semana, `Observed at=limit_created_bar`, `Production status=OFFLINE_ONLY`, `Direction handling` explícito LONG≠SHORT, transformaciones prohibidas —sin gate, sin ponderar por WR/ExpR, sin fusionar con Asia— documentadas) — ver reporte sección 21. Ningún score/peso/gate implementado — cero cambios de producción (`git diff --stat` vacío en `strategy/`/`execution/`/`api/`/`panel/`; 12/12 tests de la suite existente OK). **Reporte completo (documento maestro, autocontenido):** `reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE.md`. Script: `scripts/freeze_context_definition_xau.py`. Evidence log: `reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE-EVIDENCE.log`. Evidencia de comandos/checksums: `reports/BOT-050.2-context-freeze-evidence.txt`.
- **Siguiente paso planificado dentro de BOT-050 (ver `BOT-050.3`):** validación OOS del contrato `weekday`/Viernes — bloqueada por falta de histórico genuinamente posterior a 2026-09-15 (mismo motivo que `BOT-024.3`/`BOT-047.3`/`BOT-048.3`).
- **Dependencias:** BOT-050.1 (`DONE`), BOT-024.2 (`roc_atr_3`, reconfirmado sin modificar), BOT-047.1 (`closed_ema200_slope`, reconfirmado sin modificar), BOT-048.2 (`origin_dist_atr`, reconfirmado sin modificar).

### BOT-050.3 — Context Out-of-Sample Validation
- **Categoría:** Scoring / Investigación / Validación
- **Estado:** TODO — BLOCKED_WAITING_GENUINE_NEW_DATA
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-050`, sucesora de `BOT-050.2`. Validará el contrato congelado de `BOT-050.2` (`TEMPORAL_ONLY_FREEZE`, `weekday`/Viernes — ver contrato formal en `reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE.md` sección 21) sobre histórico genuinamente posterior al corte OOS vigente (2026-09-15) — mismo criterio que `BOT-024.3`/`BOT-047.3`/`BOT-048.3` (contrato ya congelado, esperando solo datos). No se fabrica OOS con datos ya vistos.
- **Dependencias:** BOT-050.2 (`DONE`, contrato: `weekday`/Viernes RAW categórico).

### BOT-051 — Signal Quality Integration
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** IN PROGRESS / RESEARCH — `BOT-051.1` `DONE` (decisión `VECTOR_FIRST`), `BOT-051.2` `DONE` (decisión `SIGNAL_QUALITY_VECTOR_V1_FREEZE`), `BOT-051.3` `TODO — NEXT ACTIVE`
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-20
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Integrar las dimensiones de `Signal Quality` (`Momentum` + `Alignment` + `Structure` + `Economics` + `Context`) preservando significado, trazabilidad e interpretabilidad de cada una — **no asume weighted scoring ni pesos iguales/arbitrarios**. Dirección futura de producto a mantener: `SIGNAL QUALITY: XX/100` con tabla/desglose visible de los factores y, si todos cumplen causalidad, disponible desde `limit_created_bar`. La transformación 0–100, los pesos, el manejo de confianza/`confidence` y las reglas de combinación deben definirse **posteriormente, con evidencia** — no en esta entrada ni de forma automática al completarse `BOT-049`/`BOT-050`. `BOT-051` **no introduce por sí mismo ningún gate en vivo**.
  - **Estructura interna (actualizado 2026-09-21 tras `BOT-051.1`):** SÍ adopta subestructura `.1/.2` (se revierte la expectativa original de "ID principal sin subestructura" — el trabajo real de *contract discovery* resultó suficientemente extenso como para justificarlo, igual que `BOT-047`/`BOT-048`/`BOT-049`/`BOT-050`). No se usa `.3` (OOS) porque `BOT-051` no es una feature con su propio discovery estadístico de datos nuevos — es integración de contratos ya congelados por otras líneas; la validación OOS de cada factor individual sigue viviendo en `BOT-047.3`/`BOT-048.3`/`BOT-050.3`.
  - **Economics (actualizado 2026-09-21, ver `BOT-049.2` y `BOT-051.1`):** `BOT-049` cerró con `NO_VALID_ECONOMICS_FREEZE` — no existe una representación numérica propia de Economics para integrar. `BOT-051.1` confirmó y formalizó esto: Economics queda **`EXCLUDED_ABSORBED`** del vector (no es una dimensión "pendiente", no existe como slot). El vector de Signal Quality tiene 4 slots nominales (Momentum, Alignment, Structure, Context), no 5.
  - **Momentum (hallazgo de `BOT-051.1`, 2026-09-21; cerrado por `BOT-024.4`, 2026-09-21):** a diferencia de Alignment/Structure/Context, Momentum (`BOT-024.2`) nunca había tenido un paso de Definition Freeze — solo Feature Discovery (`DONE`) y una OOS Validation `BLOCKED` antes de tener una hipótesis congelada que probar. `BOT-051.1` marcó el slot de Momentum en el vector como `PENDING_DEFINITION`. **`BOT-024.4` cerró ese gap el mismo día: `FREEZE_READY`, canónica `roc_atr_3` (RAW continua)** — ver esa entrada. El slot de Momentum ya no depende de una tarea sin ejecutar; `BOT-051.2` puede poblarlo con este contrato en vez de `PENDING_DEFINITION` (sigue sin OOS, igual que Alignment/Structure).
- **Dependencias:** `BOT-024.2`/`BOT-024.4` (Momentum, `FREEZE_READY` desde `BOT-024.4`; OOS `BOT-024.3` sigue `BLOCKED`), `BOT-047` (Alignment, `FREEZE_READY`), `BOT-048` (Structure, `ORIGIN_ONLY_FREEZE`), `BOT-049` (Economics, `DONE — NO_VALID_ECONOMICS_FREEZE`, sin representación que integrar), `BOT-050` (Context, `TEMPORAL_ONLY_FREEZE`).
- **Relación con `BOT-025`:** `BOT-025` (gate configurable de scoring) queda **downstream** de esta tarea — la secuencia acordada es `Factor Discovery/Freeze (BOT-047/048/049/050) → BOT-051 (Signal Quality Integration) → BOT-025 (gate/decisión de ejecución) → posible gate/ejecución futura`. `BOT-025` puede cambiar de diseño según lo que `BOT-051` produzca; no se marca `DONE`, `CANCELLED` ni se reinterpreta aquí — ver esa entrada.
- **Subtareas:**
  - `BOT-051.1` `DONE` — Signal Quality Integration Design / Contract Discovery (decisión `VECTOR_FIRST`).
  - `BOT-051.2` `DONE` — Signal Quality Definition Freeze (decisión `SIGNAL_QUALITY_VECTOR_V1_FREEZE`).
  - `BOT-051.3` `TODO — NEXT ACTIVE` — Signal Quality Vector Shadow Reconstruction / Observability.

### BOT-051.1 — Signal Quality Integration Design / Contract Discovery
- **Categoría:** Scoring / Investigación / Diseño de contrato
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-21
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-051`. **NO** define score 0–100, **NO** asigna pesos, **NO** define thresholds, **NO** crea gate de ejecución. Objetivo exclusivo: descubrir y documentar un contrato sólido de integración — qué significa `Signal Quality` cuando Momentum+Alignment+Structure+Context conviven en una misma evaluación ex ante de una señal, preservando causalidad, interpretabilidad, reproducibilidad, ownership y ausencia de doble conteo. Reusa exclusivamente los contratos/artefactos ya congelados/validados de `BOT-024.2`, `BOT-047.2.3`, `BOT-048.2`, `BOT-049.2`, `BOT-050.2` — sin recalcular ninguna feature congelada, sin acceso a MT5.
- **Resultado (2026-09-21):** **Pre-flight:** branch `main`, HEAD inicial `5da85c9`, working tree limpio, confirmado sin cambios en `strategy/`/`execution/`/`api/`/`panel/` antes y después. **Gap detectado (no improvisado, documentado explícitamente):** Momentum (`BOT-024`) es la única de las cinco líneas sin un paso de Definition Freeze — `BOT-024.3` (OOS) está `BLOCKED` *antes* de tener una hipótesis congelada, no después; se trata como `NOT_FROZEN`, no como equivalente a las otras cuatro. **Factor Contract Matrix construida** (`reports/BOT-051.1-factor-contract-matrix.csv`) con las 5 dimensiones: Momentum `NOT_FROZEN`, Alignment `FREEZE_READY` (Structural Alignment Consensus, categórico 6 estados, ordinalidad explícitamente rechazada), Structure `ORIGIN_ONLY_FREEZE` (`origin_dist_atr`, continuo RAW), Economics `NO_VALID_ECONOMICS_FREEZE` (excluido, absorbido por Structure/CVP), Context `TEMPORAL_ONLY_FREEZE` (`weekday`/Viernes, categórico). **Causal timestamp confirmado idéntico en los 5 factores:** `limit_created_bar`. **Auditoría pairwise:** sin redundancia fuerte (`|ρ|≥0.8`) nueva entre los tres factores congelados (Alignment↔Structure ρ=0.027, Structure↔Context sin relación mecánica directa aunque el candidato rechazado de Context —`atr_ratio_short_long`— sí solapaba con el mecanismo HTF de Structure, correlación cruzada +0.383); única correlación moderada sin resolver es Momentum↔Structure (ρ=-0.214, no crítica porque Momentum no está congelado). **Missing semantics:** diseño de dos niveles — inclusión de factor (`INCLUDED`/`EXCLUDED_ABSORBED`/`PENDING_DEFINITION`) y disponibilidad por observación (`AVAILABLE`/`NEUTRAL_OBSERVED`/`UNAVAILABLE`, generalizando el patrón ya usado por Alignment). **Reconstrucción causal empírica** (`scripts/reconstruct_signal_quality_vector_xau.py`): unión por `trade_id` de Alignment (`BOT-047.2.2`, N=2.474)/Structure (`BOT-048.1`)/Context (`BOT-050.1`) — 2.474/2.474 exitosa en ambos joins, distribución de estados de Consensus reproducida exactamente igual a la publicada en `BOT-047.2.3` (verificación cruzada de la regla de derivación). **Cardinalidad real medida** (solo dimensiones categóricas congeladas, Structure queda fuera por ser continuo): Alignment(6)×weekday(6 observados)×direction(2) = 72 teóricas, 55 observadas, 17 no observadas, 4 raras (N≤5) — sin colapsar ningún estado. **Candidatos de representación comparados:** Candidate A (Factor Vector) recomendado — preserva información, tipos heterogéneos, reconstructibilidad demostrada; Candidate B (Composite State) rechazado por prematuro (requeriría inventar bins para Structure, prohibido); Candidate C (Ordinal) rechazado (Alignment rechaza ordinalidad explícitamente en su propio contrato, asimetría LONG/SHORT documentada lo haría engañoso); Candidate D (Scalar 0-100) fuera de alcance, solo anotado conceptualmente. **Monotonicidad:** ninguna defendible entre factores; dentro de cada factor solo débil/provisional y siempre condicionada por dirección (N de celda extrema por debajo del umbral de estabilidad del proyecto en varios casos). **Economics ownership reconfirmado** sin contradicción nueva. **DECISIÓN: `VECTOR_FIRST`** — vector de 4 slots (Momentum/Alignment/Structure/Context) con `direction` como metadato obligatorio adjunto (no una 5ª dimensión); 3 slots poblables hoy, Momentum `PENDING_DEFINITION`. Ningún peso, threshold, score 0-100 ni gate introducido — cero cambios de producción. **Reporte completo (documento maestro, autocontenido):** `reports/BOT-051.1-signal-quality-integration-design.md`. Script: `scripts/reconstruct_signal_quality_vector_xau.py`. Evidence log: `reports/BOT-051.1-SIGNAL-QUALITY-INTEGRATION-EVIDENCE.log`. Artefactos: `reports/BOT-051.1-factor-contract-matrix.csv`, `reports/BOT-051.1-vector-cardinality-xau.csv`.
- **Siguiente paso planificado dentro de BOT-051 (ver `BOT-051.2`):** formalizar el esquema tipado del vector de 4 slots — sin poblar Momentum hasta que exista un nuevo Definition Freeze para esa dimensión (fuera de alcance de `BOT-051.2` salvo decisión explícita de abrirlo primero).
- **Dependencias:** BOT-024.2 (Momentum, sin freeze — gap documentado), BOT-047.2.3 (Alignment, `FREEZE_READY`), BOT-048.2 (Structure, `ORIGIN_ONLY_FREEZE`), BOT-049.2 (Economics, `NO_VALID_ECONOMICS_FREEZE`, reconfirmado sin modificar), BOT-050.2 (Context, `TEMPORAL_ONLY_FREEZE`).

### BOT-051.2 — Signal Quality Definition Freeze
- **Categoría:** Scoring / Investigación / Definición formal
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-21
- **Versión objetivo:** N/A — investigación offline, sin release de producción
- **Descripción:** Subtarea de `BOT-051`, sucesora de `BOT-051.1`. Formaliza el esquema tipado del vector `VECTOR_FIRST` decidido en `BOT-051.1`: estructura con campos `momentum`, `alignment` (enum 6 estados), `structure` (float continuo), `context` (enum 7 días), más `direction` como metadato obligatorio adjunto. `DEFINITION/VERIFICATION/FREEZE`, no discovery — reusa exclusivamente los contratos ya congelados de `BOT-024.4`/`BOT-047.2.3`/`BOT-048.2`/`BOT-049.2`/`BOT-050.2`, sin recalcular ninguna feature, sin MT5.
- **Resultado (2026-09-21):** **`SIGNAL_QUALITY_VECTOR_V1_FREEZE`.** Pre-flight confirmó que `BOT-024.4` (congelada en una sesión separada del usuario entre el cierre de `BOT-051.1` y el inicio de esta tarea, commit `06c948a`) es el contrato vigente de Momentum y reemplaza `PENDING_DEFINITION` — verificado leyendo el reporte real, no asumido del enunciado. **Esquema tipado congelado:** `SignalQualityVectorV1(schema_version, observed_at_bar, observed_at_time_utc, direction, momentum: FactorObservation[float], alignment: FactorObservation[AlignmentState], structure: FactorObservation[float], context: FactorObservation[Weekday])`, con `FactorObservation{status: AVAILABLE|UNAVAILABLE, value}` como wrapper único de disponibilidad — para Alignment, `status` se deriva 1:1 de su propio enum (que ya incluye `UNAVAILABLE` como uno de sus 6 estados) en vez de competir con él. **Reconstrucción causal empírica** (`scripts/reconstruct_signal_quality_vector_v1_xau.py`, universo base = artefacto de Alignment, N=2.474 — limitación de artefacto documentada, no de contrato): joins Momentum/Structure/Context 2.474/2.474 exitosos, 0 duplicados, 0 discrepancias, 0 valores de enum inválidos, 0 `FLIP_UNDEFINED`; **2.456/2.474 eventos reconstruidos completamente (4/4 `AVAILABLE`)**, 18/2.474 con `UNAVAILABLE` (100% atribuible a Alignment, ya documentado por su propio contrato); verificado explícitamente que ninguno de los 1.234 eventos `alignment=NEUTRAL` se confunde con `UNAVAILABLE`. **Cross-factor tras incorporar `BOT-024.4`:** Momentum↔Structure `ρ=+0.317` (recomputado por `BOT-024.4` contra la feature canónica real `roc_atr_3` — resuelve una discrepancia aparente con el `ρ=-0.214` que `BOT-048.2` había medido contra `roc_atr_10`, un candidato nunca promovido a canónico: no es una contradicción, son features distintas); Momentum↔Context sin patrón marcado, y el uso de `roc_atr_3` como control en el modelo conjunto de `BOT-050.2` queda retroactivamente confirmado como válido (cierra el Riesgo #4 de `BOT-051.1`); Momentum↔Alignment sin patrón marcado (descriptivo, Alignment no admite correlación numérica por ser no-ordinal); Alignment↔Structure↔Context sin cambios respecto a `BOT-051.1`. Ninguna redundancia fuerte (`|ρ|≥0.8`) entre los cuatro contratos congelados. **Economics confirmado `EXCLUDED_ABSORBED`**, no es campo del schema. **17 invariantes congelados** (los 14 del enunciado + 3 nuevos: `NEUTRAL`≠`UNAVAILABLE` verificado en datos, universo de reconstrucción acotado por el artefacto de Alignment documentado explícitamente, reapertura de cualquier contrato fuente requiere ID nueva). Ningún peso, threshold, bin, score 0-100 ni gate introducido — cero cambios de producción (`git diff --stat` vacío en `strategy/`/`execution/`/`api/`/`panel/`, 5/5 tests de la suite existente OK). **Reporte completo (documento maestro, autocontenido):** `reports/BOT-051.2-signal-quality-definition-freeze.md`. Contrato machine-readable: `reports/BOT-051.2-signal-quality-contract.json`. Script: `scripts/reconstruct_signal_quality_vector_v1_xau.py`. Evidence log: `reports/BOT-051.2-SIGNAL-QUALITY-FREEZE-EVIDENCE.log`. Auditoría: `reports/BOT-051.2-signal-quality-vector-audit-xau.csv`.
- **Siguiente paso planificado dentro de BOT-051 (ver `BOT-051.3`):** Shadow Reconstruction / Observability del vector — sin score, sin gate.
- **Dependencias:** BOT-051.1 (`DONE`, decisión `VECTOR_FIRST` y semántica de missing de dos niveles), BOT-024.4 (`DONE — FREEZE_READY`, contrato de Momentum poblado en el vector).

### BOT-051.3 — Signal Quality Vector Shadow Reconstruction / Observability
- **Categoría:** Scoring / Investigación / Observabilidad
- **Estado:** TODO — NEXT ACTIVE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-21
- **Versión objetivo:** N/A — investigación offline, sin release de producción (a definir si en algún punto requiere exponer datos en `panel/` como solo lectura)
- **Descripción:** Subtarea de `BOT-051`, sucesora de `BOT-051.2`. Objetivo: producir el vector `SignalQualityVectorV1` (congelado en `BOT-051.2`, `reports/BOT-051.2-signal-quality-contract.json`) en modo shadow sobre el universo histórico más amplio posible (incluyendo Universo A completo, N=3.207, una vez exista o se genere un artefacto de Alignment para los LIMITs no filled — hoy la reconstrucción de `BOT-051.2` solo cubre Universo B, N=2.474, por limitación de artefacto, no de contrato); verificar estabilidad/reconstructibilidad; preparar la exposición del vector desde `limit_created_bar`; acumular evidencia OOS en paralelo a medida que exista histórico genuinamente posterior al 2026-09-15. **Sin score, sin peso, sin threshold, sin gate** — sigue siendo observacional/shadow, no cambia el comportamiento de `strategy/`/`execution/`.
- **Dependencias:** BOT-051.2 (`DONE — SIGNAL_QUALITY_VECTOR_V1_FREEZE`, contrato a reconstruir en shadow).

### Pendientes — Análisis y validación posterior (Signal Quality)
*(Agregado 2026-09-21 al reconciliar el backlog tras el cierre de `BOT-049`/`BOT-049.2` — índice de lo que sigue abierto en esta línea de investigación, para que no se pierda de vista al pasar a `BOT-050`. No son tareas nuevas, todas referencian IDs ya existentes.)*

- **A. OOS genuino pendiente (no cancelado — esperando datos, no reinterpretación):** tres definiciones ya congeladas siguen esperando histórico genuinamente posterior al **2026-09-15** para poder validarse Out-of-Sample — **ninguna se da por válida todavía, ni se asume que la muestra ya alcanza**:
  - `BOT-024.3` — Momentum OOS, contrato canónico `roc_atr_3` congelado por `BOT-024.4` (`FREEZE_READY`, 2026-09-21). `BLOCKED`.
  - `BOT-047.3` — D1 Alignment OOS, contrato Structural Alignment Consensus (`BOT-047.2.3`, `FREEZE_READY`). `READY / WAITING FOR OOS`.
  - `BOT-048.3` — Structure OOS, contrato `origin_dist_atr` (`BOT-048.2`, `ORIGIN_ONLY_FREEZE`). `PENDING / WAITING OOS`.
  - **Distinto de `BOT-049.3`** (`NO CONTRACT TO VALIDATE` — no hay definición Economics que someter a OOS, no es un problema de datos). Retomar las tres de arriba en cuanto exista suficiente histórico nuevo — no antes.
- **B. `distance_to_limit_atr` / execution quality (hallazgo a analizar más adelante, sin US propia todavía):** `BOT-049.1`/`BOT-049.2` encontraron que `distance_to_limit_atr` (distancia entre el precio y el LIMIT al crearlo, normalizada por ATR) predice fuertemente `P(fill)` (ρ=−0.401) pero débilmente `pnl_r|filled` (ρ=+0.062) — pertenece conceptualmente a **fill probability / Time-to-Fill / execution quality**, no a Economics. No se abre una User Story principal nueva solo por esto; queda registrado como hallazgo pendiente de una futura investigación de ejecución/order lifecycle si se decide abrir esa línea. Elementos a recuperar si se retoma: `P(fill | distance_to_limit_atr)` (fill rate 95.6%→47.4% por quintil), distribución de `time_to_fill_bars | filled` (mediana=1 barra, 92.6% en ≤3 barras, sin convertir en gate), distribución de expiración/no-fill. Ver `reports/BOT-049.1-ECONOMICS-FEATURE-DISCOVERY.md` sección 8 y `reports/BOT-049.2-ECONOMICS-DEFINITION-FREEZE.md` sección 5.
- **C. CVP y futura integración:** CVP (`BOT-023`/`strategy/scoring.py::cvp_score()`) retiene ownership completo de la fricción/costo (`BOT-049.2` sección 4). Cuando se llegue a `BOT-051`: **no** duplicar `breakeven_pct`, **no** reintroducir `spread_over_risk`/`rr_effective_net` como evidencia independiente, **no** contar Economics + CVP dos veces. Nota de diseño futuro (no ejecutar ahora): si se necesita una representación continua de la fricción sin gate de `aciertos_pct`, la vía correcta es exponer/refactorizar el subcálculo interno de `cvp_score()`, no implementar una segunda fórmula paralela.
- **D. Economics podría reabrirse solo bajo cambio estructural (nota futura, no tarea activa):** `BOT-049` podría requerir una nueva investigación si en el futuro (i) el stop deja de estar mecánicamente ligado a `origin_level`, (ii) `rr` deja de ser fijo/degenerado, o (iii) la arquitectura de costos/CVP cambia materialmente. Cualquier reapertura usa una **ID nueva** (p. ej. `BOT-049.4`) — nunca reinterpreta `BOT-049.2` en silencio.
- **E. Context — resultado obtenido (2026-09-21), parcial, no forzado:** `BOT-050.2` cerró en `TEMPORAL_ONLY_FREEZE` — únicamente `weekday`/Viernes tiene ownership independiente defendible; `atr_ratio_short_long` (volatilidad relativa) tenía evidencia causal/semántica sólida pero perdió ownership independiente en un modelo diagnóstico conjunto (su contribución marginal se anuló al controlar simultáneamente por Momentum+Alignment+Structure+Friday+dirección, pese a no tener redundancia par-a-par fuerte con ninguna) — quedó `CROSS_FACTOR_ONLY`, no descartada, disponible para un futuro modelo conjunto de `BOT-051`. Ver `reports/BOT-050.2-CONTEXT-DEFINITION-FREEZE.md`.
- **F. Signal Quality Integration (`BOT-051`) no exige cinco representaciones numéricas obligatorias — actualizado 2026-09-21 tras `BOT-051.2`:** tabla de estado actual — Momentum (`BOT-024.2` `DONE`, `BOT-024.4` `FREEZE_READY` — canónica `roc_atr_3`, RAW; OOS `BOT-024.3` `BLOCKED`), Alignment (`BOT-047.2.3` `FREEZE_READY`, OOS `READY/WAITING`), Structure (`BOT-048.2` `ORIGIN_ONLY_FREEZE`, OOS `PENDING/WAITING`), Economics (`BOT-049.2` `NO_VALID_ECONOMICS_FREEZE` — **excluida del vector, `EXCLUDED_ABSORBED`, no pendiente**), Context (`BOT-050.2` `TEMPORAL_ONLY_FREEZE` — **representación parcial**: solo `weekday`/Viernes, OOS `BLOCKED_WAITING_GENUINE_NEW_DATA`). **`BOT-051.2` congeló el esquema `SignalQualityVectorV1`** (decisión `SIGNAL_QUALITY_VECTOR_V1_FREEZE`): vector de 4 slots nominales (no 5), los 4 con Definition Freeze propio y reconstrucción causal verificada (2.456/2.474 eventos con los 4 factores `AVAILABLE`), ninguno OOS-validado todavía. La integración futura (`BOT-051.3` en adelante) debe usar únicamente los factores que sobrevivan sus propios contratos/validaciones — sin pesos, score 0–100, `confidence` ni gate definidos todavía (ver `BOT-051`, `BOT-051.1`, `BOT-051.2`, `BOT-051.3`).
- **G. `BOT-024`/`BOT-025`:** sus estados siguen siendo consistentes con el diseño actual (`TODO` ambos) — no se congelan ni se cancelan prematuramente; su diseño final sigue dependiendo de completar los factores restantes y de la integración de `BOT-051` (ver esas entradas).

### BOT-044 — `scoring.py::cvp_score()` convierte comisión a precio con `contract_size` (mismo patrón que BOT-043, en código que corre en vivo)
- **Categoría:** Scoring
- **Estado:** TODO
- **Prioridad:** LOW (sin impacto real hoy — ver por qué abajo)
- **Incorporado:** 2026-09-15
- **Versión objetivo:** sin definir
- **Descripción:** Encontrado como efecto colateral de investigar BOT-043 (NO corregido ahí — BOT-043 se restringió explícitamente a "el modelo/cálculo del backtest", esto corre en vivo). `strategy/scoring.py::cvp_score()` calcula `commission_price = commission_usd / (contract_size * fixed_lot)` para convertir una comisión en USD a un equivalente en precio (línea ~251). Es el mismo patrón de conversión que BOT-043 encontró incorrecto en `strategy/engine.py` — debería usar `tick_value/tick_size` (ej. vía algo como `BrokerCosts.price_to_usd()`, ahora que existe), no `contract_size`, por la misma razón: en XAUUSDc de esta cuenta `contract_size=1.0` pero `tick_value/tick_size=100`, así que esta fórmula subvaluaría `commission_price` por 100x si `commission_usd` fuera distinto de cero.
- **Notas técnicas:** **Sin impacto real hoy:** `execution/src/bot.py:502` llama a `scoring.score_entry(..., commission_usd=0.0, ...)` hardcodeado ("no hay commission_per_lot configurado en el bot en vivo todavia") — con `commission_usd=0.0`, `commission_price` da `0.0` sin importar la fórmula, así que el score CVP actual no está afectado. El gate de CVP además está desactivado a propósito (`margen<=0` no bloquea, solo se registra — ver BOT-025). Pasaría a importar en el momento en que alguien configure `commission_per_lot` para el scoring en vivo — antes de eso, arreglarlo es una mejora de correctness sin urgencia. `strategy/scoring.py::score_entry()` (línea ~384) y `strategy/test_scoring.py` (fixtures con `contract_size=1.0`) también usan/testean este parámetro y quedarían afectados por cualquier cambio de firma.
- **Dependencias:** BOT-007 (modelo de costos), BOT-023 (scoring).

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
- **Notas técnicas:** Bloqueado por no tener acceso a una segunda máquina/terminal MT5 para probar — no es un problema de código conocido, es falta de entorno de prueba. Ver nota de seguridad en `packaging/README.md` (dev machine con el bot corriendo en vivo contra cuenta real durante las pruebas de instalador). **Decisión 2026-09-15:** no se considera necesario crear infraestructura adicional (segunda instancia del bot, otro bot paralelo, otra instalación/sesión de MT5, otra IP, otra máquina) únicamente para desbloquear este ítem — la investigación de estrategia (BOT-045 y sucesores) se hace OFFLINE sobre datasets históricos y scripts de backtesting, sin requerir una segunda terminal MT5, y el bot productivo permanece aislado de esos experimentos. BOT-031 sigue BLOCKED de forma natural hasta disponer de otra máquina/entorno apropiado por otro motivo (ej. una PC de prueba real para el instalador) — ver "Prioridad actual de trabajo" más abajo.
- **Dependencias:** BOT-026, BOT-027.

---

## Gestión de riesgo

### BOT-032 — Kill switch: máxima pérdida configurable
- **Categoría:** Riesgo
- **Estado:** DONE
- **Prioridad:** HIGH
- **Incorporado:** 2026-09-14
- **Versión objetivo:** v1.1.0
- **Descripción:** Mecanismo configurable (`max_loss = 500`, por ejemplo) que, al alcanzar la pérdida acumulada definida, impida abrir nuevas operaciones, detenga el trading automático, cambie el estado visible del bot, y muestre un mensaje claro ("Maximum loss reached. Trading has been stopped."). La reactivación debe requerir una acción explícita/manual — no debe levantarse solo.
- **Notas técnicas:** Implementado (ver `docs/reports/BOT-032_kill_switch.md` para el detalle completo, `docs/spec-live-execution.md` §12 y `docs/spec-api.md` §6). Resolución de las 3 preguntas de diseño que esta entrada dejaba abiertas:
  1. **Cómo se mide la "pérdida acumulada":** P&L NETO REALIZADO del **día operativo** (`execution/src/operating_day.py`) — un día timezone-aware (IANA `America/Costa_Rica` por defecto, vía `zoneinfo`, nunca "UTC - 6" a mano), NO por sesión ni acumulado histórico. Se recalcula siempre desde `mt5.history_deals_get()` (nunca un contador en memoria) reusando la misma reconciliación segura de `/history` (`mt5_utils.filter_own_deals`).
  2. **Operaciones ya abiertas:** siguen gestionándose con normalidad (SL/TP, `orden_viva`, `caduca`, `max_bars_trade`) — el kill switch NUNCA detiene el `run()` del bot, solo bloquea `_place_order()` para operaciones nuevas (decisión explícita del usuario, ver `docs/spec-live-execution.md` §12).
  3. **Dónde vive la config y cómo se expone:** no hay (ni había) un mecanismo de settings persistido server-side — `daily_max_loss_enabled`/`daily_max_loss_usd` viajan en el body de `POST /start` igual que cualquier otro parámetro, y se validan ahí (Pydantic). El estado "detenido por kill switch" se expone en `GET /status` (`kill_switch: {enabled, triggered, override_active, realized_daily_pnl, ...}`), distinto de `running` (que sigue reflejando si el thread está vivo). El override diario SÍ persiste (`execution/src/kill_switch_store.py`, `user_data_root()`, sobrevive reinicios/upgrades).
  **Tests:** 3 archivos nuevos (`execution/src/test_operating_day.py`, `execution/src/test_kill_switch.py`, `api/test_start_kill_switch.py`) sumados a la suite estándar del repo — **12/12 OK** (9 preexistentes + 3 nuevos), corridos antes y después del cambio, cero regresión. No se tocó ninguna línea de `strategy/` (estrategia/señal intacta por construcción).
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
2. Crear o identificar el ID correspondiente (siguiente ID **principal** disponible: **BOT-052**; si la tarea es una feature experimental que requiere discovery estadístico, considerar la subestructura `.1/.2/.3` — ver "Convención para features experimentales" más abajo — en vez de un nuevo ID principal).
3. Cambiarlo a `IN PROGRESS` al comenzar.
4. Implementar.
5. Correr los tests correspondientes (ver los scripts `test_*.py` de cada módulo — no hay `pytest` instalado en el entorno, se corren como script plano: `python strategy/test_engine.py`, etc.).
6. Cambiarlo a `DONE` únicamente cuando esté realmente validado (no por aparecer mencionado en un doc).
7. Registrar la versión correspondiente.
8. Si corresponde a una release, reflejar el cambio también en `CHANGELOG.md`.

Si durante el desarrollo aparece un bug, deuda técnica, o mejora nueva: agregarla acá con su propio ID en vez de dejarla como comentario suelto en el código.

## Regla permanente — reporte Markdown por tarea (desde 2026-09-15)

Toda tarea relevante de desarrollo, análisis, backtesting, debugging o investigación debe generar un reporte Markdown autocontenido dentro del repositorio. El reporte debe incluir suficiente contexto, resultados, decisiones, tests, artefactos y estado Git para ser compartido posteriormente con ChatGPT u otro colaborador sin depender de la conversación original de Claude Code.

Ubicación: `docs/reports/`, con nombre descriptivo (ej. `docs/reports/BOT-042_rerun_RR_post_BOT-043.md`). El reporte se commitea junto con el resto de los cambios de la tarea — no queda solo en la respuesta del chat. Ver `docs/reports/BOT-042_rerun_RR_post_BOT-043.md` como ejemplo de referencia del nivel de detalle esperado.

## Regla permanente — experimentación sobre la estrategia (desde 2026-09-15)

Toda investigación futura sobre la estrategia (indicadores nuevos, filtros, cambios de parámetros) sigue este orden, sin saltarse etapas:

```
DIAGNÓSTICO → HIPÓTESIS → PRUEBA CONTROLADA → ROBUSTEZ → VALIDACIÓN → CAMBIO EN PRODUCCIÓN
```

Evitar explícitamente: "agregar varios indicadores/filtros simultáneamente y quedarse con la combinación que dé mayor beneficio" — el objetivo es minimizar overfitting y poder atribuir cualquier mejora a una causa concreta, no a la mejor combinación encontrada por fuerza bruta. BOT-045 es el primer ítem que sigue esta regla explícitamente: cubre únicamente la etapa de Diagnóstico/Hipótesis, no autoriza por sí solo pasar a Prueba controlada ni a las etapas siguientes.

La línea de investigación de Alignment (`BOT-047.1 → BOT-047.2 → BOT-047.3`) es consistente con esta misma regla a nivel específico: `BOT-047.1` = Discovery, `BOT-047.2` = Definition Freeze (equivalente a congelar la Hipótesis), `BOT-047.3` = OOS Validation. Completar `BOT-047.3` no implica que Alignment se incorpore automáticamente a producción — cualquier cambio en `Signal Quality`/`BOT-024` requiere una etapa posterior explícita dentro del diseño global de esa US, respetando igualmente esta regla experimental.

---

## Regla permanente — convención de IDs para features experimentales (desde 2026-09-20)

Cuando una feature/capacidad requiera discovery estadístico antes de poder incorporarse al sistema, usar la subestructura decimal:

```text
BOT-XXX — Feature / capacidad principal
 ├─ BOT-XXX.1 — Feature Discovery
 ├─ BOT-XXX.2 — Definition Freeze
 └─ BOT-XXX.3 — OOS Validation
```

**`BOT-XXX` (feature padre):** representa la capacidad conceptual completa (ej. D1 Alignment, Structure, Economics, Context, o cualquier futura feature que requiera investigación estadística). Su estado refleja el agregado de sus subtareas — no se marca `DONE` hasta tener evidencia suficientemente validada (OOS) de la hipótesis final.

**`BOT-XXX.1` — Feature Discovery:** explorar features candidatas, medir relaciones, identificar comportamiento, estudiar estabilidad, estudiar LONG/SHORT, detectar posibles asimetrías, evitar optimización prematura. No congela todavía la definición final.

**`BOT-XXX.2` — Definition Freeze:** revisar la evidencia del Discovery, seleccionar variables, definir matemáticamente la feature, decidir transformaciones, definir thresholds si realmente están justificados, congelar la hipótesis antes de OOS. Después de este punto no se debe utilizar el futuro OOS para rediseñar silenciosamente la misma hipótesis.

**`BOT-XXX.3` — OOS Validation:** validar la definición congelada sobre datos genuinamente nuevos. No reoptimizar, no cambiar thresholds, no agregar ni eliminar features, no ajustar parámetros después de ver OOS, no hacer feature fishing. Si falla, el fallo debe registrarse como resultado experimental válido, no descartarse en silencio.

**Esta convención NO es obligatoria para todo el backlog.** Se usa específicamente para features experimentales que necesitan discovery estadístico. Bugs, fixes, cambios de UI, infraestructura, packaging, documentación, kill switches, mejoras operativas simples, o cualquier tarea cuya implementación ya está claramente definida, continúan usando un ID principal normal (`BOT-XXX`) sin subestructura.

**La secuencia `.1/.2/.3` es el ciclo estándar, no un límite.** Si después del OOS aparece una hipótesis materialmente nueva, se puede crear `BOT-XXX.4` (o posteriores) — documentando claramente que constituye una nueva hipótesis, nuevo experimento, nueva validación o revisión posterior. No se reutilizan `.1/.2/.3` para alterar retroactivamente experimentos ya cerrados.

**Los IDs decimales NO consumen IDs principales nuevos.** Ejemplo: `BOT-047`, `BOT-047.1`, `BOT-047.2`, `BOT-047.3` siguen dejando `BOT-048` como el siguiente ID principal disponible.

**Esta convención se adopta a partir de ahora (2026-09-20) y no reestructura retroactivamente tickets históricos.** No se renumeran `BOT-045`, `BOT-046` ni otros tickets ya cerrados. `BOT-024` ya usaba subtareas antes de esta regla formal y conserva su numeración histórica sin cambios. `BOT-047` (D1 Alignment) es la primera feature organizada formalmente bajo esta convención.

Esta convención es una organización **interna** del ciclo de una feature experimental y no sustituye la regla experimental general de arriba (`DIAGNÓSTICO → HIPÓTESIS → PRUEBA CONTROLADA → ROBUSTEZ → VALIDACIÓN → CAMBIO EN PRODUCCIÓN`). Completar `BOT-XXX.3` no autoriza automáticamente un cambio de producción.

---

## Regla permanente — BACKLOG y commit por tarea ejecutada (desde 2026-09-20)

Cada BOT/subtarea ejecutada debe actualizar `BACKLOG.md` en el mismo cambio y producir un commit Git identificable por su ID. Los fixes descubiertos durante pre-flight que pertenezcan a una tarea anterior deben ir en un commit separado, antes del commit de la tarea actual.

---

## VALIDATION-D1-OOS — Validación Out-of-Sample genuina de D1

**Estado:** PENDING
**Prioridad:** FUTURE VALIDATION

### Objetivo

Cuando exista suficiente histórico nuevo posterior al **15 de septiembre de 2026**, repetir exactamente la metodología de **BOT-046 — Dirección/D1 + Robustez Temporal** para validar las hipótesis encontradas sobre alineación con la tendencia diaria D1.

### Regla fundamental

Los datos posteriores al **2026-09-15** constituyen el primer **Out-of-Sample genuino**, ya que no participaron en BOT-045 ni BOT-046 ni en la generación de sus hipótesis.

Al ejecutar esta validación:

- NO modificar las hipótesis de BOT-046.
- NO modificar thresholds.
- NO modificar la definición de D1.
- NO optimizar parámetros utilizando los nuevos datos.
- NO redefinir qué significa `aligned_with_d1`.
- NO seleccionar únicamente períodos favorables.

Se debe aplicar sobre los nuevos datos exactamente la hipótesis congelada actualmente.

### Hipótesis principal congelada

Evaluar nuevamente si:

- operar **alineado con la tendencia D1** continúa superando a operar **contra D1**;
- `LONG + contra D1` continúa siendo un régimen especialmente desfavorable;
- `SHORT + alineado D1` continúa siendo un régimen favorable;
- la diferencia de expectancy `D1 aligned − D1 against` conserva signo y magnitud relevantes.

### Dependencia

No ejecutar hasta disponer de una cantidad suficiente de datos posteriores al **2026-09-15** para que la validación tenga una muestra razonable.

Este ticket es exclusivamente de **validación futura** y no autoriza ninguna modificación de producción.

### Nota cruzada — no confundir con BOT-047.3

`VALIDATION-D1-OOS` = validación OOS de la hipótesis histórica congelada `BOT-045`/`BOT-046` (`aligned_with_d1`, sin modificar esa definición). `BOT-047.3` = validación OOS de la nueva dimensión formal de Alignment que resulte de `BOT-047.1 → BOT-047.2`. Son experimentos conceptualmente diferentes y coexisten — este ticket no se elimina, no se convierte en BOT-047.3 ni se fusiona con él.

---

## VALIDATION-CONFIG-OOS — Validación Out-of-Sample de candidatos BOT-008

**Estado:** PENDING
**Prioridad:** FUTURE VALIDATION

### Objetivo

Cuando exista suficiente histórico nuevo posterior al **2026-09-15**, validar las configuraciones candidatas congeladas por BOT-008 (`docs/reports/BOT-008_rerun_post_BOT043.md`) sin volver a optimizar parámetros.

### Candidatos congelados

#### cfg_1260
- EMA = 14
- HTF = 200
- Buffer = 0.2
- RR = 0.5

#### cfg_1278
- EMA = 14
- HTF = 200
- Buffer = 0.7
- RR = 0.5

### Regla fundamental

NO modificar estos parámetros utilizando los nuevos datos.

NO probar EMA intermedias.

NO probar HTF adicionales.

NO probar RR adicionales.

NO optimizar Buffer.

NO combinar todavía con D1, ADX, RSI u otros hallazgos de BOT-045/BOT-046.

Los nuevos datos deben utilizarse exclusivamente para responder:

> ¿El edge marginal observado por cfg_1260/cfg_1278 continúa existiendo sobre datos que nunca participaron en su selección?

Evaluar como mínimo:

- trades;
- win rate;
- PF;
- expectancy R;
- Net R;
- Net USD;
- Max Drawdown;
- estabilidad temporal;
- costos reales.

Dado que producción utiliza lote fijo, evaluar obligatoriamente **R y USD** (ver el hallazgo de BOT-008: `cfg_2250` era la única configuración robusta en R en los 3 sub-períodos originales pero resultó perdedora neta en USD — motivo por el que esta regla es explícita acá).

No considerar una configuración validada si únicamente una de las dos métricas cuenta una historia favorable.

### Dependencia

No ejecutar hasta disponer de una muestra OOS razonable posterior al 2026-09-15.

Este ticket es exclusivamente de **validación futura** y no autoriza ninguna modificación de producción.

---

## DECISIÓN — Cierre temporal de optimización histórica

**Fecha:** 2026-09-15

A partir del cierre de BOT-008:

> No continuar realizando sweeps, expansión de rangos, búsqueda de thresholds ni nuevas combinaciones sobre el mismo histórico salvo que exista una hipótesis nueva claramente justificada.

Los candidatos de BOT-008 (`cfg_1260`, `cfg_1278`) y la hipótesis D1 de BOT-045/BOT-046 quedan **congelados** para validación futura (`VALIDATION-CONFIG-OOS` y `VALIDATION-D1-OOS`, ambos arriba). El proyecto vuelve ahora al backlog funcional/operativo previamente acordado — ver "Prioridad actual de trabajo" al principio de este archivo.

Esto tiene como objetivo evitar *data mining* y ciclos indefinidos de análisis sobre el mismo dataset.

---

## DECISIÓN — XAUUSD como activo prioritario (principio multi-activo permanente)

**Fecha:** 2026-09-19 (formalizada durante BOT-024.2, aplica a todo el proyecto hacia adelante)

> **XAUUSD es el activo prioritario del bot.** BTC es secundario. La estrategia nació originalmente para Bitcoin y posteriormente se trasladó/adaptó a Oro, por lo que el bot puede seguir operando BTC ocasionalmente — el diseño debe conservar compatibilidad multi-activo cuando sea razonable.

Reglas derivadas, permanentes:

- Ninguna decisión de scoring, estrategia o arquitectura debe **degradar una solución mejor para XAU** únicamente para forzar simetría/paridad con BTC.
- Los estudios/investigaciones deben reportar resultados **por activo** cuando existan datasets/configuraciones validados para más de uno — nunca mezclar XAU+BTC en una sola muestra estadística (eso escondería diferencias reales entre activos).
- Si una feature/hallazgo funciona en ambos activos, se reporta como evidencia de generalización; si funciona solo en XAU, sigue siendo candidata válida; si funciona solo en BTC, se documenta como específica de BTC pero no dirige el diseño principal.
- **Estado actual de BTC (confirmado en BOT-024.2, 2026-09-19):** bloqueado para cualquier estudio predictivo — `resolve_symbol("BTCUSD")` es ambiguo en el bróker conectado (`BTCUSDc` vs. `BTCUSDTc`), no existe dataset histórico BTC validado en el repositorio, y no existe ninguna configuración de estrategia BTC equivalente a "Config A". No se resuelve por cuenta propia en tareas futuras — requiere evidencia explícita nueva en el repositorio (símbolo exacto decidido, dataset descargado, configuración validada) antes de desbloquearse.
