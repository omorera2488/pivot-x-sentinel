# BOT-045 — Análisis de régimen de mercado y calidad de entradas

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Tipo de tarea:** Investigación **diagnóstica, 100% offline**. No modifica `/strategy`, `/execution`, la API, el panel, ni ningún parámetro de producción. No agrega filtros. No optimiza. No selecciona una nueva configuración.

Este documento es **autocontenido**: no depende de la conversación de Claude Code ni de nada que solo haya quedado escrito en una terminal. Contiene metodología, dataset, resultados completos, limitaciones y conclusiones necesarios para que otra persona — o ChatGPT recibiendo únicamente este archivo — entienda qué se hizo y pueda continuar el análisis.

---

## 1. Resumen ejecutivo

Se construyó un dataset enriquecido de **2.474 operaciones** (Config A: EMA=12, HTF=800min, Buffer=0.4bp, RR=1.0 — la configuración congelada usada como "la real del bot" desde BOT-042/BOT-043) con 14 categorías de variables de régimen calculadas de forma estrictamente causal (sin look-ahead), y se comparó su relación con el resultado de cada operación, global y por sub-período (`sub1`/`sub2`/`sub3`, los mismos tres tercios de índice que usa BOT-042).

**Hallazgos principales (evidencia real, ninguno forzado):**

1. **La dirección de la operación importa, y de forma consistente:** SHORT tiene expectancy ligeramente positiva (+0.004 R/trade) y LONG claramente negativa (−0.100 R/trade), con el mismo signo en los 3 sub-períodos y en la proporción winners/losers. **Evidencia A.**
2. **La alineación con la tendencia D1 (cuando existe una tendencia D1 clara) es el predictor individual más fuerte encontrado:** operaciones alineadas con la tendencia D1 dan expectancy +0.067 R/trade (WR 55.0%, PF 1.145); operaciones en contra dan −0.183 R/trade (WR 42.5%, PF 0.692) — mismo signo en los 3 sub-períodos. **Evidencia A**, con la salvedad de que solo aplica al 26% de las operaciones (74% no tiene tendencia D1 clara con este método, ver limitación §6).
3. **ADX más bajo se asocia sistemáticamente con mejor resultado** (relación inversa, no la esperable para una estrategia de seguimiento de ruptura): el ADX promedio de los winners es menor que el de los losers, con el mismo signo en los 3 sub-períodos, aunque de magnitud modesta. **Evidencia B.**
4. **`sub2` (2025-10-02→2026-03-25) se caracteriza principalmente por volatilidad relativa (ATR%) sustancialmente más alta** que `sub1` (mediana 0.127% vs 0.082%) y, en menor medida, por una mayor proporción de operaciones SHORT (55.9% vs 53.3% en sub1 y 47.1% en sub3) y un contexto D1 más alcista con menos tramos bajistas. **Ninguna variable por sí sola explica `sub2` de forma completa** — `sub3` también tiene volatilidad elevada (mediana 0.123%) y aun así expectancy negativa, así que la volatilidad es necesaria pero no suficiente.
5. Los 4 factores de scoring de BOT-023 tienen desempeño desigual: **Tendencia (multi-ventana) y CVP no muestran evidencia útil** con esta configuración (CVP no varía en absoluto a RR=1 — ver §7.4); **Divergencia** muestra una señal débil (el caso "en contra" es peor, pero "a favor" no mejora nada); **Nodo** muestra el signo contrario al que su diseño anticipaba.
6. Ninguna variable, sola o combinada, produce una segmentación con edge robusto y suficiente volumen como para proponerse ya como filtro — la combinación más prometedora encontrada (ADX≥25 + alineado con D1) da expectancy apenas positiva (+0.018 R/trade, PF 1.037, n=173) y **no se recomienda implementar** (ver §16 del ticket original — este documento es diagnóstico, no un candidato de producción).

**Criterio de éxito de BOT-045 (según el ticket):** cumplido — se puede responder con evidencia qué condiciones se asocian históricamente con mejor/peor resultado y qué caracterizó a `sub2`, y se documentan explícitamente las variables sin evidencia útil en vez de forzar un hallazgo.

---

## 2. Contexto

- **BOT-042** (re-ejecutado post-BOT-043, motor de costos corregido) encontró que variar únicamente RR no arregla Config A de forma robusta: RR=1 a RR=5 dan expectancy negativa; RR=7 es el único positivo en agregado pero no se sostiene en los 3 sub-períodos, y depende de que `sub2` favorece a **todas** las configuraciones probadas (no solo RR=7). Ver `docs/reports/BOT-042_rerun_RR_post_BOT-043.md`.
- **BOT-043** corrigió dos bugs del motor de costos (signo de swap, escala precio→USD). Es el motor vigente, sin cambios en esta tarea.
- La auditoría reciente `docs/reports/AUDIT-HTF_AB_comparison_2026-09-15.md` confirmó que el auto-armado del bloque HTF (comportamiento intencional de la estrategia desde BOT-005) no es la causa del deterioro — no se revisita esa pregunta acá.
- Este documento cubre únicamente la etapa **Diagnóstico/Hipótesis** de la regla permanente de experimentación de `BACKLOG.md` (Diagnóstico → Hipótesis → Prueba controlada → Robustez → Validación → Cambio en producción). No autoriza pasar a las etapas siguientes.

---

## 3. Metodología

### 3.1. Config A (baseline congelado)

| Parámetro | Valor |
|---|---|
| `ema_periods` | 12 |
| `periodos_htf_min` (HTF) | 800 |
| `buf_bp` (Buffer) | 0.4 |
| `rr` | 1.0 |
| `max_concurrent_por_direccion` | 1 |
| `valid_bars` | 10 |
| `orden_viva` | True |
| `max_bars_trade` | 500 |
| `fixed_lot` | 0.01 |
| `entrada_viva` | False |
| `una_operacion_a_la_vez` | True |

Misma configuración que "Config A" en BOT-042/BOT-043 (tratada ahí como "la configuración real del bot"). **No se modificó ningún parámetro** durante esta tarea — es exactamente el baseline congelado que pide el ticket.

### 3.2. Dataset y motor

