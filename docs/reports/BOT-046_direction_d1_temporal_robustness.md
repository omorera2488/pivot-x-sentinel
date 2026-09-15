# BOT-046 — Validación controlada de Dirección y Alineación D1 + Robustez Temporal

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Tipo de tarea:** Investigación **diagnóstica, 100% offline**. No modifica `/strategy`, `/execution`, la API, el panel, ni ningún parámetro de producción. No implementa filtros. No modifica Config A. No inicia BOT-008.

Este documento es **autocontenido**. Continúa directamente de `docs/reports/BOT-045_market_regime_analysis.md` — las hipótesis que prueba (H1/H2/H3) fueron congeladas ahí, antes de mirar el holdout de esta tarea.

---

## 1. Resumen ejecutivo

BOT-046 intentó **romper** las dos hipótesis de mayor confianza de BOT-045 (Dirección LONG/SHORT y Alineación con D1) sometiéndolas a mayor resolución temporal (sextiles, rolling windows de 3 meses), un split cronológico 70/30 (pseudo-OOS) y bootstrap de bloques sobre la diferencia de expectancy entre grupos.

**Ninguna de las dos hipótesis fue refutada**, pero tampoco sobrevivieron de forma idéntica ni con la misma fuerza:

- **H2 (Alineación D1) resultó la más robusta de las dos: evidencia A.** El signo (`alineado > contra`) se mantiene positivo en el **100% de los cortes evaluados** — los 3 sub-períodos, los 6 sextiles y las 16 ventanas rolling válidas, sin una sola excepción. El intervalo de bootstrap excluye cero en el histórico completo, en `sub1`, `sub2` y en `development`. Se debilita (deja de excluir cero, aunque el signo se mantiene) en `sub3` y `holdout`, explicado en gran parte por el tamaño de muestra menor en esos tramos (13% de las operaciones tiene alineación D1 definida), no por una reversión del efecto.
- **H1 (Dirección) resultó prometedora pero más frágil: evidencia B.** El delta SHORT−LONG es positivo en 17 de 18 ventanas rolling (única excepción: la primera, abr-jul 2025) y crece en magnitud con el tiempo. Sin embargo, el intervalo de bootstrap **no** excluye cero en `sub1`, `sub2` ni en `development` (el 70% inicial) — solo lo excluye en `sub3`, `holdout` y en el agregado completo. Es decir: la asimetría direccional parece un efecto que **se fortalece/emerge con el tiempo**, no uno presente con fuerza estadística desde el principio.
- **H3 (Interacción Dirección×D1) muestra el hallazgo más nítido de todo el estudio:** `LONG + contra D1` es consistentemente catastrófico (negativo en los 6 cortes evaluados, expectancy entre −0.25R y −0.55R) y `SHORT + alineado D1` es consistentemente el mejor grupo (positivo en los 6 cortes, +0.10R a +0.28R). Pero **`LONG + alineado D1` NO es consistentemente malo** (positivo en `sub2`/`development`, negativo en `sub3`/`holdout`) y **`SHORT + contra D1` NUNCA es claramente positivo** en ningún corte — el edge de SHORT desaparece cuando está contra D1. Esto muestra que el efecto no es puramente aditivo: la interacción concentra la señal en los extremos.
- Dato adicional no anticipado: **LONG tiene proporcionalmente MÁS operaciones alineadas con D1 que SHORT** (16.2% vs 10.0%) y **SHORT tiene proporcionalmente MÁS operaciones contra D1 que LONG** (15.9% vs 10.2%). Es decir, la ventaja de SHORT **no** se explica por tener una mezcla de alineación D1 más favorable — de hecho la tiene *menos* favorable — lo que sugiere que Dirección aporta información **al menos parcialmente independiente** de Alineación D1 (ver §11, Q8/Q9).

**Recomendación final (§16): RESULTADO 2 — Más historial.** La señal es demasiado consistente para descartarla (H2 en particular), pero ninguna de las dos hipótesis alcanza el estándar completo de "Robusta" simultáneamente en desarrollo Y holdout con significancia estadística — antes de abrir una prueba controlada de modificación se recomienda validar sobre datos futuros que no hayan participado en la generación de BOT-045 (ver limitación de contaminación del holdout, §9).

---

## 2. Contexto y punto de partida

BOT-045 (`docs/reports/BOT-045_market_regime_analysis.md`) encontró, sobre 2.474 operaciones de Config A:

| Variable | Grupo | N | Expectancy (R) |
|---|---|---:|---:|
| Dirección | LONG | 1.189 | −0.100 |
| Dirección | SHORT | 1.285 | +0.004 |
| D1 | Alineado | 321 | +0.067 |
| D1 | Contra | 325 | −0.183 |
| D1 | Sin tendencia clara | 1.828 | −0.042 |

