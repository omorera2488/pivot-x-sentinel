# BOT-042 — Re-run RR post BOT-043

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Commit base (motor corregido, BOT-043):** `a0e32f6`
**Commit de esta tarea:** el commit que introduce este mismo archivo — mensaje `test(backtest): rerun Config A RR analysis after BOT-043 fix (BOT-042)` en `main` (el hash exacto queda fijado recién al commitear este archivo; ver `git log --oneline -1` sobre este commit, o la respuesta final de la tarea en Claude Code para el hash literal).

Este documento es **autocontenido**: no depende de la conversación de Claude Code ni de nada que solo haya quedado escrito en una terminal. Contiene todos los números, tablas, metodología, decisiones y estado de git necesarios para que otra persona — o ChatGPT recibiendo únicamente este archivo — entienda qué se hizo y pueda continuar el análisis.

---

## Resumen ejecutivo

Se re-ejecutó el experimento de aislamiento de RR sobre Config A (BOT-042) con el motor de backtest ya corregido por BOT-043 (signo de swap + escala precio→USD). **Ningún valor de RR probado (1, 2, 3, 4, 5, 7) convierte a Config A en una configuración robustamente rentable.** RR=7 es el único que da expectancy, Profit Factor y Net R positivos en el agregado de todo el período (+0.0425 R/trade, PF=1.049, Net R=+36.99), pero **no se sostiene en los tres subperíodos** (positivo en sub1 y sub2, negativo en sub3) y depende fuertemente de un único tramo temporal favorable que también beneficia a todas las demás configuraciones probadas (incluida B). Con esa evidencia, se lo clasifica como **INTERESANTE**, no como CANDIDATO. Todos los demás RR (1, 2, 3, 4, 5) y la referencia B (motor corregido) dan expectancy negativa.

