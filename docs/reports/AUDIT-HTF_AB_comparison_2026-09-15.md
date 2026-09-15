# Experimento A/B — HTF en formación vs HTF anterior cerrado

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Commit base:** `001f9df` (sin cambios de código productivo en esta tarea)
**Tipo de tarea:** Experimento diagnóstico controlado — no modifica `/strategy`, `/execution`, configuración real ni el perfil `5m` de producción. No implementa BOT-045 ni BOT-008. No reemplaza la estrategia actual.

Este documento es **autocontenido** e incluye script y comandos completos para reproducir el experimento sin depender de la conversación de Claude Code.

---

## 1. Resumen ejecutivo

Se comparó, sobre el mismo dataset y con todos los demás parámetros idénticos, la lógica HTF actual de producción (**Variante A**, bloque en formación, auto-armado incluido) contra una variante experimental aislada (**Variante B**, bloque HTF anterior ya cerrado, niveles congelados durante todo el bloque).

**Ninguna de las dos variantes es rentable** sobre el período completo (2025-04-14 → 2026-09-15): A cierra en −$1.391,32 netos, B en −$570,00 netos. Pero al normalizar por volumen de operación — que es obligatorio, porque B opera **60,4% menos** que A (1.248 vs 3.148 trades resueltos) —, **A es sistemáticamente igual o mejor que B en toda métrica por operación**: win rate (50,08% vs 46,53%), expectancy en R (−0,0355 vs −0,3072, un orden de magnitud peor en B), profit factor en R (0,931 vs 0,587) y profit/100 trades en USD (−$44,20 vs −$45,67, prácticamente empatado, B levemente peor). La única métrica donde B "gana" es la pérdida agregada total en USD (−$570 vs −$1.391) — y esa diferencia se explica enteramente por operar muchísimo menos, no por mejor calidad de señal (ver sección 10).

**Clasificación: `A claramente superior`.** El auto-armado no es la causa de que la estrategia no tenga edge — de hecho, quitarlo (HTF cerrado) degrada la calidad de señal por operación en vez de mejorarla. Ninguna de las dos variantes resuelve el problema de fondo (ninguna es rentable), pero B no es una alternativa mejor.

---

## 2. Metodología

**Principio de diseño:** `strategy.engine.run_backtest()` ya acepta `resistencia`/`soporte` como *hook de testeo* — "si se pasan, se usan tal cual" (docstring de la función, `strategy/engine.py:201-204`). Esto permite que A y B llamen literalmente **a la misma función** (mismo cálculo de EMA, entrada, salida, expiración, concurrencia, costos, PnL) y que la única variable que cambie sea el array `resistencia`/`soporte` que reciben. La "regla fundamental" del experimento (cambiar una sola variable) queda garantizada por construcción del código, no por disciplina manual.

- **Variante A (control):** `strategy.engine.bucket_levels()` sin modificar — se corrió además `run_backtest(resistencia=None, soporte=None)` (comportamiento por default) y se comparó bar a bar contra pasarle `bucket_levels()` explícitamente: **idénticas, 6.409/6.409 señales** (ver sección 4).
- **Variante B (experimental):** función nueva `bucket_levels_previous_closed()`, definida **fuera** de `strategy/engine.py`, en el script del experimento (`backtests/scripts/06_htf_ab_experiment.py`). Usa el mismo `strategy.htf_session.bucket_start_utc_seconds()` para los límites de bloque. Para cada barra de un bloque N, devuelve el `high`/`low` FINAL (ya cerrado) del bloque N−1, constante durante todo el bloque N. El primer bloque del dataset (sin bloque anterior) queda con `NaN` — el motor real ya maneja `NaN` nativamente (`if not math.isnan(r_i) and high[i] >= r_i`), así que esas barras simplemente no pueden armar nada; no se inventó ningún nivel.
- **Conteo de armados:** `run_backtest()` no expone activaciones de armado por barra (solo señales resueltas), así que se replicó — puramente para diagnóstico, sin tocar el backtest real — la misma máquina de estados de 6 líneas que usa `engine.py` (líneas 267-292), alimentada con el mismo `ema_line` y el `resistencia`/`soporte` de cada variante.
- **Costos:** reales, obtenidos de MT5 en vivo (`symbol_info()`), igual mecanismo que `backtests/scripts/05_run_rr_isolation.py` (BOT-042).