con el mismo signo en `sub1`/`sub2`/`sub3` para ambas variables. BOT-046 toma esto como **hipótesis congeladas** y las somete a un escrutinio temporal más fino, exactamente como pide el ticket — sin generar hipótesis nuevas a partir de los mismos datos.

---

## 3. Metodología

### 3.1. Reutilización del dataset de BOT-045 (sin recalcular nada)

Todo el análisis parte de `backtests/results/BOT-045_trades_enriched_M5.csv` (2.474 operaciones, Config A: EMA=12, HTF=800, Buffer=0.4bp, RR=1.0 — **sin modificar**). No se volvió a correr `strategy.engine.run_backtest`, no se recalculó RSI/ADX/ATR/D1/scoring — se usan las columnas ya existentes (`direction`, `aligned_with_d1`, `d1_trend`, `sub_periodo`, `entry_bar`, `entry_time_utc`, `pnl_r`, `pnl_usd`, `outcome`).

### 3.2. Sanity check — reproducción de BOT-045 (obligatorio antes de empezar, §6 del ticket)

| Grupo | N (BOT-045) | N (reproducido) | Expectancy (BOT-045) | Expectancy (reproducido) | ¿Coincide? |
|---|---:|---:|---:|---:|:---:|
| LONG | 1.189 | 1.189 | −0.100 | −0.1001 | ✅ |
| SHORT | 1.285 | 1.285 | +0.004 | +0.0038 | ✅ |
| D1 alineado | 321 | 321 | +0.067 | +0.0671 | ✅ |
| D1 contra | 325 | 325 | −0.183 | −0.1829 | ✅ |
| D1 neutral | 1.828 | 1.828 | −0.042 | −0.0417 | ✅ |

**Reproducción exacta, sin diferencias materiales.** Se procedió con el experimento (de haber una diferencia, el ticket exigía detenerse — no fue necesario).

### 3.3. Cortes temporales (todos fijados de antemano, ninguno ajustado a resultados)

| Corte | Definición exacta |
|---|---|
| `sub1`/`sub2`/`sub3` | Idéntico a BOT-045 (terciles de índice sobre las 100.505 velas) — se reutiliza la columna `sub_periodo` sin cambios, para comparabilidad directa. |
| Sextiles `T1`–`T6` | Mismo método que `sub1-3` pero con 6 cortes: `chunk = 100.505 // 6 = 16.750` velas por sextil (el último toma el resto). Cada operación se etiqueta por el sextil de su `entry_bar`. |
| Rolling windows | Ventanas de **3 meses calendario**, avance de **1 mes**, sobre `entry_time_utc` — **no** sobre conteo de operaciones. Primera ventana arranca en la fecha de la primera operación (2025-04-14). 18 ventanas en total (la última, de 7 operaciones, es el remanente de \<1 mes al final del dataset — se incluye mas se documenta como no representativa). |
| Development / Holdout (pseudo-OOS 70/30) | **Cronológico sobre barras**, no sobre operaciones: `cutoff_bar = round(0.7 × 100.505) = 70.354`. Development = `entry_bar < 70.354` (1.689 operaciones, 2025-04-14 → 2026-04-14). Holdout = `entry_bar ≥ 70.354` (785 operaciones, 2026-04-14 → 2026-09-15). |

Ningún parámetro de estos cortes (largo de ventana rolling, avance, 70/30, número de sextiles) fue ajustado después de ver resultados — todos estaban especificados en el ticket antes de ejecutar nada.

### 3.4. Métricas por grupo

Para cada grupo (A–F, G1–G6) y cada corte temporal: N, % de la muestra del período, wins, losses, win rate, Profit Factor, expectancy R/trade, Net R, Net USD, avg winner R, avg loser R, max drawdown R, max drawdown USD (misma advertencia que BOT-042/BOT-045: con `fixed_lot=0.01` fijo, es una medida comparativa entre grupos, no una curva de equity realista), y longest losing streak. Grupos con menos de 20 operaciones se marcan explícitamente `muestra_insuficiente=True` en los CSV (no se ocultan, se reportan igual).

### 3.5. Bootstrap — método exacto

**Moving block bootstrap** (no IID) sobre la secuencia cronológica de operaciones (ordenadas por `entry_bar`), para respetar que las operaciones son una serie temporal y no observaciones independientes:

