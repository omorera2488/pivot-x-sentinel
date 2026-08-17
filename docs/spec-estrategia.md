# Especificación funcional — EMA y Pivotes ZS (Fase 2)

Este documento es la especificación formal de la estrategia, derivada del código Pine original en [`/basecode_tradingview`](../basecode_tradingview) (`1m EMA y Pivotes ZS — trade boxes.txt` y `5m EMA y Pivotes ZS — trade boxes.txt`, idénticos en lógica, distintos solo en los valores por defecto de sus inputs).

Es independiente de lenguaje: cualquier implementación (backtest en Python, motor en vivo sobre MT5) que siga esta especificación al pie de la letra debe producir, sobre los mismos datos de entrada, exactamente los mismos números. Donde el original tiene un comportamiento repintante, ambiguo o con bug, esta especificación define la versión corregida y solo esa — no se implementa el modo repintante del original, que solo tenía sentido como referencia visual en TradingView.

---

## 1. Alcance y diferencias respecto al original

| Punto | Original (Pine) | Esta especificación |
|---|---|---|
| Nivel de resistencia/soporte | `usarCausal=false` (default): `request.security(..., lookahead_on)`, repinta. `usarCausal=true`: extremo del bloque **que se está formando**, se autoarma trivialmente el primer bar de cada bloque (bug, ver §3). | Extremo del **bloque HTF anterior ya cerrado**. No repinta, no se autoarma nunca contra sí mismo. |
| Stop | `runHigh/runLow` (extremo del bloque en formación) en el momento de la señal. | Mismo valor que resistencia/soporte (extremo del bloque anterior cerrado) ± buffer — ver §3, ya no hace falta trackear un extremo en formación aparte. |
| Concurrencia | Sin límite: se puede acumular un número arbitrario de operaciones pendientes/abiertas en la misma dirección. | Límite explícito configurable (`maxConcurrentPorDireccion`), ver §6. |
| Cierre por tiempo máximo de una posición abierta | Sin definir un precio de salida real (el original es un indicador visual, no ejecuta órdenes). | Definido explícitamente para backtest/vivo — ver §5.4. |
| Buffer del stop | Constante en basis points, calibrada para forex (`0.4 bp` por defecto). | Mismo mecanismo (% del nivel), valor por defecto a recalibrar empíricamente en Fase 3 para Oro. |
| R:R | `1.0` por defecto, con nota manual "7 en 5m" (nunca aplicada como default real en el código). | Parámetro puro, sin default asumido — se determina en Fase 3. |

---

## 2. Notación y datos de entrada

Serie de velas OHLC del timeframe base elegido (`chartTF`), ordenadas por tiempo, sin huecos no reportados. Para cada barra `i`: `open[i]`, `high[i]`, `low[i]`, `close[i]`, `time[i]` (inicio de la barra, UTC).

**Parámetros configurables:**

| Parámetro | Símbolo | Default heredado del Pine | Notas |
|---|---|---|---|
| Periodo EMA | `emaPeriods` | 15 (variante 1m) / 12 (variante 5m) | |
| Duración del bloque HTF, en minutos | `periodos` | 100 (1m) / 400 (5m) | Ver §3.1 — ya no es "número de barras", es una ventana de tiempo fija |
| Riesgo:Beneficio | `rr` | sin default asumido | A determinar en Fase 3 |
| Buffer del stop (bp del nivel) | `bufBp` | sin default asumido | A determinar en Fase 3 |
| Barras de validez de la orden límite (modo fijo) | `validBars` | 10 | Solo aplica si `ordenViva = false` |
| Orden viva hasta invalidarse | `ordenViva` | `true` | Ver §5.2 |
| Máximo de barras por operación | `maxBarsTrade` | 500 | Ver §5.4 — se usa como dos relojes independientes |
| Entrada en EMA actual (móvil) | `entradaViva` | `false` | Variante opcional, ver §4.3 |
| Máx. operaciones concurrentes por dirección | `maxConcurrentPorDireccion` | **1 (propuesto, nuevo)** | No existe en el original — ver §6 |

---

## 3. Cálculo del bloque HTF (corregido)

### 3.1 Definición del bloque

El bloque HTF es una ventana de tiempo fija de `periodos` minutos, no solapada, alineada a época Unix UTC:

```
bucket_id(t) = floor(unix_minutes(t) / periodos)
```

Todas las barras del timeframe base cuyo `time[i]` cae en el mismo `bucket_id` pertenecen al mismo bloque. Esta es una decisión de esta especificación (el Pine original delega la alineación exacta a `time(htf)` de TradingView, ligada a la sesión del símbolo); lo que importa aquí es que backtest y vivo usen exactamente la misma regla — **si al conectar con MT5 se detecta que el servidor del bróker entrega timestamps en una zona horaria distinta a UTC, hay que normalizar a UTC antes de aplicar esta fórmula, no cambiar la fórmula.**

### 3.2 Bug corregido

En el original, `usarCausal=true` calcula `resistencia`/`soporte` como el máximo/mínimo **del bloque que se está formando en este mismo instante**:

```
si es primer bar del bloque: runHigh := high[i]; runLow := low[i]
si no:                       runHigh := max(runHigh, high[i]); runLow := min(runLow, low[i])
resistencia := runHigh
soporte     := runLow
...
si high[i] >= resistencia: armadoVenta := true
si low[i]  <= soporte:     armadoCompra := true
```

En el primer bar de cada bloque nuevo, `resistencia` se acaba de fijar en `high[i]` — la comparación `high[i] >= resistencia` es entonces `high[i] >= high[i]`, siempre verdadera. Lo mismo para `soporte`/`low[i]`. **Resultado: cada bloque nuevo arma `armadoVenta` y `armadoCompra` simultáneamente en su primer bar, sin relación con ningún nivel real** — es ruido, no señal.

### 3.3 Corrección

`resistencia`/`soporte` se calculan a partir del **bloque anterior, ya cerrado** — un valor fijo durante todo el bloque actual, que no puede compararse contra sí mismo:

```
al cerrar un bloque:
    prevHigh := high máximo observado durante ese bloque
    prevLow  := low mínimo observado durante ese bloque

para cada barra i (mientras su bloque sigue abierto):
    resistencia[i] := prevHigh   (del bloque anterior)
    soporte[i]     := prevLow    (del bloque anterior)
```

Antes de que se cierre el primer bloque de toda la serie, `resistencia`/`soporte` son indefinidos (`NaN`) y no puede haber armado — hay un período de calentamiento de hasta `periodos` minutos al arrancar el bot o el backtest.

Esta corrección resuelve a la vez el repintado (el original repintaba en el modo default por leer el bloque en formación vía `request.security` con lookahead) y el bug de autoarmado — ambos eran síntoma de usar el bloque equivocado (el que se está formando) como referencia.

---

## 4. Armado, señal y entrada

### 4.1 EMA

`ema[i] = EMA(close, emaPeriods)` — media exponencial estándar.

### 4.2 Armado

Estado persistente `armadoVenta`, `armadoCompra` (booleanos, inician en `false`).

Por cada barra `i`, en este orden:

```
cruceAbajo  = close[i-1] >= ema[i-1] and close[i] < ema[i]     // crossunder
cruceArriba = close[i-1] <= ema[i-1] and close[i] > ema[i]     // crossover

senalVenta  = armadoVenta  and cruceAbajo
senalCompra = armadoCompra and cruceArriba

si senalVenta:  armadoVenta  := false
si senalCompra: armadoCompra := false
si high[i] >= resistencia[i]: armadoVenta  := true
si low[i]  <= soporte[i]:     armadoCompra := true
```

`cruceAbajo` y `cruceArriba` son mutuamente excluyentes en una misma barra, por lo tanto `senalVenta` y `senalCompra` nunca son verdaderas a la vez.

### 4.3 Entrada

En la barra de la señal (`senalVenta` o `senalCompra`):

```
dir   = senalVenta ? -1 : +1
entry = ema[i]                          // frozen; ver variante "entrada viva" abajo
```

**Variante `entradaViva` (default `false`, opcional):** en vez de congelar `entry` en el valor de la EMA de la barra de señal, la orden límite sigue el valor ACTUAL de la EMA en cada barra mientras esté pendiente (se acerca al precio en vez de esperar un retest del nivel original). Cuando finalmente se llena, el take profit se recalcula con el riesgo real observado en ese momento (`|stop - entryUsado|`) en vez del riesgo original. No es el comportamiento por defecto; se documenta por si se quiere exponer como parámetro, pero **Fase 3 evalúa primero el modo por defecto (entrada congelada)**.

