# Backlog — pivot-x-sentinel

Fuente única de verdad de tareas, mejoras, bugs y funcionalidades — pendientes y ya resueltas — de todo el proyecto. Reemplaza el tener esto disperso entre `docs/roadmap.md`, comentarios de código, y la memoria de las sesiones de Claude.

**Relación con otros documentos:**
- **[docs/roadmap.md](docs/roadmap.md)** sigue siendo la fuente de verdad del *alcance y orden de las fases* (Fase 0 → Fase 8). Este backlog es más granular: cada tarea concreta dentro (o fuera) de esas fases tiene acá su propio ítem con estado y prioridad.
- **[CHANGELOG.md](CHANGELOG.md)** documenta qué cambió en cada *versión publicada*. Este backlog documenta qué existe, qué se está haciendo, y qué falta — independientemente de si ya se publicó una versión con eso o no.

**Regla de trabajo (ver también el pie de este archivo):** antes de implementar algo importante, buscar o crear su ID acá, pasarlo a `IN PROGRESS`, implementar, correr los tests, y recién pasarlo a `DONE` con la versión donde quedó. Nunca borrar un ítem — si se cancela, pasa a `CANCELLED` con el motivo.

**IDs:** secuenciales, nunca se reutilizan aunque el ítem se cancele. Última ID usada: **BOT-046**.

**Convenciones:**
- Estados: `TODO` · `IN PROGRESS` · `BLOCKED` · `DONE` · `CANCELLED`
- Prioridades: `CRITICAL` · `HIGH` · `MEDIUM` · `LOW`
- "Versión objetivo" solo se completa si ya está decidido — la mayoría de lo pendiente todavía no tiene versión asignada.

---

## Índice por categoría