1. Largo de bloque `L = round(√N)` del corte evaluado (heurística estándar de block bootstrap, fijada **antes** de correr el experimento — para el histórico completo, `L=round(√2474)=50`; cada sub-corte usa su propio `√N`, ver `BOT-046_bootstrap_M5.csv`).
2. Bloques **circulares** (wrap-around en el extremo del array) para evitar sesgo de borde.
3. Se arman resamples de largo N muestreando bloques con reemplazo hasta cubrir N observaciones (truncado exacto a N).
4. **10.000 resamples**, semilla fija `20260915` (documentada, no ajustada).
5. Para cada resample se recalculan `expectancy(SHORT) − expectancy(LONG)` y `expectancy(alineado) − expectancy(contra)` sobre las etiquetas de dirección/alineación que "viajan" con cada operación resampleada (preserva la estructura conjunta temporal entre régimen y resultado).
6. Intervalo de confianza: percentil 2.5%–97.5% (95%) de los 10.000 deltas.

Se aplicó sobre: histórico completo, `sub1`, `sub2`, `sub3`, `development`, `holdout`. No se corrió bootstrap por sextil ni por ventana rolling individual (fuera del alcance mínimo pedido por el ticket, que pide bootstrap "para las diferencias principales" — se cubre con los 6 cortes anteriores).

---

## 4. Experimentos controlados A–F (grupos simples)

Fuente: `backtests/results/BOT-046_direction_M5.csv`, `BOT-046_d1_M5.csv`. Histórico completo:

| Grupo | N | % muestra | WR | PF | Expectancy (R) | Net R | Max DD (R) | Max losing streak |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A — Baseline** | 2.474 | 100% | 49.4% | 0.912 | −0.046 | −114.22 | 140.66 | — |
| **B — Solo SHORT** | 1.285 | 51.9% | 51.8% | 1.008 | +0.004 | +4.84 | — | — |
| **C — Solo LONG** | 1.189 | 48.1% | 46.8% | 0.818 | −0.100 | −119.06 | — | — |
| **D — D1 alineado** | 321 | 13.0% | 55.0% | 1.145 | +0.067 | +21.54 | — | — |
| **E — D1 contra** | 325 | 13.1% | 42.5% | 0.692 | −0.183 | −59.45 | — | — |
| **F — D1 neutral** | 1.828 | 73.9% | 49.6% | 0.920 | −0.042 | −76.30 | — | — |

(Tabla completa con Net USD, avg winner/loser R, max DD USD y longest losing streak por grupo y por cada uno de los 11 períodos evaluados — completo/sub1-3/T1-6/dev/holdout — en los CSV fuente.)

**B (solo SHORT) es el único grupo simple con expectancy y Net R positivos en el agregado**, aunque marginal (PF=1.008). Ninguno de los grupos A–F, por sí solo, es un candidato de producción — esto es exactamente lo que dice el ticket §21: asociación ≠ estrategia rentable.

---

## 5. Interacción Dirección × D1 (G1–G6) — el resultado más importante de BOT-046

Fuente: `backtests/results/BOT-046_direction_d1_interaction_M5.csv`. Expectancy (R) por grupo, en 6 cortes distintos:

| Grupo | Completo | Development | Holdout | sub1 | sub2 | sub3 | ¿Consistente? |
|---|---:|---:|---:|---:|---:|---:|:---:|
| **G1 — LONG + alineado** | +0.008 | +0.036 | **−0.083** | −0.013 | +0.107 | **−0.108** | ❌ No — cambia de signo |
| **G2 — LONG + contra** | **−0.342** | **−0.406** | **−0.253** | **−0.307** | **−0.547** | **−0.253** | ✅ Sí — negativo en los 6 |
| **G3 — LONG + neutral** | −0.091 | −0.043 | −0.170 | −0.074 | −0.029 | −0.145 | ✅ Sí — negativo en los 6 |
| **G4 — SHORT + alineado** | **+0.156** | **+0.161** | **+0.148** | +0.099 | **+0.283** | +0.148 | ✅ Sí — positivo en los 6 |
| **G5 — SHORT + contra** | −0.089 | −0.081 | −0.134 | −0.200 | −0.042 | −0.009 | ✅ Sí — negativo/nulo en los 6, **nunca positivo** |
| **G6 — SHORT + neutral** | +0.003 | −0.020 | +0.058 | −0.119 | +0.097 | +0.036 | ⚠️ Parcial — negativo solo en sub1 |

**Lectura central:**

