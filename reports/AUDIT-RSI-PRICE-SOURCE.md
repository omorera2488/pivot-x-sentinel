# Auditoría BOT-024 — Fuente de precio en Divergencia RSI: `close` vs `low`/`high`

**Alcance:** auditoría READ-ONLY sobre producción. No se modificó
`strategy/scoring.py`, `strategy/live_signal.py`, `strategy/engine.py`,
`execution/`, la API ni el panel. La comparación A/B vive únicamente en
[`scripts/audit_rsi_price_source.py`](../scripts/audit_rsi_price_source.py)
(nuevo). No se implementó `low/high` en producción — este documento es
insumo para una decisión futura, no un cambio.

Log completo y reproducible:
[`reports/RSI-PRICE-SOURCE-EVIDENCE.log`](RSI-PRICE-SOURCE-EVIDENCE.log)
(generado con `.venv/Scripts/python.exe scripts/audit_rsi_price_source.py`,
0 fallas).

---

## 1. Implementación actual

Confirmado por inspección directa (y por el script, sección 1 del log, que
vuelca el código fuente real):

- `strategy/scoring.py:_bullish_candidate()` (línea 190-206) compara
  `close[latest_low.bar] < close[prior_low.bar]` (línea 198).
- `strategy/scoring.py:_bearish_candidate()` (línea 209-225) compara
  `close[latest_high.bar] > close[prior_high.bar]` (línea 217).
- Ninguna de las dos funciones referencia `low[...]` ni `high[...]` — solo
  `close[...]`, verificado por grep del cuerpo real de ambas funciones.
- Los pivotes (`latest_low`/`prior_low`/`latest_high`/`prior_high`) siguen
  siendo pivotes del **RSI** (`find_confirmed_pivots(rsi_values, ...)`,
  línea 193/212) — el precio solo se lee en el `bar` del pivote ya
  encontrado, nunca decide dónde está el pivote.
- Flujo real a producción: `execution/src/bot.py:_score_entry()` →
  `scoring.score_entry()` → `divergence_detail()` (línea 273) →
  `_bullish_candidate(close, ...)` / `_bearish_candidate(close, ...)` — el
  mismo array `close` para ambos lados. Sin cambios respecto al fix de
  `reports/AUDIT-RSI-DIVERGENCE.md`.

## 2. Definición A/B evaluada

| | Variante A (actual) | Variante B (extremos de vela) |
|---|---|---|
| Bullish — precio | `close[latest] < close[prior]` | `low[latest] < low[prior]` |
| Bullish — RSI | `RSI[latest] > RSI[prior]` (sin cambios) | igual |
| Bearish — precio | `close[latest] > close[prior]` | `high[latest] > high[prior]` |
| Bearish — RSI | `RSI[latest] < RSI[prior]` (sin cambios) | igual |
| Pivotes | RSI 5/5, sin cambios | igual |
| `confirmation_bar` | `pivot_bar + lbR`, sin cambios | igual |
| Separación / vigencia | sin cambios | igual |
| Resolución simultáneas | `resolve_divergence()` real de producción, sin cambios | igual (misma función, sin modificar) |

Implementación de la comparación (`scripts/audit_rsi_price_source.py`):
reusa de `strategy/scoring.py`, **sin tocarlo**, `rsi()`,
`find_confirmed_pivots()`, `_most_recent_fresh()`, `_prior_in_range()`,
`resolve_divergence()`, `DivergenceCandidate` y todas las constantes
(`RSI_PERIOD`, `DIVERGENCE_LB_LEFT/RIGHT`, `DIVERGENCE_RANGE_MIN/MAX`,
`DIVERGENCE_FRESH_BARS`). Solo se reimplementó localmente una versión
genérica de `_bullish_candidate()`/`_bearish_candidate()` parametrizada por
qué array de precio leer — es la única pieza de lógica duplicada, y es
deliberadamente mínima (misma estructura línea por línea).