- `backtests/data/XAUUSDc_M5_latest.parquet` — 100.505 velas M5, XAUUSDc, 2025-04-14 18:50 UTC → 2026-09-15 00:40 UTC (mismo dataset que BOT-008/BOT-042/BOT-043).
- Motor: `strategy.engine.run_backtest`, **sin modificar**, costos reales vía `symbol_info` de MT5 en el momento de la corrida (mismo mecanismo que `03_run_sweep.py`/`04_run_robustness.py`/`05_run_rr_isolation.py`):

  | | |
  |---|---|
  | `point` | 0.001 |
  | `tick_value` | 0.1 |
  | `tick_size` | 0.001 |
  | `swap_long_points` | −533.9 |
  | `swap_short_points` | 0.0 |
  | `commission_per_lot` | 0.0 (supuesto de cuenta Standard, sin confirmar — mismo supuesto que BOT-008/BOT-042/BOT-043) |

- **Diferencia metodológica deliberada frente a `04_run_robustness.py`/`05_run_rr_isolation.py`:** esos scripts cortan el dataset en 3 sub-períodos y corren el motor **por separado** en cada uno (sin continuidad de EMA/HTF entre sub-períodos). Para el dataset **por operación** de BOT-045 se corrió el motor **una sola vez, de forma continua**, sobre las 100.505 velas completas — más representativo de cómo el bot corre en la práctica (nunca se reinicia en medio de una serie histórica real) — y luego cada operación se etiquetó `sub1`/`sub2`/`sub3` según en qué tercio de índice cae su barra de entrada (los mismos 3 cortes de índice: ~33.501/33.501/33.503 velas). Por eso el conteo de operaciones por sub-período de este dataset difiere en unas pocas unidades del de `robustness_subperiods_M5.csv`/`rr_subperiods_post_BOT-043_M5.csv` (ver §4 — la diferencia es de 0-2 operaciones por sub-período, no material).
- Script: `backtests/scripts/07_bot045_regime_dataset.py`. Reproducible con:
  ```
  python backtests/scripts/07_bot045_regime_dataset.py M5
  ```

### 3.3. `sub1`/`sub2`/`sub3` — definición exacta

Terciles de índice sobre las 100.505 velas (`chunk = n // 3`):

| Sub-período | Rango de fechas (aprox.) | Velas |
|---|---|---|
| `sub1` | 2025-04-14 → 2025-10-02 | ~33.501 |
| `sub2` | 2025-10-02 → 2026-03-25 | ~33.501 |
| `sub3` | 2026-03-25 → 2026-09-15 | ~33.503 |

Una operación se etiqueta por el sub-período que contiene su **barra de entrada** (`entry_bar`), no la barra de señal ni la de salida.

### 3.4. Variables calculadas — cómo, y evitando look-ahead

Todas las variables se calculan con información disponible **hasta la barra de entrada de la operación, inclusive** — ninguna usa barras posteriores. Método:

| # | Variable (ticket) | Cómo se calculó | Fuente |
|---|---|---|---|
| 1 | D1 / contexto HTF | Clasificación HH/HL de los últimos 3 bloques de sesión de 1440min (**misma ancla de sesión 22:00 UTC** que ya usa el HTF de producción, `strategy/htf_session.py`) **ya cerrados antes de la entrada** — alcista/bajista/sin secuencia clara/historial insuficiente. Reutiliza el mismo algoritmo que `strategy.scoring._classify_sequence`, precomputado una vez por performance (ver §3.5). | Nuevo (script BOT-045) |
| 2 | RSI | `strategy.scoring.rsi()` (Wilder, período 14), sin modificar | Reuso directo |
| 3 | ADX | Wilder ADX(14) estándar (+DM/−DM, TR suavizado, DI+/DI−, DX, ADX) — **no existía en el repo**, se implementó en el script de BOT-045 (no en `/strategy`) | Nuevo (script BOT-045) |
| 4 | ATR / volatilidad | ATR(14) de Wilder — nuevo (mismo script). Se usa además `atr_pct_entry = ATR/close*100` como medida **relativa**, comparable entre períodos de distinto nivel de precio del oro | Nuevo (script BOT-045) |
| 5 | Sesión | Partición fija por hora UTC (ver tabla abajo) — **sin ajuste de horario de verano** (limitación documentada en §6) | Nuevo (script BOT-045) |
| 6 | Hora | Hora UTC de la barra de entrada | Directo del dataset |
| 7 | Día de semana | Día UTC de la barra de entrada | Directo del dataset |
| 8 | LONG vs SHORT | `Trade.direction` del motor (+1/−1) | Motor (`strategy/engine.py`) |
| 9 | Distancia a EMA | `close − ema_line` en la barra de entrada; normalizada como `abs(dist)/ATR` | EMA del motor + ATR nuevo |
| 10 | Características del bloque HTF | Ancho del bloque (`resistencia − soporte`) normalizado por ATR; posición del precio dentro del bloque (`(close−soporte)/ancho`, 0=soporte, 1=resistencia); antigüedad en barras desde el inicio del bloque | `resistencia`/`soporte` del motor (mismo HTF=800 que Config A) |
| 11 | Divergencia | `strategy.scoring.divergence_score()` (RSI 14 + pivotes tipo `ta.pivothigh/low`, ±1), reimplementado sobre pivotes precomputados por performance pero **algoritmo idéntico** | Reuso directo (algoritmo) |
| 12 | Tendencia (factor de scoring BOT-023) | `strategy.scoring.trend_score()`, ventanas 30min/240min (perfil "5m"), mismo algoritmo | Reuso directo (algoritmo) |
| 13 | CVP | `strategy.scoring.cvp_score()`, mismo algoritmo — **aproximado**, ver limitación §6 | Reuso directo (algoritmo) + aproximación |
| 14 | Nodo | `strategy.scoring.node_score()` (perfil de volumen de rango fijo del bloque HTF actual), mismo algoritmo, usando `tick_volume` como proxy de volumen (`real_volume`=0 en este símbolo) | Reuso directo (algoritmo) |

**Sesiones UTC usadas (partición fija, sin solapamiento, documentada explícitamente):**