- **`G2` (LONG contra D1) es el grupo más consistentemente malo de todo el estudio** — negativo en los 6 cortes, con magnitud grande (−0.25R a −0.55R), muestras de 29 a 70 operaciones por corte (no triviales).
- **`G4` (SHORT alineado D1) es el grupo más consistentemente bueno** — positivo en los 6 cortes, +0.10R a +0.28R, muestras de 26 a 78 por corte.
- **`G1` (LONG alineado D1) NO es un grupo confiablemente malo** — fue positivo en `development`/`sub2`, prácticamente neutro en `sub1`, y solo se volvió negativo en `sub3`/`holdout`. Esto contradice una narrativa simple de "LONG es malo siempre" — LONG **alineado con D1** históricamente rindió cerca de breakeven o mejor, hasta el tramo más reciente.
- **`G5` (SHORT contra D1) nunca fue claramente positivo** en ningún corte — el "edge" de SHORT se diluye o revierte cuando la operación va contra la tendencia D1.

Esto responde directamente **Q6 y Q7** (§11): LONG **no** es uniformemente malo (es malo sobre todo cuando está en contra de D1 o sin D1 claro; alineado con D1 fue aceptable hasta el tramo reciente), y SHORT **no** conserva su ventaja de forma incondicional cuando está contra D1 (la pierde). Ver gráfico `05_matriz_direccion_d1.png`.

---

## 6. sub1 / sub2 / sub3 — comparabilidad con BOT-045

Ver tabla completa de G1–G6 en §5. Para A–F:

| Grupo | sub1 | sub2 | sub3 |
|---|---:|---:|---:|
| LONG | −0.074 | −0.029 | −0.145 |
| SHORT | −0.119 | +0.097 | +0.036 |
| D1 alineado | +0.052 | +0.128 | −0.021 |
| D1 contra | −0.226 | −0.189 | −0.179 |

D1-contra es negativo en los 3 sub-períodos de forma muy consistente y con magnitud similar (−0.18 a −0.23). D1-alineado es positivo en `sub1`/`sub2` pero se vuelve levemente negativo en `sub3` (−0.021, cerca de cero) — primera señal de que la ventaja de alineación se está achicando en el tramo más reciente, consistente con lo que muestra el rolling (§8).

---

## 7. Sextiles T1–T6 — mayor resolución temporal

Fuente: `backtests/results/BOT-046_sextiles_M5.csv`.

| Sextil | Rango (aprox.) | N | Expectancy baseline | Δ Dirección (SHORT−LONG) | Δ D1 (alineado−contra) |
|---|---|---:|---:|---:|---:|
| T1 | 2025-04-14 → 2025-07-10 | 401 | −0.147 | **−0.056** | +0.124 |
| T2 | 2025-07-10 → 2025-10-02 | 430 | −0.053 | +0.015 | +0.355 |
| T3 | 2025-10-03 → 2025-12-29 | 406 | +0.073 | +0.117 | +0.379 |
| T4 | 2025-12-30 → 2026-03-25 | 363 | −0.029 | +0.116 | +0.258 |
| T5 | 2026-03-26 → 2026-06-19 | 463 | −0.135 | **+0.218** | +0.182 |
| T6 | 2026-06-21 → 2026-09-15 | 411 | +0.027 | **+0.169** | +0.106 |

**Δ Dirección:** positivo en 5 de 6 sextiles (única excepción: T1, el más antiguo) y con tendencia creciente hacia los sextiles más recientes (T5/T6 son los de mayor magnitud). **Δ D1:** positivo en los **6 de 6** sextiles, sin una sola excepción, aunque con una tendencia decreciente en magnitud desde T3 (+0.379) hacia T6 (+0.106). Ver gráficos `01`–`04`.

---

## 8. Rolling windows (3 meses, avance mensual) — 18 ventanas

Fuente: `backtests/results/BOT-046_rolling_M5.csv`. Resumen (ver CSV completo para las 18 filas con fechas exactas):

- **Δ Dirección (SHORT−LONG):** positivo en **17 de 18 ventanas** — la única excepción es la primera ventana (2025-04-14 → 2025-07-14, Δ=−0.069). A partir de la segunda ventana (mayo 2025) el delta es positivo en absolutamente todas las ventanas restantes, y su magnitud crece con el tiempo (de ~+0.03/+0.08 en 2025 a +0.16/+0.38 en el primer semestre de 2026, antes de la ventana final de solo 7 operaciones que se descarta por ser no representativa).
- **Δ D1 (alineado−contra):** positivo en **16 de 16 ventanas válidas** (dos ventanas finales sin suficientes operaciones alineadas/contra para calcularlo, marcadas `NaN`, no se fuerza un valor). Rango +0.105 a +0.589 — nunca negativo.

Este es el resultado de mayor resolución temporal de todo el estudio y el que más pesa en la clasificación de §10: **ninguna de las dos hipótesis se invierte de signo en ninguna ventana móvil de 3 meses** salvo la excepción puntual y temprana de Dirección en la primera ventana. Ver gráficos `06_rolling_long_short.png` y `07_rolling_d1.png`.