**Verificación de que la réplica es fiel:** antes de confiar en la
comparación, el script prueba que su Variante A (genérica, con
`price_bullish=price_bearish=close`) produce resultados **idénticos** a
`divergence_detail()` real de producción en 1134 combinaciones (barras
31–4000 cada 7, ambas direcciones): **0 discrepancias** (log, sección 2).
También valida que la versión "rápida" (índice con `bisect`, necesaria para
poder recorrer 100k+ barras sin costo O(n²)) coincide exactamente con la
versión "lenta" (idéntica a producción) en 5938 combinaciones para ambas
variantes: **0 discrepancias** (log, sección 3).

## 3. Pruebas sintéticas (casos 1–8)

Todos ejecutados y verificados por el script (log, sección 4):

| Caso | Descripción | A | B | Resultado |
|---|---|---|---|---|
| 1 | close y low hacen LL, RSI hace HL | BULLISH | BULLISH | ✅ ambas detectan |
| 2 | close **no** hace LL (sube), low **sí** hace LL | NONE | BULLISH | ✅ solo B detecta |
| 3 | close hace LL, low **no** (mecha previa más profunda) | BULLISH | NONE | ✅ solo A detecta — geométricamente posible con OHLC válido (`low≤close≤high` respetado en ambas barras) |
| 4 | close y high hacen HH, RSI hace LH | BEARISH | BEARISH | ✅ ambas detectan |
| 5 | close **no** hace HH (baja), high **sí** hace HH | NONE | BEARISH | ✅ solo B detecta |
| 6 | close hace HH, high **no** (mecha previa más alta) | BEARISH | NONE | ✅ solo A detecta — geométricamente posible con OHLC válido |
| 7 | causalidad: pivot_bar=100, lbR=5 | NONE en 100–104, BULLISH desde 105 (ambas variantes) | | ✅ ninguna variante adelanta información |
| 8a | ambas vigentes, mismos candidatos en A y B, bearish más reciente | BEARISH/MOST_RECENT | BEARISH/MOST_RECENT | ✅ resolución idéntica |
| 8b | la fuente de precio cambia qué candidatos existen (bullish solo activo en B) | BEARISH (solo bearish activo) | BULLISH/MOST_RECENT (bullish y bearish activos, bullish más reciente) | ✅ la mecánica de resolución (`resolve_divergence`) es la misma función sin cambios; el resultado final difiere porque **el conjunto de candidatos de entrada** difiere |

Los casos 3 y 6 (el "inverso" pedido por la tarea) son **geométricamente
posibles**: basta con que la mecha (low/high) del pivote **previo** sea más
extrema que la del pivote **reciente**, mientras el cierre se mueve al
revés. Ejemplo case 3 exacto (log): `close[60]=100.0, close[100]=95.0` (LL)
vs `low[60]=90.0, low[100]=92.0` (no LL) — válido porque
`low[60]=90≤close[60]=100≤high[60]=105` y `low[100]=92≤close[100]=95≤high[100]=100`.

## 4. Causalidad (caso 7)

```text
pivot_bar=100, lbR=5, confirmation_bar=105

t=100  A=NONE      B=NONE
t=101  A=NONE      B=NONE
t=102  A=NONE      B=NONE
t=103  A=NONE      B=NONE
t=104  A=NONE      B=NONE
t=105  A=BULLISH   B=BULLISH   <- confirmado, ambas variantes
t=106  A=BULLISH   B=BULLISH
```

Cambiar la fuente de precio **no** cambia cuándo la divergencia se vuelve
conocida — la causalidad depende exclusivamente de los pivotes del RSI
(`find_confirmed_pivots`, sin cambios entre variantes). Verificado también
sobre el índice rápido usado para el dataset completo (sección 3 del log).

## 5. Estadísticas sobre el dataset histórico real