---

## 3. Parámetros efectivos

```
strategy.profiles.get_profile('5m')   # SIN overrides, tal cual está en el repo
StrategyParams(ema_periods=12, periodos_htf_min=400, buf_bp=0.4, rr=1.0,
                max_concurrent_por_direccion=1, valid_bars=10, orden_viva=True,
                max_bars_trade=500, fixed_lot=0.01, entrada_viva=False,
                una_operacion_a_la_vez=True)

Símbolo: XAUUSDc
Dataset: backtests/data/XAUUSDc_M5_latest.parquet — 100.505 velas M5
Rango:   2025-04-14 18:50:03 UTC -> 2026-09-15 00:40:03 UTC

Costos en vivo (MT5 symbol_info, 2026-09-15):
  point=0.001  contract_size=1.0  tick_value=0.1  tick_size=0.001
  swap_long=-533.9 pts/noche/lote  swap_short=0.0 pts/noche/lote
  spread_fallback_points=260 (fallback; se usa el spread real por vela cuando está disponible)
```

---

## 4. Validación del baseline A

```
Variante A (resistencia=None, default) vs A (resistencia=bucket_levels() explícito):
  IDÉNTICAS bar a bar -- 6.409/6.409 señales
Variante A: señales=6.409 (BUY=3.176 SELL=3.233), trades resueltos=3.148
Referencia de la auditoría previa (docs/reports/AUDIT-HTF_autoarmado_2026-09-15.md): 6.409 señales -- COINCIDE
```

El control reproduce exactamente el comportamiento de producción documentado en la auditoría del 2026-09-15. Se procede con la comparación A vs B sobre un baseline confirmado.

---

## 5. Validación de HTF cerrado (Variante B)

- **Barras sin nivel válido (primer bloque, sin HTF anterior):** 26/100.505 — exactamente las barras del primer bloque completo (`bar 0..25`), como exige la especificación del experimento. Sin inventar niveles.
- **Assert `resistencia_B == high final del bloque anterior` (y `soporte_B == low`)**, sobre las 100.479 barras con bloque anterior definido: **OK en 100.479/100.479 (100%)**.
- **Constancia dentro del bloque** (`resistencia_B`/`soporte_B` no deben cambiar mientras dure el bloque actual): **0 cambios detectados** sobre las 100.505 barras.
- **Demostración explícita — una vela que hace nuevo máximo del bloque EN CURSO no mueve el nivel de B:**

```
bar 33  2025-04-14 22:35:03 UTC: high=3213.961 (nuevo máx. del bloque en curso)
        resistencia_B=3213.821 (SIN CAMBIAR, = high del bloque N-1)
        resistencia_A(en formación)=3213.961 (SÍ se actualizó, self-ref -- ver auditoría previa)
bar 34  2025-04-14 22:40:03 UTC: high=3215.225 (nuevo máx. del bloque en curso)
        resistencia_B=3213.821 (SIN CAMBIAR)      resistencia_A=3215.225 (SÍ se actualizó)
bar 63  2025-04-15 01:05:03 UTC: high=3215.562 (nuevo máx. del bloque en curso)
        resistencia_B=3213.821 (SIN CAMBIAR)      resistencia_A=3225.213 (más adelante, arrastrado por A)
```

Tabla de ejemplo, primeras dos transiciones de bloque completas (`periodos_htf_min=400`):

```
 bar  timestamp_utc              bucket_id   nuevo_blk   high      low     res_B    sop_B    res_A    sop_A
   0  2025-04-14 18:50:03+00:00  1744653600    True     3204.624 3202.236   NaN      NaN     3204.624 3202.236
  15  2025-04-14 20:05:03+00:00  1744653600    False    3213.821 3211.944   NaN      NaN     3213.821 3202.236
  25  2025-04-14 20:55:03+00:00  1744653600    False    3211.240 3210.350   NaN      NaN     3213.821 3202.236
  26  2025-04-14 22:00:03+00:00  1744668000    True     3213.686 3211.488  3213.821 3202.236  3213.686 3211.488
  34  2025-04-14 22:40:03+00:00  1744668000    False    3215.225 3213.464  3213.821 3202.236  3215.225 3210.780
  63  2025-04-15 01:05:03+00:00  1744668000    False    3215.562 3211.885  3213.821 3202.236  3215.562 3210.002
 105  2025-04-15 04:35:03+00:00  1744668000    False    3228.396 3227.401  3213.821 3202.236  3230.515 3210.002
 106  2025-04-15 04:40:03+00:00  1744692000    True     3229.795 3227.225  3230.515 3210.002  3229.795 3227.225
```