| Sesión | Horario UTC |
|---|---|
| Asia | 00:00–07:00 |
| Asia/Londres (overlap) | 07:00–08:00 |
| Londres | 08:00–12:00 |
| Londres/NY (overlap) | 12:00–16:00 |
| Nueva York | 16:00–21:00 |
| Post-NY / transición | 21:00–24:00 |

### 3.5. Nota de performance (no afecta los resultados)

Para no recorrer el historial completo por cada una de las ~2.474 operaciones, las funciones de `strategy/scoring.py` que internamente recalculan sobre el array completo (`trend_score`/`_closed_blocks`, `find_confirmed_pivots`) se **reimplementaron con el mismo algoritmo exacto** pero precomputando los bloques/pivotes **una sola vez** sobre todo el dataset y consultándolos por operación con búsqueda binaria (los bloques/pivotes son deterministas y no dependen de cuántas barras adicionales tenga el array, solo de la barra de referencia — precomputar una vez y filtrar por "cerrado antes de la barra de entrada" es matemáticamente equivalente a recortar el array antes de cada llamada). El score CVP y Nodo sí usan las funciones originales de `strategy/scoring.py` sin modificar (`sc.cvp_score`, y la lógica interna de `_volume_profile`/`_value_area` sobre la ventana causal del bloque actual).

### 3.6. Limitación conocida y aceptada

`strategy/scoring.py::cvp_score()` convierte comisión a precio usando `contract_size` en vez de `tick_value/tick_size` (BOT-044, encontrado en BOT-043, **no corregido, sin impacto real hoy** porque `commission_usd=0.0`). Como este análisis también usa `commission_usd=0.0` (mismo supuesto que el resto de los scripts de backtest), **no afecta ningún resultado de este informe** — se documenta por transparencia, no se corrigió (fuera de alcance, ver BOT-044).

---

## 4. Baseline (referencia obligatoria antes de segmentar)

Fuente: `backtests/results/BOT-045_baseline_M5.csv`.

| Período | N trades | Wins | Losses | Win rate | Profit Factor | Expectancy (R) | Net R | Net USD | Avg Winner (R) | Avg Loser (R) | Max DD (R) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Completo** | 2.474 | 1.220 | 1.251 | 49.37% | 0.912 | −0.046 | −114.22 | −$1.375,66 | 0.966 | −1.034 | 140.66 |
| sub1 | 831 | 392 | 439 | 47.17% | 0.821 | −0.098 | −81.69 | −$561,96 | 0.957 | −1.040 | 84.86 |
| sub2 | 769 | 402 | 365 | 52.41% | 1.051 | +0.025 | +19.15 | −$25,65 | 0.977 | −1.025 | 25.21 |
| sub3 | 874 | 426 | 447 | 48.80% | 0.888 | −0.059 | −51.68 | −$788,05 | 0.965 | −1.034 | 81.14 |

Coincide (dentro de 0-2 operaciones por sub-período, ver §3.2) con `robustness_subperiods_M5.csv`/`rr_subperiods_post_BOT-043_M5.csv` de BOT-042: `sub2` es el único sub-período con expectancy y Net R positivos, `sub1` y `sub3` son negativos. Confirma que el problema de fondo (expectancy agregada negativa) persiste y que `sub2` sigue siendo el tramo anómalamente favorable.

---

## 5. Resultados por variable (univariado)

Fuente completa: `backtests/results/BOT-045_univariate_M5.csv` (87 filas, todas las variables y buckets). Gráficos en `backtests/results/BOT-045_charts/`. Resumen de lo más relevante:

### 5.1. RSI en la entrada

| Bucket | N | % muestra | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|---:|
| <30 | 3 | 0.1% | 0% | 0.000 | −1.035 |
| 30–40 | 163 | 6.6% | 34.4% | 0.492 | −0.343 |
| 40–50 | 1.035 | 41.8% | 50.8% | 0.961 | −0.020 |
| 50–60 | 1.036 | 41.9% | 55.3% | 1.157 | **+0.073** |
| 60–70 | 235 | 9.5% | 28.5% | 0.376 | −0.459 |
| >70 | 2 | 0.1% | 0% | 0.000 | −1.026 |

El 83.7% de las operaciones cae en 40–60, con expectancy cercana a break-even (ligeramente positiva en 50–60). Los buckets extremos (30–40, 60–70) muestran expectancy muy negativa, pero con muestra chica (6.6%/9.5%) — ver robustez en §9 (el efecto winners-vs-losers de RSI **cambia de signo entre sub-períodos**, así que esto no se toma como señal confiable, solo se documenta).

### 5.2. ADX en la entrada

| Bucket | N | % muestra | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|---:|
| <20 (débil/no-tendencial) | 683 | 27.6% | 51.1% | 0.959 | −0.021 |
| 20–25 (transición) | 468 | 18.9% | 51.7% | 1.006 | **+0.003** |
| 25–40 (tendencia) | 938 | 37.9% | 48.1% | 0.872 | −0.068 |
| >40 (tendencia fuerte) | 384 | 15.5% | 46.4% | 0.818 | −0.100 |

Relación **inversa**: a más ADX (más "tendencial" el mercado por esta medida), peor resultado. Contraintuitivo para una estrategia basada en ruptura de bloque HTF + cruce de EMA, pero consistente: ver §9, el ADX promedio de winners es menor que el de losers **en los 3 sub-períodos por separado**.

### 5.3. ATR% (volatilidad relativa)

| Bucket (cuartiles del dataset) | N | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|
| Q1 muy baja [0.023–0.080%] | 619 | 49.3% | 0.867 | −0.071 |
| Q2 baja [0.080–0.109%] | 618 | 49.0% | 0.897 | −0.054 |
| Q3 alta [0.109–0.147%] | 618 | 49.4% | 0.925 | −0.039 |
| Q4 muy alta [0.147–1.028%] | 619 | 49.8% | 0.960 | **−0.020** |

Gradiente monótono: a mayor volatilidad relativa, expectancy menos negativa (aunque nunca positiva en agregado). El win rate es prácticamente idéntico entre cuartiles (49.0%–49.8%) — la mejora viene del lado de PF/expectancy, no de mayor probabilidad de acierto (ver §9: el ATR de winners y losers es casi idéntico dentro de cada operación — el efecto es de **régimen/costos**, no de selección de trade individual: con mayor ATR, el costo de spread pesa proporcionalmente menos sobre el riesgo de 1R).