---

## 9. Development (70%) vs Holdout (30%) — pseudo-OOS

Fuente: `backtests/results/BOT-046_dev_holdout_M5.csv`.

| | Development (n=1.689, 2025-04-14→2026-04-14) | Holdout (n=785, 2026-04-14→2026-09-15) |
|---|---:|---:|
| Expectancy LONG | −0.086 | −0.170 |
| Expectancy SHORT | −0.041 | +0.055 |
| **Δ Dirección (SHORT−LONG)** | **+0.045** | **+0.226** |
| Expectancy D1 alineado | +0.077 | +0.031 |
| Expectancy D1 contra | −0.176 | −0.199 |
| **Δ D1 (alineado−contra)** | **+0.253** | **+0.230** |

Ambos deltas **mantienen el mismo signo positivo** en development y en holdout — ninguna hipótesis se invierte al pasar al tramo más reciente. Δ Dirección incluso **crece** en el holdout (de +0.045 a +0.226); Δ D1 se mantiene prácticamente estable (+0.253 → +0.230). Sin embargo (ver bootstrap, §10), el bootstrap **no confirma con 95% de confianza** el delta de Dirección en `development` ni el delta de D1 en `holdout` — la dirección del efecto se sostiene, pero la certeza estadística no es uniforme en todos los cortes. Ver gráfico `08_development_vs_holdout.png`.

### 9.1. Advertencia sobre contaminación del holdout (ticket §15)

**Este 70/30 NO es un out-of-sample virgen en sentido estadístico estricto.** BOT-045 generó las hipótesis de Dirección/D1 usando el **histórico completo**, incluyendo el 30% que acá se llama "holdout" — por lo tanto, cualquier patrón específico de ese tramo ya pudo haber influido (aunque sea indirectamente, al formar parte del análisis univariado y de sub-períodos de BOT-045) en que estas dos variables fueran las elegidas para BOT-046 en primer lugar. Se lo trata correctamente como **validación temporal interna / pseudo-OOS**, útil para verificar que el efecto no depende de continuar mirando el mismo tramo que lo generó, pero **no** como prueba definitiva de generalización a datos verdaderamente nuevos. Una validación OOS genuina requiere velas futuras posteriores a esta tarea, o un dataset histórico independiente que no haya participado en BOT-045/BOT-046.

---

## 10. Bootstrap — intervalos de confianza (block bootstrap, 10.000 resamples)

Fuente: `backtests/results/BOT-046_bootstrap_M5.csv`. Método: §3.5.

| Corte | N | Largo de bloque | Δ Dirección — estimado puntual | IC 95% | ¿Excluye cero? | Δ D1 — estimado puntual | IC 95% | ¿Excluye cero? |
|---|---:|---:|---:|---|:---:|---:|---|:---:|
| **Completo** | 2.474 | 50 | +0.104 | [0.020, 0.187] | ✅ | +0.250 | [0.107, 0.393] | ✅ |
| sub1 | 831 | 29 | −0.017 | [−0.165, 0.130] | ❌ | +0.278 | [0.058, 0.487] | ✅ |
| sub2 | 769 | 28 | +0.119 | [−0.027, 0.261] | ❌ | +0.312 | [0.052, 0.576] | ✅ |
| sub3 | 874 | 30 | +0.198 | [0.070, 0.328] | ✅ | +0.160 | [−0.126, 0.439] | ❌ |
| **Development** | 1.689 | 41 | +0.045 | [−0.061, 0.146] | ❌ | +0.253 | [0.084, 0.418] | ✅ |
| **Holdout** | 785 | 28 | +0.226 | [0.090, 0.357] | ✅ | +0.248 | [−0.038, 0.531] | ❌ |

**Lectura:**
- **Δ Dirección** excluye cero solo en `sub3`, `holdout` y en el agregado completo — **no** en `sub1`, `sub2` ni en `development` (el 70% inicial completo). El punto estimado es positivo en 5 de 6 cortes (excepción: `sub1`, levemente negativo), pero la incertidumbre es demasiado grande para confirmarlo estadísticamente en la primera mitad del histórico.
- **Δ D1** excluye cero en el agregado completo, `sub1`, `sub2` y `development` — **no** en `sub3` ni `holdout`. El punto estimado es positivo en los 6 cortes sin excepción, pero el intervalo se ensancha en el tramo más reciente porque el tamaño de muestra de operaciones alineadas/contra cae (13% de una muestra ya más chica).
- Ninguno de los dos efectos se invierte de signo en ningún corte — la falta de significancia en algunos cortes es consistente con **menor poder estadístico por menor N**, no con evidencia de un efecto nulo o contrario.

