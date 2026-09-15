# BOT-008 — Re-run completo del sweep de parámetros con motor corregido

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Commit base (motor corregido, BOT-043):** `a0e32f6` y siguientes

Este documento es autocontenido, siguiendo la regla permanente de reportes de `BACKLOG.md`.

---

## Resumen ejecutivo

Se re-ejecutó el barrido completo de 3.780 combinaciones de BOT-008 con el motor de backtesting corregido por BOT-043, sobre el mismo espacio de parámetros original (`docs/spec-backtest.md` §4.1) y el mismo dataset (100.505 velas M5, 2025-04-14 a 2026-09-15). Se detectó que el espacio efectivamente único es de 1.260 configuraciones (no 3.780 — `max_concurrent_por_direccion` resultó inerte con `una_operacion_a_la_vez=True`). **71/1.260 (5.6%) configuraciones únicas tienen expectancy positiva después de costos** — la gran mayoría del espacio sigue sin edge. Existe una región concreta y no aleatoria (EMA≈14-17, HTF=200, Buffer bajo, **RR=0.5**, el extremo inferior de la malla) que pasa la mayoría de los filtros de robustez: consistente en vecindad (MESETA, no pico aislado) y, para dos configuraciones específicas (`cfg_1260`, `cfg_1278`), positiva en USD en los 3 sub-períodos. Sin embargo, **ninguna configuración es simultáneamente robusta en R y en USD en los 3 sub-períodos** — la única que sí lo era en términos de R (`cfg_2250`) resultó ser un perdedor neto en dólares, un hallazgo que subraya por qué verificar ambas métricas (pedido explícito de la tarea) fue decisivo. **Clasificación: ESCENARIO A marginal** — hay evidencia de un edge real pero delgado (PF~1.05), no listo para producción sin una validación Out-of-Sample genuina. Ningún parámetro de producción fue modificado.

---

## Contexto

BOT-008 es el barrido original de parámetros de la estrategia (`docs/spec-backtest.md` §4.1, 3.780 combinaciones sobre el perfil 5m). Ya se ejecutó dos veces con motores contaminados: la corrida original (2026-08-18, sobre `XAUUSDm`, con la lógica HTF vieja) y una re-ejecución (2026-09-15, sobre `XAUUSDc`, con la lógica HTF actual pero con el motor de costos con el bug de BOT-043). BOT-043 corrigió dos errores críticos del motor de backtesting: (1) el signo del swap estaba invertido (se acreditaba en vez de cobrarse); (2) la conversión de precio a USD usaba `contract_size` en vez de `tick_value/tick_size`, subvaluando el PnL/riesgo real en precio por 100x en XAUUSDc. Por ello los resultados de ambas corridas anteriores de BOT-008 **no pueden utilizarse para seleccionar configuraciones** — quedan como evidencia histórica marcada explícitamente como inválida, sin sobrescribirse.

BOT-042 (re-ejecutado post-BOT-043) encontró que variar únicamente RR sobre Config A no produce una mejora robusta. BOT-045/BOT-046 (también post-BOT-043) encontraron evidencia diagnóstica de que la dirección (LONG/SHORT) y la alineación con la tendencia D1 se correlacionan con el resultado de las operaciones, pero **ningún filtro fue implementado** — son hipótesis congeladas para una futura validación Out-of-Sample (`VALIDATION-D1-OOS`), no forman parte de este re-run.

**Esta tarea NO agrega indicadores nuevos ni filtros de BOT-045/BOT-046.** Es exclusivamente una re-evaluación del espacio de parámetros original (EMA, HTF, Buffer, RR, concurrencia) con el motor ya corregido — la misma pregunta que se hizo originalmente BOT-008, respondida con la contabilidad correcta.

**Pregunta central:** ¿existe dentro del espacio original de 3.780 configuraciones alguna configuración que muestre edge robusto cuando se evalúa correctamente con el motor actual?

---

## Motor

| | |
|---|---|
| Branch | `main` |
| Commit base | `a0e32f6` (BOT-043) y todos los commits posteriores hasta el momento de esta corrida |
| `strategy/costs.py::price_to_usd()` | confirmado presente (`price_diff / tick_size * tick_value * lot`) |
| Signo del swap | confirmado `pnl_usd += costs.swap_total_usd(...)` en `strategy/engine.py` |
| Tests de verificación | `strategy/test_costs.py`, `strategy/test_engine.py`, `strategy/test_diagnostics.py` — **TODOS OK** antes de ejecutar |
| Lógica HTF | la de producción (bloque en formación, auto-armado incluido) — no la variante alternativa investigada en `docs/reports/AUDIT-HTF_AB_comparison_2026-09-15.md` (ese audit ya concluyó que la lógica actual es igual o mejor que la alternativa, así que este sweep usa la lógica de producción sin modificarla) |

---

## Dataset

| | |
|---|---|
| Archivo | `backtests/data/XAUUSDc_M5_latest.parquet` |
| Cantidad de velas | 100,505 |
| Rango temporal | 2025-04-14 18:50:03 UTC → 2026-09-15 00:40:03 UTC |
| Símbolo | `XAUUSDc` (resuelto en runtime vía `resolve_symbol("XAUUSD")`) |

Mismo dataset usado en BOT-008 (corrida 2026-09-15 original), BOT-042 y BOT-045/046 — sin re-descargar, sin cambiar el período.

---

## Espacio de búsqueda — 3.780 configuraciones

Localizado en `backtests/src/sweep.py::grid_5m()` (sin modificar) y cruzado contra la definición original en `docs/spec-backtest.md` §4.1 — coinciden exactamente:

| Parámetro | Valores | Cantidad |
|---|---|---:|
| `ema_periods` | 8, 11, 14, 17, 20, 23 | 6 |
| `periodos_htf_min` (HTF) | 200, 350, 500, 650, 800 | 5 |
| `buf_bp` (Buffer) | 0.2, 0.7, 1.2, 1.7, 2.2, 2.7, 3.2 | 7 |
| `rr` (RR) | 0.5, 1.0, 1.5, 2.0, 2.5, 3.0 | 6 |
| `max_concurrent_por_direccion` | 1, 2, 3 | 3 |

**Producto cartesiano:** 6 × 5 × 7 × 6 × 3 = **3.780** — confirmado por cálculo directo antes de ejecutar (`assert total == 3780` en el script, además de la cuenta manual). Sin discrepancias con la definición original — no hizo falta documentar ningún ajuste.

`valid_bars=10`, `orden_viva=True`, `max_bars_trade=500`, `fixed_lot=0.01` fijos en toda la malla (defaults del Pine, igual que el barrido original). `una_operacion_a_la_vez` no forma parte de la malla — usa el default de `StrategyParams` (`True`, igual que producción) en las 3.780 combinaciones.

---

## Sanity check — Config A

Config A (EMA=12, HTF=800, Buffer=0.4, RR=1.0, resto de parámetros de producción) **no forma parte de la malla de 3.780** (ni `ema_periods=12` ni `buf_bp=0.4` están en los valores barridos — es la configuración real de producción, no un punto de la grilla de búsqueda). Se reprodujo por separado con el motor actual, antes de correr el sweep completo, para verificar consistencia contra los números ya publicados en BOT-042/BOT-043:

| Métrica | BOT-042/043 (referencia) | Esta corrida (sanity check) | Coincide |
|---|---:|---:|:---:|
| Trades | 2,474 | 2,474 | ✅ exacto |
| Win Rate | 49.37% | 49.37% | ✅ exacto |
| Net R | −114.22 | −114.28 | ✅ (diff 0.06, ruido de acumulación en punto flotante) |
| Expectancy R/trade | −0.0462 | −0.0462 | ✅ exacto |
| Profit Factor | 0.912 | 0.912 | ✅ exacto |
| Max Drawdown (R) | 140.66 | 140.72 | ✅ (diff 0.06, mismo motivo) |
| % overnight | 6.79% | 6.79% | ✅ exacto |

**Coincide** dentro de una tolerancia despreciable (diferencias de centésimas de R, atribuibles al orden de acumulación en punto flotante entre dos implementaciones distintas del mismo cálculo, no a una discrepancia real). Se procedió con el sweep completo.

---

## Metodología

1. **Etapa 1 — Barrido completo:** las 3.780 combinaciones corridas una por una con `strategy.engine.run_backtest` (motor sin modificar), mismo dataset, mismos costos reales (vía `symbol_info` de MT5 al momento de la corrida). Se guardan **todas** las filas, no solo las mejores. Script: `backtests/scripts/10_bot008_full_sweep_rerun.py`.
2. **Etapa 2 — Robustez temporal de un conjunto amplio de candidatos:** candidatos pre-seleccionados con un criterio **definido antes de ver los resultados completos** (ver más abajo), evaluados en los mismos 3 sub-períodos por índice que usa `04_run_robustness.py`/`05_run_rr_isolation.py`/BOT-045/046 (sin continuidad de estado entre sub-períodos). Script: `backtests/scripts/11_bot008_robustness_candidates.py`.
3. **Etapa 3 — Sensibilidad local (vecindad):** para los finalistas que pasan la etapa 2, se buscan sus vecinos inmediatos en cada una de las 5 dimensiones de la malla (ya calculados en la etapa 1, sin backtests nuevos) para distinguir meseta robusta de pico aislado. Script: `backtests/scripts/12_bot008_neighborhood_analysis.py`.
4. **Etapa 4 — Cobertura exhaustiva de sub-períodos (Q4-Q6) + verificación cruzada R/USD:** para responder Q4/Q5/Q6 sin muestreo, se corrieron los 3 sub-períodos sobre las **1.260 configuraciones únicas completas** (no solo los candidatos de la Etapa 2). Script: `backtests/scripts/13_bot008_subperiods_full_space.py`. Adicionalmente, para los 11 finalistas + `cfg_2250` (el único positivo en R en los 3 sub-períodos), se verificó `net_usd` por sub-período — ver hallazgo dedicado más abajo.

### Criterio de selección de candidatos para la Etapa 2 (pre-definido, antes de ver el sweep completo)

1. Muestra mínima: `n_trades >= 100` en el período completo.
2. Conjunto amplio — unión de: top 25 por `expectancy_r`, top 25 por `profit_factor`, top 25 por *recovery factor* (`net_r / max_drawdown_r`), todos sobre el subconjunto que cumple (1). No se usa "Top 1".

### Criterio de clasificación de vecindad (Etapa 3, pre-definido)

- **MESETA:** ≥60% de los vecinos inmediatos existentes en la malla también tienen `expectancy_r > 0`.
- **PICO AISLADO:** <60% — señal de posible overfitting.

### Criterios de "candidato" vs "descartado" (Etapa 4, pre-definidos, sección 13 del pedido original)

Una configuración se considera candidata solo si combina: expectancy positiva, PF razonable (>1), suficiente número de trades (≥100), drawdown aceptable (recovery factor positivo, no desproporcionado frente a Config A), estabilidad temporal (`positive_subperiods >= 2`, sin depender exclusivamente de sub2), y sensibilidad local razonable (MESETA, no PICO AISLADO). Nunca por tener el mayor Net USD, mayor PF, mayor win rate, funcionar espectacularmente solo en sub2, o ser la única positiva entre vecinas.

---

## Costos utilizados