### 5.4. Distancia a EMA (normalizada por ATR)

| Bucket (cuartiles) | N | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|
| Q1 muy cerca [0.000–0.133] | 619 | 47.6% | 0.852 | −0.080 |
| Q2 cerca [0.133–0.288] | 618 | 49.7% | 0.917 | −0.043 |
| Q3 lejos [0.288–0.528] | 618 | 50.6% | 0.959 | **−0.021** |
| Q4 muy lejos [0.528–2.843] | 619 | 49.5% | 0.922 | −0.041 |

Sin patrón monótono claro (Q3 mejor, Q4 peor que Q3) y sin diferencia entre winners/losers (§9) — **sin evidencia útil**.

### 5.5. Características del bloque HTF

| Variable | Mejor bucket | Peor bucket | Lectura |
|---|---|---|---|
| Ancho del bloque / ATR | Angosto [0.8–4.0]: −0.009 | Muy ancho [9.8–29.5]: −0.075 | Gradiente monótono, bloques angostos (relativo a volatilidad) mejor — pero se invierte en `sub2` al mirar winners/losers (§9), no totalmente consistente |
| Posición dentro del bloque | Medio (0.33–0.67): **+0.035** | Cerca soporte (<0.33): −0.112 | Único bucket de esta variable con expectancy positiva; cerca de los extremos del bloque (recién armado) es lo peor |
| Antigüedad en el bloque (barras) | Medio-temprano [18–39]: −0.009 | Medio-tardío [39–74]: −0.094 | Sin gradiente monótono claro |

### 5.6. Sesión

| Sesión | N | % muestra | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|---:|
| Asia | 742 | 30.0% | 47.3% | 0.847 | −0.083 |
| Asia/Londres overlap | 77 | 3.1% | 48.1% | 0.874 | −0.067 |
| **Londres** | 335 | 13.5% | 53.1% | 1.046 | **+0.022** |
| Londres/NY overlap | 743 | 30.0% | 49.7% | 0.940 | −0.031 |
| Nueva York | 287 | 11.6% | 47.2% | 0.838 | −0.088 |
| Post-NY/transición | 290 | 11.7% | 52.1% | 0.953 | −0.024 |

Único sesión con expectancy positiva: **Londres** (13.5% de la muestra). Asia es la peor sesión de forma **consistente en los 3 sub-períodos** (ver §9): −0.123 (sub1), −0.038 (sub2), −0.084 (sub3), siempre negativa.

### 5.7. Hora UTC

Ver gráfico `06_expectancy_por_hora.png` y `BOT-045_univariate_M5.csv` (24 filas). Muestras por hora son chicas (39–238 operaciones) y el patrón es ruidoso — mejor hora 08h UTC (+0.145, n=63), peor 04h UTC (−0.413, n=61). Con esta muestra no se puede aislar con confianza señal por hora individual, más allá de que 08h-15h UTC (aprox. Londres) tiende a concentrar los valores menos negativos, consistente con §5.6.

### 5.8. Día de semana

| Día | N | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|
| Lunes | 484 | 53.3% | 1.067 | +0.032 |
| Jueves | 491 | 52.0% | 1.018 | +0.009 |
| Miércoles | 512 | 48.6% | 0.885 | −0.061 |
| Martes | 533 | 48.2% | 0.864 | −0.073 |
| **Viernes** | 409 | 44.0% | 0.739 | **−0.151** |
| Domingo | 45 | 48.9% | 0.889 | −0.059 |

Viernes es sistemáticamente el peor día (negativo en `sub1` y `sub3`, apenas positivo +0.029 en `sub2`). Miércoles negativo en los 3 sub-períodos.

### 5.9. LONG vs SHORT

| Dirección | N | % muestra | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|---:|
| LONG | 1.189 | 48.1% | 46.8% | 0.818 | **−0.100** |
| SHORT | 1.285 | 51.9% | 51.8% | 1.008 | **+0.004** |

Ver robustez completa en §9 — es de las variables **más consistentes** de todo el análisis.

### 5.10. Contexto D1 y alineación

| `d1_trend` | N | % muestra | WR | Expectancy (R) |
|---|---:|---:|---:|---:|
| Alcista | 397 | 16.0% | 49.5% | −0.042 |
| Bajista | 249 | 10.1% | 47.4% | −0.086 |
| Sin secuencia clara | 1.810 | 73.2% | 49.8% | −0.039 |
| Historial insuficiente | 18 | 0.7% | 33.3% | −0.367 |

| `aligned_with_d1` | N | % muestra | WR | PF | Expectancy (R) |
|---|---:|---:|---:|---:|---:|
| Alineado (True) | 321 | 13.0% | **55.0%** | **1.145** | **+0.067** |
| En contra (False) | 325 | 13.1% | **42.5%** | **0.692** | **−0.183** |
| Sin tendencia D1 clara | 1.828 | 73.9% | 49.6% | 0.920 | −0.042 |

El hallazgo más fuerte de todo el análisis univariado (ver robustez en §9).

### 5.11. Factores de scoring existentes (BOT-023)

| Factor | Bucket | N | % muestra | WR | Expectancy (R) | Lectura |
|---|---|---:|---:|---:|---:|---|
| Divergencia | −1 (en contra) | 90 | 3.6% | 41.1% | −0.219 | Peor que "sin divergencia" |
| Divergencia | 0 (sin divergencia) | 1.973 | 79.7% | 49.8% | −0.037 | Mayoría de la muestra |
| Divergencia | +1 (a favor) | 411 | 16.6% | 49.1% | −0.052 | **No mejora** respecto a "sin divergencia" — solo el caso "en contra" separa |
| Tendencia (scoring) | −1 | 226 | 9.1% | 48.2% | −0.066 | |
| Tendencia (scoring) | 0 | 2.242 | 90.6% | 49.4% | −0.045 | 90.6% de la muestra cae acá — factor casi sin variabilidad práctica |
| Tendencia (scoring) | +1 | 6 | 0.2% | 66.7% | +0.309 | Muestra insuficiente, no se interpreta |
| CVP | 0 | 2.474 | 100% | 49.4% | −0.046 | **Sin variación en absoluto** — ver §7.4 |
| Nodo | −1 (nodo en el camino) | 2.194 | 88.7% | 49.7% | **−0.040** | |
| Nodo | 0 (sin nodo) | 280 | 11.3% | 47.1% | **−0.096** | Contrario a lo que el diseño del factor anticipa (ver §7.4) |