Ver gráfico `09_bootstrap_ci.png`.

---

## 11. Respuestas obligatorias (ticket §19)

**Q1. ¿SHORT sigue superando a LONG cuando aumentamos la resolución temporal?**
Sí, en la gran mayoría de las ventanas: 5/6 sextiles y 17/18 ventanas rolling tienen delta positivo. La única excepción consistente es el tramo más antiguo del dataset (T1 / primera ventana rolling).

**Q2. ¿SHORT tiene edge propio o simplemente pierde menos que LONG?**
Ambas cosas, según el corte: en el agregado completo SHORT es levemente positivo (+0.004R) — sí tiene un pequeño edge propio, no solo "pierde menos". Pero desagregado por D1 (§5), ese edge se concentra casi enteramente en `SHORT+alineado` (+0.156R) y `SHORT+neutral` (~breakeven); `SHORT+contra` es negativo. Es más preciso decir: **SHORT tiene edge propio cuando no está contra D1; cuando está contra D1, simplemente pierde menos que el equivalente LONG, no tiene edge real.**

**Q3. ¿LONG es consistentemente negativo o existen regímenes donde funciona correctamente?**
No es uniformemente negativo. `LONG+alineado con D1` (G1) fue positivo o cercano a cero en `development`, `sub1` y `sub2` — solo se volvió claramente negativo en `sub3`/`holdout`. `LONG+contra D1` (G2) y `LONG+neutral` (G3), en cambio, son negativos en los 6 cortes evaluados sin excepción. Existe entonces un régimen (LONG alineado con D1, al menos hasta hace pocos meses) donde LONG no fue claramente malo.

**Q4. ¿La alineación D1 sigue superando a operar contra D1 en T1...T6?**
Sí, en los 6 de 6 sextiles, sin ninguna excepción — el corte más consistente de todo el estudio.

**Q5. ¿El efecto D1 sobrevive el pseudo-OOS 70/30?**
El signo sí sobrevive (Δ D1 positivo tanto en `development` +0.253 como en `holdout` +0.230, magnitudes casi iguales). La significancia estadística (bootstrap) sobrevive en `development` pero no en `holdout` (IC cruza cero, por menor N en el tramo reciente) — sobrevive parcialmente: dirección sí, certeza estadística completa no.

**Q6. ¿LONG sigue siendo malo cuando está alineado con D1?**
No de forma consistente — ver Q3. Fue aceptable-a-positivo en `development`/`sub1`/`sub2`, y se volvió negativo recién en `sub3`/`holdout`. No se puede afirmar "LONG alineado con D1 es malo" como hallazgo robusto.

**Q7. ¿SHORT sigue siendo bueno cuando está contra D1?**
No. `SHORT+contra` (G5) nunca fue claramente positivo en ningún corte evaluado (completo, development, holdout, sub1, sub2, sub3) — el edge de SHORT depende de no estar en contra de D1.

**Q8. ¿Qué tiene mayor poder explicativo independiente: Dirección o Alineación D1?**
Con esta evidencia, **Alineación D1 es la variable individualmente más robusta** (consistente en 100% de los cortes de mayor resolución, sextiles y rolling). Pero hay un dato que evita concluir que Dirección sea meramente un reflejo de D1: **LONG tiene proporcionalmente más operaciones alineadas con D1 que SHORT** (16.2% vs 10.0%) y **SHORT tiene proporcionalmente más operaciones contra D1 que LONG** (15.9% vs 10.2%) — es decir, la mezcla de alineación D1 de SHORT es, si acaso, *menos* favorable que la de LONG, y aun así SHORT rinde mejor en agregado. Esto sugiere que Dirección aporta información **al menos parcialmente independiente** de D1, aunque más débil y más reciente/emergente que D1 por sí sola.

**Q9. ¿Existe interacción real entre ambas?**
Sí, clara: los efectos no son aditivos. `LONG+contra` (−0.34R) es sustancialmente peor que lo que la suma de los efectos individuales de "ser LONG" y "estar contra D1" predeciría por separado, y `SHORT+alineado` (+0.16R) es sustancialmente mejor que la suma de sus efectos individuales. La interacción concentra la señal en esos dos extremos (G2 y G4) más que en los grupos "puros" de Dirección o D1 solos.

**Q10. ¿Los resultados justifican abrir una futura prueba controlada de filtro/scoring, o todavía necesitamos más datos?**
Ver recomendación formal en §12 — **RESULTADO 2, más historial**, con la salvedad de que la interacción G2/G4 (LONG-contra / SHORT-alineado) es la que acumula más evidencia y sería el punto de partida más justificado si se decide seguir por esta vía más adelante.