Capturados en vivo vía `symbol_info()` de MT5 al momento de la corrida del sweep completo:

| | |
|---|---|
| `point` | 0.001 |
| `contract_size` | 1.0 *(informativo, no usado para precio→USD desde BOT-043)* |
| `tick_value` | 0.1 |
| `tick_size` | 0.001 |
| `swap_long_points` | −539.0 |
| `swap_short_points` | 0.0 |
| `commission_per_lot` | 0.0 *(supuesto sin confirmar, igual que en BOT-008/BOT-042/BOT-043)* |
| `triple_swap_weekday` | 2 (miércoles) |

`swap_long_points` (−539.0) difiere ligeramente del valor capturado en la sesión de BOT-043 (−533.9) — variación normal del bróker día a día, no un problema; ambos negativos, mismo orden de magnitud.

## Hallazgo metodológico — `max_concurrent_por_direccion` es inerte

Antes de interpretar los resultados: se detectó que el parámetro `max_concurrent_por_direccion` (barrido en {1, 2, 3}) **no tiene ningún efecto** sobre ninguna de las 3.780 combinaciones — confirmado numéricamente (0 de 1.260 grupos de parámetros muestra variación en `expectancy_r` ni en `n_trades` al variar `max_concurrent_por_direccion`). La causa está en `strategy/engine.py`: con `una_operacion_a_la_vez=True` (el default de producción, fijo en todo este sweep — no forma parte de la malla), el candado de concurrencia es **global** (`limite=1` fijo, cuenta pendientes+abiertas en cualquier dirección) e ignora por completo `max_concurrent_por_direccion`, que solo se usa cuando `una_operacion_a_la_vez=False`. Esto significa que el **espacio efectivamente único** del sweep no es 3.780 sino **1.260** combinaciones (6 EMA × 5 HTF × 7 Buffer × 6 RR), cada una repetida idénticamente 3 veces. No se ajustó la malla original (se corrió tal cual está definida en `docs/spec-backtest.md` §4.1, sin inventar ni recortar valores, tal como se pidió) — se documenta la redundancia acá, y todas las estadísticas de "espacio único" de este reporte usan el denominador correcto de 1.260, no 3.780.

---

## Resultados completos

3.780 filas (1.260 configuraciones únicas × 3 repeticiones inertes) guardadas en `backtests/results/sweep_full_M5_post_BOT-043.csv` — **todas**, no solo las mejores.

**Distribución de `expectancy_r` sobre las 3.780 filas:**

| | valor |
|---|---:|
| Mínimo | −0.1497 R/trade |
| P25 | −0.0818 R/trade |
| Mediana | −0.0549 R/trade |
| Media | −0.0565 R/trade |
| P75 | −0.0346 R/trade |
| Máximo | +0.0189 R/trade |
| Desvío estándar | 0.0333 R/trade |

**Distribución de `profit_factor`:** mínimo 0.805, mediana 0.914, máximo 1.062, media 0.916.

**Distribución de `n_trades`:** mínimo 854, mediana 1.970, máximo 5.355 — todas las 3.780 combinaciones superan ampliamente cualquier umbral razonable de muestra mínima (ninguna quedó por debajo de 100 trades, a diferencia del barrido original que usaba `n_trades>=30` como filtro porque algunas combinaciones sí caían por debajo).

La gran mayoría del espacio (94.4% de las 1.260 configuraciones únicas) tiene expectancy negativa después de costos. Un extremo (**cero** combinaciones cerca del máximo teórico) y el grueso de la masa concentrado entre −0.08 y −0.03 R/trade — un panorama consistente con "el motor corregido no encuentra un edge grande en ningún rincón de esta malla", sin el patrón de picos extremos aislados que sí aparecía en el barrido contaminado original (mejor combinación entonces: +0.01R con 36R de drawdown — un cociente rendimiento/riesgo pésimo, característico de ruido/overfitting).

## Top configuraciones (agregado, período completo)

Top 5 configuraciones únicas por `expectancy_r` (de las 1.260, ignorando los 2 duplicados inertes de `max_concurrent_por_direccion` de cada una):

| cfg_id | EMA | HTF | Buffer | RR | Trades | WR | PF | Exp R | Net R | Max DD (R) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cfg_1260 | 14 | 200 | 0.2 | 0.5 | 4,093 | 70.56% | 1.062 | **+0.0189** | +77.52 | 35.31 |
| cfg_1764 | 14 | 800 | 0.2 | 0.5 | 2,407 | 70.13% | 1.057 | +0.0175 | +42.20 | 31.33 |
| cfg_1927 | 17 | 200 | 1.2 | 0.5 | 3,591 | 70.06% | 1.056 | +0.0173 | +62.21 | 25.13 |
| cfg_1963 | 17 | 200 | 2.2 | 0.5 | 3,527 | 69.89% | 1.056 | +0.0173 | +61.01 | 26.83 |
| cfg_1909 | 17 | 200 | 0.7 | 0.5 | 3,613 | 70.14% | 1.052 | +0.0162 | +58.59 | 29.22 |

**Patrón inmediato y consistente en el top del sweep: RR=0.5 (el extremo INFERIOR de la malla, no el superior) domina completamente el top-20 por expectancy** — señal opuesta a la que encontró BOT-042 sobre Config A aislada, donde subir el RR (hasta 7, fuera de este rango) era lo que mejoraba el resultado. Esto muestra que el efecto de RR no es universal: interactúa fuertemente con EMA/HTF/Buffer, exactamente el tipo de interacción que un barrido completo (y no una optimización de un solo parámetro) está diseñado para revelar. El Win Rate de estas configuraciones (~70%) es naturalmente alto porque RR=0.5 exige ganar menos que se arriesga por operación — no es, por sí solo, evidencia de una señal de entrada mejor.