Dataset reusado, **no se descargó ni inventó nada nuevo**:
[`backtests/data/XAUUSDc_M5_latest.parquet`](../backtests/data/XAUUSDc_M5_latest.parquet)
— 100 505 barras M5 de XAUUSDc, 2025-04-14 a 2026-09-15 (el mismo dataset
que usan `backtests/scripts/03_run_sweep.py` y demás scripts de backtest).
A y B se corrieron **causalmente** bar por bar (100 474 barras evaluadas,
tras descartar el warmup de RSI+pivotes) usando el índice rápido validado
en la sección 3 del log contra el cálculo lento idéntico a producción.

| Estado | A | B |
|---|---:|---:|
| NONE | 85 784 | 86 079 |
| BULLISH | 6 572 | 6 433 |
| BEARISH | 8 118 | 7 962 |
| CONFLICT | 0 | 0 |

```text
coinciden bullish (A=B=BULLISH): 5696
coinciden bearish (A=B=BEARISH): 7121
solo A bullish (A=BULLISH, B!=BULLISH): 876
solo B bullish (B=BULLISH, A!=BULLISH): 737
solo A bearish (A=BEARISH, B!=BEARISH): 997
solo B bearish (B=BEARISH, A!=BEARISH): 841
NONE en ambas: 84244
CONFLICT en A: 0   CONFLICT en B: 0

porcentaje total de barras con estado DIFERENTE A vs B: 3413/100474 = 3.397%
```

**CONFLICT nunca ocurrió en ~100k barras reales, en ninguna variante.**
Consistente con el hallazgo geométrico de
`reports/AUDIT-RSI-DIVERGENCE.md` (separación mínima real de pivotes): con
`lbL=lbR=5` fijo para ambos tipos, `CONFLICT` requiere que el pivote bajo
más reciente y el pivote alto más reciente caigan en el **mismo bar**
(mismo `confirmation_bar = bar+lbR`), lo cual exige que esa barra sea
simultáneamente el mínimo Y el máximo estricto de su ventana de RSI —
imposible salvo degeneración total. Esto es así en ambas variantes (A y B),
porque `CONFLICT` depende únicamente de los pivotes del RSI, no del precio.

## 6. Matriz de transición A → B

```text
A -> B          NONE   BULLISH   BEARISH  CONFLICT
NONE           84244       706       834         0
BULLISH          869      5696         7         0
BEARISH          966        31      7121         0
CONFLICT           0         0         0         0
```

Lectura: de las 100 474 barras, en 84 244 ambas variantes coinciden en
`NONE`; en 5696+7121=12 817 coinciden en tener una divergencia activa del
mismo tipo. El resto (3413 barras, 3.397%) difiere: la mayoría son
transiciones `NONE↔BULLISH/BEARISH` (706+834+869+966=3375), y solo **38
barras** (0.038% del total) cambian de un tipo activo a **otro tipo activo
distinto** (p. ej. `A=BULLISH, B=BEARISH`) — el caso más "disruptivo" de
discrepancia es, en la práctica, extremadamente raro.

## 7. Ejemplos de discrepancias

Catálogos completos generados por el script (log, sección 6); se incluyen
aquí los primeros de cada categoría con contexto completo.

### NONE(A) → BULLISH(B) — 706 encontrados (se pidieron ≥5)

```text
current_bar=1774  bullish_pivot_bar=1769  confirmation_bar=1774  prior_pivot_bar=1747
  latest_rsi=37.317  prior_rsi=30.247
  latest_close=3323.391  prior_close=3323.301   (close NO hace LL: 3323.391 > 3323.301)
  latest_low=3322.223    prior_low=3322.606     (low SI hace LL: 3322.223 < 3322.606)
  -> A=NONE, B=BULLISH
```

### NONE(A) → BEARISH(B) — 834 encontrados (se pidieron ≥5)

```text
current_bar=667  bearish_pivot_bar=662  confirmation_bar=667  prior_pivot_bar=649
  latest_rsi=54.046  prior_rsi=58.852
  latest_close=3342.068  prior_close=3344.570   (close NO hace HH: 3342.068 < 3344.570)
  latest_high=3345.470   prior_high=3344.570    (high SI hace HH: 3345.470 > 3344.570)
  -> A=NONE, B=BEARISH
```