### 4.4 Stop y take profit

```
buf  = bufBp / 10000                     // fracción del nivel

stop = dir < 0 ? resistencia[i] * (1 + buf) : soporte[i] * (1 - buf)

// validez: el stop debe quedar del lado correcto respecto a la entrada
valido = dir < 0 ? (stop > entry) : (stop < entry)

si no valido:
    descartar la señal (contador "descartada por stop del lado incorrecto"),
    no se crea ninguna orden.

riesgo  = |stop - entry|
target  = dir < 0 ? entry - rr * riesgo : entry + rr * riesgo
```

`resistencia[i]`/`soporte[i]` en el momento de la señal son el mismo valor congelado del bloque anterior descrito en §3 — no hace falta trackear por separado un "extremo en formación" como en el original: al ya no repintar, el nivel usado para armar y el nivel usado para el stop son el mismo, todo el tiempo, durante el bloque completo.

---

## 5. Ciclo de vida de la orden

### 5.1 Creación

Si la señal es válida (§4.4) y pasa el chequeo de concurrencia (§6), se encola como **orden pendiente**:

```
{ dir, entry, stop, target, bornBar = i }
```

### 5.2 Orden pendiente — evaluación por barra

Mientras la orden esté pendiente, en cada barra `j >= bornBar`, en este orden estricto de prioridad:

```
tocada = dir < 0 ? high[j] >= entry : low[j] <= entry

si tocada:
    -> LLENA en esta barra (ver §5.3)

si no tocada:
    tpAntes = dir < 0 ? low[j] <= target : high[j] >= target
    si tpAntes:
        -> EXPIRADA — "target alcanzado sin haberse llenado" (el movimiento
           ocurrió sin la entrada; ya no hay nada que capturar)
    si no y ordenViva = true:
        muerto = dir < 0 ? high[j] >= stop : low[j] <= stop
        caduca = (j - bornBar) >= maxBarsTrade
        si muerto o caduca:
            -> EXPIRADA
    si no y ordenViva = false:
        caduca = (j - bornBar) >= validBars
        si caduca:
            -> EXPIRADA
    si ninguna condición aplica:
        -> sigue pendiente
```

Nota: en modo `ordenViva = false` (ventana fija), el precio alcanzando el nivel de stop **no** invalida la orden — solo el paso del tiempo (`validBars`) o el TP-antes-de-llenarse la matan. Es una diferencia real de comportamiento entre los dos modos, no solo de duración.

### 5.3 Llenado (misma barra en que `tocada = true`)

```
precioLlenado = entry            // orden límite; sin slippage en la especificación
                                   // (el motor de ejecución en vivo puede medir y
                                   // reportar slippage real por separado, Fase 4)

en la MISMA barra, chequear inmediatamente:
    hitSL = dir < 0 ? high[j] >= stop   : low[j] <= stop
    hitTP = dir < 0 ? low[j]  <= target : high[j] >= target

    si hitSL:            -> resuelta como PÉRDIDA, misma barra   (empate = gana el SL)
    si no y hitTP:        -> resuelta como GANANCIA, misma barra
    si ninguna:            -> pasa a ABIERTA, openBar = j
```

La regla "empate = gana el SL" (una barra que toca ambos niveles a la vez cuenta como stop, nunca como take profit) se aplica siempre, tanto en el llenado mismo-barra como en la resolución de posiciones abiertas (§5.4) — es la lectura conservadora, igual que en el original.

### 5.4 Posición abierta — evaluación por barra

Mientras esté abierta, en cada barra `j >= openBar`:

```
hitSL   = dir < 0 ? high[j] >= stop   : low[j] <= stop
hitTP   = dir < 0 ? low[j]  <= target : high[j] >= target
tooLong = (j - openBar) >= maxBarsTrade

si hitSL:              -> PÉRDIDA
si no y hitTP:          -> GANANCIA
si no y tooLong:        -> CERRADA POR TIEMPO — ver definición de precio de salida abajo
si ninguna:              -> sigue abierta
```