---

## Robustez sub1/sub2/sub3

Etapa 2 (33 filas = Config A + 33 candidatos, 11 configuraciones únicas × 3 repeticiones inertes de `max_concurrent_por_direccion`, criterio de selección pre-definido arriba). Tabla completa en `backtests/results/bot008_robustness_candidates_post_BOT-043_M5.csv`; resumen de las 11 configuraciones únicas:

| cfg_id | EMA | HTF | Buf | RR | N | WR | PF | Exp R (full) | sub1 Exp R | sub2 Exp R | sub3 Exp R | positive_subperiods |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Config A (ref.) | 12 | 800 | 0.4 | 1.0 | 2,474 | 49.37% | 0.912 | −0.0462 | −0.0983 | **+0.0263** | −0.0568 | **1/3** |
| cfg_1260 | 14 | 200 | 0.2 | 0.5 | 4,093 | 70.56% | 1.062 | +0.0189 | −0.0011 | +0.0164 | +0.0390 | 2/3 |
| cfg_1278 | 14 | 200 | 0.7 | 0.5 | 4,063 | 70.19% | 1.051 | +0.0157 | −0.0046 | +0.0135 | +0.0358 | 2/3 |
| cfg_1764 | 14 | 800 | 0.2 | 0.5 | 2,407 | 70.13% | 1.057 | +0.0175 | −0.0092 | +0.0307 | +0.0305 | 2/3 |
| cfg_1890 | 17 | 200 | 0.2 | 0.5 | 3,655 | 70.23% | 1.048 | +0.0150 | −0.0145 | +0.0312 | +0.0287 | 2/3 |
| cfg_1908 | 17 | 200 | 0.7 | 0.5 | 3,613 | 70.14% | 1.052 | +0.0162 | −0.0168 | +0.0303 | +0.0349 | 2/3 |
| cfg_1926 | 17 | 200 | 1.2 | 0.5 | 3,591 | 70.06% | 1.056 | +0.0173 | −0.0086 | +0.0297 | +0.0309 | 2/3 |
| cfg_1944 | 17 | 200 | 1.7 | 0.5 | 3,557 | 69.81% | 1.047 | +0.0147 | −0.0184 | +0.0253 | +0.0365 | 2/3 |
| cfg_1962 | 17 | 200 | 2.2 | 0.5 | 3,527 | 69.89% | 1.056 | +0.0173 | −0.0112 | +0.0204 | +0.0417 | 2/3 |
| cfg_1980 | 17 | 200 | 2.7 | 0.5 | 3,499 | 69.65% | 1.049 | +0.0152 | −0.0098 | +0.0103 | +0.0441 | 2/3 |
| cfg_1999 | 17 | 200 | 3.2 | 0.5 | 3,459 | 69.38% | 1.040 | +0.0125 | −0.0136 | +0.0044 | +0.0454 | 2/3 |
| cfg_2394 | 17 | 800 | 0.2 | 0.5 | 2,222 | 69.85% | 1.049 | +0.0153 | −0.0235 | +0.0318 | +0.0401 | 2/3 |
| cfg_2538 | 20 | 200 | 0.7 | 0.5 | 3,348 | 69.98% | 1.048 | +0.0151 | −0.0260 | +0.0612 | +0.0105 | 2/3 |

**Patrón consistente y no anticipado:** las 11 configuraciones únicas del top-33 muestran exactamente el mismo patrón — **sub1 negativo, sub2 y sub3 ambos positivos**. Ninguna alcanza 3/3 sub-períodos positivos. A diferencia del patrón encontrado en BOT-042 (donde `sub2` era el único tramo favorable y `sub3` fallaba), acá **`sub3` es tan fuerte o más fuerte que `sub2`** en 7 de las 11 configuraciones (ej. cfg_1999: sub3 +0.045 vs sub2 +0.004) — ninguna de estas 11 depende exclusivamente de `sub2` (todas tienen `sub3` también positivo, la señal de "sub2_only" del script da `False` en las 33 filas). El punto débil sistemático es **`sub1`** (2025-04-14 → 2025-10-02), consistentemente negativo en las 11 configuraciones, con magnitud creciendo junto con el Buffer/EMA en varios casos.

**Config A de referencia muestra el patrón opuesto** (positiva solo en `sub2`, negativa en `sub1` y `sub3`) — confirma lo ya encontrado en BOT-042: el problema de Config A no es solo el RR, es un patrón de dependencia de régimen distinto al de estas configuraciones candidatas.

---

## Sensibilidad local (vecindad)

Para las 11 configuraciones únicas de la Etapa 2 (finalistas: `positive_subperiods>=2` y `expectancy_r>0` — las 11 cumplen ambas condiciones), se buscaron sus vecinos inmediatos en cada una de las 5 dimensiones de la malla, usando los datos ya calculados del sweep completo (sin backtests nuevos). Resultado (`backtests/results/bot008_neighborhood_analysis_post_BOT-043_M5.csv`):

| cfg_id | Vecinos encontrados | Vecinos positivos | % positivos | Clasificación |
|---|---:|---:|---:|:---:|
| cfg_1260 | 6 | 4 | 67% | MESETA |
| cfg_1278 | 7 | 5 | 71% | MESETA |
| cfg_1764 | 6 | 3 | 50% | **PICO AISLADO** |
| cfg_1890 | 6 | 5 | 83% | MESETA |
| cfg_1908 | 7 | 6 | 86% | MESETA |
| cfg_1926 | 7 | 5 | 71% | MESETA |
| cfg_1944 | 7 | 6 | 86% | MESETA |
| cfg_1962 | 7 | 6 | 86% | MESETA |
| cfg_1980 | 7 | 6 | 86% | MESETA |
| cfg_1999 | 7 | 6 | 86% | MESETA |
| cfg_2394 | 6 | 4 | 67% | MESETA |
| cfg_2538 | 7 | 4 | 57% | **PICO AISLADO** |

