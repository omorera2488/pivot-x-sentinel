# Especificación funcional — EMA y Pivotes ZS (Fase 2)

Este documento es la especificación formal de la estrategia, derivada del código Pine original en [`/basecode_tradingview`](../basecode_tradingview) (`1m EMA y Pivotes ZS — trade boxes.txt` y `5m EMA y Pivotes ZS — trade boxes.txt`, idénticos en lógica, distintos solo en los valores por defecto de sus inputs).

Es independiente de lenguaje: cualquier implementación (backtest en Python, motor en vivo sobre MT5) que siga esta especificación al pie de la letra debe producir, sobre los mismos datos de entrada, exactamente los mismos números. No se implementa el modo repintante del original (`usarCausal=false`, `request.security` con lookahead) — eso requiere datos del futuro y solo tiene sentido como referencia visual en TradingView, es imposible de replicar en un bot en vivo.

> **Enmienda (2026-08-19):** §3 originalmente definía resistencia/soporte como el bloque HTF **anterior ya cerrado** (corrigiendo el auto-armado trivial del Pine con `usarCausal=true`, ver §3.2). A pedido explícito del usuario, se revirtió esa corrección: el motor (`strategy/engine.py`, `strategy/live_signal.py`) ahora replica bit a bit `usarCausal=true` del Pine de referencia — el bloque **en formación**, con el auto-armado incluido — porque es la única variante del indicador de TradingView que el usuario puede correr en vivo (el modo repintante es literalmente imposible de correr en vivo) y se quiere paridad exacta entre lo que se ve en el chart y lo que hace el bot. §3.2/§3.3 abajo quedan como estaban (documentan el comportamiento tal cual es, ya no como "bug a corregir" sino como la lógica vigente); ver [[pivot-x-sentinel-tv-reference-mismatch]] en la memoria del proyecto para el detalle de la decisión.

---

## 1. Alcance y diferencias respecto al original

| Punto | Original (Pine) | Esta especificación |
|---|---|---|
| Nivel de resistencia/soporte | `usarCausal=false` (default): `request.security(..., lookahead_on)`, repinta. `usarCausal=true`: extremo del bloque **que se está formando**, se autoarma en cada nuevo máximo/mínimo local del bloque (ver §3.2). | Igual a `usarCausal=true`: extremo del **bloque HTF en formación**, actualizado barra a barra (enmienda 2026-08-19 — ver nota arriba). No repinta (no usa `request.security`/lookahead), pero sí se autoarma como el original. |
| Stop | `runHigh/runLow` (extremo del bloque en formación) en el momento de la señal. | Mismo valor que resistencia/soporte (extremo del bloque en formación en la barra de señal) ± buffer — ver §3, un solo extremo trackeado, igual que el original. |
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

> **Enmienda (2026-09-04):** la formula original de esta sección (`bucket_id = floor(unix_minutes(t) / periodos)`, bloques continuos alineados a época Unix) quedó **descartada por prueba de paridad directa contra TradingView** — ver evidencia y regla nueva más abajo. La implementación vive en [`strategy/htf_session.py`](../strategy/htf_session.py), compartida bit a bit entre el motor batch (`engine.bucket_levels`) y el motor en vivo (`live_signal.LiveSignalEngine`) — ver [[pivot-x-sentinel-tv-reference-mismatch]] en la memoria del proyecto para el contexto de la sesión que detectó el desajuste.

**Evidencia observada:** se midió directamente en TradingView, con `time(str(periodos))` (la misma expresión que usa el Pine de referencia — `basecode_tradingview/"5m EMA y Pivotes ZS...".txt` línea 76, `nuevoBucket = ta.change(time(htf)) != 0`) sobre XAUUSD/OZ (feed TVC), `periodos=800`, contra el bot corriendo en vivo (XAUUSDc, MT5, misma cuenta real) el 2-4 de septiembre de 2026:

```
2026-09-02 22:00 UTC  -> bloque nuevo
2026-09-03 11:20 UTC  -> bloque nuevo   (800 min después de las 22:00)
2026-09-03 22:00 UTC  -> bloque nuevo   (640 min después de las 11:20, NO 800)
```

La fórmula vieja predice bloques SIEMPRE de exactamente `periodos` minutos, sin importar la hora del día — no puede producir el salto de 640 minutos entre las 11:20 y las 22:00. Con esa fórmula, el bot llegó a calcular el bloque vigente ~2 horas desfasado respecto al que mostraba TradingView en el mismo instante (confirmado también agregando un log de transición de bloque al bot y comparándolo en vivo, no solo a ojo sobre capturas).

**La regla nueva (bloque HTF sobre sesión, no sobre época Unix pura):** el patrón observado (800, después 640, después 800 de nuevo) es lo que produce TradingView al armar una resolución intradía "no estándar" (un número pelado de minutos, ej. `"800"`) sobre un símbolo con día de sesión de 24hs: cada DÍA de sesión (desde el inicio de sesión hasta el inicio de la sesión siguiente, 1440 minutos) se trocea en bloques de `periodos` minutos a partir del inicio de sesión, y el ÚLTIMO bloque del día se trunca en el límite de sesión siguiente en vez de completar `periodos` minutos si 1440 no es múltiplo exacto de `periodos` (800×1=800, 1440−800=640 → el bloque truncado medido).

```
anchor  = hora de inicio de sesión, en minutos desde medianoche UTC (medida: 22:00 UTC)
dia(t)  = t - ((t - anchor) mod 1440min)          // inicio del día de sesión al que pertenece t
delta   = (t - anchor) mod 1440min                 // minutos transcurridos desde ese inicio
bloque  = floor(delta / periodos)
bucket_start(t) = dia(t) + bloque * periodos       // inicio real del bloque HTF
```

Todas las barras del timeframe base cuyo `bucket_start(time[i])` coincide pertenecen al mismo bloque — comparar ese valor entre barras consecutivas alcanza para detectar un bloque nuevo. Implementación de referencia: `strategy/htf_session.bucket_start_utc_seconds()`.

**Supuestos pendientes de validar (no confirmados todavía):**

1. **DST.** El ancla de sesión (22:00 UTC) es un valor MEDIDO, no deducido — es la convención típica de "cierre de Nueva York" que usan muchos brokers forex/CFD, y esos brokers suelen correr esa hora con el horario de verano de EEUU. La medición se hizo en una sola ventana de 2 días (2-3 septiembre 2026) sin ningún cambio de DST de por medio — no hay evidencia todavía de que 22:00 UTC se mantenga después de un cambio de DST (EEUU 1-nov-2026, UE ya cambiado para cuando se mida de nuevo). Por eso el ancla es un parámetro explícito (`session_anchor_utc_min` en `htf_session.py`), no una constante escondida en el cálculo de señal — hay que volver a medir si se sospecha desalineación.
2. **Símbolo/feed.** Se midió solo Oro, feed TVC de TradingView — no se confirmó el mismo ancla contra el feed nativo del bróker (XAUUSDc en MT5) de forma independiente, más allá de que el bot ahora usa esta regla contra ese feed y el log de transición de bloque permite seguir comparándolo.
3. **Offset de reloj del bróker.** Esto es un problema DISTINTO del de arriba y sigue resuelto como antes — no se tocó: **si al conectar con MT5 se detecta que el servidor del bróker entrega timestamps en una zona horaria distinta a UTC, hay que normalizar a UTC antes de aplicar `bucket_start_utc_seconds()`, no cambiar la fórmula.** Confirmado que NO era la causa de este desajuste: `measure_broker_offset_seconds()` midió -1.86s (ruido de red) para la cuenta real usada, nada parecido a las ~2hs de diferencia que causaba la fórmula vieja.