---

## 6. Limitaciones documentadas (variables que no se pudieron calcular con plena fidelidad)

Siguiendo el punto 3 del ticket ("si alguna variable no puede calcularse con los datos disponibles, documentarlo claramente. No inventar información"):

1. **CVP (aciertos_pct):** en producción, `cvp_score()` usa el % de aciertos **real** medido de las operaciones ya cerradas por el bot en la **cuenta en vivo** (`execution/src/bot.py`) — ese historial de cuenta viva no existe para el rango offline analizado (2025-04 a 2026-09, mayormente anterior a que el bot operara en real). Se aproximó con un **win-rate causal acumulado del propio backtest** (solo operaciones ya cerradas antes de la entrada de la operación evaluada, mínimo 10 muestras — mismo umbral `CVP_MIN_SAMPLE` que usa el código real). Es una aproximación razonable pero **no es la métrica que usa producción**; columna `cvp_n_closed_before`/`cvp_aciertos_pct_causal` en el dataset documentan exactamente cuántas operaciones previas se usaron en cada caso, para que quede trazable.
2. **Sesión / hora:** la partición usada es una convención fija de horario UTC (§3.4), **sin ajuste de horario de verano** — ni de EEUU/UE (afecta Londres/NY) ni de ningún otro mercado. La sesión asignada a una operación cerca de un cambio de DST puede no coincidir exactamente con la sesión de mercado real de ese día. No se corrigió por no haber evidencia en el repo de cómo el bróker ajusta sus horarios de vela ante DST (mismo tipo de limitación ya documentada en `strategy/htf_session.py` respecto al ancla de sesión de 22:00 UTC).
3. **D1 / tendencia diaria:** no existe un dataset D1 descargado por separado — se derivó agregando el M5 en bloques de sesión de 1440 minutos (misma ancla 22:00 UTC que ya usa el HTF de producción). Es una elección metodológica razonable y consistente con el resto del código, pero **no es necesariamente la misma definición de "día" que usaría un indicador D1 estándar de un bróker/TradingView** (que normalmente ancla a medianoche del bróker, no a 22:00 UTC). El 73% de las operaciones no tiene una tendencia D1 clasificable como clara (secuencia HH/HL de 3 bloques) — se documenta como "sin secuencia clara", no se fuerza una clasificación.
4. **Comisión en CVP:** ver BOT-044 — `cvp_score()` tiene un problema de conversión de comisión a precio (usa `contract_size` en vez de `tick_value/tick_size`) que **no afecta este análisis** porque `commission_usd=0.0` en todas las corridas (mismo supuesto que el resto de los scripts de backtest).
5. **`real_volume` es 0** en este símbolo/bróker (típico de CFDs) — el factor Nodo usa `tick_volume` como proxy, igual que tendría que hacer en vivo si se activara para este símbolo (no es una limitación introducida por este análisis, es una característica del dato disponible).

---

## 7. Comparación sub1 vs sub2 vs sub3 — ¿qué tuvo de diferente `sub2`?

Fuente: `backtests/results/BOT-045_subperiod_continuous_M5.csv` y `BOT-045_subperiod_categorical_M5.csv`.

### 7.1. Variables continuas — medias/medianas por sub-período

| Variable | sub1 (mediana) | sub2 (mediana) | sub3 (mediana) | ¿Diferencia relevante? |
|---|---:|---:|---:|---|
| RSI en la entrada | 50.49 | 51.38 | 49.65 | No — prácticamente igual |
| ADX en la entrada | 26.31 | 25.79 | 26.50 | No — prácticamente igual |
| **ATR% (volatilidad relativa)** | **0.082%** | **0.127%** | 0.123% | **Sí — sub2 y sub3 notablemente más volátiles que sub1, sub2 el máximo** |
| Distancia a EMA/ATR | 0.300 | 0.286 | 0.285 | No |
| Ancho de bloque HTF/ATR | 5.96 | 6.28 | 5.96 | No — marginal |
| **Posición dentro del bloque** | 0.520 | **0.592** | 0.465 | Parcial — sub2 más alto (más cerca de resistencia en promedio), sub3 más bajo |
| Antigüedad en el bloque | 39 | 40 | 37 | No |

**La diferencia más grande y clara de todo el dataset es ATR% (volatilidad relativa):** `sub2` tiene una mediana 55% mayor que `sub1` (0.127% vs 0.082%). Sin embargo, `sub3` también está elevado (0.123%, casi igual a `sub2`) y aun así tiene expectancy negativa — la volatilidad por sí sola **no explica** por qué `sub2` fue positivo y `sub3` no.

### 7.2. Variables categóricas — proporciones por sub-período

| Variable | sub1 | sub2 | sub3 | Lectura |
|---|---|---|---|---|
| **% SHORT** | 53.3% | **55.9%** | 47.1% | `sub2` tiene la mayor proporción de SHORT (la dirección que globalmente rinde mejor, §5.9); `sub3` la menor — **contribuye parcialmente** a explicar por qué `sub3` es peor que `sub2` |
| **% D1 alcista** | 15.5% | **22.4%** | 11.0% | `sub2` claramente más alcista en D1 |
| **% D1 bajista** | 11.1% | **7.2%** | 11.7% | `sub2` con menos tramos D1 bajistas (la peor categoría D1, §5.10) — **contribuye parcialmente** |
| % alineado con D1 (True) | 13.4% | 13.5% | 12.1% | Prácticamente igual — no explica `sub2` |
| % en contra de D1 (False) | 13.2% | **16.0%** | 10.5% | `sub2` tiene **más** operaciones en contra de D1 (la peor categoría de alineación) que `sub1`/`sub3` — esto **no favorece** a `sub2`, es evidencia en contra de que la alineación D1 explique la ventaja de `sub2` |
| Sesión / día de semana / divergencia / tendencia / nodo | — | — | — | Sin diferencias relevantes entre sub-períodos |

### 7.3. Síntesis — ¿qué caracterizó a `sub2`?