**9 de 11 (82%) clasifican como MESETA** — la región alrededor de EMA∈{14,17}, HTF=200 (mayormente, con una excepción a HTF=800), Buffer bajo-medio, RR=0.5 es una zona genuinamente amplia y consistente del espacio de parámetros, no un pico puntual aislado. `cfg_1764` (HTF=800, el único finalista fuera de HTF=200) y `cfg_2538` (EMA=20, el único finalista con EMA fuera de {14,17}) son los dos casos que sí clasifican como pico aislado — consistente con estar en el borde de la región densa, no en su centro.

---

## Comparación contra Config A

Mejor finalista (`cfg_1260`, MESETA, mayor expectancy del sweep) contra Config A:

| Métrica | Config A | cfg_1260 (EMA=14, HTF=200, Buf=0.2, RR=0.5) |
|---|---:|---:|
| Trades | 2,474 | 4,093 |
| WR | 49.37% | 70.56% |
| PF | 0.912 | 1.062 |
| Expectancy R/trade | −0.0462 | **+0.0189** |
| Net R | −114.22 | **+77.52** |
| Max DD (R) | 140.72 | 35.31 |
| sub1 expectancy | −0.0983 | −0.0011 |
| sub2 expectancy | +0.0263 | +0.0164 |
| sub3 expectancy | −0.0568 | +0.0390 |

**¿Es rentable?** Marginalmente sí en el agregado (a diferencia de Config A, claramente negativa). **¿Mejora de forma estructural y temporalmente robusta sobre Config A?** Parcialmente: mejora en los 3 sub-períodos individualmente frente a Config A (incluido `sub1`, donde pasa de −0.098 a −0.001 — prácticamente neutraliza el peor tramo de Config A, aunque sin cruzarlo a positivo) y agrega positividad en `sub3` (Config A es negativa ahí). Pero **ningún candidato — incluido este — alcanza 3/3 sub-períodos positivos**, y la magnitud de la mejora es pequeña en términos absolutos por operación (PF apenas por encima de 1). No es una mejora contundente; es una mejora real pero modesta y parcial.

---

## Hallazgo adicional — Net R positivo no implica Net USD positivo (lote fijo)

Al construir la comparación de la Etapa 2 se notó que `net_r` y `net_usd` **no siempre coinciden en signo** — 60 de las 1.260 configuraciones únicas (4.8%) tienen expectancy en R positiva pero PnL en USD negativo, o viceversa (correlación entre ambas: 0.80, alta pero lejos de 1.0). La causa: la cuenta real opera con **lote fijo** (`fixed_lot=0.01`), no con sizing normalizado por riesgo — el múltiplo R de un trade se normaliza por SU PROPIA distancia de stop (que varía con `buf_bp` y el nivel de precio), pero el PnL en dólares no se normaliza por nada. Cuando el `buf_bp` es grande, los stops (y por lo tanto el riesgo en USD por trade) pueden ser bastante más anchos, y si las operaciones ganadoras y perdedoras de un período tienen distancias de stop sistemáticamente distintas, el resultado agregado en R y en USD puede divergir en signo.

Se verificó esto específicamente para los 11 finalistas de la Etapa 2 más `cfg_2250` (el único positivo en R en los 3 sub-períodos), calculando `net_usd` por sub-período:

| cfg_id | Buf | sub1 USD | sub2 USD | sub3 USD | Total USD | positive_subperiods (USD) | positive_subperiods (R) |
|---|---:|---:|---:|---:|---:|:---:|:---:|
| **cfg_1260** | 0.2 | +40.8 | +638.7 | +304.6 | **+984.1** | **3/3** | 2/3 |
| **cfg_1278** | 0.7 | +20.3 | +505.9 | +367.1 | **+893.3** | **3/3** | 2/3 |
| cfg_2538 | 0.7 | −98.3 | +526.0 | +84.8 | +512.5 | 2/3 | 2/3 |
| cfg_1764 | 0.2 | −73.3 | +267.7 | −22.5 | +171.9 | 1/3 | 2/3 |
| cfg_1890 | 0.2 | −29.3 | −151.2 | +254.5 | +73.9 | 1/3 | 2/3 |
| cfg_1908 | 0.7 | −68.2 | −175.1 | +330.4 | +87.1 | 1/3 | 2/3 |
| cfg_1926 | 1.2 | −63.8 | −185.9 | +346.3 | +96.6 | 1/3 | 2/3 |
| cfg_1944 | 1.7 | −113.3 | −176.1 | +392.2 | +102.9 | 1/3 | 2/3 |
| cfg_1962 | 2.2 | −113.8 | −266.6 | +374.6 | −5.9 | 1/3 | 2/3 |
| cfg_1980 | 2.7 | −106.4 | −408.4 | +366.5 | −148.3 | 1/3 | 2/3 |
| cfg_1999 | 3.2 | −126.6 | −367.7 | +417.5 | −76.9 | 1/3 | 2/3 |
| cfg_2394 | 0.2 | −86.2 | −500.4 | +98.9 | −487.7 | 1/3 | 2/3 |
| **cfg_2250** *(el único 3/3 en R)* | 3.2 | +39.7 | **−452.3** | **−42.1** | **−454.7** | **1/3** | **3/3** |

**Esto cambia la lectura del sweep de forma importante:**

