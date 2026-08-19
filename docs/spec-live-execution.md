# Motor de ejecución en vivo — MT5 (Fase 4)

> **Estado: IMPLEMENTADO en `/execution`, opera en vivo por defecto.** La Fase 3 corrió el barrido completo sobre M5 y no encontró una combinación de parámetros con edge robusto (`docs/spec-backtest.md §8`). El usuario decidió explícitamente avanzar con la implementación y operar de todos modos, sin esperar esa validación — la señal (qué parámetros usar, si el armado persistente necesita rediseño) sigue siendo una hipótesis, no algo confirmado por backtest. Qué cuenta usar (demo o real) y si operar en vivo o en `dry_run` es una decisión de quien conecta la cuenta a MT5 y arranca el bot — el código no distingue ni restringe por tipo de cuenta. Ver el disclaimer de riesgo en `README.md`.

**Objetivo:** la misma lógica de `spec-estrategia.md`, corriendo en tiempo real contra un terminal MT5, sin intervención manual.

---

## 1. Principio de diseño: dos fuentes de verdad distintas

El motor en vivo maneja dos tipos de estado que **nunca se mezclan**:

1. **Estado de señal** (bloque HTF, `armadoVenta`/`armadoCompra`, EMA): es puramente una función de la serie de precios. No existe en ningún lado más que en la memoria del proceso — si el bot se reinicia, se **reconstruye por replay** sobre historial reciente (§4), nunca se asume "desarmado" por default.
2. **Estado de órdenes** (qué está pendiente, qué está abierto, con qué stop/target): la fuente de verdad es **el bróker**, no la memoria del proceso. Todo lo que el motor cree saber sobre sus propias órdenes se reconcilia contra `mt5.orders_get()` / `mt5.positions_get()` en cada ciclo (§6) — la memoria interna es una cache, no la verdad.

Esta separación es la que hace posible reiniciar el bot en cualquier momento sin perder ni duplicar operaciones.

---

## 2. Arquitectura

Un solo proceso Python (decisión ya tomada en Fase 0), con un bucle principal que:

1. Se conecta a la terminal MT5 (`mt5.initialize()`), identifica el símbolo (búsqueda por `XAU`, igual que en Fase 3 — nunca hardcodeado a un bróker).
2. Mide el offset horario del bróker (`symbol_info_tick` vs UTC, ver `spec-estrategia.md` §3.1) y lo vuelve a medir periódicamente (cada N minutos — el offset puede correr con el horario de verano del bróker).
3. Hace el **replay de arranque** (§4) para reconstruir el estado de señal.
4. Reconcilia el estado de órdenes contra el bróker (§6).
5. Entra al **bucle de polling** (§3): en cada vela nueva que cierra, corre exactamente el mismo procesamiento por barra de `spec-estrategia.md` §5.5 — evaluar señal, resolver abiertas, evaluar pendientes, encolar orden nueva — pero reemplazando cada paso "interno" (backtest) por una llamada real a la API de MT5 (§5).

No hay proceso "shadow" ni capas paralelas (decisión de Fase 0) — el mismo proceso calcula la señal y envía la orden.

---

## 3. Detección de vela cerrada (polling)

MT5 no empuja eventos de "vela nueva" — hay que sondear. Cada `pollIntervalSeg` (propuesto: 5-15s, configurable):

```
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, K)   // K >= 3, margen de seguridad
ultima_cerrada = rates[-2]   // la posicion 0 es la vela EN FORMACION, -2 es la ultima cerrada
```

Se procesa `ultima_cerrada` solo si su `time` es mayor al de la última vela ya procesada. **Nunca se evalúa señal/armado sobre la vela en formación** (posición `-1`/`rates[0]`) — hacerlo violaría el diseño no-repintante de `spec-estrategia.md` (el mismo motivo por el que se corrigió el bug del bloque HTF en Fase 2). La vela en formación solo se puede usar para *monitoreo visual* (ej. mostrar en el panel el precio actual respecto al nivel armado), nunca para lógica de decisión.