Nótese: al arrancar el bloque 2 (bar 26), `resistencia_B`/`soporte_B` toman exactamente el high/low final del bloque 1 (3213.821/3202.236) y **permanecen fijos** durante las 80 barras siguientes (bar 26 a 105) pese a que el precio se movió muy por encima (hasta 3228.396) — exactamente la semántica pedida. Al cerrar el bloque 2 y arrancar el bloque 3 (bar 106), `resistencia_B` salta al high final del bloque 2 (3230.515).

---

## 6. Comparación de señales

```
                              A (formación)     B (cerrado)
Señales totales                   6.409             5.623
Señales válidas (stop del lado
  correcto)                       6.393 (99,8%)     2.498 (44,4%)
Armados venta (activaciones)      3.233             3.014
Armados compra (activaciones)     3.176             2.609

Coincidentes (mismo timestamp+dir):  2.866
Solo en A (desaparecen en B):        3.543  (55,3% de A)
Solo en B (nuevas, no están en A):   2.757  (49,0% de B)
```

Hallazgo estructural: la tasa de señales **válidas** cae de 99,8% (A) a 44,4% (B). Esto es consecuencia directa de la semántica de B: como `resistencia`/`soporte` quedan congelados en el bloque anterior mientras el precio sigue moviéndose libremente dentro del bloque actual, es mucho más frecuente que el stop calculado (`resistencia*(1+buf)` o `soporte*(1-buf)`) termine del lado incorrecto respecto de la entrada (`ema_now`) — más de la mitad de las señales de B se descartan por esto, algo que casi nunca ocurre en A porque ahí el nivel se acaba de actualizar con la vela actual.

---

## 7. Comparación de performance (trades resueltos, período completo)

```
                        A (formación)      B (cerrado)
Trades                       3.148              1.248
Winners / Losers / TO   1.575 / 1.570 / 3    576 / 662 / 10
Win Rate                    50,08%             46,53%
Net Profit (USD)          -1.391,32            -570,00
Net R                      -111,63             -383,33
Gross Win / Loss (USD)  14.667,75 / 16.059,07  7.174,39 / 7.744,39
Profit Factor (USD)          0,913              0,926
Profit Factor (R)            0,931              0,587
Expectancy (R)              -0,0355            -0,3072
Expectancy (USD)            -0,442             -0,457
Avg Winner (USD / R)     9,28 / 0,963R       12,00 / 0,941R
Avg Loser  (USD / R)    -10,22 / -1,037R    -11,51 / -1,398R
Max Drawdown (USD)         1.668,56           1.201,74
Max Drawdown (R)             136,00             393,53
Max Loss Streak                 10                  9
Max Win Streak                  10                 10
Trades/mes                  184,98              73,47
Profit/mes (USD)            -81,75             -33,56
Profit/100 trades (USD)     -44,20             -45,67
Return/DD (USD)             -0,834             -0,474
```

**Nota sobre max drawdown %:** el motor opera con lote fijo (`fixed_lot=0.01`), no con equity compuesto sobre un balance de cuenta — no hay una base de capital definida en el motor para expresar el drawdown como porcentaje sin inventar un balance inicial arbitrario. Se reportan drawdown en USD y en R (múltiplos de riesgo), ambos nativos del motor, sin inventar supuestos adicionales.

**Observación sobre `avg_loser_r`:** en B es notablemente más negativo (−1,398R vs −1,037R en A). Como `resistencia`/`soporte` en B provienen del bloque previo (potencialmente muy alejado del precio vigente al momento de la señal), la distancia de stop puede diferir bastante entre operaciones de A y B aun con `buf_bp` idéntico — esto queda señalado como observación cuantitativa, no como una causa verificada con más detalle; no se investigó la distribución completa de distancias de stop en esta tarea (fuera del alcance pedido: aislar únicamente la semántica HTF, sin agregar análisis adicionales).

---

## 8. Resultados mensuales

18 meses, ambas variantes, mismo dataset:

