# Auditoría técnica — Divergencia RSI actual

**Alcance original (2026-09-19):** auditoría de solo lectura de la implementación
de Divergencia RSI (`strategy/scoring.py`). No se modificó ningún archivo de
producción, ni parámetros, ni scoring, ni comportamiento del bot. Este documento
conserva el hallazgo original tal como se encontró — ver **sección H** para el
fix aplicado después, bajo BOT-024.

Toda la evidencia de este reporte (antes y después del fix) es reproducible
ejecutando:

```bash
.venv/Scripts/python.exe scripts/audit_rsi_divergence.py
```

Log completo de la corrida más reciente (0 fallas, 6 advertencias, incluye la
verificación del fix de la sección H):
`reports/RSI-DIVERGENCE-EVIDENCE.log`.

---

## A. Implementación encontrada

Toda la lógica de Divergencia RSI vive en **un único archivo**,
[`strategy/scoring.py`](../strategy/scoring.py) — no hay una segunda implementación
paralela ni en `execution/` ni en `backtests/`:

| Pieza | Función/clase | Líneas |
|---|---|---|
| RSI de Wilder | `rsi()`, `_rsi_from_avgs()` | scoring.py:68-96 |
| Pivotes RSI 5/5 | `Pivot` (dataclass), `find_confirmed_pivots()` | scoring.py:99-127 |
| Selección de pivote vigente | `_most_recent_fresh()` | scoring.py:130-133 |
| Selección de pivote previo en rango | `_prior_in_range()` | scoring.py:136-138 |
| Signo según dirección | `_signed()` | scoring.py:141-144 |
| Score de divergencia | `divergence_score()` | scoring.py:147-173 |
| Orquestador (4 factores) | `score_entry()` | scoring.py:381-413 |

**Flujo de datos real (único camino a producción):**

```
execution/src/bot.py: process_closed_bar()  (bar recién cerrada)
  -> _score_entry()                          [bot.py:552-591]
       -> mt5.copy_rates_range(...)          -- SCORE_LOOKBACK_BARS velas hasta raw_bar_time (la barra que acaba de cerrar)
       -> scoring.score_entry(...)           [bot.py:579, scoring.py:381]
            -> rsi_values = rsi(close)                       [scoring.py:390]
            -> current_bar = len(close) - 1                  [scoring.py:391]  (== la barra de la señal)
            -> divergence_score(direction, close, rsi_values, current_bar)  [scoring.py:393]
  -> log + score_store.record(...) SOLO para registrar        [bot.py:670-682]
```

Puntos clave de esta arquitectura:

- **No existe** un cálculo "batch/histórico" separado del "vivo/secuencial": es
  la misma función pura (`divergence_score`) la que corre siempre, con `close`/
  `rsi_values` recortados a lo que existía hasta la barra de la señal. No hay
  drift posible entre "modo backtest" y "modo bot" porque no hay dos
  implementaciones — hay una sola, llamada con distintos datos de entrada.
- `score_entry()` (y por lo tanto `divergence_score()`) se llama **solo para
  registrar** la calificación (log + `score_store`); nunca decide si se coloca
  la orden ni el volumen (bot.py:554-558, docstring explícito). Esto está
  fuera del alcance de esta auditoría (no se tocó), pero es relevante: un bug
  en Divergencia RSI hoy **no** puede hacer que el bot opere distinto — sólo
  ensuciaría el log/registro.
- No hay estado persistido entre llamadas: cada barra vuelve a buscar pivotes
  desde cero sobre el historial que le llega (ver hallazgo en sección F).

---

## B. Parámetros reales