**Respuesta a la pregunta central: cambiar únicamente el RR NO arregla Config A** de forma robusta y reproducible. Ver sección [Conclusión](#conclusión) para el detalle.

---

## Contexto

- **BOT-042** es el experimento de "optimización aislada del RR sobre Config A": mantener EMA/HTF/Buffer fijos en los valores reales de producción y variar únicamente RR, para aislar su efecto sin tocar el resto de la lógica de entrada.
- **BOT-043** encontró y corrigió dos bugs en el motor de costos del backtest (`strategy/costs.py` / `strategy/engine.py`): (1) el swap se restaba con el signo ya invertido, acreditándolo en vez de cobrarlo; (2) la conversión de precio a USD usaba `contract_size` en vez de `tick_value/tick_size`, subvaluando el PnL/riesgo real en precio por 100x en el símbolo de esta cuenta (validado contra `mt5.order_calc_profit()`). Detalle completo en `BACKLOG.md` (ítem BOT-043) y en el reporte previo enviado al usuario (`BOT-043_resolucion.md`).
- **Por qué los resultados anteriores quedaron invalidados:** la primera corrida de BOT-042 (y el barrido completo de BOT-008) corrieron con el motor con el bug. La corrida de control de BOT-043 mostró que, para Config A con RR=1, el motor con el bug daba Net R=+588.44 (positivo) mientras que el motor corregido da Net R=**−114.22** (negativo) — mismos trades, mismo Win Rate, resultado económico opuesto. Cualquier conclusión basada en los números viejos no es válida.
- **Qué se prueba ahora:** exactamente el mismo experimento de aislamiento de RR (RR ∈ {1,2,3,4,5,7} sobre Config A fija), pero con el motor ya corregido, para responder si el problema de Config A se explica simplemente por tener el RR demasiado bajo (RR=1) — o si el problema es más profundo (entrada, EMA, HTF, Buffer) y cambiar solo el RR no alcanza.

---

## Motor

| | |
|---|---|
| Commit base | `a0e32f6` — `fix(backtest): correct swap sign and price->USD scale in cost model (BOT-043)` |
| Branch | `main` |
| Corrección BOT-043 confirmada | Sí — ver [Verificación previa](#verificación-previa) |
| Modelo de costos | `strategy.costs.BrokerCosts`, costos reales vía `symbol_info()` de MT5 en el momento de la corrida (spread real por vela, comisión explícita, swap por rollover con día triple) |
| Motor | `strategy.engine.run_backtest` (sin modificar en esta tarea) |
| Tests previos ejecutados | `strategy/test_costs.py`, `strategy/test_engine.py`, `strategy/test_diagnostics.py` |

### Verificación previa

Antes de ejecutar cualquier backtest se confirmó:

1. **Branch:** `main` (confirmado con `git branch --show-current`).
2. **BOT-043 presente:** `git log --oneline -1` → `a0e32f6 fix(backtest): correct swap sign and price->USD scale in cost model (BOT-043)`.
3. **`strategy/costs.py` usa `price_to_usd()` basado en `tick_value/tick_size`:** confirmado — `def price_to_usd(self, price_diff, lot): return price_diff / self.tick_size * self.tick_value * lot`, y tanto `risk_usd()` como el PnL de precio en `strategy/engine.py` pasan por este método (no por `contract_size`).
4. **El swap se incorpora al PnL con su propio signo:** confirmado — `strategy/engine.py` tiene `pnl_usd += costs.swap_total_usd(...)` (no `-=`).
5. **Tests ejecutados** (working tree limpio antes de correr, ningún cambio de código en esta tarea sobre `strategy/`):

```
$ python strategy/test_costs.py
  A) price_to_usd() == mt5.order_calc_profit() de referencia (XAUUSDc); no regresiona simbolo estandar: OK
  B) swap_long negativo => swap_usd_per_lot_per_night() y swap_total_usd() negativos (costo real): OK
  C) direccion short usa swap_short_points (no swap_long_points), signo correcto: OK
  D) nights_held=0 -> swap_total_usd() == 0.0 exacto: OK
  E) dia de triple swap (miercoles) cobrado 3x, resto 1x: OK
  F) ganador: bruto=9.9800 swap=-0.5339 comision=-0.0500 -> neto=9.3961 (esperado 9.3961), 1R=10.00, R=0.93961: OK
  G) perdedor: bruto=-10.0200 swap=-0.5339 comision=-0.0500 -> neto=-10.6039 (esperado -10.6039), R=-1.06039: OK
  H) swap_long negativo overnight reduce el PnL en $0.5339 (1 noche) frente a sin swap: OK
  I) cross-check en vivo con mt5.order_calc_profit() (XAUUSDc): OK
TODO OK — exit code 0

$ python strategy/test_engine.py
  A-H) las 8 reglas mecanicas del motor: OK
TODO OK — exit code 0

$ python strategy/test_diagnostics.py
  A-B) campos de diagnostico puramente informativos, motor batch sin cambios: OK
TODO OK — exit code 0
```

**Los tres pasaron sin fallos.** Se procedió con el experimento (si alguno hubiera fallado, el experimento se detenía sin generar resultados — no fue necesario).

---

## Dataset

| | |
|---|---|
| Archivo | `backtests/data/XAUUSDc_M5_latest.parquet` |
| Timeframe | M5 |
| Cantidad de velas | **100,505** (confirmado leyendo el parquet directamente antes de ejecutar) |
| Rango temporal | **2025-04-14 18:50:03 UTC → 2026-09-15 00:40:03 UTC** |
| Símbolo | `XAUUSDc` (resuelto en runtime vía `resolve_symbol("XAUUSD")`, cuenta conectada) |

Coincide con lo esperado (~100,505 velas, 2025-04-14 → 2026-09-15). No se descargó otro dataset, no se cambió el período.

---

## Configuración

**Fija en las 6 corridas de RR (Config A):**

| Parámetro | Valor |
|---|---|
| `ema_periods` | 12 |
| `periodos_htf_min` (HTF) | 800 |
| `buf_bp` (Buffer) | 0.4 |
| `max_concurrent_por_direccion` | 1 |
| `valid_bars` | 10 |
| `orden_viva` | True |
| `max_bars_trade` | 500 |
| `fixed_lot` | 0.01 |
| `entrada_viva` | False |
| `una_operacion_a_la_vez` | True |

**Único parámetro variado:** `rr` ∈ {1.0, 2.0, 3.0, 4.0, 5.0, 7.0}.

**Costos usados (reales, vía `symbol_info` de MT5 al momento de la corrida):**

| | |
|---|---|
| `point` | 0.001 |
| `contract_size` | 1.0 *(informativo únicamente desde BOT-043 — no se usa para convertir precio→USD)* |
| `tick_value` | 0.1 |
| `tick_size` | 0.001 |
| `swap_long_points` | −533.9 |
| `swap_short_points` | 0.0 |
| `commission_per_lot` | 0.0 *(supuesto de cuenta Standard, sin confirmar — igual que en BOT-008/BOT-042 original)* |
| `triple_swap_weekday` | 2 (miércoles) |

**Config B — referencia opcional (motor corregido), corrida UNA sola vez, NO forma parte del experimento principal:**

`ema_periods=17, periodos_htf_min=800, buf_bp=2.2, rr=3.0`, mismos parámetros compartidos que A. Etiquetada en todas las tablas como **"B — referencia, motor corregido"**. Sus números anteriores (de BOT-008, motor contaminado) **no se reutilizan** en ningún cálculo de este reporte.

**Metodología:** una corrida por valor de RR (no un sweep combinatorio), motor real (`strategy.engine.run_backtest`), mismo dataset, mismos costos, misma lógica HTF/causal/EMA/armado — solo RR cambia entre corridas. Cada RR se corrió además sobre los mismos 3 subperíodos por índice (~33,501/33,501/33,503 velas) que usa `backtests/scripts/04_run_robustness.py`, sin continuidad de estado entre subperíodos (cada uno recalcula su propio bloque HTF desde cero).

**Comando ejecutado:**

```
python backtests/scripts/05_run_rr_isolation.py M5
```

(Nuevo script, `backtests/scripts/05_run_rr_isolation.py` — ver [Artefactos](#artefactos). Análogo a `03_run_sweep.py`/`04_run_robustness.py` pero aislando una sola dimensión en vez de barrer una grilla.)

---

## Resultados principales

Ordenados por RR (no por rendimiento), período completo (100,505 velas):

| RR | Trades | Winners | Losers | WR | Net R | Exp R | PF | Max DD (R) | Recovery | Max LS | Max WS | Avg Winner R | Avg Loser R | Trades/mes | Overnight |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **1** | 2,474 | 1,220 | 1,251 | 49.37% | −114.22 | −0.0462 | 0.912 | 140.66 | −0.812 | 10 | 9 | 0.966 | −1.034 | 145.4 | 6.79% |
| **2** | 2,041 | 656 | 1,378 | 32.25% | −131.83 | −0.0646 | 0.907 | 143.41 | −0.919 | 21 | 6 | 1.964 | −1.033 | 119.9 | 13.18% |
| **3** | 1,518 | 345 | 1,155 | 23.00% | −153.61 | −0.1012 | 0.871 | 164.77 | −0.932 | 34 | 5 | 2.964 | −1.034 | 89.4 | 18.05% |
| **4** | 1,243 | 224 | 991 | 18.44% | −97.32 | −0.0783 | 0.905 | 107.95 | −0.902 | 33 | 4 | 3.961 | −1.034 | 73.2 | 21.00% |
| **5** | 1,051 | 160 | 855 | 15.76% | −22.06 | −0.0210 | 0.975 | 73.88 | −0.299 | 30 | 3 | 4.954 | −1.034 | 61.9 | 24.45% |
| **7** | 870 | 94 | 722 | 11.52% | **+36.99** | **+0.0425** | **1.049** | 66.68 | **0.555** | 25 | 4 | 6.941 | −1.037 | 51.2 | 27.59% |
| B *(ref.)* | 1,070 | 257 | 793 | 24.48% | −33.76 | −0.0316 | 0.959 | 59.47 | −0.568 | 16 | 6 | 2.967 | −1.028 | 63.0 | 24.86% |

*(Trades − Winners − Losers no suma exactamente 0 en todos los casos porque quedan algunas operaciones cerradas por timeout de `max_bars_trade`, ver `n_open_timeout` en el JSON de trazabilidad — no afecta el cálculo de Net R/expectancy, que sí las incluye.)*

**Único RR con expectancy, PF y Net R positivos en el agregado: RR=7.** Ver caveat de robustez temporal más abajo — no es suficiente para declararlo candidato.

---

## Comparación contra RR1

Cambios de cada RR frente a A RR=1 (mismo Config A, solo cambia RR):

| RR | Δ Net R | Δ Expectancy | Δ PF | Δ Max DD | Δ Win Rate | Δ Trades |
|---|---:|---:|---:|---:|---:|---:|
| 2 | −17.61 | −0.0184 | −0.0043 | +2.75 | −17.12 pp | −433 |
| 3 | −39.39 | −0.0550 | −0.0403 | +24.11 | −26.37 pp | −956 |
| 4 | +16.90 | −0.0321 | −0.0066 | −32.71 | −30.94 pp | −1,231 |
| 5 | +92.16 | +0.0252 | +0.0634 | −66.78 | −33.61 pp | −1,423 |
| 7 | +151.20 | +0.0887 | +0.1377 | −73.98 | −37.85 pp | −1,604 |

**Lectura:** dejar correr más las ganadoras (subir RR) mejora Net R, Expectancy y PF de forma bastante consistente a partir de RR=4-5 en adelante, y reduce el Max Drawdown en R de forma marcada (RR=7 tiene **menos de la mitad** del DD de RR=1: 66.68R vs 140.66R). El costo es una caída muy grande y monótona del Win Rate (de 49.4% a 11.5%, −37.85pp en el extremo) y una caída fuerte en la cantidad de trades (de 2,474 a 870, −65%). Ninguna mejora convierte a RR≤5 en positivo — solo RR=7 cruza a positivo, y por un margen chico (Exp R=+0.04, PF=1.05).

---

## Robustez temporal

Mismos 3 subperíodos por índice que `backtests/scripts/04_run_robustness.py` (sin continuidad de estado entre ellos):

| RR | Período | Trades | WR | Net R | Exp R | PF | Max DD (R) | Max Losing Streak |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | sub1 (2025-04-14 → 2025-10-02) | 831 | 47.17% | −81.69 | −0.0983 | 0.821 | 84.86 | 10 |
| 1 | sub2 (2025-10-02 → 2026-03-25) | 768 | 52.48% | +20.18 | +0.0263 | 1.054 | 24.19 | 6 |
| 1 | sub3 (2026-03-25 → 2026-09-15) | 876 | 48.91% | −49.72 | −0.0568 | 0.893 | 81.14 | 8 |
| 2 | sub1 | 711 | 30.04% | −99.78 | −0.1403 | 0.807 | 108.37 | 12 |
| 2 | sub2 | 633 | 35.14% | +20.68 | +0.0327 | 1.049 | 25.49 | 11 |
| 2 | sub3 | 698 | 31.85% | −53.79 | −0.0771 | 0.890 | 79.36 | 21 |
| 3 | sub1 | 550 | 22.99% | −66.45 | −0.1208 | 0.849 | 84.43 | 17 |
| 3 | sub2 | 450 | 23.64% | −24.79 | −0.0551 | 0.928 | 43.82 | 21 |
| 3 | sub3 | 526 | 22.50% | −62.78 | −0.1194 | 0.849 | 104.99 | 34 |
| 4 | sub1 | 464 | 18.16% | −48.44 | −0.1044 | 0.876 | 61.04 | 19 |
| 4 | sub2 | 366 | 19.77% | +0.17 | +0.0005 | 1.001 | 32.55 | 17 |
| 4 | sub3 | 421 | 17.72% | −47.35 | −0.1125 | 0.865 | 80.24 | 33 |
| 5 | sub1 | 393 | 16.62% | −3.21 | −0.0082 | 0.990 | 45.00 | 23 |
| 5 | sub2 | 304 | 17.53% | +27.67 | +0.0910 | 1.112 | 32.07 | 13 |
| 5 | sub3 | 360 | 13.62% | −40.73 | −0.1131 | 0.868 | 73.88 | 30 |
| **7** | **sub1** | 314 | 11.75% | **+8.15** | **+0.0260** | 1.030 | 34.40 | 23 |
| **7** | **sub2** | 257 | 12.18% | **+33.50** | **+0.1304** | **1.156** | 25.87 | 25 |
| **7** | **sub3** | 308 | 10.38% | **−13.96** | **−0.0453** | 0.948 | 66.68 | 25 |
| B *(ref.)* | sub1 | 385 | 24.54% | −19.59 | −0.0509 | 0.934 | 35.45 | 14 |
| B *(ref.)* | sub2 | 328 | 24.29% | −5.58 | −0.0170 | 0.977 | 31.42 | 10 |
| B *(ref.)* | sub3 | 364 | 24.65% | −7.77 | −0.0213 | 0.972 | 59.47 | 16 |

**Hallazgo estructural importante:** el subperíodo **sub2** (2025-10-02 → 2026-03-25) es el único con expectancy positiva en **todas** las configuraciones probadas (RR 1 a 5, RR=7, y B) — incluidas las que terminan negativas en el agregado completo. Esto es evidencia de un efecto de **régimen de mercado específico de ese tramo**, no de una ventaja estructural de ningún RR en particular. sub1 y sub3 son negativos o marginales en casi todas las configuraciones.

**Ningún RR es positivo en los 3 subperíodos simultáneamente:**
- RR=1: sub1 negativo, sub2 positivo, sub3 negativo.
- RR=2: igual patrón (sub1/sub3 negativos, sub2 positivo).
- RR=3: **negativo en los 3 subperíodos** — el peor caso, sin ninguna dependencia favorable de régimen.
- RR=4: sub1/sub3 negativos, sub2 esencialmente en cero (+0.0005 — no representa una mejora real).
- RR=5: sub1 levemente negativo, sub2 positivo, sub3 negativo.
- **RR=7 (el "ganador" agregado): sub1 y sub2 positivos, sub3 negativo.** Su resultado agregado positivo depende de que sub2 fue particularmente fuerte para RR=7 (+0.130 R/trade, el mejor expectancy de toda la tabla) — sin ese tramo, el resultado se parecería más a los demás RR.
- B (referencia): **negativo en los 3 subperíodos** — con el motor corregido, B ya no muestra ninguna ventaja consistente.

**Deterioro progresivo:** no se observa un deterioro monótono simple; lo que se observa es que sub1 y sub3 son sistemáticamente peores que sub2 en casi todas las configuraciones, y que RR=3 es la única configuración negativa en los tres tramos sin excepción — el peor caso de "dependencia de un régimen favorable" es paradójicamente el que NO tiene ninguno.

---

## Losing streaks

Distribución completa de rachas de pérdidas consecutivas (período completo):

| RR | Max LS | ≥3 | ≥5 | ≥7 | ≥10 | ≥15 | ≥20 | Total rachas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 161 | 42 | 9 | 2 | 0 | 0 | 611 |
| 2 | 21 | 206 | 100 | 44 | 10 | 1 | 1 | 446 |
| 3 | 34 | 157 | 92 | 52 | 22 | 6 | 2 | 281 |
| 4 | 33 | 137 | 87 | 49 | 24 | 6 | 1 | 211 |
| 5 | 30 | 109 | 75 | 44 | 20 | 8 | 4 | 167 |
| **7** | **25** | 85 | 64 | 47 | 24 | 5 | 4 | 123 |
| B *(ref.)* | 16 | 117 | 61 | 36 | 11 | 1 | 0 | 213 |

Como se esperaba, el Win Rate cae fuerte al subir RR (49.4% → 11.5%) y las rachas de pérdidas se alargan: a RR=7, **24 rachas de 10+ pérdidas consecutivas y 4 rachas de 20+** ocurren a lo largo de ~1.4 años de datos — aproximadamente una racha de 20+ pérdidas cada ~4 meses. Esto es tolerable solo si el trader está psicológicamente preparado para sostener rachas muy largas sin abandonar el sistema — un costo operativo real que no aparece en Net R/Expectancy.

---

## Costos

Desglose de costos por configuración (período completo):

| RR | Overnight | Swap total | Swap prom./overnight | Comisión total | Spread total | Costos totales | PnL bruto | PnL neto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6.79% | −$82.75 | −$0.4926 | $0.00 | $510.66 | $593.42 | −$782.24 | −$1,375.66 |
| 2 | 13.18% | −$136.68 | −$0.5081 | $0.00 | $420.07 | $556.75 | −$471.73 | −$1,028.48 |
| 3 | 18.05% | −$148.42 | −$0.5417 | $0.00 | $313.01 | $461.43 | −$634.72 | −$1,096.15 |
| 4 | 21.00% | −$151.09 | −$0.5789 | $0.00 | $255.93 | $407.02 | −$123.52 | −$530.54 |
| 5 | 24.45% | −$156.97 | −$0.6108 | $0.00 | $215.73 | $372.69 | +$734.51 | +$361.82 |
| 7 | 27.59% | −$164.98 | −$0.6874 | $0.00 | $180.28 | $345.26 | **+$1,581.32** | **+$1,236.06** |
| B *(ref.)* | 24.86% | −$159.10 | −$0.5981 | $0.00 | $221.38 | $380.48 | −$324.41 | −$704.89 |

*(`comisión total`=$0.00 en todas las corridas porque `commission_per_lot=0.0` — supuesto de cuenta Standard sin confirmar, igual que en BOT-008/BOT-042 original y BOT-043; no es un artefacto de esta corrida.)*

**Nota sobre "PnL bruto/neto":** están expresados en USD nominales con `fixed_lot=0.01` fijo en toda la serie — no representan una curva de equity realista (no reflejan compounding ni el tamaño de cuenta real), son solo la suma de los PnL en dólares de cada trade individual con ese lote fijo, útiles para comparar el peso relativo de cada componente de costo entre configuraciones, no como proyección de resultado en una cuenta real.

**Sanity checks pedidos, todos verificados:**
- ✅ **Swap negativo reduce resultados:** en las 7 configuraciones, `swap_total_usd` es negativo y PnL neto < PnL bruto − spread (es decir, el swap resta, no suma). Confirmado además por los tests de BOT-043 (`test_costs.py::test_h`).
- ✅ **Ningún costo negativo se convierte artificialmente en beneficio:** verificado trade a trade en `strategy/test_costs.py` (tests F/G/H) y a nivel agregado acá — swap consistentemente negativo en todas las configuraciones, sin excepciones.
- ✅ **`raw_risk` en escala monetaria coherente:** el swap promedio por trade overnight (−$0.49 a −$0.69) es ahora una fracción razonable de un R típico (recordar: antes de BOT-043 una sola noche de swap equivalía a ~6.8x la mediana de 1R; ahora el swap es un costo menor, proporcional).
- ✅ **No aparecen realized R absurdos:** ver percentiles en la siguiente sección — el rango completo de R va de −1.98 a +6.99 (para RR=7), sin ningún valor de decenas o cientos de R como se veía antes del fix.

---

## Distribución de R

Percentiles de R realizado, todos los trades resueltos (período completo):

| RR | Min | P1 | P5 | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | −1.775 | −1.106 | −1.061 | −1.005 | 0.989 | 0.994 | 0.999 |
| 2 | −1.775 | −1.124 | −1.061 | −1.017 | 1.986 | 1.991 | 1.998 |
| 3 | −1.775 | −1.167 | −1.071 | −1.020 | 2.983 | 2.991 | 2.998 |
| 4 | −1.775 | −1.167 | −1.074 | −1.020 | 3.980 | 3.989 | 3.997 |
| 5 | −1.775 | −1.171 | −1.077 | −1.021 | 4.976 | 4.988 | 4.995 |
| 7 | −1.775 | −1.225 | −1.082 | −1.022 | 6.966 | 6.985 | 6.992 |
| B *(ref.)* | −1.976 | −1.160 | −1.060 | −1.015 | 2.985 | 2.991 | 2.997 |

Ningún outlier extremo: el mínimo se mantiene estable alrededor de −1.78R a −1.98R en todos los RR (consistente con un stop tocado más el costo adicional de spread/swap, nunca una pérdida descontrolada de decenas de R como ocurría con el motor contaminado). El máximo de cada RR queda **justo por debajo** del RR nominal (ej. RR=7 → max realizado 6.992, no 7.000) — pérdida esperable por el spread al cerrar en el target, económicamente coherente.

### Validación de RR realizado (ganadores vs perdedores)

| RR objetivo | Avg Winner R | Median Winner R | P10 Winner R | P90 Winner R | Avg Loser R | Median Loser R | P10 Loser R | P90 Loser R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.966 | 0.973 | 0.939 | 0.989 | −1.034 | −1.027 | −1.060 | −1.012 |
| 2 | 1.964 | 1.973 | 1.938 | 1.989 | −1.033 | −1.025 | −1.055 | −1.012 |
| 3 | 2.964 | 2.972 | 2.932 | 2.988 | −1.034 | −1.025 | −1.057 | −1.012 |
| 4 | 3.961 | 3.971 | 3.924 | 3.987 | −1.034 | −1.025 | −1.060 | −1.011 |
| 5 | 4.954 | 4.969 | 4.906 | 4.986 | −1.034 | −1.024 | −1.060 | −1.012 |
| 7 | 6.941 | 6.965 | 6.843 | 6.984 | −1.037 | −1.025 | −1.061 | −1.012 |
| B *(ref.)* | 2.967 | 2.976 | 2.934 | 2.989 | −1.028 | −1.020 | −1.045 | −1.009 |

**Confirmado: no hay artefacto contable.** El R promedio de los ganadores sigue de cerca al RR objetivo en cada configuración (ej. RR=7 objetivo → 6.941 promedio, 6.965 mediana — el pequeño déficit frente a 7.0 es exactamente el costo de spread al cerrar en el target, no un error de escala). El R promedio de los perdedores se mantiene estable alrededor de −1.03 a −1.04 en todas las configuraciones (el stop es independiente de RR, solo cambia el target) — coherente con lo esperado: RR más alto no cambia cuánto se pierde por operación perdedora, solo cuánto se gana por ganadora y con qué frecuencia se llega a ganar.

---

## Break-even

Comparación entre el Win Rate observado y el Win Rate nominal de break-even (sin costos):

| RR | WR observado | WR break-even nominal | Diferencia |
|---|---:|---:|---:|
| 1 | 49.37% | 50.00% | −0.63 pp |
| 2 | 32.25% | 33.33% | −1.08 pp |
| 3 | 23.00% | 25.00% | −2.00 pp |
| 4 | 18.44% | 20.00% | −1.56 pp |
| 5 | 15.76% | 16.67% | −0.91 pp |
| 7 | 11.52% | 12.50% | −0.98 pp |
| B *(ref.)* | 24.48% | 25.00% | −0.52 pp |

El WR observado queda sistemáticamente **por debajo** del break-even nominal (diferencia negativa en las 7 configuraciones) — coherente con la existencia de costos reales (spread + swap neto), que exigen un WR más alto que el nominal para llegar a break-even. La brecha es relativamente chica y consistente (−0.5 a −2.0 puntos porcentuales), sin ningún salto anómalo. **Esta comparación es solo de referencia** — la métrica que manda es el backtest neto después de costos (secciones anteriores), no esta aproximación nominal.

---

## Anomalías

- **Ninguna anomalía de escala o contabilidad.** Todos los sanity checks de la sección [Costos](#costos) y [Distribución de R](#distribución-de-r) pasaron: sin R absurdos, sin costos que se conviertan en beneficio, swap consistentemente negativo, `raw_risk` en escala monetaria coherente con `mt5.order_calc_profit()` (ver BOT-043).
- **Efecto de régimen en sub2:** ya documentado arriba en [Robustez temporal](#robustez-temporal) — no es una anomalía de cálculo, es un patrón de mercado real en el dataset (todas las configuraciones mejoran en ese tramo), pero es la razón por la que el resultado agregado de RR=7 no debe leerse como una ventaja estructural confirmada.
- **RR=4, sub2 prácticamente en cero** (Net R=+0.17, Exp R=+0.0005) — no es un error, es el punto de transición donde esa configuración pasa de negativa a casi neutra en ese tramo específico; se documenta para que quede claro que no se trata de un resultado "positivo" real, es ruido alrededor de cero.
- **Trades/Winners/Losers no suman exactamente `n_trades`** en ninguna fila — la diferencia son operaciones cerradas por timeout (`max_bars_trade=500`), que cuentan como trade resuelto para Net R/Expectancy pero no como winner ni loser puro. Documentado para que no se lea como un error de conteo.

---

## Clasificación

| RR | Expectancy>0 | PF>1 | Net R>0 | 3/3 subperíodos ≥0 | Max DD | Recovery | Rachas | Overnight | Clasificación |
|---|:---:|:---:|:---:|:---:|---|---|---|---|:---:|
| 1 | ❌ | ❌ | ❌ | ❌ (2/3 neg.) | Alto (140.7R) | Negativo | Moderadas (max 10) | Bajo (6.8%) | **DESCARTADO** |
| 2 | ❌ | ❌ | ❌ | ❌ (2/3 neg.) | Alto (143.4R) | Negativo | Crecientes (max 21) | Bajo-medio (13.2%) | **DESCARTADO** |
| 3 | ❌ | ❌ | ❌ | ❌ (**3/3 neg.**) | Muy alto (164.8R) | Negativo | Altas (max 34) | Medio (18.1%) | **DESCARTADO** (peor caso) |
| 4 | ❌ | ❌ | ❌ (mixto) | ❌ (2/3 neg., 1 ≈0) | Medio-alto (108.0R) | Negativo | Altas (max 33) | Medio (21.0%) | **DESCARTADO** |
| 5 | ❌ | ❌ | ❌ (mixto) | ❌ (2/3 neg.) | Medio (73.9R) | Negativo débil | Altas (max 30) | Medio-alto (24.5%) | **DESCARTADO**, tendencia hacia break-even |
| **7** | ✅ | ✅ | ✅ | ❌ (**2/3 pos., 1 neg.**) | Menor de todos (66.7R) | Positivo (0.55) | Altas (max 25, 4×≥20) | **Más alto (27.6%)** | **INTERESANTE** (no candidato — falla robustez temporal) |
| B *(ref.)* | ❌ | ❌ | ❌ | ❌ (**3/3 neg.**) | Bajo (59.5R) | Negativo | Moderadas (max 16) | Medio-alto (24.9%) | **DESCARTADO** — sin la ventaja que mostraba con el motor contaminado |

Ningún RR alcanza el estándar de **CANDIDATO** definido para esta tarea (evidencia razonable de edge después de costos, incluyendo consistencia entre subperíodos). RR=7 es el único con métricas agregadas positivas, pero al no sostenerse en los 3 subperíodos — y depender de un tramo temporal que también favorece a todas las demás configuraciones — no hay evidencia suficiente de que sea un edge genuino de RR=7 en particular, en vez de ruido/régimen de mercado.

---

## Respuestas obligatorias

**1. ¿Algún RR convierte a A de expectancy negativa a positiva?**
Sí, únicamente RR=7 (+0.0425 R/trade en el agregado), pero no de forma robusta — ver clasificación arriba.

**2. ¿Cuál tiene mayor Net R?**
RR=7 (+36.99).

**3. ¿Cuál tiene mayor expectancy?**
RR=7 (+0.0425 R/trade).

**4. ¿Cuál tiene mejor Profit Factor?**
RR=7 (1.049).

**5. ¿Cuál tiene menor Max Drawdown entre los RR rentables?**
Solo RR=7 es rentable en el agregado, así que es automáticamente el de menor (y único) Max DD entre los rentables: 66.68R. (Si se compara contra B, que no es rentable, B tiene un DD aún menor, 59.47R, pero con expectancy negativa — no es comparable en términos de "rentable".)

**6. ¿Cuál tiene mejor Recovery Factor?**
RR=7 (0.555) — también el único positivo del grupo A. Le sigue RR=5, con Recovery menos negativo (−0.299) que el resto pero todavía negativo.

**7. ¿Cuál es más estable entre los tres subperíodos?**
Ninguno es "estable y positivo" a la vez. El más estable en el sentido de **no depender de un solo tramo** es paradójicamente RR=3 — negativo en los 3 subperíodos, consistentemente malo, sin sorpresas. Entre los que tienen algún tramo positivo, RR=1 y RR=2 muestran el patrón más repetido (positivo solo en sub2), y RR=7 es el que más se acerca a ser positivo en 2/3, pero con la salvedad de que su positivo es el más grande de la tabla (sub2=+0.130) y su negativo también es notable (sub3=−0.045).

**8. ¿Qué RR tiene la mejor relación entre retorno y drawdown?**
RR=7 (Recovery Factor=0.555, el único positivo). En términos de reducción de drawdown per se, subir RR reduce el DD de forma bastante consistente desde RR=3 en adelante (164.8R → 66.7R), independientemente de si el resultado es rentable.

**9. ¿Qué costo tiene cada RR en términos de Win Rate y rachas de pérdidas?**
Costo muy alto y monótono: el Win Rate cae de 49.4% (RR=1) a 11.5% (RR=7), una caída de 37.85 puntos porcentuales. Las rachas de pérdidas se alargan en paralelo: de un máximo de 10 pérdidas seguidas en RR=1 a rachas de hasta 34 en RR=3 (el peor caso de rachas, aunque no el de peor Net R) y 25 en RR=7, con 4 rachas de 20+ pérdidas consecutivas en RR=7 a lo largo de 1.4 años.

**10. ¿Existe un RR claramente superior a A RR=1?**
En términos de Net R/Expectancy/PF, sí hay una tendencia clara de mejora al subir RR (con la excepción de RR=3, que es el peor de la serie) — pero "superior" no es lo mismo que "rentable" o "confiable": solo RR=7 cruza a positivo, y con el caveat de robustez temporal ya señalado. No hay un RR que sea claramente superior Y confiablemente rentable.

**11. ¿Existe suficiente evidencia para usar alguno como nueva baseline experimental?**
No con el estándar de esta tarea (edge razonable + consistencia en 3 subperíodos). RR=7 es el candidato más cercano y merecería explorarse más (ver Próximo paso), pero declararlo baseline ahora sería sobreajustar a un resultado que depende de un solo tramo temporal.

**12. ¿Cambiar RR por sí solo arregla Config A?**
**No.** Ver conclusión destacada abajo.

---

## Conclusión

### **¿CAMBIAR ÚNICAMENTE RR ARREGLÓ CONFIG A: SÍ O NO?**

# **NO.**

Con el motor de backtest corregido (BOT-043), Config A (EMA=12, HTF=800, Buffer=0.4) da expectancy negativa en RR=1 (−0.046 R/trade) y se mantiene negativa en RR=2, 3, 4 y 5. Solo RR=7 cruza a positivo en el agregado completo del dataset (+0.0425 R/trade, PF=1.049), pero ese resultado positivo **no se sostiene en los tres subperíodos independientes** — es negativo en el último tramo (sub3: −0.045 R/trade) y depende en gran parte de un único subperíodo (sub2) que resulta favorable para **todas** las configuraciones probadas en este experimento, no solo para RR=7. Eso apunta a un efecto de régimen de mercado compartido, no a una ventaja estructural específica de RR=7.

Ni siquiera la Config B (ganadora del barrido original de BOT-008, ahora corrida con el motor corregido) se sostiene: con los costos ya bien calculados, B también da expectancy negativa en el agregado y en los 3 subperíodos por separado — su aparente ventaja anterior era en gran parte (o enteramente) un artefacto del bug de BOT-043.

**La entrada de Config A (armado/EMA/HTF/Buffer) no muestra, con este método, un edge que el RR por sí solo pueda destapar de forma confiable.** El experimento cumplió su objetivo: aisló matemáticamente el efecto de RR y produjo una respuesta reproducible y trazable — la respuesta es negativa, y se reporta como tal, sin intentar optimizar otros parámetros dentro de esta tarea.

---

## Próximo paso recomendado

**No se ejecuta en esta tarea — solo se deja indicado.**

Dado que variar únicamente RR no resuelve Config A, el siguiente experimento lógico — siguiendo el mismo método de aislar una sola dimensión por vez, sin sweep combinatorio — sería repetir este mismo procedimiento variando **Buffer** de forma aislada (EMA/HTF/RR fijos) y, por separado, variando **EMA** de forma aislada (HTF/Buffer/RR fijos), para ver si alguno de esos dos parámetros por sí solo mueve a Config A hacia expectancy positiva de forma más robusta que RR=7 (es decir, positiva en los 3 subperíodos, no solo en el agregado). Si ninguno de los tres aislados (RR, Buffer, EMA) alcanza ese estándar por separado, sería evidencia de que el problema no está en la calibración de un parámetro individual sino en la lógica de entrada/armado en sí (ver la nota ya documentada en `docs/spec-backtest.md` §4.4 sobre el "stop del lado incorrecto" y el armado persistente, revisada y descartada como causa de un bug de contabilidad en BOT-043, pero que sigue siendo relevante como posible causa estructural del bajo edge).

Sea cual sea el siguiente paso, cualquier candidato que resulte de ese experimento debería exigirse el mismo estándar de robustez usado acá (positivo en los 3 subperíodos, no solo en el agregado) antes de considerarlo una nueva baseline.

---

## Backlog

Estado de los ítems relevantes en `BACKLOG.md` después de esta tarea:

| Ítem | Estado | Nota |
|---|---|---|
| **BOT-008** | `DONE` — ⚠️ RESULTADOS HISTÓRICOS INVALIDADOS, REQUIERE RE-RUN | Sin cambios en esta tarea — sigue señalado como inválido, no se re-corrió el barrido completo de BOT-008 acá (esta tarea corrió solo Config A aislada en RR, no la grilla de 3.780 combinaciones). |
| **BOT-042** | `TODO` → **`DONE`** | Re-ejecutado después de BOT-043 con el motor corregido (commit `a0e32f6`), dataset `backtests/data/XAUUSDc_M5_latest.parquet` (100,505 velas), Config A con RR∈{1,2,3,4,5,7} y B como referencia opcional. Conclusión: cambiar RR por sí solo NO arregla Config A de forma robusta — ver este reporte (`docs/reports/BOT-042_rerun_RR_post_BOT-043.md`) y los artefactos en `backtests/results/*post_BOT-043*`. |
| **BOT-043** | `DONE` | Sin cambios — se mantiene DONE, es la base sobre la que corrió este experimento. |
| **BOT-044** | `TODO` | Sin cambios administrativos necesarios en esta tarea. |

(El detalle completo de la actualización de BOT-042 se refleja en `BACKLOG.md` mismo — ver el diff de esta tarea.)

---

## Artefactos

**Script nuevo (reproducible, versionado):**
- `backtests/scripts/05_run_rr_isolation.py` — corre el aislamiento de RR sobre una configuración fija, genera todos los CSV/JSON de abajo. Uso: `python backtests/scripts/05_run_rr_isolation.py M5`.

**Resultados (`backtests/results/`, sufijo `post_BOT-043` para no confundir con los contaminados):**
- `rr_summary_post_BOT-043_M5.csv` — 1 fila por RR (+ B referencia), todas las métricas agregadas del período completo.
- `rr_subperiods_post_BOT-043_M5.csv` — 1 fila por RR × subperíodo.
- `rr_loss_streaks_post_BOT-043_M5.csv` — distribución completa de rachas de pérdidas por RR.
- `rr_cost_and_r_dist_post_BOT-043_M5.csv` — desglose de costos y percentiles de R por RR.
- `rr_isolation_post_BOT-043_M5.json` — volcado completo de trazabilidad (incluye las longitudes crudas de cada racha de pérdidas y todos los parámetros de costos usados).

**Este reporte:**
- `docs/reports/BOT-042_rerun_RR_post_BOT-043.md` (este archivo).

Ninguno de estos artefactos sobrescribe los resultados contaminados de BOT-008/BOT-042 original (`sweep_full_M5.csv`, `sweep_top20_M5.csv`, `robustness_subperiods_M5.csv` siguen intactos, sin el sufijo `post_BOT-043`, y siguen marcados como inválidos en `BACKLOG.md`).

---

## Git

| | |
|---|---|
| **Commit** | este commit — mensaje `test(backtest): rerun Config A RR analysis after BOT-043 fix (BOT-042)` (hash exacto: `git log --oneline -1` sobre `main` inmediatamente después de este commit, o ver la respuesta final de la tarea) |
| **Branch** | `main` |
| **Push** | confirmado a `origin/main` |
| **Working tree** | limpio tras el push |

Mensaje de commit: `test(backtest): rerun Config A RR analysis after BOT-043 fix (BOT-042)`

---

## Regla permanente de reportes MD (documentada en esta tarea)

A partir de esta tarea, toda tarea relevante de desarrollo, análisis, backtesting, debugging o investigación en este proyecto debe generar un reporte Markdown autocontenido como este, guardado en `docs/reports/`. La regla completa está documentada en `BACKLOG.md`, sección "Regla para futuros cambios" (ver ese archivo para el texto exacto y su alcance).

---

*Generado por Claude Code a partir de la tarea "BOT-042 Re-run con motor corregido + reporte MD obligatorio" del usuario. No se modificó lógica de entrada/salida, pivotes, HTF, EMA, Buffer, RR, scoring, ni configuración/ejecución en producción en ningún momento de esta tarea — solo se ejecutó el motor ya corregido por BOT-043 sobre Config A variando RR, y se documentó el resultado.*