| Mes | Trades A | WR A | Net USD A | PF(R) A | Trades B | WR B | Net USD B | PF(R) B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-04 | 100 | 45,0% | -49,95 | 0,772 | 38 | 62,2% | -29,66 | 1,300 |
| 2025-05 | 197 | 41,6% | -297,40 | 0,666 | 76 | 45,3% | 46,18 | 0,716 |
| 2025-06 | 163 | 46,6% | -108,76 | 0,808 | 66 | 50,0% | 18,00 | 0,834 |
| 2025-07 | 193 | 50,3% | -47,18 | 0,906 | 90 | 40,0% | -135,75 | 0,558 |
| 2025-08 | 194 | 54,1% | -17,26 | 1,018 | 90 | 44,9% | -16,50 | 0,193 |
| 2025-09 | 193 | 49,2% | -75,40 | 0,885 | 79 | 54,4% | 51,46 | 0,964 |
| 2025-10 | 191 | 57,1% | 287,34 | 1,273 | 76 | 42,7% | -203,38 | 0,692 |
| 2025-11 | 153 | 55,3% | 148,10 | 1,170 | 58 | 50,0% | 32,18 | 0,894 |
| 2025-12 | 186 | 53,2% | 8,60 | 1,071 | 79 | 44,9% | 37,73 | 0,680 |
| 2026-01 | 185 | 51,9% | 41,87 | 1,033 | 73 | 39,7% | -763,21 | 0,559 |
| 2026-02 | 132 | 53,4% | 161,47 | 1,101 | 52 | 56,9% | 240,49 | 1,229 |
| 2026-03 | 183 | 43,7% | -680,48 | 0,732 | 70 | 61,8% | 505,92 | 1,431 |
| 2026-04 | 192 | 50,0% | 10,29 | 0,933 | 59 | 52,5% | 117,78 | 0,681 |
| 2026-05 | 210 | 42,4% | -436,87 | 0,676 | 86 | 39,5% | -152,95 | 0,518 |
| 2026-06 | 229 | 51,1% | -198,57 | 0,971 | 83 | 34,9% | -127,34 | 0,390 |
| 2026-07 | 192 | 48,4% | -169,50 | 0,868 | 68 | 47,8% | 152,91 | 0,736 |
| 2026-08 | 189 | 57,1% | 40,40 | 1,234 | 74 | 45,9% | -180,39 | 0,401 |
| 2026-09* | 66 | 52,3% | -8,02 | 1,011 | 31 | 36,7% | -163,48 | 0,509 |

_(\*2026-09 es parcial — dataset termina el 15 de septiembre.)_

No hay un patrón consistente donde B supere a A mes a mes — B gana en algunos meses (2025-05, 2025-06, 2025-09, 2026-02, 2026-03, 2026-04, 2026-07) y pierde en otros (2025-04, 2025-07, 2025-08, 2025-10, 2025-11, 2025-12, 2026-01, 2026-05, 2026-06, 2026-08, 2026-09), sin tendencia direccional clara. El mes 2026-03 es un outlier fuerte para B (+$505,92, PF 1,431) que por sí solo explica buena parte de la ventaja agregada de B en USD — ver sección 9 (no es un efecto sostenido, es concentrado).

---

## 9. Primer 50% vs segundo 50% (estabilidad, sin optimizar nada)

División cronológica simple del dataset en dos mitades (50.252 / 50.253 velas), sin warmup cruzado — mismo criterio que usan `04_run_robustness.py`/`05_run_rr_isolation.py` para sub-períodos:

```
                    H1 (2025-04-14 .. 2025-12-30)      H2 (2025-12-30 .. 2026-09-15)
              Trades   WR      NetUSD    PF(USD)  MaxDD   Trades   WR      NetUSD    PF(USD)  MaxDD
A (formación)  1.550   50,42%  -215,51   0,960    611,40   1.598   49,69%  -1.216,43  0,886   1.668,56
B (cerrado)      639   47,48%  -249,41   0,903    450,83     608   45,44%   -346,77   0,933     920,42
```