**Cómo medir el offset del bróker, sin asumir de antemano cuál es:** al conectar, pedir un tick reciente con `symbol_info_tick` (trae su propio timestamp de servidor) y compararlo contra el reloj UTC del sistema en el instante exacto de esa consulta. La diferencia es el offset horario de ESE bróker en ESE momento — funciona igual sin importar qué bróker sea, y no depende de tener hardcodeada la zona horaria de ningún servidor en particular. Este mismo mecanismo resuelve tanto la ingesta histórica (Fase 3) como el arranque del motor en vivo (Fase 4) contra una cuenta nueva sin configuración manual previa. Nota: el offset puede cambiar con el horario de verano de la zona del bróker, así que conviene re-medirlo en cada conexión, no cachearlo indefinidamente.

### 3.2 Comportamiento de `usarCausal=true` (adoptado, no "corregido")

> Hasta la enmienda del 2026-08-19 esta sección describía esto como un bug a corregir (ver control de cambios al tope del documento). Se deja la descripción tal cual porque sigue siendo exacta — lo único que cambió es la conclusión: en vez de evitarlo, el motor lo reproduce a propósito, porque es lo mismo que hace `usarCausal=true` en el indicador real que corre en TradingView.

`usarCausal=true` calcula `resistencia`/`soporte` como el máximo/mínimo **del bloque que se está formando en este mismo instante**:

```
si es primer bar del bloque: runHigh := high[i]; runLow := low[i]
si no:                       runHigh := max(runHigh, high[i]); runLow := min(runLow, low[i])
resistencia := runHigh
soporte     := runLow
...
si high[i] >= resistencia: armadoVenta := true
si low[i]  <= soporte:     armadoCompra := true
```

El efecto no se limita a la primera barra del bloque: `runHigh := max(runHigh, high[i])` (y su equivalente para `runLow`) se recalcula en **cualquier barra** que haga un nuevo máximo o mínimo dentro del bloque en formación, no solo en la barra de apertura. Cada vez que eso ocurre, `resistencia`/`soporte` se actualiza al `high[i]`/`low[i]` de esa misma barra, y la comparación `high[i] >= resistencia` (o `low[i] <= soporte`) es una autocomparación trivialmente verdadera. **Resultado: `armadoVenta` y `armadoCompra` se re-arman —a menudo simultáneamente— en cada barra que expande el rango del bloque en formación, durante todo el tiempo que dure el bloque.** Es una fuente real de señales frecuentes, no un problema acotado a la barra de apertura — quien use esta especificación para razonar sobre la frecuencia de señales debe tenerlo presente.

### 3.3 Implementación

`resistencia`/`soporte` se calculan como el extremo acumulado del **bloque HTF en formación**, actualizado barra a barra, replicando `runHigh`/`runLow` del Pine de referencia (`usarCausal=true`) sin el componente de lookahead (`request.security`) del modo default:

```
al empezar un bloque nuevo (barra i es la primera de ese bloque, incluida la barra 0 de toda la serie):
    runHigh := high[i]
    runLow  := low[i]
si no (misma barra dentro del bloque en curso):
    runHigh := max(runHigh, high[i])
    runLow  := min(runLow, low[i])

resistencia[i] := runHigh
soporte[i]     := runLow
```

No hay período de calentamiento: desde la primera barra de toda la serie ya hay un nivel de referencia (el propio high/low de esa barra) — a diferencia de la versión con bloque anterior cerrado (que sí tenía un período sin nivel hasta cerrar el primer bloque), acá `resistencia`/`soporte` nunca son `NaN`.

Esta versión no repinta (nunca usa `request.security`/lookahead — el nivel de la barra `i` solo depende de datos de la barra `i` o anteriores), pero sí conserva el auto-armado de §3.2 — ambos son propiedades independientes del mecanismo, no la misma cosa: no repintar es sobre qué datos se usan (pasado vs. futuro), auto-armarse es sobre qué nivel se compara contra qué (el bloque en curso contra sí mismo). Esta especificación elige no repintar (imposible de operar en vivo si repintara) y sí auto-armarse (para tener paridad exacta con el indicador de TradingView, decisión explícita del usuario por sobre la alternativa de bloque anterior cerrado — ver control de cambios al tope del documento).