**No hay una única variable que explique `sub2` de forma limpia y completa.** La combinación de evidencia apunta a:

1. **Volatilidad relativa (ATR%) sustancialmente más alta** que `sub1` — el cambio más grande y claro del dataset, consistente con el gradiente de expectancy por cuartil de ATR% (§5.3). Necesario pero no suficiente (`sub3` también está elevado y no fue positivo).
2. **Mayor proporción de operaciones SHORT** (55.9% vs 53.3%/47.1%) — dirección con mejor resultado global — contribuye, pero la diferencia de proporción es moderada, no dramática.
3. **Contexto D1 más alcista y con menos tramos bajistas** — dirección D1 "bajista" es la peor categoría D1 individual (§5.10), y `sub2` tuvo la menor proporción de ella.
4. **La alineación estricta dirección-de-operación-vs-D1 (`aligned_with_d1`) NO explica `sub2`** — de hecho `sub2` tiene *más* operaciones "en contra de D1" que los otros sub-períodos, no menos. Esta es evidencia importante en sentido contrario a una hipótesis simple de "sub2 tuvo más operaciones bien alineadas" — no es así.

Siguiendo la instrucción explícita del ticket (§12: *"no asumir que esas serán las variables reales... la conclusión debe salir exclusivamente de los datos"*): la lectura honesta es que `sub2` fue, sobre todo, un **régimen de volatilidad más alta con una mezcla direccional ligeramente más favorable (más SHORT, D1 menos bajista)** — un efecto de régimen de mercado combinado, no una única palanca, y **no completamente reproducible ni aislable con las variables medidas acá**.

---

## 8. Winners vs losers — dentro y fuera de sub-período (evitando correlación accidental con `sub2`)

Fuente: `backtests/results/BOT-045_winners_losers_continuous_M5.csv` y `BOT-045_winners_losers_categorical_M5.csv`. Se comparó cada variable entre operaciones ganadoras y perdedoras **globalmente y dentro de cada uno de `sub1`/`sub2`/`sub3` por separado**, para distinguir un efecto real de régimen de una correlación accidental con que `sub2` domine cierta región (ticket §9).

| Variable | Global (winners − losers) | sub1 | sub2 | sub3 | ¿Consistente en signo? |
|---|---:|---:|---:|---:|---|
| ADX | −0.785 | −0.750 | −0.880 | −0.746 | **Sí, en los 3** — winners tienen ADX más bajo siempre |
| RSI | −0.107 | −0.983 | −0.626 | **+1.119** | **No** — cambia de signo en sub3 |
| ATR% | +0.001 | −0.002 | −0.000 | −0.002 | Prácticamente cero en los 3 — sin efecto real a nivel de trade individual |
| Distancia EMA/ATR | −0.001 | −0.009 | +0.009 | +0.000 | No hay efecto real (todos ~0) |
| Ancho bloque HTF/ATR | −0.268 | −0.621 | **+0.090** | −0.249 | Mayormente consistente (2/3), se invierte en sub2 |
| Antigüedad en bloque | −1.029 | −3.922 | **+4.307** | −2.969 | **No** — se invierte en sub2 |
| **Dirección (% SHORT en winners vs losers)** | 54.5% vs 49.5% | 52.8% vs 53.8% | **58.7% vs 52.9%** | **52.1% vs 42.5%** | **Sí, en los 3** (marginal en sub1, clara en sub2/sub3) |
| **Alineado con D1 (% en winners vs losers)** | 14.4% vs 11.5% | 15.3% vs 11.6% | 15.2% vs 11.8% | 12.9% vs 11.2% | **Sí, en los 3** |

**Conclusión de esta sección:** de todas las variables candidatas, solo **ADX**, **dirección (LONG/SHORT)** y **alineación con D1** muestran el mismo signo de efecto en los 3 sub-períodos por separado — son las que se clasifican con mayor confianza en §10. RSI, antigüedad en el bloque y ancho del bloque **cambian de signo** entre sub-períodos — su aparente señal en el análisis univariado agregado (§5) está contaminada, al menos en parte, por la composición de `sub2`, y se degradan a evidencia débil/inconsistente.

---

## 9. Interacciones (solo variables con señal previa)

Fuente: `backtests/results/BOT-045_interactions_M5.csv`. Se combinaron únicamente variables que mostraron señal individual (ADX, alineación D1, sesión, dirección, distancia a EMA, factores de scoring) — sin búsqueda combinatoria indiscriminada.

| Combinación | N | % muestra | WR | PF | Expectancy (R) | Distribución sub1/sub2/sub3 |
|---|---:|---:|---:|---:|---:|---|
| **ADX≥25 + alineado con D1** | 173 | 7.0% | 52.3% | 1.037 | **+0.018** | 33.5% / 34.1% / 32.4% (pareja — no concentrada en sub2) |
| ADX≥25 + en contra de D1 | 157 | 6.3% | 42.0% | 0.685 | **−0.188** | 36.9% / 36.9% / 26.1% |
| ADX<20 + Londres/NY overlap | 232 | 9.4% | 50.4% | 0.962 | −0.020 | 28.9% / 36.2% / 34.9% |
| SHORT + tendencia en contra (scoring) | 143 | 5.8% | 48.3% | 0.877 | −0.065 | 35.7% / 42.0% / 22.4% |
| LONG + tendencia en contra (scoring) | 83 | 3.4% | 48.2% | 0.873 | −0.068 | 33.7% / 14.5% / 51.8% |
| Distancia EMA lejos (Q4) + ADX≥25 | 320 | 12.9% | 49.8% | 0.941 | −0.030 | 32.2% / 30.9% / 36.9% |
| Distancia EMA cerca (Q1) + ADX≥25 | 332 | 13.4% | 46.1% | 0.806 | −0.107 | 35.5% / 28.6% / 35.8% |
| Divergencia a favor + ADX≥25 | 272 | 11.0% | 47.8% | 0.858 | −0.077 | 34.2% / 28.7% / 37.1% |
| Asia + ADX<20 | 165 | 6.7% | 53.9% | 1.096 | +0.046 | 31.5% / 35.8% / 32.7% |
| Londres/NY overlap + ADX≥25 | 338 | 13.7% | 47.6% | 0.872 | −0.068 | 37.3% / 29.3% / 33.4% |