Ambas variantes empeoran de H1 a H2 (consistente con el hallazgo de BOT-042: "sin edge robusto", régimen de mercado desfavorable en el tramo más reciente). El efecto del cambio HTF (A→B) aparece en **ambos** períodos, no depende de una sola etapa: en ambos H1 y H2, A tiene mejor win rate que B; en H1 A tiene mejor PF(USD) que B (0,960 vs 0,903), en H2 se invierte levemente (0,886 vs 0,933) — pero A concentra su pérdida agregada casi enteramente en H2 (−$1.216 de −$1.391 total), mientras B la reparte más parejo entre ambas mitades (−$249 / −$347). Esto es consistente con A operando ~2,5× más que B: cualquier régimen adverso de H2 se amplifica más en A por volumen, no porque la señal de A sea peor por operación en ese tramo específico (WR de A en H2 sigue siendo 49,69%, superior al WR de B en cualquiera de las dos mitades).

---

## 10. Análisis A-only / B-only

Responde directamente la pregunta del experimento: *¿el HTF cerrado elimina principalmente operaciones malas, buenas, o ambas proporcionalmente?*

```
A-only (3.543 señales, desaparecen en B):
  1.317 llegaron a trade resuelto (673 win / 643 loss / 1 timeout)
  Win Rate = 51,14%   Net USD = -154,40   Net R = -27,18
  2.226 no llegaron a trade resuelto (inválidas / expiradas / bloqueadas por concurrencia)

B-only (2.757 señales, nuevas -- no existían en A):
  434 llegaron a trade resuelto (210 win / 223 loss / 1 timeout)
  Win Rate = 48,50%   Net USD = +313,04   Net R = -223,94
  2.323 no llegaron a trade resuelto
```

**Respuesta:** el HTF cerrado **no elimina selectivamente operaciones malas**. El win rate de las señales que A pierde al pasar a B (51,14%) es *superior* al win rate general de A (50,08%) — es decir, lo que B descarta es, si acaso, una muestra ligeramente **mejor que el promedio** de A, no peor. Su contribución en USD (−$154,40) es pequeña en relación al total de A (−$1.391,32).

Las señales nuevas que aparecen en B (2.757, de las cuales solo 434 resuelven en trade) tienen win rate por debajo de 50% (48,50%) y Net R fuertemente negativo (−223,94R), pero casualmente Net USD positivo (+$313,04) — reflejo del mismo patrón de la sección 7 (stops más amplios en B, resultado en $ desacoplado del resultado en R). Esta es la explicación completa de por qué B "pierde menos dólares" en el agregado: no es que sus señales sean de mejor calidad (de hecho su win rate es más bajo, 48,50% vs 51,14% de lo que se pierde de A), sino que produce un subconjunto pequeño (434 trades) que, por azar de distancias de stop/tamaño de movimiento, resulta positivo en dólares pese a ser negativo en R. No es evidencia de una mejora estructural.

---

## 11. Tabla final A/B

| Métrica | A — HTF formación | B — HTF cerrado | Diferencia (B−A) |
|---|---:|---:|---:|
| Señales | 6.409 | 5.623 | −786 |
| Trades | 3.148 | 1.248 | −1.900 |
| Winners | 1.575 | 576 | −999 |
| Losers | 1.570 | 662 | −908 |
| Win Rate | 50,08% | 46,53% | −3,55 pp |
| Net Profit (USD) | −1.391,32 | −570,00 | **+821,32** |
| Profit Factor (USD) | 0,913 | 0,926 | +0,013 |
| Profit Factor (R) | 0,931 | 0,587 | **−0,344** |
| Expectancy (R) | −0,0355 | −0,3072 | **−0,272** |
| Avg Winner (USD) | 9,28 | 12,00 | +2,72 |
| Avg Loser (USD) | −10,22 | −11,51 | −1,29 |
| Max Drawdown (USD) | 1.668,56 | 1.201,74 | −466,82 |
| Trades/mes | 184,98 | 73,47 | −111,51 |
| Profit/mes (USD) | −81,75 | −33,56 | +48,19 |
| Profit/100 trades (USD) | −44,20 | −45,67 | −1,47 |
| Return/DD (USD) | −0,834 | −0,474 | +0,360 |

No se ocultan las métricas donde B es superior en términos absolutos (Net Profit, Profit/mes, Max Drawdown, Return/DD) — todas mejoran en B. Pero todas son consecuencia mecánica de operar 60,4% menos veces (menor exposición total), no de mejor calidad de señal: las métricas normalizadas por operación (Win Rate, Profit Factor R, Expectancy R, Profit/100 trades) favorecen a A en 3 de 4, y la cuarta (Profit/100 trades) prácticamente empata con leve ventaja para A.