- [Prioridad actual de trabajo](#prioridad-actual-de-trabajo) · [Arquitectura](#arquitectura) · [Estrategia](#estrategia) · [Backtest](#backtest) · [Ejecución en vivo](#ejecución-en-vivo) · [API](#api) · [Panel](#panel) · [Scoring de entradas](#scoring-de-entradas) · [Empaquetado y releases](#empaquetado-y-releases) · [Gestión de riesgo](#gestión-de-riesgo) · [Noticias económicas](#noticias-económicas) · [Validación y salida a real](#validación-y-salida-a-real) · [Deuda técnica y documentación](#deuda-técnica-y-documentación)

---

## Prioridad actual de trabajo

*(Última actualización: 2026-09-15, ver BOT-046.)* Esta sección representa el **orden operativo recomendado** — puede diferir de la prioridad intrínseca (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`) de cada ítem, que no se modifica solo para coincidir con este orden. Por ejemplo, BOT-008 sigue siendo `CRITICAL` aunque BOT-045/BOT-046 se hayan ejecutado primero.

1. ~~**BOT-045** — Market regime / calidad de entradas~~ `DONE`. ~~**BOT-046** — Dirección/D1 + robustez temporal~~ `DONE` — recomendación: RESULTADO 2 (más historial), ver `docs/reports/BOT-046_direction_d1_temporal_robustness.md`. No se abre todavía una Prueba controlada de filtro/scoring.
2. **BOT-008** — Re-run completo del sweep (`CRITICAL`) — ya puede retomarse, BOT-045/BOT-046 fueron revisados. Los resultados históricos actuales permanecen invalidados (ver BOT-043) mientras tanto.
3. **BOT-032** — Kill switch / máxima pérdida (`HIGH`) — protección de capital, mejora independiente de la optimización de estrategia.
4. **BOT-024 + BOT-025** — Normalización y gate de scoring (`LOW`/`MEDIUM`) — evaluar su implementación ahora que se conocen los resultados de BOT-045 (factores de scoring existentes sin poder explicativo robusto salvo lo ya cubierto por BOT-046). BOT-025 sigue dependiendo de BOT-024.
5. **BOT-033** — Alerta de noticias económicas (`MEDIUM`).
6. **BOT-038** — Checklist de validación (`HIGH`) — revisar/redefinir considerando que el bot ya está operando en real.
7. **BOT-044** — Fix de conversión de comisión en CVP (`LOW` mientras `commission_usd` siga siendo 0).
8. **BOT-039 / BOT-040** — documentación/deuda técnica.

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
- **Estado:** DONE — ⚠️ **RESULTADOS HISTÓRICOS INVALIDADOS, REQUIERE RE-RUN** (ver BOT-043)
- **Prioridad:** CRITICAL
- **Incorporado:** 2026-08-19 (ampliado 2026-09-03)
- **Versión objetivo/alcanzada:** sin release asociado (resultado de barrido, no cambio de código de producto)
- **Descripción:** El único barrido de backtest que existía (`docs/spec-backtest.md` §8, 3.780 combinaciones sobre M5 real) había corrido contra la lógica HTF **vieja** — reemplazada dos veces desde entonces: "bloque en formación" (BOT-005, 2026-08-19) y "alineado a sesión" (BOT-004, 2026-09-03). Re-ejecutado el 2026-09-15: datos frescos descargados (100.505 velas M5, `XAUUSDc`, 2025-04-14 a 2026-09-15), barrido completo (`03_run_sweep.py`) y prueba de robustez en 3 sub-períodos (`04_run_robustness.py`) — ambos corriendo ya contra `htf_session.py` (BOT-004).
- **Notas técnicas:** `backtests/scripts/03_run_sweep.py` y `04_run_robustness.py` tenían `SYMBOL = "XAUUSDm"` hardcodeado (bróker/cuenta vieja) — corregido para usar `resolve_symbol("XAUUSD")` (mismo mecanismo que BOT-011), resuelto en runtime antes de conectar, no como constante de import. Resultados en `backtests/results/sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv` — a pedido explícito del usuario, el contenido/interpretación del resultado no se documenta ni se discute acá (ver `docs/claude-memory/pivot-x-sentinel-no-backtest-talk.md`); el ítem se cierra por haberse *ejecutado*, no por el resultado obtenido. **Actualización 2026-09-15 (BOT-043):** el motor con el que corrió este barrido tenía el bug de costos de BOT-043 (swap acreditado en vez de cobrado + precio→USD subvaluado 100x). La corrida de control de BOT-043 sobre Config A con params idénticos confirma el impacto: mismo `n_trades`/`win_rate` (2.474 / 49.37%, esos no dependen de USD), pero Net R pasa de **+588.44 a −114.22** y Profit Factor de **1.476 a 0.912** con el motor corregido — es decir, este barrido (`sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv`) está corrido con el motor viejo y sus resultados **no son confiables** para ninguna combinación con trades `nights_held>0` (la gran mayoría de las 3.780). Este ítem se mantiene DONE porque el trabajo de *ejecutarlo* está hecho y no se re-abre solo, pero cualquier decisión que dependa de sus números debe esperar un re-run explícito con el motor corregido (fuera de alcance de BOT-043, ver nota de BOT-042). **Actualización 2026-09-15 (BOT-045):** el re-run completo de este barrido (3.780 combinaciones) queda pendiente pero se recomienda ejecutarlo **después** de revisar los hallazgos de BOT-045 (análisis de régimen de mercado/calidad de entrada) — antes de volver a correr 3.780 combinaciones, conviene entender si hay variables de régimen de mercado que expliquen buena parte del comportamiento de la estrategia. Esto no cancela ni degrada la prioridad de BOT-008 (sigue CRITICAL, sus resultados siguen invalidados) — solo ordena el trabajo operativo, ver "Prioridad actual de trabajo" más abajo. **Actualización 2026-09-15 (BOT-045 completado):** BOT-045 ya está `DONE` (ver ese ítem y `docs/reports/BOT-045_market_regime_analysis.md`) — encontró evidencia consistente (dirección LONG/SHORT, alineación con tendencia D1) pero ningún filtro fue implementado, es diagnóstico puro. El re-run completo de BOT-008 sigue pendiente y puede retomarse ahora que se revisó BOT-045.
- **Dependencias:** BOT-004, BOT-005. Ver BOT-043 (bug de costos que invalida los resultados), BOT-042 (re-run parcial ya hecho, aislado en RR) y BOT-045 (revisar antes del re-run completo del barrido).

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
2. Crear o identificar el ID correspondiente (siguiente disponible: **BOT-047**).
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