---

## 4. Armado, señal y entrada

### 4.1 EMA

`ema[i] = EMA(close, emaPeriods)`, replicando la fórmula real de `ta.ema` de Pine (verificada, no supuesta):

```
alpha = 2 / (emaPeriods + 1)
ema[0] = close[0]
ema[i] = alpha * close[i] + (1 - alpha) * ema[i-1]     // i >= 1
```

**Ojo con esto al portar a otro lenguaje/librería:** no es la convención de TA-Lib/MT5, que siembra la EMA con una SMA de las primeras `emaPeriods` barras y recién arranca el cálculo recursivo después de ese período de calentamiento. `ta.ema` no espera ningún calentamiento — arranca en la primera barra con `ema[0] = close[0]`. La diferencia se diluye rápido (la influencia de la semilla decae exponencialmente en unas pocas veces el período) pero es una fórmula distinta, y usar la convención equivocada fue un error real detectado durante la implementación en `/strategy` — no una decisión de esta especificación.

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

**Variante `entradaViva` (default `false`, opcional, implementada en `strategy/engine.py` como `StrategyParams.entrada_viva`):** en vez de congelar `entry` en el valor de la EMA de la barra de señal, la orden límite sigue el valor ACTUAL de la EMA en cada barra mientras esté pendiente (se acerca al precio en vez de esperar un retest del nivel original). Cuando finalmente se llena, el take profit se recalcula con el riesgo real observado en ese momento (`|stop - entryUsado|`) en vez del riesgo original. El stop nunca se mueve — sigue siendo el mismo, congelado desde la señal. Las condiciones de expiración de la orden pendiente (`tpAntes`/`muerto`/`caduca`, §5.2) siguen evaluándose contra el `entry`/`target` ORIGINALES de la señal, sin importar `entradaViva` — solo cambia qué nivel dispara el llenado y el target una vez llenada, igual que en el Pine. No es el comportamiento por defecto.

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

`resistencia[i]`/`soporte[i]` en el momento de la señal son el mismo extremo del bloque en formación descrito en §3 — el nivel usado para armar y el nivel usado para el stop son el mismo, en esa barra puntual (a diferencia del original, donde el stop toma `runHigh/runLow` en el instante de la señal pero el nivel PLOTEADO puede seguir moviéndose después — acá, al congelar `stop` en el momento de la señal como cualquier otro campo de la orden, no hay ambigüedad de cuál valor corresponde).

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

**En vivo (Fase 4, agregado 2026-08-23):** este cálculo por-barra es exacto para el backtest (§5.5 corre una vez por vela cerrada), pero contra un bróker real deja una ventana de riesgo: `_watch_pending` en `execution/src/bot.py` solo corre cuando cierra una vela nueva (hasta `bar_seconds` de exposición — 5 minutos en el perfil `5m`), mientras el precio se sigue moviendo en tiempo real dentro de esa vela. En cuenta demo se observó el caso concreto (2026-08-23): el precio toca `target` dentro de la vela en formación sin que la orden límite se haya llenado, se devuelve, y llena esa misma orden de verdad en el bróker — todo antes de que el bot llegara a cancelarla como "target alcanzado sin llenarse". Corrección: `_watch_pending_live` evalúa `tpAntes`/`muerto` contra el **tick en vivo** (`symbol_info_tick`, usando `bid`) en cada ciclo del loop de polling (`poll_interval_s`, 10s típico), reduciendo la ventana de "hasta `bar_seconds`" a "hasta `poll_interval_s`". `caduca`/`maxBarsTrade` sigue evaluándose solo por vela cerrada — depende de conteo de barras reales (`_bars_between`, ver spec-live-execution.md), no de precio, así que una vela intermedia no cambia el resultado. `_watch_pending` (por vela cerrada) se mantiene sin cambios como red de seguridad redundante.

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