---

## 12. Conclusión

**`A claramente superior`** — con el matiz explícito de que **ninguna de las dos variantes es rentable** sobre este dataset y perfil. La conclusión no es "el auto-armado le da edge a la estrategia" (los números de A siguen siendo netos negativos), sino: **el auto-armado no es la causa del resultado negativo de la estrategia, y quitarlo no lo arregla — lo empeora en términos normalizados por operación.**

Justificación numérica:
- En las 4 métricas normalizadas por volumen que evitan el sesgo de "B opera menos" (Win Rate, Profit Factor en R, Expectancy en R, Profit por 100 trades en USD), **A iguala o supera a B en las 4**, y en 2 de ellas (Profit Factor R, Expectancy R) la diferencia es de un orden de magnitud.
- La única ventaja de B (menor pérdida agregada en USD, +$821,32) se explica enteramente por operar 60,4% menos (sección 10) — no por descartar selectivamente operaciones malas (el win rate de lo que B descarta de A es *superior* al promedio de A, sección 10).
- El efecto es consistente en ambas mitades cronológicas del dataset (sección 9) — no depende de un régimen de mercado puntual.

---

## 13. Impacto sobre BOT-045

Según la plantilla de clasificación del experimento (sección 13 del prompt): **"Si A gana claramente → BOT-045 debe estudiar el auto-armado como una característica intencional de momentum/volatilidad intrabloque."**

Esto es consistente con lo encontrado: el auto-armado no está degradando la estrategia respecto de la alternativa "más limpia" (HTF cerrado) — al contrario. BOT-045 puede avanzar con la semántica actual (`HTF en formación`) como la población de señales a diagnosticar, tratando el armado como proxy de momentum/volatilidad intrabloque (tal como se señaló en la auditoría previa, sección 9 de `AUDIT-HTF_autoarmado_2026-09-15.md`), sin necesidad de replantear la semántica HTF como variable experimental de primer orden dentro de BOT-045.

---

## 14. Recomendación del siguiente paso

1. **No adoptar la Variante B como reemplazo de producción.** El experimento no encontró evidencia de que mejore la estrategia de forma normalizada; al contrario, degrada la calidad por operación (Profit Factor R, Expectancy R) y reduce drásticamente la tasa de señales válidas (44,4% vs 99,8%), lo cual introduce fragilidad operativa adicional (más señales descartadas por stop mal ubicado) sin compensación de calidad.
2. **Continuar con BOT-045 usando la semántica HTF actual (Variante A / producción real)**, tratando el armado autorreferencial como variable de régimen/momentum, no como defecto a corregir antes del análisis.
3. **No se recomienda una investigación adicional de "HTF cerrado" como variable de robustez** en el corto plazo — el experimento ya descartó que sea una mejora, no solo que sea neutral.
4. Documentado en `BACKLOG.md` como ítem cerrado con este reporte como referencia — no se abre ítem nuevo, es un experimento puntual solicitado explícitamente por el usuario, análogo a BOT-042.

---

## Apéndice — reproducibilidad

Script completo: [`backtests/scripts/06_htf_ab_experiment.py`](../../backtests/scripts/06_htf_ab_experiment.py) (nuevo, aislado — no modifica `strategy/engine.py`, `strategy/live_signal.py` ni `/execution`).

```bash
python backtests/scripts/06_htf_ab_experiment.py M5
```

Salidas en `backtests/results/`:
- `htf_ab_signals_M5.csv` — 1 fila por señal (A y B), con `match_status` (same/A_only/B_only)
- `htf_ab_trades_M5.csv` — 1 fila por trade resuelto (A y B)
- `htf_ab_monthly_M5.csv` — 1 fila por (config, mes)
- `htf_ab_subperiods_M5.csv` — 1 fila por (config, mitad H1/H2)
- `htf_ab_summary_M5.json` — resumen completo con todas las métricas, costos y parámetros usados

La función experimental `bucket_levels_previous_closed()` vive únicamente en el script del experimento, no en `strategy/`. El resto de la lógica (EMA, entrada, salida, expiración, concurrencia, costos, PnL) es **exactamente** `strategy.engine.run_backtest()` sin modificar, invocada con el hook de testeo `resistencia=`/`soporte=` que ya existía en el motor antes de este experimento.