**Múltiples velas cerradas entre un poll y el siguiente** (el proceso estuvo caído, hubo latencia, etc.): se procesan **todas, en orden, una por una** — nunca se salta directo a la más reciente. Es la única forma de mantener correcto el estado de bloque HTF y de armado, que son inherentemente secuenciales (dependen de haber visto cada barra intermedia).

---

## 4. Replay de arranque (reconstrucción del estado de señal)

Al conectar (o reconectar tras una caída), el bot no sabe si `armadoVenta`/`armadoCompra` deberían estar activos — esa información no vive en MT5, solo en la secuencia de barras recientes. Antes de operar:

1. Descargar un lookback de al menos **3 bloques HTF completos** (`3 × periodos` minutos) de velas cerradas — suficiente para tener un bloque anterior cerrado real (no solo el de calentamiento) y ver si hubo un evento de armado reciente sin resolver todavía.
2. Correr esas velas, en orden, a través de la misma lógica de `spec-estrategia.md` §3.3/§4.2 (cálculo de bloque, armado) — **sin crear ninguna orden real** durante el replay, aunque el replay detecte que "hubiera" disparado una señal en el pasado. Solo interesa el estado de armado al llegar a la vela más reciente ya cerrada.
3. Recién de ahí en adelante, las velas nuevas que cierren en vivo pueden generar órdenes reales.

Si el lookback pedido no alcanza a cubrir un bloque anterior completo (símbolo con poco historial, terminal recién conectada), el bot arranca en período de calentamiento igual que el backtest (§3.3 de `spec-estrategia.md`) — sin armado posible hasta que se cierre un bloque completo observado en vivo.

---

## 5. Colocación de la orden

Al dispararse una señal válida (misma lógica de `spec-estrategia.md` §4.4, con el chequeo de concurrencia de §6 abajo) se envía una orden límite real:

```
mt5.order_send({
    action: TRADE_ACTION_PENDING,
    symbol: symbol,
    volume: fixedLot,                                  // tamaño fijo, ver spec-backtest.md #3.4
    type: dir < 0 ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_BUY_LIMIT,
    price: entry,
    sl: stop,
    tp: target,
    magic: MAGIC_NUMBER,                                // identifica ordenes de ESTE bot
    comment: f"pxs|born={bornBarTime}|dir={dir}",        // metadata legible, ver #7
    type_time: ORDER_TIME_GTC,
    type_filling: <segun lo que acepte el broker/simbolo>,
})
```

`MAGIC_NUMBER` es fijo y propio de este bot — el motor **nunca** toca ni cuenta órdenes/posiciones de otro magic number o sin magic number (evita interferir con operativa manual del usuario en la misma cuenta).

SL/TP van adjuntos a la orden desde el envío — no se gestionan por separado con órdenes de cierre manuales, para no depender de que el bot esté corriendo en el instante exacto en que el precio toca el nivel (si el bot se cae con una posición abierta, el bróker igual respeta el SL/TP ya cargado en la orden).

---

## 6. Reconciliación de estado (cada ciclo)

Antes de decidir nada, el bot lee el estado real:

```
mis_pendientes = mt5.orders_get(symbol=symbol) filtradas por magic == MAGIC_NUMBER
mis_abiertas   = mt5.positions_get(symbol=symbol) filtradas por magic == MAGIC_NUMBER
```

Esto reemplaza a los arrays `pending`/`open` en memoria que usa el motor de backtest (`spec-backtest.md`, `strategy/engine.py`) — en vivo, la lista de pendientes/abiertas ES la que devuelve el bróker, no una que el proceso mantenga por su cuenta. El **conteo de concurrencia** (`spec-estrategia.md` §6) se calcula sobre estas listas reales, no sobre una copia en memoria que podría desincronizarse si una orden se llenó, canceló o cerró por fuera del bot (ej. el usuario la tocó manualmente, o el bróker la cerró por stop-out).