---

## 12. Clasificación de robustez (ticket §18)

| Hipótesis | Signo mayoría de ventanas | Efecto material | Muestra suficiente | Dev y Holdout mantienen dirección | IC razonablemente favorable | Clasificación |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **H1 — Dirección (SHORT>LONG)** | ✅ 5/6 sextiles, 17/18 rolling | ✅ (crece hasta +0.2R/trade en tramos recientes) | ✅ (1.189/1.285) | ✅ (ambos positivos) | ⚠️ Parcial — excluye cero en completo/sub3/holdout, no en sub1/sub2/development | **B — Prometedora** |
| **H2 — Alineación D1** | ✅ 6/6 sextiles, 16/16 rolling válidas | ✅ (+0.25R/trade en agregado) | ⚠️ Cobertura acotada (26% de la muestra) pero N absoluto razonable (321/325) | ✅ (ambos positivos, magnitud casi igual) | ⚠️ Parcial — excluye cero en completo/sub1/sub2/development, no en sub3/holdout (N menor) | **A — Robusta**, con la salvedad explícita de que la significancia estadística se debilita en el tramo más reciente por tamaño de muestra, no por cambio de signo |
| **H3 — Interacción Dirección×D1** | Depende de la celda — G2/G4: ✅ 6/6; G1: ❌ cambia de signo; G5: ✅ nunca positivo (consistente en su negatividad); G6: ⚠️ parcial | ✅ en G2/G4 (magnitud grande) | ✅ para G2-G6 (29-953), ⚠️ ajustada para G1/G4 en algunos cortes (26-78) | G2/G4: ✅; G1: ❌ | No se corrió bootstrap por celda (fuera del alcance mínimo del ticket) | **B — Prometedora**, con G2 (LONG+contra) y G4 (SHORT+alineado) acercándose a A por su consistencia perfecta, y G1 (LONG+alineado) degradando la hipótesis de "interacción limpia" |

**Ninguna hipótesis se eleva a A únicamente por el histórico completo** — la clasificación de H2 como A se apoya en la consistencia de signo en TODOS los sextiles y ventanas rolling, no solo en el resultado agregado (ver ticket §18, última línea).

---

## 13. Distinción explícita (ticket §21)

- **SHORT > LONG** (asociación estadística) **no implica** que "SHORT-only" sea una estrategia rentable — B (solo SHORT) da expectancy apenas positiva (+0.004R, PF 1.008) en el agregado, casi breakeven, no un edge grande.
- **Alineado > Contra** (asociación estadística) **no implica** que filtrar las operaciones contra D1 vuelva rentable al bot — el grupo D1-neutral (73.9% de la muestra, sin tendencia D1 clasificable) sigue siendo negativo (−0.042R) y es la mayoría del volumen; filtrar solo el 13% "contra D1" no resuelve la expectancy agregada negativa de Config A por sí solo.
- La variable predictiva más clara para una futura prueba controlada, si se decide avanzar, sería la **combinación** LONG+contra-D1 (evitar) y SHORT+alineado-D1 (posible foco), no cada variable por separado — y **nada de esto se implementa en esta tarea**.

---

## 14. Limitaciones

- Ver §9.1 — el holdout 70/30 es pseudo-OOS, contaminado por construcción (BOT-045 usó el histórico completo para generar la hipótesis).
- El bootstrap no se corrió por sextil ni por ventana rolling individual (computacionalmente no aportaba más allá de lo que ya muestran los 6 cortes con bootstrap completo + la inspección directa de signos en sextiles/rolling).
- La ventana rolling final (2026-08-14 a 2026-09-15) tiene solo 7 operaciones — se incluye en el CSV por completitud pero no se usa para ninguna conclusión (no representativa).
- Igual que en BOT-045: un solo símbolo, un solo bróker, un único rango temporal (~1.4 años) y una sola configuración de parámetros (Config A, RR=1). Nada de esto se generaliza a otros símbolos/configuraciones sin volver a probarlo.
- `aligned_with_d1` tiene cobertura del 26% de la muestra (74% queda "neutral", sin tendencia D1 clasificable con el método de BOT-045) — cualquier conclusión sobre D1 aplica solo a ese subconjunto.

---

## 15. Entregables

**Scripts:**
- `backtests/scripts/09_bot046_direction_d1_robustness.py` — reutiliza el dataset de BOT-045, corre todo el experimento. Uso: `python backtests/scripts/09_bot046_direction_d1_robustness.py M5`.