**La combinación más interesante es "ADX≥25 + alineado con D1"** (+0.018 R/trade, PF 1.037, n=173, 7.0% de la muestra) — su contraparte "en contra de D1" con el mismo ADX alto da el peor resultado de toda la tabla de interacciones (−0.188). La distribución entre sub-períodos de ambas combinaciones está razonablemente equilibrada (no concentrada en `sub2`), lo que le da algo más de credibilidad que a un hallazgo agregado simple. **Aun así, con 173 operaciones y una expectancy apenas por encima de cero, esto es evidencia exploratoria, no un candidato** — ver §11 y §16 (no se implementa nada en esta tarea).

---

## 10. Robustez y clasificación de hallazgos

| Variable | Evidencia | N (aprox.) | Efecto observado | Estabilidad (3 sub-períodos) | ¿Explica `sub2`? | Recomendación |
|---|:---:|---:|---|---|:---:|---|
| **LONG vs SHORT** | **A** | 2.474 | SHORT +0.004R vs LONG −0.100R | Mismo signo en los 3 (winners/losers y expectancy) | Parcial (sub2 tiene más SHORT) | Variable de mayor prioridad para una futura Hipótesis/Prueba controlada — **no implementar todavía** |
| **Alineación con D1 (`aligned_with_d1`)** | **A** (dentro de su cobertura) | 646 (26% de la muestra) | Alineado +0.067R vs en contra −0.183R | Mismo signo en los 3 | No (sub2 tiene *más* operaciones en contra, no menos) | Señal fuerte pero de cobertura limitada — candidata a investigar con más historial antes de cualquier prueba controlada |
| **ADX** | **B** | 2.474 | Relación inversa, ADX bajo mejor | Mismo signo en los 3 (winners/losers) | No (ADX similar entre sub-períodos) | Prometedora, magnitud modesta — requiere más validación |
| **ATR% / volatilidad relativa** | **B** | 2.474 | Gradiente de régimen (PF/expectancy sube con ATR%), sin efecto a nivel de trade individual | Efecto de régimen, no de trade-a-trade | **Sí, parcialmente** (mayor diferencia sub1 vs sub2/sub3 de todo el dataset) | Variable de régimen agregado, no de selección de entrada individual |
| **Sesión (Asia peor, Londres mejor)** | B | 742 (Asia) / 335 (Londres) | Asia consistentemente negativa en los 3 sub-períodos | Asia sí, Londres/NY no | No | Señal de régimen razonable, no suficiente para filtro |
| **Día de semana (Viernes/Miércoles peores)** | B | 409 / 512 | Viernes y Miércoles negativos en la mayoría de los sub-períodos | Parcial | No | Exploratoria |
| Posición dentro del bloque HTF | C | 2.474 | Medio del bloque mejor que los extremos | No verificado por sub-período de forma separada | No | Exploratoria |
| Ancho del bloque HTF / ATR | C | 2.474 | Gradiente univariado, pero se invierte en `sub2` (winners/losers) | No | No | Débil/inconsistente |
| Antigüedad en el bloque HTF | C | 2.474 | Sin gradiente monótono, se invierte en `sub2` | No | No | Débil/inconsistente |
| RSI en la entrada | C | 2.474 | Extremos peores, pero cambia de signo entre sub-períodos (winners/losers) | No | No | Débil/inconsistente |
| Divergencia (BOT-023) | C | 501 (con divergencia) | "En contra" peor, "a favor" no mejora | No verificado por sub-período | No | Señal parcial, no accionable |
| Distancia a EMA / ATR | D | 2.474 | Sin patrón monótono, sin diferencia winners/losers | No | No | Sin evidencia útil |
| Tendencia (scoring, BOT-023) | D | 2.474 | 90.6% de la muestra en el bucket "0" — casi sin variabilidad | No | No | Sin evidencia útil con esta configuración |
| CVP (BOT-023) | D | 2.474 | Cero variación absoluta a RR=1 | N/A | No | Sin evidencia útil **a este RR específicamente** — ver §7.4 nota |
| Nodo (BOT-023) | D/C | 2.474 | Signo contrario al esperado por diseño, bucket "0" muy chico (11%) | No | No | Contraintuitivo, requiere revisión del diseño del factor antes de sacar conclusiones |
| Día D1 (tendencia sola, sin alinear con dirección) | C | 664 (con tendencia clara) | Bajista peor que alcista, pero 73% de la muestra sin clasificar | No | Parcial | Ver `aligned_with_d1` en su lugar (más fuerte) |

---

## 11. Respuestas obligatorias (ticket §15)

**A. ¿Existe realmente un régimen donde la estrategia tiene edge?**
Sí, indicios claros pero acotados: dentro de las 173 operaciones con ADX≥25 **y** alineadas con D1, la expectancy es positiva (+0.018R, PF 1.037) — un margen chico, sobre una muestra que es el 7% del total. También hay evidencia consistente (dirección, ADX, alineación D1) de que **ciertos sub-conjuntos rinden sistemáticamente mejor que otros**, aunque ninguno solo alcanza para revertir la expectancy agregada negativa de Config A.

**B. ¿Qué variables caracterizan ese régimen?**
Con la evidencia de mayor confianza (clasificación A/B en §10): dirección SHORT, alineación de la operación con la tendencia D1 (cuando esta existe), ADX relativamente bajo, sesión de Londres, y — como variable de régimen agregado más que de trade individual — volatilidad relativa (ATR%) más alta.

**C. ¿Qué tenía de diferente `sub2`?**
Principalmente volatilidad relativa (ATR%) sustancialmente más alta que `sub1`, junto con una mezcla direccional algo más orientada a SHORT y un contexto D1 más alcista con menos tramos bajistas — ver síntesis completa en §7.3. Ninguna variable lo explica por completo; la alineación con D1 en particular **no** explica `sub2` (tiene más operaciones en contra de D1, no menos).

**D. ¿Qué condiciones caracterizan los períodos/trades negativos?**
LONG (vs SHORT), operaciones en contra de la tendencia D1 (cuando esta es clasificable), ADX alto, sesión Asia o Nueva York, viernes/miércoles, entradas cerca de los extremos del bloque HTF (en vez del medio).