**Corrección encontrada al implementar (`execution/src/bot.py`):** este borrador asumía que iba a hacer falta un registro local aparte (json/sqlite) para los metadatos que "MT5 no guarda". Resultó innecesario — el objeto de la orden pendiente (`orders_get()`) y el de la posición abierta (`positions_get()`) ya traen todo lo que hace falta de forma nativa: `time_setup` (posición: `time`) es exactamente el `bornBar`/hora de la señal, `sl`/`tp` son el stop/target congelados, `type` da la dirección, `price_open` es el entry. No hay ningún dato crítico que MT5 no persista ya por su cuenta. El campo `comment` (`"pxs|{perfil}"`) queda solo como etiqueta legible en el terminal — nada crítico se reconstruye parseándolo. Esto simplifica la reconciliación: no hay una cache aparte que pueda desincronizarse, todo sale de la misma consulta a `orders_get()`/`positions_get()` de la que ya depende el conteo de concurrencia.

---

## 7. Vigilancia y cancelación de pendientes invalidados

En cada vela cerrada, para cada orden en `mis_pendientes`: aplicar exactamente `spec-estrategia.md` §5.2 (`tpAntes`, `muerto`, `caduca` según `ordenViva`) usando el `high`/`low` de la vela recién cerrada contra el `stop`/`target` que el bot recuerda para esa orden (del `comment` o del registro local). Si corresponde expirar:

```
mt5.order_send({ action: TRADE_ACTION_REMOVE, order: ticket })
```

Si el "llenado" (§5.3) ya ocurrió del lado del bróker antes de que el bot llegue a cancelarla (carrera entre el precio tocando la entrada y el bot detectando la expiración), la orden ya no aparece en `orders_get()` sino como posición en `positions_get()` — el bot debe verificar el estado real antes de intentar cancelar (una cancelación sobre un ticket que ya no es una orden pendiente falla silenciosamente o con error, hay que loguearlo, no tratarlo como excepción fatal).

---

## 8. Cierre por tiempo máximo (posición abierta)

En cada vela cerrada, para cada posición en `mis_abiertas`: aplicar `spec-estrategia.md` §5.4. `hitSL`/`hitTP` ya los resuelve el bróker automáticamente (SL/TP adjuntos, §5) — lo que el bot debe vigilar activamente es `tooLong` (`maxBarsTrade`), que MT5 no aplica solo:

```
si (velaActual - openBar) >= maxBarsTrade:
    mt5.order_send({ action: TRADE_ACTION_DEAL, position: ticket,
                      type: <opuesto a la posicion>, volume: posicion.volume })
    // cierre a mercado
```

A diferencia del backtest (que cierra a `close[j]` por definición, `spec-estrategia.md` §5.4), en vivo el cierre es a mercado real — precio de ejecución sujeto al spread/slippage del momento, no al `close` exacto de la vela. Es la naturaleza de "vivo" vs "backtest de velas"; ya estaba anotado como diferencia esperada en `spec-backtest.md` §5.4.

**Bug encontrado y corregido (reportado por el usuario, no detectado en la implementación inicial):** `spec-estrategia.md` §5.2/§5.4 define `caduca`/`tooLong` contando **barras realmente formadas** (`bar_index` de Pine, que no avanza con el mercado cerrado). La primera versión de `execution/src/bot.py` estimaba esto dividiendo el tiempo de reloj transcurrido desde `time_setup`/`time` (nativos de MT5) por la duración nominal de la barra — eso cuenta minutos de calendario, no barras. Verificado contra datos reales: en una ventana de 58 horas que cruza un fin de semana (viernes 20:00 UTC a lunes 06:00 UTC), esa estimación contaba **696 barras M5**, cuando el mercado formó realmente **108**. Con `maxBarsTrade=500` (default), una posición abierta el viernes se habría cerrado por timeout en pleno sábado, sin mercado abierto — mucho antes de lo que la especificación pretende.