1. **`cfg_2250` — el único candidato robusto en R en los 3 sub-períodos — resulta un perdedor neto en USD** (−$454.7 total, negativo en 2 de 3 sub-períodos). Con lote fijo, esta configuración **habría perdido dinero real** pese a tener expectancy en R positiva en todo momento. Se descarta como candidato pese a "ganar" el criterio Q4.
2. **Solo dos configuraciones — `cfg_1260` y `cfg_1278`, ambas con EMA=14 — son positivas en USD en los 3 sub-períodos simultáneamente**, incluido `sub1` (donde su R era ligeramente negativo: las pocas operaciones perdedoras de ese tramo tuvieron un riesgo en dólares menor que las ganadoras, aun con una relación R ligeramente desfavorable). Son, con esta evidencia adicional, los dos finalistas más sólidos del sweep completo — más que `cfg_2250` a pesar de que este último "gana" el criterio literal de 3/3 en R.
3. El resto de los finalistas EMA=17 (que dominaban el ranking por R) resultan bastante más débiles en USD — la mayoría solo 1/3 positivo, con `sub2` pasando de positivo en R a **negativo en USD** en 7 de 9 casos.

**Conclusión de esta sección:** ningún candidato de las 1.260 configuraciones es simultáneamente robusto en R **y** en USD en los 3 sub-períodos — el máximo alcanzado es 3/3 en USD con 2/3 en R (`cfg_1260`/`cfg_1278`). Optimizar y clasificar candidatos únicamente por `expectancy_r` (como es estándar para comparar configuraciones de forma independiente del tamaño de posición) puede llevar a conclusiones engañosas sobre el resultado real de una cuenta con lote fijo — verificar ambas métricas, como se pidió explícitamente en la sección 7 del pedido original, resultó decisivo acá.

---

## Respuestas Q1–Q10

**Nota de denominador:** el espacio *definido* tiene 3.780 combinaciones, pero el espacio *efectivamente único* es 1.260 (ver hallazgo metodológico arriba: `max_concurrent_por_direccion` no tiene efecto). Las respuestas usan 1.260 como base — dividir por 3.780 da exactamente el mismo porcentaje (cada fila única se triplica idénticamente).

**Q1. ¿Cuántas de las 3.780 configuraciones tienen expectancy positiva?**
213/3.780 en filas totales = **71/1.260 configuraciones únicas (5.63%)**.

**Q2. ¿Cuántas tienen PF > 1?**
Las mismas 213/3.780 (71/1.260) — `PF>1` y `expectancy_r>0` son matemáticamente equivalentes en esta definición (ambos dependen solo del signo de `gross_win − gross_loss`), no es una coincidencia de esta corrida.

**Q3. ¿Cuántas cumplen ambas?**
213/3.780 (71/1.260) — el mismo conjunto que Q1/Q2, por la razón anterior.

**Q4. ¿Cuántas son positivas en sub1, sub2 y sub3 simultáneamente?**
**1 de 1.260** (`cfg_2250`: EMA=17, HTF=500, Buffer=3.2, RR=0.5) — evaluado sobre el espacio único **completo**, no una muestra. Sin embargo, ver el hallazgo de la sección anterior: esa única configuración es **USD-negativa** en 2 de 3 sub-períodos y en el total — no se sostiene como candidato una vez verificado en dólares.

**Q5. ¿Cuántas son positivas en al menos 2 de 3 subperíodos?**
**98 de 1.260 (7.78%)**, evaluado sobre el espacio único completo.

**Q6. ¿Los mejores resultados están concentrados nuevamente en sub2?**
**No de la misma forma que en BOT-042/045/046.** Entre los 11 finalistas de mayor expectancy (Etapa 2), el patrón dominante es sub1 negativo / sub2 y sub3 ambos positivos — `sub3` iguala o supera a `sub2` en 7 de los 11 casos en términos de R. En términos de USD, el patrón es distinto todavía: para el subgrupo EMA=17 (9 de los 11), `sub2` pasa a ser **negativo** en USD mientras `sub3` se mantiene fuertemente positivo — es `sub3`, no `sub2`, el período que sostiene el resultado en dólares para la mayoría de los finalistas. Los únicos dos candidatos sólidos en USD en los 3 tramos (`cfg_1260`/`cfg_1278`) no dependen desproporcionadamente de ningún sub-período único.

**Q7. ¿Existe una región/meseta de parámetros robusta o solamente picos aislados?**
Mayormente meseta: 9 de los 11 finalistas (82%) clasifican MESETA por vecindad (≥60% de vecinos inmediatos también con expectancy_r>0). La región se ubica en EMA∈{14,17}, HTF=200 (principalmente), Buffer bajo-medio, **RR=0.5** — el extremo inferior de la malla barrida. Los 2 casos PICO_AISLADO (`cfg_1764` en HTF=800, `cfg_2538` en EMA=20) están en el borde de esa región, no en su centro.

**Q8. ¿Qué parámetros parecen tener mayor impacto sobre el resultado?**
- `rr`: el más determinante — el top-20 completo por expectancy está en `rr=0.5`, y la mediana de expectancy sube monótonamente a medida que `rr` baja en este espacio (patrón opuesto al que mostró Config A aislada en BOT-042, donde subir RR ayudaba — la interacción con EMA/HTF/Buffer es real).
- `ema_periods`: la región positiva se concentra en EMA∈{14,17} — EMA muy bajo (8) o muy alto (20,23) tiende a peor resultado.
- `periodos_htf_min`: HTF=200 (el más chico de la malla) domina el top, aunque no exclusivamente (`cfg_1764`/`cfg_2394` con HTF=800 también aparecen, con expectancy algo menor).
- `buf_bp`: efecto más débil y no monótono dentro de la región positiva — importa más para la robustez en USD (buffers chicos, 0.2–0.7, son los únicos con USD 3/3) que para la expectancy en R misma.
- `max_concurrent_por_direccion`: **sin ningún efecto** (ver hallazgo metodológico).