**E. ¿El problema parece estar relacionado principalmente con tendencia, volatilidad, dirección, temporalidad, estructura HTF u otra característica?**
Con esta evidencia, los tres factores con más peso son **dirección** (LONG/SHORT), **alineación con tendencia D1** y, en segundo plano, **régimen de volatilidad**. La estructura HTF (ancho/posición/antigüedad del bloque) y la temporalidad (sesión/hora/día) muestran señal más débil o inconsistente entre sub-períodos.

**F. ¿Qué variables merecen pasar a una segunda fase de investigación?**
Dirección (LONG/SHORT) y alineación con D1 — son las de evidencia A, consistentes en los 3 sub-períodos y con una lógica de mercado razonable (más allá de ser cierto en este dataset). ADX y volatilidad relativa como variables secundarias de contexto. Cualquier paso siguiente debe seguir la regla de experimentación de `BACKLOG.md` (Diagnóstico → **Hipótesis** → Prueba controlada → Robustez → Validación → Cambio en producción) — este documento cubre solo Diagnóstico.

**G. ¿Cuáles podemos descartar (por ahora, sin evidencia útil)?**
Distancia a EMA normalizada, el factor "Tendencia" de scoring (BOT-023, casi sin variabilidad con esta configuración), CVP (sin variación a RR=1) y, con más cautela porque el resultado es contraintuitivo, el factor "Nodo" tal como está diseñado hoy.

---

## 12. Limitaciones generales del estudio

- Un solo símbolo (XAUUSDc), un solo bróker/cuenta, un único rango temporal (~1.4 años) y una sola configuración de parámetros (Config A, RR=1). Ningún hallazgo debe generalizarse a otros símbolos, brókers o configuraciones sin volver a probarlo.
- El dataset D1 es derivado (agregación de M5), no un feed D1 independiente — ver limitación §6.3.
- CVP usa una aproximación causal, no el historial real de cuenta en vivo — ver limitación §6.1.
- Sesión/hora sin ajuste de horario de verano — ver limitación §6.2.
- Con 2.474 operaciones totales, cualquier segmentación en varios buckets simultáneos (interacciones triples o más) cae rápidamente en muestras insuficientes — por eso este estudio se limitó a univariado + interacciones de a pares, siguiendo la instrucción explícita del ticket de no hacer búsqueda combinatoria indiscriminada.
- Ningún resultado de este informe fue optimizado ni ajustado para maximizar ninguna métrica — todos los buckets/umbrales usados (RSI, ADX, cuartiles de ATR/distancia/ancho) son convenciones estándar o percentiles del propio dataset, no thresholds ajustados a mano para mejorar el resultado.

---

## 13. Artefactos

**Scripts nuevos (reproducibles, versionados, offline, no tocan `/strategy` ni producción):**
- `backtests/scripts/07_bot045_regime_dataset.py` — construye el dataset enriquecido por operación. Uso: `python backtests/scripts/07_bot045_regime_dataset.py M5`.
- `backtests/scripts/08_bot045_analysis.py` — univariado, sub-períodos, winners/losers, interacciones, gráficos. Uso: `python backtests/scripts/08_bot045_analysis.py M5`.

**Dataset enriquecido:**
- `backtests/results/BOT-045_trades_enriched_M5.csv` / `.parquet` — 2.474 filas, 1 por operación, todas las variables de §3.4.

**Resultados agregados:**
- `backtests/results/BOT-045_baseline_M5.csv`
- `backtests/results/BOT-045_univariate_M5.csv`
- `backtests/results/BOT-045_subperiod_continuous_M5.csv` / `BOT-045_subperiod_categorical_M5.csv`
- `backtests/results/BOT-045_winners_losers_continuous_M5.csv` / `BOT-045_winners_losers_categorical_M5.csv`
- `backtests/results/BOT-045_interactions_M5.csv`

**Gráficos** (`backtests/results/BOT-045_charts/`):
- `01_expectancy_pf_por_periodo.png`, `02_rsi_winners_vs_losers.png`, `03_adx_winners_vs_losers.png`, `04_atr_pct_winners_vs_losers.png`, `05_expectancy_por_sesion.png`, `06_expectancy_por_hora.png`, `07_long_vs_short.png`, `08_distancia_ema_atr.png`, `09_sub_periodos_adx_atr.png`, `10_heatmap_adx_sesion.png`.

**Este reporte:**
- `docs/reports/BOT-045_market_regime_analysis.md` (este archivo).

---

## 14. MUY IMPORTANTE — nada de esto se implementó

Siguiendo el ticket §16 al pie de la letra: **no se agregó ningún filtro**, no se bloqueó SHORT ni LONG, no se modificó ninguna entrada, no se tocó `strategy/scoring.py`, `strategy/engine.py`, `execution/`, la API, el panel, ni ningún parámetro de producción. Todos los hallazgos de este documento son **diagnósticos**. Cualquier paso siguiente (por ejemplo, una Hipótesis formal sobre dirección o alineación D1 seguida de una Prueba controlada) debe abrirse como un ticket/experimento aparte y seguir la regla de experimentación de `BACKLOG.md`, validándose fuera de muestra antes de cualquier cambio en producción.

---

## 15. Git

| | |
|---|---|
| **Commit base** | `001f9df` (branch `main`, antes de esta tarea) |
| **Archivos nuevos** | 2 scripts (`backtests/scripts/07_*.py`, `08_*.py`), 1 informe (este archivo), dataset y CSV de resultados en `backtests/results/`, 10 gráficos en `backtests/results/BOT-045_charts/` |
| **Archivos modificados** | `BACKLOG.md` (BOT-045 → `DONE`, ver diff de esta tarea) |
| **No se modificó** | `strategy/`, `execution/`, `api/`, `panel/`, `VERSION`, `CHANGELOG.md`, ni ningún dataset/script preexistente de `backtests/` |

---

*Generado por Claude Code a partir del prompt "BOT-045 — Análisis de régimen de mercado y calidad de entradas" del usuario. Tarea 100% diagnóstica y offline — no se modificó lógica de entrada/salida, pivotes, HTF, EMA, Buffer, RR, scoring, ni configuración/ejecución en producción en ningún momento.*