**Corrección:** `_bars_between()` en `bot.py` cuenta barras reales consultando `mt5.copy_rates_range()` entre el timestamp de origen (`time_setup`/`time`, hora de servidor sin corregir) y la barra actual, en vez de estimar por tiempo de reloj. Si el mercado estuvo cerrado en ese lapso, MT5 simplemente no devuelve barras para esa ventana — el conteo excluye el hueco automáticamente, igual que `bar_index` en Pine. No hace falta persistir nada nuevo para esto: sigue sin haber un registro local aparte (§6), solo una consulta distinta.

---

## 9. Reconexión y errores

- Si `mt5.initialize()` falla o la conexión se cae en medio del bucle: reintentar con backoff (ej. 5s, 15s, 60s, tope 5 min), sin perder el estado de señal ya calculado (solo se pierde si el PROCESO se reinicia, no la conexión).
- Si el proceso se reinicia: todo vuelve a pasar por §4 (replay) y §6 (reconciliación) — nunca asumir que el mundo está como se lo dejó la última vez.
- Ninguna orden se reintenta ciegamente: si `order_send` devuelve error, se loguea con el motivo (`mt5.last_error()`) y NO se reintenta automáticamente en el mismo ciclo — evita duplicar órdenes por un error transitorio que en realidad sí se ejecutó del lado del servidor. Se revisa recién en el siguiente ciclo de reconciliación (§6), que va a mostrar si la orden quedó puesta o no.

---

## 10. Alcance de esta fase

- **Tipo de cuenta (demo o real): decisión de quien opera el bot, no de esta especificación ni del código.** El motor no consulta ni distingue `account_info().trade_mode` en ningún punto — hace exactamente lo mismo contra cualquier cuenta que la terminal MT5 tenga conectada. El criterio de aceptación original de la Fase 4 ("resultados consistentes con el backtest de la Fase 3") sigue sin cumplirse — no hay edge validado — pero eso no bloquea nada a nivel código, es información para que quien opera decida con conocimiento de causa.
- Tamaño de posición: lote fijo (`fixedLot`), igual que en `spec-backtest.md` §3.4 — el dimensionamiento por riesgo variable sigue siendo tema de la Fase 8, no de esta.
- Un solo símbolo por instancia del bot (Oro). Multi-símbolo no está en el alcance de esta fase.
- **`dry_run=False` por defecto** (`execution/src/bot.py`, `LiveExecutionBot`): el bot manda órdenes reales de una. Pasar `--dry-run` (`execution/scripts/run_bot.py`) o desmarcar "Operar en vivo" en el panel calcula señales/timeouts/concurrencia igual pero solo loguea, sin mandar `order_send`/`order_remove` — sirve para validar una configuración nueva antes de operar con ella.

---

## 11. Decisiones abiertas

1. **`pollIntervalSeg`** — propuesto 5-15s; a ajustar contra qué tan seguido el bróker realmente actualiza velas M5/M1 y el rate-limit de la API.
2. **Codificación del `comment`** de la orden — formato exacto y qué hacer si MT5 trunca el campo (límite de caracteres varía por bróker/build).
3. **Filling mode** (`type_filling`) de la orden límite — depende de lo que acepte `XAUUSDm` en Exness (o el símbolo/bróker que corresponda); se detecta en tiempo de ejecución vía `symbol_info().filling_mode`, no se hardcodea.
4. **Lookback del replay de arranque** (§4) — "3 bloques HTF completos" es un punto de partida conservador; a ajustar si el arranque tarda demasiado con bloques HTF muy largos.
5. Todo lo que dependa de los parámetros de la estrategia (`emaPeriods`, `periodos`, `bufBp`, `rr`, `maxConcurrentPorDireccion`) queda **sin valores** hasta que la Fase 3 (o su rediseño) entregue una combinación validada — ver nota al inicio del documento.