El original no limita cuántas operaciones pendientes/abiertas pueden coexistir — cada señal válida siempre encola una orden nueva, sin mirar el estado de las anteriores.

**`unaOperacionALaVez` (default `true`, agregado 2026-08-19 a pedido del usuario):** antes de crear una orden nueva (paso 7 de §5.5), contar cuántas órdenes en estado PENDIENTE + ABIERTA existen ya, **en cualquier dirección** (venta o compra). Si el conteo es `>= 1`, la señal se descarta (contador propio, distinto del de "stop del lado incorrecto") y no se crea ninguna orden — aunque la señal sea válida y de la dirección contraria a la que ya está viva. Es un candado global, no por dirección: con este activado nunca hay más de una operación (pendiente o abierta) al mismo tiempo, sin importar el sentido.

**`maxConcurrentPorDireccion` (default `1`, aplica solo si `unaOperacionALaVez = false`):** el límite vuelve a contarse por dirección — cuántas órdenes PENDIENTE + ABIERTA existen ya con la misma dirección (`dir`) que la señal actual. Si el conteo es `>= maxConcurrentPorDireccion`, la señal se descarta. A diferencia del candado global, esto sí permite tener una venta y una compra vivas al mismo tiempo (cada dirección con su propio cupo).

El valor final de `maxConcurrentPorDireccion` para cuando `unaOperacionALaVez` esté desactivado, igual que R:R y el buffer, se valida empíricamente en la Fase 3.

---

## 7. Métricas a preservar del original (para validar la migración)

El original lleva contadores en vivo que sirven de referencia al portar la lógica: `nSig` (señales), `nFill` (llenadas), `nWin`/`nLoss`, `nNone` (expiradas sin llenar), `nSkip` (descartadas por stop inválido — ahora hay que separar esto de las descartadas por concurrencia), `nOpen` (cerradas por tiempo). El motor de backtest de la Fase 3 debe exponer estos mismos contadores.

**Importante (actualizado 2026-08-19):** con la enmienda de §3.3, el armado/señal (`nSig`, qué barra dispara y en qué dirección) debería coincidir con `usarCausal=true` del Pine barra a barra — es la misma fórmula. Pero eso NO garantiza que `nFill`/`nWin`/`nLoss`/`nNone`/`nOpen` agregados coincidan exactamente: el ciclo de vida completo de la orden (§5) — prioridad de llenado antes que expiración, empate = gana el SL, el precio de salida al cerrar por tiempo (§5.4, "decisión abierta", no existe en el Pine visual) — es una definición nueva de esta especificación, no algo que el indicador de TradingView calcule (es un indicador visual, no ejecuta ni gestiona órdenes). Tampoco coincide con `usarCausal=false` (repintante, imposible de replicar en vivo). El checksum útil sigue sin ser "¿el total coincide con el Pine?", sino verificar sobre casos puntuales que las reglas mecánicas del ciclo de vida se cumplen (§5.2–§5.5) Y que el armado/señal coincide barra a barra con `usarCausal=true` (este último sí es ahora una expectativa razonable, a diferencia de antes de la enmienda).

---

## 8. Decisiones abiertas (a confirmar antes de Fase 3)

1. ~~Alineación del bloque HTF a época UTC~~ (§3.1) — **descartada 2026-09-04**, reemplazada por alineación a sesión (ancla medida en TradingView, `strategy/htf_session.py`). Queda abierto el DST del ancla de sesión y si vale igual para otros símbolos/feeds — ver los 3 supuestos pendientes listados en §3.1.
2. **Precio de cierre por `tooLong`** (§5.4) — se asume `close[j]` de la barra que dispara el límite; alternativa es cierre a mercado en vivo.
3. **`maxConcurrentPorDireccion = 1`** (§6) como punto de partida del barrido de parámetros.
4. **Timeframe base a usar para Oro** (M1 vs M5, o ambos) — no se fija aquí; Fase 3 lo trata como un parámetro más del barrido, junto con `emaPeriods`, `periodos` (duración del bloque HTF), `bufBp` y `rr`.