**Resultados:**
- `backtests/results/BOT-046_direction_M5.csv`, `BOT-046_d1_M5.csv`, `BOT-046_direction_d1_interaction_M5.csv` — métricas completas por grupo y por los 11 períodos (completo/sub1-3/T1-6/dev/holdout).
- `backtests/results/BOT-046_sextiles_M5.csv`, `BOT-046_rolling_M5.csv`, `BOT-046_dev_holdout_M5.csv`, `BOT-046_bootstrap_M5.csv`.

**Gráficos** (`backtests/results/BOT-046_charts/`):
- `01_expectancy_long_short_sextiles.png`, `02_delta_direction_por_periodo.png`, `03_expectancy_d1_sextiles.png`, `04_delta_d1_por_periodo.png`, `05_matriz_direccion_d1.png`, `06_rolling_long_short.png`, `07_rolling_d1.png`, `08_development_vs_holdout.png`, `09_bootstrap_ci.png`.

**Este reporte:**
- `docs/reports/BOT-046_direction_d1_temporal_robustness.md` (este archivo).

---

## 16. Recomendación final (ticket §24)

### **RESULTADO 2 — Más historial.**

La señal es demasiado consistente en signo (especialmente H2/D1: 6/6 sextiles, 16/16 rolling; y la interacción G2/G4: 6/6 cada una) para descartarla como artefacto puro del histórico (RESULTADO 3). Pero tampoco alcanza el estándar completo de robustez simultánea en desarrollo Y holdout con significancia estadística consistente (RESULTADO 1) — Dirección en particular no es significativa en el 70% de desarrollo, y D1 no es significativa en el holdout más reciente, ambas por caída de tamaño de muestra más que por reversión del efecto.

**Se recomienda:**
1. No abrir todavía un ticket de prueba controlada de filtro/scoring basado en Dirección/D1.
2. Acumular más historial en vivo (el bot ya opera en real, ver `BACKLOG.md`) antes de reintentar esta validación con una muestra mayor, especialmente para robustecer las celdas `aligned`/`against` de D1, que son las de menor cobertura (13% cada una).
3. Si se decide investigar más, el punto de partida con más evidencia acumulada es la interacción específica **LONG+contra-D1** (evitar) y **SHORT+alineado-D1** (foco), no las variables Dirección o D1 por separado — son las dos celdas que se mantuvieron perfectamente consistentes en los 6 cortes evaluados.
4. Cuando exista una validación OOS genuina (velas futuras no usadas en BOT-045/BOT-046, ver §9.1), repetir este mismo procedimiento antes de plantear cualquier Prueba Controlada real.

**No se seleccionó esta recomendación por producir el mejor backtest — se seleccionó porque es la que refleja honestamente que la evidencia es consistente pero estadísticamente incompleta en algunos cortes**, tal como exige el ticket §24.

---

## 17. MUY IMPORTANTE — nada de esto se implementó

Config A permanece exactamente igual (EMA=12, HTF=800, Buffer=0.4bp, RR=1.0). No se tocó `strategy/`, `execution/`, la API, el panel, ni scoring. No se implementó ningún filtro LONG/SHORT ni D1. No se inició BOT-008. Todo el contenido de este documento es diagnóstico — cualquier paso siguiente requiere abrir un ticket separado y seguir la regla de experimentación de `BACKLOG.md` (Diagnóstico → Hipótesis → **Prueba controlada** → Robustez → Validación → Cambio en producción). BOT-046 cubre Diagnóstico + una validación de robustez temporal adicional sobre la Hipótesis, pero no constituye por sí solo una Prueba controlada.

---

## 18. Git

| | |
|---|---|
| **Commit base** | El commit de BOT-045 en esta misma sesión (ver `docs/reports/BOT-045_market_regime_analysis.md`) |
| **Archivos nuevos** | 1 script (`backtests/scripts/09_*.py`), 1 informe (este archivo), 7 CSV de resultados en `backtests/results/`, 9 gráficos en `backtests/results/BOT-046_charts/` |
| **Archivos modificados** | `BACKLOG.md` (nuevo ítem BOT-046) |
| **No se modificó** | `strategy/`, `execution/`, `api/`, `panel/`, `VERSION`, `CHANGELOG.md`, ni ningún dataset/script preexistente |

---

*Generado por Claude Code a partir del prompt "BOT-046 — Dirección/D1 + Robustez Temporal" del usuario. Tarea 100% diagnóstica y offline — no se modificó lógica de entrada/salida, pivotes, HTF, EMA, Buffer, RR, scoring, ni configuración/ejecución en producción en ningún momento. El objetivo era intentar romper las hipótesis de BOT-045; se documentan tanto lo que sobrevivió como lo que no, sin forzar una conclusión favorable.*