### A detecta y B no (cualquier tipo) — 1835 encontrados (se pidieron ≥5)

```text
current_bar=249  bearish_pivot_bar=244  confirmation_bar=249  prior_pivot_bar=236
  latest_rsi=55.363  prior_rsi=55.448
  latest_close=3222.956  prior_close=3222.865   (close SI hace HH: 3222.956 > 3222.865)
  latest_high=3223.359   prior_high=3223.417    (high NO hace HH: 3223.359 < 3223.417)
  -> A=BEARISH, B=NONE
```

### Cambia la resolución entre BULLISH/BEARISH/CONFLICT — 38 encontrados (se pidieron "cualquiera")

```text
current_bar=34521  estado_A=BULLISH (resolution=NONE)  estado_B=BEARISH (resolution=MOST_RECENT)
current_bar=50240  estado_A=BEARISH (resolution=NONE)  estado_B=BULLISH (resolution=NONE)
```

En el primer ejemplo, A solo tiene un candidato activo (bullish, por eso
`resolution=NONE`, no hubo nada que resolver), mientras que B tiene
**ambos** candidatos activos y el bearish resulta más reciente
(`resolution=MOST_RECENT`) — la mecánica de resolución no cambió, cambió el
conjunto de candidatos que llegó a ella. Ningún caso de `CONFLICT`
apareció en esta categoría (consistente con la sección 5: CONFLICT no
ocurrió en absoluto en el dataset).