**Precio de salida al cerrar por tiempo (definición nueva, no existe en el original):** se cierra al precio de `close[j]` de la barra que dispara `tooLong`. El original es un indicador visual y no define esto (solo cuenta "sin resolver" para estadística); backtest y ejecución en vivo necesitan un precio real de cierre, y `close[j]` es la convención más simple y auditable. **Se marca como decisión abierta a confirmar antes de Fase 3** — alternativas serían cerrar a mercado en el primer tick disponible tras cumplirse `tooLong` (más realista para vivo, pero no reproducible 1:1 en un backtest de velas).

**Nota sobre el "doble reloj" de `maxBarsTrade`:** el mismo parámetro limita, de forma independiente, (a) cuánto puede esperar una orden pendiente antes de llenarse (§5.2, contado desde `bornBar`) y (b) cuánto puede durar una posición ya abierta (§5.4, contado desde `openBar`). En el peor caso una operación puede tardar hasta `2 × maxBarsTrade` barras desde la señal hasta su resolución final. Esto reproduce el comportamiento del original tal cual — se documenta explícitamente para que no se lea como bug al portarlo.

### 5.5 Orden de procesamiento dentro de una misma barra

Para que dos implementaciones coincidan barra a barra, el orden de evaluación dentro de cada barra `i` debe ser:

1. Determinar el bloque HTF de `i`; si `i` es la primera barra de un bloque nuevo, cerrar el bloque anterior (congelar `prevHigh`/`prevLow`) y arrancar el acumulador del bloque que empieza.
2. Calcular `resistencia[i]`, `soporte[i]` (§3.3) y `ema[i]`.
3. Calcular `cruceAbajo`/`cruceArriba`, `senalVenta`/`senalCompra` (con el estado de armado tal como quedó de barras anteriores).
4. Actualizar `armadoVenta`/`armadoCompra` (desarme por señal, armado por nivel) — §4.2.
5. Resolver posiciones **abiertas** (§5.4) usando `high[i]`/`low[i]`.
6. Evaluar órdenes **pendientes** (§5.2/§5.3) usando `high[i]`/`low[i]`.
7. Si hubo señal en el paso 3, intentar encolar una **orden nueva** (§4.4, §5.1), sujeta a validez de stop y al límite de concurrencia (§6).

---

## 6. Reglas de concurrencia (nuevo respecto al original)

El original no limita cuántas operaciones pendientes/abiertas pueden coexistir en la misma dirección — cada señal válida siempre encola una orden nueva, sin mirar el estado de las anteriores.

**Regla propuesta:** antes de crear una orden nueva (paso 7 de §5.5), contar cuántas órdenes en estado PENDIENTE + ABIERTA existen ya con la misma dirección (`dir`) que la señal actual. Si el conteo es `>= maxConcurrentPorDireccion`, la señal se descarta (contador propio, distinto del de "stop del lado incorrecto") y no se crea ninguna orden.

Propongo `maxConcurrentPorDireccion = 1` como default de partida (una sola operación viva por dirección a la vez) — el valor final, igual que R:R y el buffer, se valida empíricamente en la Fase 3. Si no hay objeción se deja así.

---

## 7. Métricas a preservar del original (para validar la migración)

El original lleva contadores en vivo que sirven como checksum al portar la lógica: `nSig` (señales), `nFill` (llenadas), `nWin`/`nLoss`, `nNone` (expiradas sin llenar), `nSkip` (descartadas por stop inválido — ahora hay que separar esto de las descartadas por concurrencia), `nOpen` (cerradas por tiempo). El motor de backtest de la Fase 3 debe exponer estos mismos contadores para poder comparar contra un recorrido manual del Pine original sobre el mismo tramo de datos como sanity check.

---

## 8. Decisiones abiertas (a confirmar antes de Fase 3)

1. **Alineación del bloque HTF a época UTC** (§3.1) — asumido por esta especificación; a verificar que no choque con cómo MT5 entrega timestamps del bróker.
2. **Precio de cierre por `tooLong`** (§5.4) — se asume `close[j]` de la barra que dispara el límite; alternativa es cierre a mercado en vivo.
3. **`maxConcurrentPorDireccion = 1`** (§6) como punto de partida del barrido de parámetros.
4. **Timeframe base a usar para Oro** (M1 vs M5, o ambos) — no se fija aquí; Fase 3 lo trata como un parámetro más del barrido, junto con `emaPeriods`, `periodos` (duración del bloque HTF), `bufBp` y `rr`.