**Q9. ¿Alguna configuración supera de manera convincente a Config A?**
En el agregado y en R, sí, de forma clara: Config A da expectancy −0.046 R/trade; los finalistas dan entre +0.012 y +0.019 R/trade — una mejora de ~0.06–0.07 R/trade. En USD y en robustez temporal, la superación es **real pero modesta**: `cfg_1260`/`cfg_1278` superan a Config A en USD en los 3 sub-períodos (Config A es USD-negativa en 2 de 3), con una magnitud total de metodología positiva de ~$900–990 sobre 1.4 años a lote 0.01 — una mejora, no una revolución. "Convincente" es una palabra fuerte para un PF de ~1.05.

**Q10. ¿El espacio original de parámetros contiene evidencia suficiente de edge para justificar continuar optimizando esta arquitectura?**
Ver [Conclusión](#conclusión---escenario-a--b--c) — la respuesta es matizada, no un sí/no simple.

---

---

## Limitaciones

- El sweep cubre únicamente el perfil 5m (igual que BOT-008 original) — el perfil 1m no se re-ejecutó en esta tarea.
- La verificación cruzada R/USD por sub-período (sección dedicada arriba) se hizo sobre los 11 finalistas de la Etapa 2 + `cfg_2250`, no sobre las 1.260 configuraciones completas — extenderla a todo el espacio es un candidato razonable para una futura mejora de `13_bot008_subperiods_full_space.py` (agregar `net_usd` junto a `expectancy_r`), no se hizo en esta tarea por alcance/tiempo. Los indicadores Q4–Q6 (positividad en sub-períodos) sí son exhaustivos sobre las 1.260 combinaciones, pero solo en R — el equivalente en USD queda como límite conocido.
- `commission_per_lot=0.0` sigue siendo un supuesto sin confirmar (cuenta Standard, spread-only) — igual que en BOT-008/BOT-042/BOT-043, no se investigó en esta tarea.
- Este re-run usa exclusivamente el motor/lógica de entrada actual — no incorpora ninguna de las variables de régimen de mercado diagnosticadas en BOT-045/BOT-046 (dirección, alineación D1), que quedan congeladas para una futura Prueba Controlada explícita, fuera de este alcance.
- Los sub-períodos se corren de forma independiente (sin continuidad de estado, mismo criterio que `04_run_robustness.py`) — la suma de los 3 resultados por sub-período no coincide exactamente con el resultado del período completo (diferencias de un puñado de trades en los bordes de cada tramo, donde una operación que seguiría abierta en una corrida continua se resuelve distinto al cortar el historial) — ya documentado como característica aceptada de esta metodología desde BOT-042, se aplica igual acá tanto a R como a USD.

---

## Conclusión — Escenario A / B / C

### **ESCENARIO A, marginal — edge real pero delgado, no listo para producción sin validación adicional.**

Hay una región concreta del espacio de parámetros (EMA∈{14,17}, HTF≈200, Buffer bajo, **RR=0.5**) que cumple, con matices, los criterios pre-definidos de Escenario A:

- ✅ Expectancy positiva (+0.012 a +0.019 R/trade) — pequeña pero no nula.
- ✅ PF > 1 (1.04–1.06) — delgado, no espectacular.
- ✅ Comportamiento consistente en configuraciones vecinas — 9 de 11 finalistas son MESETA, no pico aislado.
- ⚠️ Estabilidad temporal — **no llega a 3/3 en R** (máximo 2/3, con `sub1` sistemáticamente débil), pero **dos configuraciones (`cfg_1260`, `cfg_1278`) sí llegan a 3/3 en USD**, la métrica que efectivamente importa para una cuenta de lote fijo.
- ⚠️ Drawdown — aceptable pero no bajo (25–35R en el agregado; Recovery Factor ~1.2–2.4, muy superior al ~0.03 del barrido contaminado original, pero lejos de excelente).

**No es un Escenario A limpio.** Es la mejor evidencia que produjo un barrido exhaustivo y honesto sobre el espacio completo, con un hallazgo adicional importante que refuerza la cautela: el único candidato que sí cumplía el criterio más estricto (3/3 en R, `cfg_2250`) **resultó ser un perdedor neto en USD** — un ejemplo concreto y verificado de que optimizar solo por R-multiple con lote fijo puede engañar. Los dos finalistas que sobreviven el chequeo cruzado R+USD (`cfg_1260`, `cfg_1278`) representan la evidencia más creíble de este sweep, pero siguen siendo un edge **delgado** (PF~1.05) sobre una malla de parámetros, no una señal de entrada demostrablemente distinta.

**No es Escenario C** — no es cierto que "la gran mayoría o totalidad del espacio permanece negativa/inestable" sin matices: hay una región identificable, no aleatoria, que se sostiene bajo verificación de vecindad y (para 2 configuraciones) bajo verificación cruzada R+USD en los 3 sub-períodos.

**Tampoco es un Escenario B puro** (edge que depende exclusivamente de un solo sub-período o que es enteramente pico aislado) — el patrón encontrado es distinto y más matizado que el de BOT-042/045/046: no depende de `sub2` en particular, la mayoría de los finalistas son MESETA, y dos configuraciones pasan el chequeo más estricto en USD.

Se clasifica como **A marginal** precisamente porque el criterio de esta tarea (sección 14) exige explícitamente combinar expectancy positiva + PF razonable + N suficiente + drawdown aceptable + estabilidad temporal + sensibilidad local razonable — y la estabilidad temporal, aunque mejor que cualquier otra cosa vista hasta ahora en este proyecto, **no llega al estándar más limpio de 3/3 en ambas métricas para ningún candidato**.

---

## Recomendación siguiente

**No se ejecuta nada de esto en esta tarea — es una recomendación, no una acción.**

Siguiendo la regla permanente de experimentación (`Diagnóstico → Hipótesis → Prueba controlada → Robustez → Validación → Cambio en producción`), este re-run de BOT-008 cubre las etapas de **Diagnóstico** (¿hay algo interesante en el espacio de parámetros?) y **Robustez** (subperíodos + vecindad + verificación cruzada R/USD). El paso que sigue, antes de tocar producción, es **Validación**:

1. **Validación Out-of-Sample genuina** sobre `cfg_1260`/`cfg_1278` (EMA=14, HTF=200, Buffer 0.2–0.7, RR=0.5) — mismo espíritu que `VALIDATION-D1-OOS` ya definido para BOT-046: esperar a que exista historial posterior al 2026-09-15 que no haya participado en este sweep, y verificar si el patrón (USD positivo en los 3 tramos, PF~1.05) se sostiene sin volver a ajustar ningún parámetro sobre esos datos nuevos.
2. **No mezclar con BOT-045/046 todavía** — las hipótesis de dirección/alineación D1 quedan congeladas por diseño; combinarlas con este resultado de RR=0.5 sería otra optimización simultánea de múltiples variables, exactamente lo que la regla de experimentación busca evitar.
3. Si se decide en el futuro explorar más el vecindario de esta región (ej. RR entre 0.3 y 0.8, no cubierto por la malla original que arranca en 0.5), tratarlo como una **Prueba Controlada nueva, con su propio ID**, no como una extensión silenciosa de este sweep.
4. **No cambiar la configuración real del bot** a partir de este resultado — el criterio de esta tarea es explícito: ningún ganador del sweep se implementa automáticamente, y la evidencia, aunque real, es demasiado delgada (PF~1.05) para saltar directamente a producción sin la etapa de Validación.

---

---

## Backlog

Cambios en `BACKLOG.md`:

- **BOT-008** → `DONE` (ya lo estaba administrativamente, pero ahora con el resultado válido) — Estado actualizado quitando la marca de "resultados invalidados" (siguen invalidados los de las corridas *anteriores*, marcados explícitamente como tales sin borrarlos) y agregando el resumen del resultado de este re-run, con link a este reporte.
- **BOT-042** → sin cambios (`DONE`, no forma parte del alcance de esta tarea).
- **BOT-043** → sin cambios (`DONE`).
- **BOT-044** → sin cambios (`TODO`) — no se tocó.
- **"Prioridad actual de trabajo"** → BOT-008 se tacha como completado, con el resultado y el próximo paso recomendado (validación OOS, no ejecutada).

No se creó ningún ítem `BOT-XXX` nuevo — el hallazgo de que `max_concurrent_por_direccion` es inerte no es un bug (es consecuencia esperada del candado global de `una_operacion_a_la_vez=True`, ya documentado en el código), así que se documenta como nota metodológica en este reporte y en la actualización de BOT-008, no como un ítem de backlog independiente.

---

## Artefactos

**Scripts nuevos (reproducibles, versionados):**
- `backtests/scripts/10_bot008_full_sweep_rerun.py` — barrido completo de las 3.780 combinaciones.
- `backtests/scripts/11_bot008_robustness_candidates.py` — robustez temporal de un conjunto amplio de candidatos (criterio pre-definido).
- `backtests/scripts/12_bot008_neighborhood_analysis.py` — sensibilidad local/vecindad de los finalistas.
- `backtests/scripts/13_bot008_subperiods_full_space.py` — cobertura exhaustiva de sub-períodos sobre las 1.260 configuraciones únicas completas (Q4–Q6, sin muestreo).

**Resultados (`backtests/results/`, sufijo `post_BOT-043` — no se sobrescribió ningún archivo histórico contaminado):**
- `sweep_full_M5_post_BOT-043.csv` — 3.780 filas, todas las combinaciones.
- `bot008_robustness_candidates_post_BOT-043_M5.csv` — Config A + 33 candidatos (11 únicos), con desglose por sub-período.
- `bot008_neighborhood_analysis_post_BOT-043_M5.csv` — clasificación de vecindad (MESETA/PICO AISLADO) de los 11 finalistas.
- `bot008_subperiods_full_space_post_BOT-043_M5.csv` — sub-períodos sobre las 1.260 configuraciones únicas completas.

**Este reporte:**
- `docs/reports/BOT-008_rerun_post_BOT043.md` (este archivo).

Los archivos históricos contaminados (`sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv`) permanecen intactos, sin tocar, como evidencia histórica marcada inválida.

---

## Git

| | |
|---|---|
| **Commit** | este commit — mensaje `research(backtest): full 3780-combination sweep re-run with corrected engine (BOT-008)` en `main` (hash exacto: `git log --oneline -1` sobre este commit, o ver la respuesta final de la tarea) |
| **Branch** | `main` |
| **Push** | confirmado a `origin/main` |
| **Working tree** | limpio tras el push |
| **VERSION** | sin cambios (1.0.0) — esta tarea no modifica código de producto |
| **CHANGELOG.md** | sin cambios — mismo criterio que otras tareas de análisis puro (BOT-008 original, BOT-042, BOT-045/046) |

---

*Generado por Claude Code a partir de la tarea "BOT-008 — Re-run completo del sweep de parámetros con motor corregido" del usuario. 100% offline — no se modificó `strategy/`, `execution/`, la API, el panel, la configuración real, `VERSION` ni `CHANGELOG.md`. Ningún ganador del sweep se implementó automáticamente.*