**Nota de definiciones:** "solo A bullish"/"solo B bullish" (sección 5) se
definen como *A=BULLISH y B≠BULLISH* (puede que B sea BEARISH, no
necesariamente NONE). "A detecta y B no" (esta sección) exige que B sea
estrictamente `NONE`. Son catálogos con criterios ligeramente distintos,
ambos pedidos explícitamente por la tarea; los números no son directamente
comparables entre sí por esa razón (876+997=1873 "solo A" vs. 1835 "A
detecta y B es NONE").

## 8. Propiedad de subconjunto

**Pregunta:** ¿toda divergencia detectada con `close` existe también con
`low`/`high`?

**Respuesta: NO, en ninguna dirección.** Demostrado por tres vías
independientes:

1. **Razonamiento OHLC:** por definición `low[i] ≤ close[i] ≤ high[i]` para
   toda barra `i`, pero eso no impone ninguna relación de orden entre
   `close[latest] < close[prior]` y `low[latest] < low[prior]` — son
   comparaciones de **arrays distintos** en los mismos índices. Un cierre
   más bajo puede coexistir con un mínimo intrabar más alto (mecha inferior
   del pivote previo más profunda que la del pivote reciente) y viceversa.
2. **Casos sintéticos:** Caso 3 y Caso 6 (sección 3 de este reporte)
   construyen explícitamente, con OHLC válido, una divergencia que A
   detecta y B no. Caso 2 y Caso 5 construyen el inverso: B detecta y A no.
   Ambas direcciones están refutadas por construcción.
3. **Dataset real:** 1873 barras "solo A" y 1578 barras "solo B" sobre
   100 474 evaluadas — ambos conjuntos no vacíos, confirmando en datos
   reales lo que el razonamiento y los casos sintéticos ya probaban.

**Conclusión de esta sección:** `low`/`high` **no** es simplemente una
versión "más sensible" de `close` que añade señales sin quitar ninguna —
es un conjunto **materialmente distinto**: pierde ~1873 divergencias que
`close` sí detecta y gana ~1578 que `close` no detecta (cifras "solo
A"/"solo B" de la sección 5; ver nota de definiciones arriba sobre por qué
estos números difieren ligeramente de "A detecta y B es NONE").

## 9. Evidencia de TradingView

Se buscó en todo el repositorio (`basecode_tradingview/*.txt`, el Pine
Script real que usa el proyecto, ver
`pivot-x-sentinel-tv-reference-mismatch` en memoria del proyecto) cualquier
mención a `rsi`, `divergence`, `pivothigh` o `pivotlow` como palabra
completa.

**Resultado: NO existe en el repositorio ningún Pine Script ni
especificación del indicador "Divergence" de RSI.** Los dos únicos
archivos Pine del repo (`1m EMA y Pivotes ZS — trade boxes.txt`, `5m EMA y
Pivotes ZS — trade boxes.txt`) son el indicador de tendencia/cajas de
trade (EMA + pivotes de precio para armado de operaciones) — **no** el
indicador de divergencia de RSI. Una búsqueda ingenua por substring
inicialmente dio un falso positivo (`//@version=6` contiene la subcadena
"rsi" dentro de "ve**rsi**on") — corregido con coincidencia de palabra
completa antes de concluir.

**Por lo tanto: la fuente de precio real que usa el indicador "Divergence"
de TradingView que corre (o corrió) el usuario queda `UNVERIFIED`.** No se
afirma que TradingView use `close` ni que use `low`/`high` — ninguna de las
dos cosas está respaldada por evidencia de este repositorio. El propio
docstring de `strategy/scoring.py` (líneas 49-52) ya señalaba esto desde
antes de esta auditoría: los parámetros de divergencia son "defaults
públicos" del indicador genérico, no los parámetros reales configurados en
el chart del usuario.

## 10. Tests ejecutados

| Suite | Resultado |
|---|---|
| `strategy/test_scoring.py` | **PASS** |
| `scripts/audit_rsi_divergence.py` | **PASS** (0 fallas, 6 advertencias — sin cambios respecto a la corrida previa) |
| `scripts/audit_rsi_price_source.py` | **PASS** (0 fallas) |
| `strategy/test_engine.py` | **PASS** |
| `strategy/test_costs.py` | **PASS** |
| `strategy/test_htf_session.py` | **PASS** |
| `strategy/test_diagnostics.py` | **PASS** |

`git diff --stat HEAD -- strategy/ execution/ api/ panel/` no muestra
ninguna diferencia — producción quedó intacta.

---

# HECHOS

1. La implementación actual (`strategy/scoring.py:_bullish_candidate()`/
   `_bearish_candidate()`) usa `close[pivot_bar]` para ambos lados
   (bullish y bearish). Verificado por inspección directa del código
   fuente real.
2. Existe al menos un caso sintético, geométricamente válido bajo OHLC
   (`low≤close≤high`), donde A detecta una divergencia y B no (Casos 3 y
   6), y al menos un caso donde B detecta y A no (Casos 2 y 5). Ninguna
   variante es subconjunto de la otra — demostrado por construcción.
3. Sobre 100 474 barras reales de XAUUSDc M5 (2025-04-14 a 2026-09-15), A y
   B difieren en el 3.397% de las barras (3413/100474). De esas, 3375
   barras son transiciones `NONE↔BULLISH/BEARISH` y 38 barras cambian
   entre `BULLISH`/`BEARISH` activos (ninguna involucra `CONFLICT`, que no
   ocurrió ni una sola vez en ninguna variante).
4. En el dataset real, A detecta 876 bullish y 997 bearish que B no
   detecta con ese mismo tipo; B detecta 737 bullish y 841 bearish que A
   no detecta con ese mismo tipo.
5. Cambiar la fuente de precio no altera la causalidad: en el caso de
   prueba (`pivot_bar=100`, `lbR=5`), ninguna variante conoce la
   divergencia antes de `confirmation_bar=105`, y ambas la conocen
   exactamente en esa barra.
6. La mecánica de resolución de divergencias simultáneas
   (`resolve_divergence()`, fix de `reports/AUDIT-RSI-DIVERGENCE.md`) es
   **la misma función, sin ninguna modificación**, para ambas variantes —
   la fuente de precio solo determina qué candidatos existen antes de
   llegar a esa función, nunca cómo se resuelven.
7. No existe en el repositorio ningún Pine Script ni especificación del
   indicador "Divergence" de RSI real del usuario. La fidelidad de
   `close` o de `low`/`high` respecto a ese indicador queda `UNVERIFIED`.

# INTERPRETACIÓN

- El 3.4% de discrepancia total puede sonar bajo, pero corresponde a
  **miles** de barras sobre un dataset de 17 meses (3413 barras ≈ varias
  semanas de señales potencialmente distintas), y el patrón dominante es
  "una variante ve algo donde la otra no ve nada" (transiciones
  `NONE↔activo`), no un desacuerdo sistemático sobre la dirección. Los
  casos donde directamente cambia BULLISH↔BEARISH entre variantes son
  raros (38 de 100 474, 0.038%).
- Técnicamente, `low`/`high` **no es una versión más sensible o más
  permisiva** de `close` (no es "close + señales extra") — es un criterio
  **estructuralmente distinto**: en algunos casos es más sensible (detecta
  donde close no detecta) y en otros casos es más estricto (deja pasar por
  alto algo que close sí marcaba). Esto se debe a que ambos comparan
  precios en los **mismos bares de pivote del RSI**, pero leen columnas
  OHLC distintas cuya relación de orden entre sí no está garantizada por
  la restricción `low≤close≤high`.
- Que `CONFLICT` nunca haya ocurrido en ~100k barras reales, en ninguna
  variante, es consistente con el hallazgo geométrico ya documentado en
  `reports/AUDIT-RSI-DIVERGENCE.md`: con `lbL=lbR=5` compartido entre
  ambos tipos de pivote, `CONFLICT` exige que la misma barra sea
  simultáneamente máximo y mínimo estricto del RSI en su ventana, algo que
  la propia definición de pivote hace casi imposible. Esto no cambia entre
  variantes porque `CONFLICT` depende solo de los pivotes de RSI, nunca
  del precio.

# DECISIÓN PENDIENTE

**No se cambió producción en esta auditoría.**

> **¿`low/high` es simplemente una versión más sensible de `close`, o
> ambas definiciones producen conjuntos materialmente diferentes de
> divergencias?**

Producen conjuntos **materialmente diferentes** — no hay relación de
subconjunto en ninguna dirección (sección 8), y el dataset real muestra
miles de barras "solo A" y miles "solo B" en proporciones comparables
(1873 vs. 1578). No es "más señales" en una dirección; es un criterio
distinto que gana algunas señales y pierde otras.

> **¿Tenemos evidencia suficiente para elegir una definición ahora, antes
> de evaluar capacidad predictiva?**

**No.** Esta auditoría midió *cuánto cambia la detección*, no *cuál
detección es mejor*. Sabemos con precisión:
- que las dos definiciones no son intercambiables (3.4% de barras
  difieren, y las que difieren no son un subconjunto trivial una de la
  otra);
- que la elección no afecta causalidad, vigencia, separación ni la
  mecánica de resolución de simultáneas;
- que no hay evidencia en el repositorio sobre qué usa el indicador real
  de TradingView del usuario (queda `UNVERIFIED`).

Lo que **no** sabemos, y esta auditoría deliberadamente no midió, es cuál
de las dos definiciones produce una señal de Divergencia RSI más útil
como componente de Momentum/Signal Quality — eso requiere la evaluación
predictiva que el usuario indicó explícitamente que viene **después** de
definir correctamente qué significa Divergencia RSI. No se fuerza una
recomendación entre `close` y `low`/`high` en este documento.

---

## Archivos de esta auditoría

- [`scripts/audit_rsi_price_source.py`](../scripts/audit_rsi_price_source.py) — script de auditoría (nuevo, read-only).
- [`reports/RSI-PRICE-SOURCE-EVIDENCE.log`](RSI-PRICE-SOURCE-EVIDENCE.log) — log reproducible completo.
- Este documento.

Ningún archivo de producción fue modificado (`git diff --stat HEAD --
strategy/ execution/ api/ panel/` vacío).