| Parámetro | Esperado | Implementado | Match |
|---|---:|---:|---|
| RSI período | 14 | `RSI_PERIOD = 14` (scoring.py:41) | ✅ |
| RSI fuente | close | `rsi(close)` — único parámetro de precio (scoring.py:68, bot.py:582) | ✅ |
| Pivot left (lbL) | 5 | `DIVERGENCE_LB_LEFT = 5` (scoring.py:47) | ✅ |
| Pivot right (lbR) | 5 | `DIVERGENCE_LB_RIGHT = 5` (scoring.py:48) | ✅ |
| Min separación | 5 | `DIVERGENCE_RANGE_MIN = 5` (scoring.py:49) — **nominal 5, geométricamente inalcanzable por debajo de 6 con lbL=lbR=5** (ver sección F, hallazgo #3) | ⚠️ PARCIAL |
| Max separación | 60 | `DIVERGENCE_RANGE_MAX = 60` (scoring.py:50) | ✅ |
| Vigencia | 10 | `DIVERGENCE_FRESH_BARS = 10` (scoring.py:51) — **11 barras activas en la práctica** (edad 0..10 inclusive), ver hallazgo #4 | ⚠️ PARCIAL |

Nada de esto se cambió. Las dos filas "PARCIAL" son diferencias entre la
especificación documentada en texto y el comportamiento matemático real de esa
misma fórmula — no son errores de tipeo en las constantes.

---

## C. Resultado de auditoría

| Área | Resultado |
|---|---|
| RSI Wilder | **PASS** (+ 1 WARNING: caso degenerado de precio plano) |
| Pivotes | **PASS** (+ 1 WARNING: manejo de empates) |
| Causalidad | **PASS** |
| Precio asociado | **PASS** (+ 1 WARNING: `close` vs `low`/`high`) |
| Separación | **PASS** (fórmula correcta) (+ 1 WARNING: rango mínimo inalcanzable) |
| Vigencia | **PASS** (+ 1 WARNING: ambigüedad de nomenclatura 10 vs 11 barras) |
| LONG/SHORT | **PASS** |
| Divergencias simultáneas | ~~**WARNING** (prioridad fija no documentada, bajista se descarta en silencio)~~ → **RESOLVED** (BOT-024, ver sección H): resolución explícita por `confirmation_bar` más reciente + estado `CONFLICT` |
| Batch/live parity | **PASS** (738/738 comparaciones idénticas) |
| LIMIT-time parity | **PASS** |

**No se encontró ningún CRITICAL.** No hay look-ahead, no hay uso de barras
futuras, no hay índices negativos ni corrimientos incorrectos: la
implementación es causal y matemáticamente consistente con la fórmula de
Wilder. Los hallazgos son de **diseño/especificación** (qué tan fiel es al
indicador de referencia, qué prioridad usar ante señales simultáneas, cómo se
documenta la vigencia), no de corrección aritmética.

---

## D. Timeline causal (ejemplo real, evidencia reproducible)

Pivote RSI bajo en `pivot_bar=100` (lbR=5) → `confirmation_bar=105`. Con un
pivote previo en `bar=60` (RSI más bajo, precio más alto) que arma una
divergencia alcista regular cuando ambos están confirmados. `fresh_bars=10` →
`expiration_bar` en 116.

| Barra | ¿Pivote(100) conocido? | `divergence_score(+1, ...)` | Estado |
|---:|---|---|---|
| 100 | No | `0, 'sin divergencia vigente'` | NO CONOCIDA |
| 101 | No | `0, 'sin divergencia vigente'` | NO CONOCIDA |
| 102 | No | `0, 'sin divergencia vigente'` | NO CONOCIDA |
| 103 | No | `0, 'sin divergencia vigente'` | NO CONOCIDA |
| 104 | No | `0, 'sin divergencia vigente'` | NO CONOCIDA |
| **105** | **Sí (recién confirmado)** | `+1, 'divergencia alcista RSI vigente -- a favor de la entrada'` | **DETECTION** |
| 106…115 | Sí | `+1, ...` (idéntico) | ACTIVA (edad 1..10) |
| 116 | Sí, pero expirado | `0, 'sin divergencia vigente'` | EXPIRADA |

Esto confirma, con ejecución real del código (no sólo lectura), que:

- un LIMIT creado en las barras 101–104 **no** puede usar la divergencia cuyo
  segundo pivote está en la barra 100 (exactamente el escenario que pedía la
  sección 14 del pedido de auditoría);
- la divergencia se activa recién en la barra 105 y permanece activa 11 barras
  (105 a 115 inclusive), no 10;
- el texto (`reason`) es idéntico en todas las barras activas — el código no
  distingue "recién detectada" de "vigente hace rato" (sección F, hallazgo
  #5).

Evidencia completa (incluye el caso simétrico con `find_confirmed_pivots`
directamente): `reports/RSI-DIVERGENCE-EVIDENCE.log`, sección "5. Auditoria
critica de causalidad".

---

## E. Evidencia

Script de auditoría: [`scripts/audit_rsi_divergence.py`](../scripts/audit_rsi_divergence.py)
(nuevo, solo lectura, no toca producción). Log completo:
[`reports/RSI-DIVERGENCE-EVIDENCE.log`](RSI-DIVERGENCE-EVIDENCE.log).

Resumen de lo ejecutado (58 checks PASS + 6 WARN, 0 FAIL — incluye las
verificaciones agregadas en el fix BOT-024, sección H):

1. **RSI Wilder** — verificado contra una segunda implementación de Wilder
   escrita de forma independiente (acumuladores explícitos, sin reusar código
   de `scoring.py`) sobre 500 barras de ruido gaussiano: diferencia máxima
   `0.000e+00`, máscara de NaN idéntica. Además: `n<period+1` → NaN completo
   sin excepción; `n==period+1` → exactamente un valor válido en el índice
   correcto; subida monótona → RSI=100.0 exacto; bajada monótona → RSI=0.0
   exacto.
2. **Pivotes** — `bar` vs `confirmed_bar` se distinguen correctamente
   (`bar+lbR`); NaN dentro de una ventana descarta ese candidato sin excepción;
   el límite exacto del array (`n-lbR-1`) se detecta, y quitar un solo bar
   derecho lo vuelve indetectable (sin *slicing* silenciosamente truncado).
3. **Causalidad** — ver sección D. Probado con `find_confirmed_pivots` sobre
   `rsi[:t+1]` para `t=96..107` y con `divergence_score` completo para
   `t=100..116`.
4. **Asociación precio↔pivote** — se armó un caso con valores "señuelo" en
   `confirmed_bar` que producen el patrón CONTRARIO al de `pivot_bar`; el
   resultado coincidió con usar `close[pivot_bar]`, confirmando que el código
   nunca lee el precio del `confirmed_bar` (ni de `high`/`low`).
5. **Separación** — boundary test directo sobre `_prior_in_range` con objetos
   `Pivot` sintéticos: 4→rechazado, 5→aceptado, 6→aceptado, 59→aceptado,
   60→aceptado, 61→rechazado (fórmula `range_min <= dist <= range_max`
   correcta, ambos límites inclusive). Además, un experimento geométrico con
   `find_confirmed_pivots` real mostró que **ningún par de pivotes verdaderos
   puede estar a menos de 6 barras** cuando `lbL=lbR=5` (ver hallazgo #3).
6. **Vigencia** — timeline completo bar por bar de 98 a 117 con
   `_most_recent_fresh`, clasificando cada barra como NO CONOCIDA / ACTIVA /
   EXPIRADA.
7. **LONG/SHORT** — tabla 2×2 (bullish/bearish × LONG/SHORT) ejecutada
   directamente: coincide exactamente con la tabla esperada.
8. **Divergencias simultáneas** — hallazgo original (2026-09-19): se
   construyó un caso con una divergencia alcista (confirmada en 105) y una
   bajista (confirmada en 106, más reciente) ambas vigentes en
   `current_bar=106`; el resultado para `direction=-1` (SHORT) dio `-1`
   ("en contra") en vez de `+1`, porque el código nunca llegó a evaluar la
   divergencia bajista. **RESUELTO en BOT-024 (sección H): el mismo caso
   ahora resuelve `BEARISH`/`MOST_RECENT` y SHORT da `+1`** — este es
   exactamente el caso que reproduce `strategy/test_scoring.py::test_m_*`.
9. **Casos borde** — historial insuficiente para RSI, insuficiente para
   pivotes, primer pivote sin previo, precios iguales, RSI iguales, tercer
   pivote más reciente reemplazando al segundo, NaN aislado en el RSI: los 9
   casos pasan sin excepciones y con el resultado esperado.
10. **Paridad batch/secuencial** — 738 comparaciones (barras 31 a 399,
    ambas direcciones) entre calcular con el array completo (`close_full`,
    `rsi_batch` precalculado una vez) y recalcular todo desde cero sobre
    `close_full[:cur+1]` en cada paso ("secuencial", nunca ve el futuro):
    **0 discrepancias**.
11. **Paridad en tiempo de LIMIT** — replay explícito de "crear un LIMIT en
    la barra 101, 102, 103… 106" usando sólo los datos visibles hasta esa
    barra en cada caso: el score da 0 en 101-104 y +1 recién en 105-106,
    igual que en la sección D.

---

## F. Hallazgos

### 1. Prioridad fija y no documentada entre divergencia alcista y bajista simultáneas — **HIGH**

> **Estado: RESOLVED (BOT-024, 2026-09-19).** Ver sección H para el fix
> aplicado. El hallazgo original queda tal cual se documentó, sin editar,
> como registro histórico.

**Qué ocurre:** si en la misma barra hay una divergencia alcista vigente
(pivotes bajos) *y* una divergencia bajista vigente (pivotes altos) —
situación perfectamente posible porque usan conjuntos de pivotes distintos —
`divergence_score()` siempre devuelve el resultado de la alcista y **nunca
evalúa la bajista**, sin importar cuál sea más reciente.

**Por qué ocurre:** scoring.py:159-171 — el bloque `if latest_low is not
None: ... return ...` se ejecuta primero y hace `return` inmediatamente si
encuentra una divergencia alcista válida; el bloque bajista es código
inalcanzable en ese caso.

**Impacto potencial:** en el caso reproducido (bullish confirmada en 105,
bearish más reciente confirmada en 106, ambas vigentes en barra 106), una
entrada SHORT recibe `-1` ("en contra de la entrada") cuando la divergencia
bajista —la más reciente, la que técnicamente respalda ese SHORT— habría dado
`+1`. Es una diferencia de **2 puntos** en el score registrado, en el sentido
contrario al que sugeriría la señal más nueva. Como el score sólo se registra
(no bloquea la orden), no afecta qué opera el bot, pero sí ensucia
sistemáticamente el dato que se pretende usar en el futuro sistema de Signal
Quality.

**Archivo/función responsable:** `strategy/scoring.py:divergence_score()`
(líneas 159-171).

### 2. Fuente de precio (`close` en ambos lados) posiblemente distinta a la del indicador de referencia — **MEDIUM/HIGH (pendiente de confirmación)**

**Qué ocurre:** `divergence_score()` compara `close[pivot_bar]` tanto para el
lado alcista como el bajista (scoring.py:163, 170). El indicador público de
TradingView más difundido para divergencias con RSI (y varias
reimplementaciones ampliamente conocidas) usa `low` para el lado alcista y
`high` para el bajista, no `close` en los dos casos.

**Por qué ocurre:** decisión de diseño explícita, pero basada en "defaults
públicos" del indicador genérico — el propio docstring de `scoring.py`
(líneas 43-46) ya advierte que **no son los parámetros reales del indicador
del usuario**, que "todavía no los dio".

**Impacto potencial:** si el indicador real del usuario usa `low`/`high`,
algunas divergencias que el bot detecta con `close` no coincidirían
exactamente con las que se ven en el chart (y viceversa) — mismo tipo de
riesgo de paridad visual que ya se resolvió para el bloque de tendencia/HTF
(ver memoria del proyecto sobre `usarCausal=true`). **No se pudo verificar en
vivo contra TradingView desde este entorno** (sin acceso al chart real del
usuario); queda como pendiente explícito, no como bug confirmado.

**Archivo/función responsable:** `strategy/scoring.py:divergence_score()`
(líneas 163, 170).

### 3. `DIVERGENCE_RANGE_MIN=5` es geométricamente inalcanzable con `lbL=lbR=5` — **MEDIUM**

**Qué ocurre:** con los pivotes de 5/5 barras, dos pivotes reales del mismo
tipo (ambos bajos, o ambos altos) no pueden estar separados por menos de 6
barras: si estuvieran más cerca, cada uno caería dentro de la ventana
estricta del otro y uno de los dos —el de valor menos extremo— dejaría de ser
único-máximo/mínimo en esa ventana y jamás se generaría como pivote. Se
verificó experimentalmente con `find_confirmed_pivots` real: separaciones de
3, 4 y 5 barras nunca producen dos pivotes simultáneos; separaciones de 6 en
adelante sí.

**Por qué ocurre:** es una consecuencia matemática de combinar
`DIVERGENCE_LB_LEFT=DIVERGENCE_LB_RIGHT=5` con `DIVERGENCE_RANGE_MIN=5` — no
es un bug de la fórmula de `_prior_in_range` (esa fórmula, probada de forma
aislada con objetos `Pivot` sintéticos, sí respeta el límite de 5 barras
correctamente).

**Impacto potencial:** ninguno sobre el resultado actual (el filtro de
separación mínima nunca tiene la oportunidad de rechazar nada en la práctica),
pero es una discrepancia entre la especificación documentada ("5-60 barras")
y el comportamiento real posible ("6-60 barras" en la práctica). Si en el
futuro se cambian `lbL`/`lbR` sin revisar `range_min`, el comportamiento
podría cambiar de forma no evidente.

**Archivo/función responsable:** `strategy/scoring.py` constantes (líneas
47-50) + `_prior_in_range()` (líneas 136-138).

### 4. "Vigencia 10 barras" se traduce en 11 barras activas — **LOW/MEDIUM (ambigüedad de nomenclatura)**

**Qué ocurre:** la condición `current_bar - confirmed_bar <= fresh_bars(=10)`
incluye la propia barra de confirmación (edad 0) hasta edad 10 inclusive —
son 11 barras con la divergencia activa (105 a 115 en el ejemplo de la
sección D), no 10.

**Por qué ocurre:** es la definición literal de "edad ≤ 10", que
matemáticamente son 11 valores posibles de edad (0,1,...,10).

**Impacto potencial:** ninguno sobre la corrección del cálculo — es
puramente una cuestión de qué significa "vigencia de 10 barras" en la
documentación/diseño (¿10 barras totales, o 10 barras *después* de la
confirmación?). Vale la pena que quede escrito sin ambigüedad antes de usarlo
como insumo del sistema de Signal Quality.

**Archivo/función responsable:** `strategy/scoring.py:_most_recent_fresh()`
(línea 132) y constante `DIVERGENCE_FRESH_BARS` (línea 51).

### 5. Sin distinción entre "evento de detección" y "estado vigente" en los datos persistidos — **LOW**

**Qué ocurre:** `divergence_score()` es una función pura sin memoria: en cada
barra vuelve a buscar todos los pivotes confirmados y decide desde cero. El
`reason` (texto) es idéntico en todas las barras mientras la divergencia
sigue activa — no dice si es la primera barra donde aparece o la décima. El
`EntryScore` persistido en `score_store.py` tampoco guarda `pivot_bar`,
`confirmation_bar` ni la edad de la divergencia — sólo el score (+1/0/-1) y
el texto genérico.

**Por qué ocurre:** diseño intencional de "recalcular todo siempre" (evita
drift), pero no se agregó ningún campo adicional de trazabilidad al
registrar el score.

**Impacto potencial:** ninguno sobre la corrección del score en el momento en
que se calcula. Sí dificulta auditar en retrospectiva, a partir del log o de
`score_store`, exactamente qué pivotes (bar/confirmed_bar) originaron el
score de una operación ya cerrada — hay que volver a correr el cálculo con
los datos de mercado de esa fecha para reconstruirlo.

**Archivo/función responsable:** `strategy/scoring.py:EntryScore` (líneas
363-378), `execution/src/score_store.py`.

### 6. Manejo de empates en pivotes (`(window==v).sum()==1`) no verificado contra TradingView — **LOW/MEDIUM (pendiente de confirmación)**

**Qué ocurre:** si dos o más barras dentro de la ventana de un pivote
candidato tienen exactamente el mismo valor de RSI que el máximo/mínimo, el
código actual **no** genera ningún pivote (exige unicidad estricta). Se
verificó con una serie `[0,1,5,5,1,0]`: ningún pivote alto detectado pese a
que 5 es claramente el extremo de la ventana.

**Por qué ocurre:** la condición `(window == v).sum() == 1` en
`find_confirmed_pivots()` (scoring.py:123-126) exige que el valor sea único
en toda la ventana, no sólo que sea el máximo/mínimo.

**Impacto potencial:** en datos reales con RSI de punto flotante, los
empates exactos son poco frecuentes salvo en tramos de precio perfectamente
plano, pero no se puede descartar del todo. **No se pudo confirmar contra el
comportamiento real de `ta.pivothigh`/`ta.pivotlow` de Pine en este entorno**
(sin acceso al chart) si esa función acepta empates de forma asimétrica; si
los acepta, esta implementación perdería pivotes válidos en esos casos
puntuales.

**Archivo/función responsable:** `strategy/scoring.py:find_confirmed_pivots()`
(líneas 123-126).

### 7. RSI=50 en precio perfectamente plano (`avg_gain=0` y `avg_loss=0`) no verificado — **LOW**

**Qué ocurre:** cuando no hay ningún cambio de precio dentro de la ventana de
14 barras, `avg_gain=avg_loss=0`, matemáticamente `rs=0/0` indefinido. El
código devuelve 50.0 por una rama especial (`_rsi_from_avgs`, scoring.py:92-96).

**Por qué ocurre:** decisión de diseño razonable para evitar NaN, pero no
verificada bit a bit contra el comportamiento de `ta.rsi` de Pine en ese
caso degenerado específico.

**Impacto potencial:** mínimo — requiere 14+ barras consecutivas con el
precio de cierre idéntico, algo muy infrecuente en XAUUSD/FX reales.

**Archivo/función responsable:** `strategy/scoring.py:_rsi_from_avgs()`
(líneas 92-96).

---

## G. Recomendaciones (NO implementadas — solo quedan documentadas)

1. ~~**Decidir y documentar explícitamente** qué hacer cuando hay una
   divergencia alcista y una bajista vigentes simultáneamente (hallazgo #1):
   ¿prioridad por recencia (`confirmed_bar` más alto gana)?, ¿se anulan entre
   sí (0)?, ¿se mantiene la prioridad fija actual pero documentada y testeada
   como tal? Cualquiera de las tres es razonable — lo que falta es que sea
   una decisión consciente, no un efecto colateral del orden del código.~~
   **DONE (BOT-024, 2026-09-19)** — ver sección H: se implementó
   "prioridad por recencia" (`confirmation_bar` más alto gana), con
   `CONFLICT` explícito para el empate exacto.
2. **Confirmar con el usuario los parámetros reales** de su indicador
   "Divergence" en TradingView (Pivot Lookback Left/Right, Range Min/Max, y
   sobre todo qué precio usa cada lado: close/low/high) antes de asumir
   paridad visual — el propio código ya señala que esto está pendiente
   (hallazgo #2).
3. Si se confirma que el indicador real usa `low`/`high` en vez de `close`,
   evaluar el cambio en `divergence_score()` (no se tocó en esta auditoría).
4. **Revisar la relación entre `DIVERGENCE_RANGE_MIN` y `lbL`/`lbR`**
   (hallazgo #3): o se documenta explícitamente que el mínimo efectivo es
   `2*lbR` (o similar), o se ajusta `DIVERGENCE_RANGE_MIN` para que sea
   coherente con los pivotes usados.
5. **Aclarar en el docstring** si "vigencia 10 barras" significa 10 o 11
   barras activas en total (hallazgo #4), y alinear la constante/comentario
   con esa definición.
6. ~~**Agregar trazabilidad** al registrar el score (hallazgo #5): guardar
   `pivot_bar`, `confirmation_bar` y edad de la divergencia junto al score en
   `score_store`, para poder reconstruir después qué pivotes concretos
   originaron cada calificación sin tener que recorrer de nuevo los datos de
   mercado.~~ **DONE (BOT-024, 2026-09-19)** — ver sección H. Sigue sin
   haber una fila persistida de "evento de nacimiento" (se recalcula en
   cada barra), eso queda deliberadamente igual.
7. **Verificar en vivo contra TradingView** (cuando haya oportunidad de
   comparar el chart real) los dos casos marcados como pendientes: manejo de
   empates en pivotes (hallazgo #6) y el valor de RSI en tramos de precio
   perfectamente plano (hallazgo #7).

---

## H. Fix aplicado — BOT-024 (2026-09-19)

**Hallazgo original:** bullish tenía prioridad accidental sobre bearish
cuando ambas divergencias estaban vigentes a la vez, por simple orden del
código (`if bullish: return ...` se evaluaba antes que el bloque bearish).

**Fix:** resolución explícita por `confirmation_bar`. Bullish y bearish se
detectan de forma completamente independiente (`_bullish_candidate()`,
`_bearish_candidate()`); después, `resolve_divergence()` decide cuál manda
usando **exclusivamente** `confirmation_bar` (nunca `pivot_bar`, nunca la
dirección del trade):

- 0 candidatos vigentes → `NONE`, score 0.
- 1 candidato vigente → gana ese (`BULLISH` o `BEARISH`).
- 2 candidatos vigentes, `confirmation_bar` distinto → gana el más reciente
  (`MOST_RECENT`).
- 2 candidatos vigentes, `confirmation_bar` **igual** → `CONFLICT`, score 0
  (distinto de `NONE`: hay información válida de ambos lados, pero ninguno
  se favorece).

La dirección (LONG/SHORT) se aplica **después** de resolver el estado, nunca
antes — la tabla LONG/SHORT (`BULLISH+LONG=+1`, `BULLISH+SHORT=-1`,
`BEARISH+LONG=-1`, `BEARISH+SHORT=+1`, `NONE`/`CONFLICT`=0) no cambió.

`divergence_score()` se mantuvo como wrapper compatible — misma firma
posicional, mismo contrato `(score, reason)` — para no romper
`strategy/test_scoring.py` ni `scripts/audit_rsi_divergence.py`, que lo
llaman posicionalmente. El detalle completo (candidatos + resolución) vive
en la nueva `divergence_detail()`, usada por `score_entry()` para volcar
trazabilidad a `EntryScore`: `divergencia_resolved_state`,
`divergencia_resolution`, y por lado (`bullish`/`bearish`)
`_active`/`_pivot_bar`/`_confirmation_bar`/`_age`. Son campos aditivos —
`score_store.py`, `api/app.py` y `panel/app.js` leen por nombre y toleran
campos nuevos, sin cambios necesarios en esos consumidores (verificado por
inspección de cada uno antes de tocar el dataclass).

**Estado posterior: RESOLVED.**

**No tocado (deliberadamente, alcance de BOT-024):**

- `close` como fuente de precio (vs `low`/`high`) — sigue pendiente,
  hallazgo #2.
- Hidden divergence — no implementada, no se pidió.
- D1, Momentum, EMA200 como desempate — no se usan en ningún punto de la
  resolución (`resolve_divergence()` sólo mira `confirmation_bar`).
- Evaluación predictiva de Divergencia RSI, optimización de parámetros — no
  forman parte de esta auditoría/fix.

**Definiciones para referencia futura (sin ambigüedad):**

```text
Divergencia soportada: REGULAR unicamente (no hidden).

Vigencia: age 0..10 inclusive vigente (11 valores de edad posibles,
          contando la barra de confirmacion como age=0). Expira en age 11.

Separacion nominal:  5..60 barras (DIVERGENCE_RANGE_MIN/MAX).
Separacion efectiva: 6..60 barras con pivotes 5/5 (ver hallazgo #3 -- ningun
                      par de pivotes reales puede estar a menos de 6 barras
                      quando lbL=lbR=5; no cambio con este fix).

Fuente de precio: close[pivot_bar] (no confirmation_bar, no high/low).

CONFLICT: bullish y bearish vigentes con el MISMO confirmation_bar.
          score = 0, resolution = SAME_CONFIRMATION_BAR, reason =
          "conflicto de divergencias RSI vigentes" (distinto de
          "sin divergencia vigente").
```

**Evidencia:** `reports/RSI-DIVERGENCE-EVIDENCE.log` sección 11 (casos
`bearish más reciente` — reproduce y corrige el bug original —, `bullish más
reciente`, y `CONFLICT`) y sección 9 (trazabilidad). Tests unitarios
correspondientes: `strategy/test_scoring.py` I–P (en particular **M**,
que reproduce exactamente el bug de la auditoría y demuestra que quedó
corregido).

---

## Regla final — respuesta directa

> **¿La Divergencia RSI que calcula actualmente el bot está correctamente
> implementada y representa únicamente información que realmente estaba
> disponible en ese momento?**

**Sí, en cuanto a causalidad y aritmética.** El RSI de Wilder está bien
implementado (verificado contra una segunda implementación independiente,
diferencia numérica cero), los pivotes se confirman con el lag correcto
(`bar+lbR`), no hay look-ahead en ningún punto probado (738/738 comparaciones
batch-vs-secuencial idénticas, y el caso explícito de "LIMIT creado antes de
que el segundo pivote se confirme" da 0 en las 4 barras donde debe dar 0), y
la tabla LONG/SHORT coincide exactamente con lo esperado.

**La laguna de diseño detectada originalmente ya está resuelta (BOT-024, ver
sección H):** cuando existen divergencias alcista y bajista vigentes al
mismo tiempo, el código ahora resuelve explícitamente por `confirmation_bar`
más reciente, con un estado `CONFLICT` distinguible para el empate exacto —
ya no hay prioridad fija ni descarte silencioso. Quedan pendientes, sin
cambios por este fix, dos puntos de fidelidad al indicador de referencia de
TradingView que requieren **confirmación en vivo** porque este entorno no
tiene acceso al chart real del usuario (uso de `close` vs `low`/`high`, y
manejo de empates en pivotes) — ver hallazgos #2 y #6.

No se evaluó ni se opina aquí sobre si Divergencia RSI aporta valor
predictivo, ni sobre su interacción con Momentum o D1 — eso queda,
correctamente, para la siguiente etapa.
