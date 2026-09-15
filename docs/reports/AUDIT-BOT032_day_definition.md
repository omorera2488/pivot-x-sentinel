# AUDIT-BOT032 — Definición actual de "día" en el bot (pre-implementación)

**Alcance:** auditoría de solo lectura. No se modificó ningún archivo. No se toma ninguna decisión de diseño para BOT-032 (Kill switch / máxima pérdida diaria) — solo se documenta el comportamiento temporal ACTUAL del código, con evidencia verificable (archivo, línea, código, explicación).

**Repositorio:** `pivot-x-sentinel` — foco en `execution/` (motor en vivo, Fase 4/5) y `api/` (Fase 5), con contraste puntual contra `strategy/`, `panel/`, `packaging/` y `backtests/` donde es relevante para entender diferencias de convención horaria.

---

## 1. Resumen ejecutivo

- El bot en vivo (`execution/src/bot.py`, `execution/src/mt5_utils.py`, `api/app.py`) trabaja **exclusivamente en UTC real** (`datetime.now(timezone.utc)`, `datetime.fromtimestamp(..., tz=timezone.utc)`). No hay ningún uso de hora local del sistema en la ruta de trading, ni de hora "cruda" del servidor MT5 sin declarar explícitamente que es hora de servidor.
- El bot **mide** el offset del reloj del servidor del broker contra UTC (`measure_broker_offset_seconds()`), pero desde el 2026-09-04 **decidió explícitamente NO aplicar esa corrección** al timestamp de las velas que alimenta el motor de señal (EMA/HTF/armado). El offset queda solo como dato de diagnóstico en el log.
- **No existe hoy ningún concepto de "día calendario" (00:00→23:59:59) en ningún sentido — ni UTC, ni servidor, ni local.** Lo que sí existe es un concepto distinto: un **"bloque de sesión HTF"**, anclado a las 22:00 UTC, con duración variable (800min y luego 640min truncado, según `periodos_htf_min`) — no es un día de 24hs ni resetea a media medianoche.
- No hay ningún P&L diario, límite diario, estadística diaria, ni reset diario en el código actual. `/history` y el panel trabajan con ventanas móviles de N días (`days=30/365/3650`) contadas hacia atrás desde "ahora" (UTC), nunca con fronteras de día calendario.
- No hay persistencia de ningún estado asociado a una fecha/día — todo lo que podría parecerse (`_started_at`, snapshots de órdenes/posiciones) vive en memoria del proceso y se pierde en cada reinicio.
- Para BOT-032, la convención más coherente de reutilizar es: **filtrar deals de `history_deals_get()` por su timestamp `time` (segundos Unix UTC reales, sin corrección de offset) contra una frontera de 00:00–23:59:59 UTC**, que es exactamente el mismo sistema de tiempo que ya usa todo el resto del bot (`/history` en `api/app.py`, `_aciertos_pct()` en `bot.py`).

---

## 2. Evidencia encontrada en el código

### 2.1 `execution/src/mt5_utils.py` — medición del offset de reloj del broker

**ARCHIVO:** [execution/src/mt5_utils.py:103-128](execution/src/mt5_utils.py:103)
**FUNCIÓN:** `measure_broker_offset_seconds(symbol, samples=3)`

```python
def measure_broker_offset_seconds(symbol: str, samples: int = 3) -> float:
    """Devuelve el offset (segundos) del servidor del broker respecto a UTC.
    ...
    """
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(...)

    offsets = []
    for _ in range(samples):
        t0 = datetime.now(timezone.utc).timestamp()
        tick = mt5.symbol_info_tick(symbol)
        t1 = datetime.now(timezone.utc).timestamp()
        if tick is None:
            continue
        local_mid = (t0 + t1) / 2.0
        offsets.append(tick.time - local_mid)
    ...
    return sum(offsets) / len(offsets)
```

**EXPLICACIÓN:** Mide cuánto se desvía `tick.time` (el timestamp que entrega MT5 en el tick, hora de "servidor") respecto al reloj UTC real de la máquina que corre el bot (`datetime.now(timezone.utc)`), promediando 3 muestras para amortiguar el jitter de red. `tick.time` es un entero Unix (segundos desde 1970-01-01 UTC), pero **su origen (qué zona horaria usa internamente el servidor del broker) es arbitrario por broker** — este offset es precisamente la forma que tiene el bot de descubrirlo en vivo, sin hardcodear ningún huso horario del broker.

### 2.2 `execution/src/bot.py` — dónde se usa (y dónde NO se usa) ese offset

**ARCHIVO:** [execution/src/bot.py:159-185](execution/src/bot.py:159)
**FUNCIÓN:** `LiveExecutionBot.connect()`

```python
self._offset_seconds = measure_broker_offset_seconds(self.symbol)
...
self._log(f"Offset servidor vs UTC: {self._offset_seconds:+.2f}s | "
          f"digits={info.digits} point={info.point} filling_mode={self._filling_mode}")
```

**EXPLICACIÓN:** El offset se mide una vez al conectar (y en cada reconexión tras un error, ver `run()`), se guarda en `self._offset_seconds` y se loguea. Es **puramente diagnóstico** — se puede verificar en el log de arranque de cada sesión.

**ARCHIVO:** [execution/src/bot.py:75-88](execution/src/bot.py:75)
**FUNCIÓN:** `_corrected_utc_seconds(raw_time_s, offset_seconds)`

```python
def _corrected_utc_seconds(raw_time_s: int, offset_seconds: float) -> int:
    """Resta el offset de reloj del SERVIDOR del broker ... de `raw_time_s`.

    NO se usa para el timestamp de las velas que entra al motor de señal
    (replay_startup()/process_closed_bar(), ver spec-estrategia.md #3.1,
    enmienda 2026-09-04): incluso 1-2s de correccion pueden desplazar una
    vela situada justo en el limite de sesion (ej. 22:00:00) al bloque
    equivocado ... hoy mismo no la llama nadie en el camino de EMA/HTF/señal."""
    return raw_time_s - round(offset_seconds)
```

**EXPLICACIÓN:** Esta función existe y tiene aritmética válida (verificada por `execution/src/test_timestamp_offset.py`, tests A y B), pero **el propio docstring documenta explícitamente que nada en el camino de EMA/HTF/señal la llama**. Confirmado por grep: la única función que la importa es el archivo de test.

**ARCHIVO:** [execution/src/bot.py:200-226](execution/src/bot.py:200), [549-558](execution/src/bot.py:549)
**FUNCIÓN:** `replay_startup()`, `process_closed_bar()`

```python
# replay_startup():
for r in closed:
    # NO se corrige por _offset_seconds aca (enmienda 2026-09-04, ...)
    self.signal_engine.process_bar(int(r["time"]),
                                    float(r["high"]), float(r["low"]), float(r["close"]))

# process_closed_bar():
raw_time = int(r["time"])  # timestamp de apertura tal cual lo entrega copy_rates_* -- SIN corregir
...
t = raw_time
```

**EXPLICACIÓN:** El timestamp que entrega `copy_rates_range`/`copy_rates_from_pos` (`r["time"]`, hora de servidor cruda) se pasa **tal cual, sin restar/sumar el offset**, al motor de señal. Esto es intencional (ver `strategy/htf_session.py`, sección 3 de este informe) y está cubierto por regresión explícita en `test_timestamp_offset.py` (tests C-G).

**ARCHIVO:** [execution/src/bot.py:256-279](execution/src/bot.py:256)
**FUNCIÓN:** `_bars_between(t_from_server, t_to_server)`

```python
def _bars_between(self, t_from_server: int, t_to_server: int) -> int:
    """... t_from/t_to en hora de SERVIDOR sin corregir -- mismo sistema
    que time_setup/time de las ordenes/posiciones de MT5 y que
    copy_rates_range, asi que se comparan directamente sin tocar el offset."""
    if t_to_server <= t_from_server:
        return 0
    dt_from = datetime.fromtimestamp(t_from_server, tz=timezone.utc)
    dt_to = datetime.fromtimestamp(t_to_server, tz=timezone.utc)
    rates = mt5.copy_rates_range(self.symbol, self.timeframe, dt_from, dt_to)
    ...
```

**EXPLICACIÓN:** Usa `o.time_setup`/`p.time` (metadatos nativos de MT5, hora de servidor cruda, sin corregir) directamente contra `copy_rates_range`, que trabaja en el mismo sistema. `datetime.fromtimestamp(..., tz=timezone.utc)` es solo la forma de envolver un entero Unix en un objeto `datetime` para llamar a la API de MT5 — **no es una conversión de zona horaria real**, es una etiqueta UTC puesta sobre un valor que en realidad es "hora cruda de servidor" (ver sección 5).

**ARCHIVO:** [execution/src/bot.py:443-467](execution/src/bot.py:443)
**FUNCIÓN:** `_aciertos_pct()`

```python
date_to = datetime.now(timezone.utc)
date_from = date_to - timedelta(days=AGE_LOOKBACK_DAYS_FOR_ACIERTOS)  # 365
deals = mt5.history_deals_get(date_from, date_to)
```

**EXPLICACIÓN:** Único lugar del bot en vivo que calcula un P&L agregado sobre un historial de deals. Es una **ventana móvil de 365 días** contada desde el instante UTC actual (`datetime.now(timezone.utc)`) — no es "los últimos 365 días calendario" en el sentido de fronteras de medianoche, es literalmente "ahora menos 365×86400 segundos". No hay ningún concepto de día individual aquí, solo un rango continuo.

**ARCHIVO:** [execution/src/bot.py:469-508](execution/src/bot.py:469)
**FUNCIÓN:** `_score_entry()`

```python
dt_to = datetime.fromtimestamp(raw_bar_time, tz=timezone.utc)
dt_from = dt_to - timedelta(seconds=self.bar_seconds * SCORE_LOOKBACK_BARS)
rates = mt5.copy_rates_range(self.symbol, self.timeframe, dt_from, dt_to)
...
time_utc = rates["time"].astype("int64") - round(self._offset_seconds)
```

**EXPLICACIÓN:** Caso interesante y distinto de `process_closed_bar()`: aquí, para alimentar `strategy.scoring` (que sí corrige por offset, es lógica de scoring/diagnóstico, no de señal/HTF), **sí se resta `self._offset_seconds`** a las velas de lookback. Confirma que el offset SE USA en algún lugar del bot — pero no en el camino de señal/armado (ver 2.2 arriba) ni en el de kill switch potencial.

### 2.3 `execution/src/bot.py` — logging (`_log`)

**ARCHIVO:** [execution/src/bot.py:152-155](execution/src/bot.py:152)

```python
def _log(self, msg: str) -> None:
    ts = datetime.now(timezone.utc)
    print(f"[{ts:%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)
    self.events.append({"time": ts.isoformat(), "msg": msg})
```

**EXPLICACIÓN:** Todo el log de eventos del bot (consola y `/events` de la API) usa `datetime.now(timezone.utc)` — hora real UTC de la máquina, no hora de servidor, no hora local. Confirma que "ahora" para el bot, en el único sentido en que el concepto se usa hoy, es UTC real.

### 2.4 `api/app.py` — `/history`, `/start`

**ARCHIVO:** [api/app.py:241-262](api/app.py:241)
**FUNCIÓN:** `history(symbol, magic, days=30)`

```python
@app.get("/history")
def history(symbol: str = DEFAULT_SYMBOL, magic: int = DEFAULT_MAGIC,
            days: int = Query(30, ge=1, le=3650)):
    _require_mt5()
    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=days)
    with mt5_lock:
        sym = _resolve_query_symbol(symbol)
        deals = mt5.history_deals_get(date_from, date_to)
    ...
```

**EXPLICACIÓN:** Mismo patrón que `_aciertos_pct()`: ventana móvil de `days` días desde `datetime.now(timezone.utc)`, sin fronteras de día calendario. Este es el endpoint que consume el panel (`panel/index.html:209` con `days=365`, `panel/history.html:43` con `days=3650`) — **ningún consumidor del bot pide ni recibe "las operaciones de hoy"**, solo "las operaciones de los últimos N días".

**ARCHIVO:** [api/app.py:163](api/app.py:163)
```python
_bot, _thread, _started_at = bot, thread, datetime.now(timezone.utc)
```
**EXPLICACIÓN:** `_started_at` (cuándo arrancó la sesión actual del bot) también se registra en UTC real. Es una variable de módulo en memoria — no se persiste (ver sección 6).

### 2.5 `strategy/htf_session.py` — el único concepto de "sesión/día" que existe hoy, y NO es un día calendario

**ARCHIVO:** [strategy/htf_session.py:87-128](strategy/htf_session.py:87)
**FUNCIÓN:** `bucket_start_utc_seconds(time_utc_s, periodos_min, session_anchor_utc_min=22*60)`

```python
MINUTES_PER_DAY = 24 * 60
_DAY_LEN_S = MINUTES_PER_DAY * 60
DEFAULT_SESSION_ANCHOR_UTC_MIN = 22 * 60  # 22:00 UTC

def bucket_start_utc_seconds(time_utc_s, periodos_min, session_anchor_utc_min=DEFAULT_SESSION_ANCHOR_UTC_MIN) -> int:
    anchor_s = session_anchor_utc_min * 60
    block_len_s = periodos_min * 60
    since_session_start = (time_utc_s - anchor_s) % _DAY_LEN_S
    session_start = time_utc_s - since_session_start
    block_index = since_session_start // block_len_s
    return session_start + block_index * block_len_s
```

**EXPLICACIÓN — la más importante de este informe:** Esto SÍ define un "día de sesión" de 1440 minutos (`MINUTES_PER_DAY`), anclado a **22:00 UTC** (medido empíricamente contra TradingView, ver docstring del módulo líneas 1-84, no una constante inventada). Pero **este "día de sesión" no es un día calendario ni un concepto de P&L**: es exclusivamente la unidad sobre la que se trocean los "bloques HTF" (`periodos_htf_min`, ej. 800min) que usa el armado de EMA/pivotes. Con `periodos_min=800`:

```
bloque 1: 22:00 UTC -> 11:20 UTC (800min, completo)
bloque 2: 11:20 UTC -> 22:00 UTC (640min, truncado por el limite de sesion)
bloque 3 (dia siguiente): 22:00 UTC -> 11:20 UTC ... se repite
```

Es decir: dentro de cada "día de sesión" de 22:00 a 22:00 UTC hay **dos bloques HTF de duración distinta** (800min y 640min), no una única frontera diaria. Además, el propio docstring (líneas 60-67) deja constancia de que **no está validado si 22:00 UTC se mantiene todo el año** (posible corrimiento por DST de EEUU/UE) — es una incertidumbre documentada, no un supuesto oculto.

`strategy/live_signal.py:87-89` confirma que `_cur_bucket` (el estado que usa el motor de señal) es exactamente el valor devuelto por esta función — no hay ninguna otra noción de "bloque"/"día" en el motor de señal.

### 2.6 `execution/src/paths.py`, `execution/src/score_store.py` — persistencia (sin fecha)

Ver sección 6.

### 2.7 `packaging/control_window.py` — única excepción a "todo es UTC" (irrelevante para trading)

**ARCHIVO:** [packaging/control_window.py:112](packaging/control_window.py:112)

```python
def _install_log_redirection():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _log_dir() / f"bot_{ts}.log"
```

**EXPLICACIÓN:** Único uso de `datetime.now()` **naive** (hora local del sistema, sin timezone) en todo el repo. Se usa solo para nombrar el archivo de log de la sesión de la ventana de control (Tkinter) — no toca ninguna lógica de trading, P&L, ni fronteras de día. Se documenta por completitud (el punto 2 de la auditoría pedía "todos los usos"), pero no es candidato a reutilizar para BOT-032.

### 2.8 `backtests/src/download.py` — contraste: SÍ corrige offset (contexto distinto)

**ARCHIVO:** [backtests/src/download.py:75-79](backtests/src/download.py:75)

```python
"""Persiste el historial crudo + una columna time_utc corregida por offset."""
df["time_utc"] = (df["time_server"] - round(offset_seconds)).astype("int64")
```

**EXPLICACIÓN:** A diferencia del motor en vivo, la ingesta de historial para investigación/backtest sí aplica la corrección de offset al guardar `time_utc`. Es un módulo separado, con un propósito distinto (dataset para análisis offline), y **no es el código que va a alimentar BOT-032** (que necesariamente lee de MT5 en vivo vía `history_deals_get`, camino de `bot.py`/`api/app.py`). Se documenta como evidencia de que existe más de una convención de "corrección de offset" en el repo, relevante para el riesgo de la sección 8.

---

## 3. Manejo actual de UTC / broker / hora local

| Dato | Origen | ¿Se corrige por offset? | ¿Qué timezone queda? |
|---|---|---|---|
| `r["time"]` de `copy_rates_range`/`copy_rates_from_pos` (velas) | MT5, hora de servidor cruda | **No** (decisión explícita 2026-09-04) | Hora de servidor sin corregir, tratada como si fuera UTC para el cálculo de bloque HTF |
| `o.time_setup` / `p.time` (órdenes/posiciones) | MT5, hora de servidor cruda | No (nunca se corrigió) | Hora de servidor sin corregir |
| `d.time` de `history_deals_get()` (deals) | MT5, hora de servidor cruda | No (no se toca en `_aciertos_pct()` ni en `/history`) | Hora de servidor sin corregir |
| `tick.time` (tick en vivo) | MT5, hora de servidor cruda | Solo se usa para *medir* el offset (`measure_broker_offset_seconds`), no se corrige al consumirlo en `_watch_pending_live()` | Hora de servidor sin corregir |
| `datetime.now(timezone.utc)` (logs, `/history` `date_from/date_to`, `_started_at`, `_aciertos_pct` `date_to`) | Reloj de la máquina que corre el bot | N/A (ya es UTC real) | UTC real |
| Velas usadas para scoring (`_score_entry`) | MT5, hora de servidor cruda | **Sí** (`rates["time"] - offset_seconds`) | Corregida hacia UTC real (aproximado) |
| Log de sesión de la ventana de control | Reloj de la máquina | N/A | Hora local del sistema (naive) |

**Conclusión de esta sección:** el bot **no usa "hora local de la PC" para nada relacionado con trading**. Usa dos sistemas de tiempo en paralelo, ambos con sello "UTC" en el código pero de origen distinto:
1. **UTC real** (`datetime.now(timezone.utc)`): logs, ventanas de `/history`, `_aciertos_pct()`, `_started_at`.
2. **Hora de servidor MT5 sin corregir, tratada como si fuera UTC** (`r["time"]`, `time_setup`, `time`, `d.time`): velas, órdenes, posiciones, deals — todo el camino de señal/armado/concurrencia/watchers.

La distancia entre ambos sistemas es el offset medido por `measure_broker_offset_seconds()` (¬-1.86s en la única medición registrada en el código, ver `test_timestamp_offset.py:8-9` — negligible en ese momento, pero **no hay garantía de que se mantenga así**, ver sección 8).

---

## 4. ¿Existe actualmente el concepto de "día"?

**No, en el sentido de "día de trading" para P&L/límites/reset.** Lo que existe:

- Un **"día de sesión" de 1440 minutos anclado a 22:00 UTC**, pero su único uso es trocear bloques HTF de duración variable (`strategy/htf_session.py`) — no resetea ningún contador de P&L ni estadística, y de hecho el motor de señal (`armado_venta`/`armado_compra` en `strategy/live_signal.py`) puede persistir a través de ese límite sin resetearse (el reset de armado depende de la lógica de pivotes/EMA, no de cruzar las 22:00 UTC).
- Ninguna estructura de datos, variable, ni endpoint que agregue P&L "de hoy" — todo lo que agrega P&L (`_aciertos_pct()`, `/history`) usa ventanas móviles de N días, nunca fronteras de medianoche de ningún tipo.
- Ningún reset diario de ningún estado (contadores, flags, snapshots).

---

## 5. Manejo de timestamps MT5

Contestando punto por punto lo pedido:

- **¿En qué timezone vienen originalmente?** Todos los timestamps que entrega el paquete `MetaTrader5` (`copy_rates_*["time"]`, `tick.time`, `order.time_setup`, `position.time`, `deal.time`) son **enteros Unix en la hora del SERVIDOR del broker**, no UTC real per se (por eso hace falta `measure_broker_offset_seconds()` para saber cuánto se desvían de UTC).
- **¿El bot aplica algún offset?** Depende del consumidor:
  - Velas → señal/HTF (`process_closed_bar`, `replay_startup`): **NO**.
  - Órdenes/posiciones → watchers de tiempo (`_bars_between`, `_watch_open`, `_watch_pending`): **NO** (se comparan tiempos de servidor contra tiempos de servidor, consistente por diseño).
  - Deals → `_aciertos_pct()`, `/history`: **NO**.
  - Velas → scoring (`_score_entry`): **SÍ**.
  - Tick en vivo → `_watch_pending_live()`: **NO** (usa `tick.bid`, no compara tiempo).
- **¿Cómo calcula ese offset?** Diferencia promedio (3 muestras) entre `tick.time` y el punto medio de dos lecturas de `datetime.now(timezone.utc).timestamp()` alrededor de la llamada a `symbol_info_tick()` (ver 2.1).
- **¿A qué timezone quedan normalizados finalmente?** En el camino de señal/watchers/`_aciertos_pct`/`/history`: **ninguna normalización** — quedan en hora de servidor cruda, simplemente envuelta en objetos `datetime` con `tzinfo=timezone.utc` como etiqueta (no como conversión real). En el camino de scoring: corregidos hacia una aproximación de UTC real.
- **¿Diferencias entre velas, órdenes, deals y posiciones?** No en cuanto a corrección (ninguno de los cuatro se corrige en el camino principal) — todos comparten el mismo sistema de "hora de servidor sin tocar", lo cual los hace **mutuamente consistentes entre sí** (por eso `_bars_between` puede comparar `time_setup` de una orden contra `r["time"]` de una vela sin problema).

---

## 6. Persistencia y reinicios

Búsqueda de todo estado persistente en disco (`execution/src/paths.py` define las dos raíces: `app_root()` reemplazable en upgrade, `user_data_root()` persistente):

- **`execution/src/score_store.py`** ([líneas 29, 37-45](execution/src/score_store.py:29)): único dato que persiste en disco (`user_data_root()/execution/data/scores/{symbol}_{magic}.jsonl`). Es un registro `{ticket: score}` (calificación Divergencia/Tendencia/CVP de cada orden) — **no tiene ningún campo de fecha/día**, ni se indexa ni se filtra por fecha. Sobrevive reinicios y upgrades por diseño (para no perder el historial de calificaciones), pero no es un estado "de un día".
- **`_started_at`** ([api/app.py:55, 163](api/app.py:55)): variable de módulo en memoria (`datetime | None`), se pierde en cada reinicio del proceso (no hay ningún `save`/`load`).
- **`_known_orders` / `_known_positions`** ([bot.py:136-137, 193-198](execution/src/bot.py:136)): snapshots en memoria del objeto `LiveExecutionBot`, se reconstruyen desde cero contra MT5 en cada `connect()` (`_seed_known_state()`) — no persisten, y no tienen fecha asociada.
- **No hay ningún archivo de configuración, base de datos local, ni variable de entorno que registre "el día actual", "P&L acumulado hoy", ni un timestamp de "último reset diario".**

**Conclusión:** un reinicio del proceso/aplicación hoy no afecta ningún estado relacionado con fechas o tiempo simplemente porque **no existe ningún estado de ese tipo para afectar**. Todo lo que sobrevive un reinicio (`score_store`) es agnóstico de fecha; todo lo demás vive en memoria y se recalcula contra MT5/broker al reconectar.

---

## 7. Implicaciones para BOT-032

(Descriptivo, no prescriptivo — no se decide implementación en esta auditoría.)

- El bot ya tiene, en `_aciertos_pct()` y en `/history`, el patrón exacto de "traer deals cerrados de MT5 en una ventana de tiempo y sumar `profit+swap+commission+fee`" (ver 2.2 y 2.4) — es el bloque de código más cercano a lo que necesitaría un cálculo de P&L realizado.
- Ninguno de esos dos usa fronteras de día calendario hoy — ambos son ventanas móviles de N días. Introducir un Kill Switch con P&L "del día" sería la **primera vez** que el bot necesita una frontera de día calendario real.
- El único timezone que el bot ya trata como "verdad de reloj" en todo el código (logs, `_started_at`, ventanas de `/history`) es **UTC real** (`datetime.now(timezone.utc)`) — no hora de servidor, no hora local.
- Los timestamps de los `deals` (`d.time`, usados para identificar qué operación pertenece a qué período) son hora de servidor cruda, **igual que todo lo demás que el bot ya consume sin corregir** (velas de señal, `time_setup`, `time` de posiciones) — es decir, tratarlos como si fueran UTC (sin restar el offset) es coherente con cómo el resto del bot ya trata esos mismos objetos MT5, aunque no sea UTC real en sentido estricto.

---

## 8. Riesgos / casos borde

- **Ambigüedad de qué es "UTC" en el código:** el bot usa `datetime.fromtimestamp(x, tz=timezone.utc)` tanto para timestamps que son UTC real (los que salen de `datetime.now(timezone.utc)`) como para timestamps que son hora de servidor sin corregir (los que salen de MT5). El código es internamente consistente (porque nunca mezcla ambos sistemas en una misma comparación), pero **el nombre de la etiqueta (`timezone.utc`) no garantiza que el valor sea UTC real** — es una fuente de confusión para quien lea el código sin este contexto.
- **Offset no garantizado estable:** `measure_broker_offset_seconds()` se mide en cada `connect()`/reconexión, no es una constante. El único valor medido y registrado en el repo es -1.86s (negligible), pero el propio código (`spec-live-execution.md:25`) documenta que "el offset puede correr con el horario de verano del bróker" — un broker que cambie de convención (o un cambio de DST) podría desviar la hora de servidor de UTC real por una cantidad no trivial, sin que nada en el camino de señal/deals lo detecte automáticamente (solo queda logueado).
- **Ancla de sesión HTF (22:00 UTC) no validada contra DST:** documentado explícitamente en `strategy/htf_session.py:60-67` como supuesto pendiente — si BOT-032 terminara reutilizando esa ancla de sesión en vez de una frontera UTC pura de medianoche, heredaría esa misma incertidumbre.
- **Inconsistencia entre módulos del repo:** `backtests/src/download.py` sí corrige el offset al persistir `time_utc`, mientras que el motor en vivo deliberadamente no lo hace para señal/HTF. Si en el futuro se comparara P&L "diario" calculado por distintas rutas del repo (viva vs. offline) sin tener esto presente, podrían no coincidir exactamente en los bordes de una frontera de día.
- **Broker vs. Python vs. bot — interpretaciones de "día":** hoy, ninguno de los tres impone una interpretación activa (el broker entrega timestamps crudos, Python no aplica ninguna zona horaria implícita porque todo es UTC-aware explícito, y el bot no define ningún "día"). El riesgo aparece recién **cuando se introduzca** una frontera de día para BOT-032: si esa frontera se define en hora de servidor cruda (sin saber que no es UTC real) en vez de en UTC real explícito, un deal ejecutado cerca de medianoche podría clasificarse en el día equivocado según cuál de los dos relojes se use — exactamente el mismo tipo de riesgo que ya se documentó y mitigó para el bloque HTF (ver `strategy/htf_session.py` y `test_timestamp_offset.py`).
- **`history_deals_get()` sin filtro de `magic` en el deal de cierre:** documentado ya en `api/app.py:252-259` — el deal de cierre de una posición cerrada manualmente desde el terminal no hereda el `magic` de la posición. Cualquier cálculo de P&L diario que filtre por `magic` deal-por-deal (en vez de por posición, como ya hace `/history`) repetiría ese bug ya conocido y corregido en otro lugar del repo.

---

## 9. Conclusión

**A. ¿Podemos afirmar que el bot actualmente define un "día de trading"?**
No. Existe un "día de sesión" de 1440 minutos anclado a 22:00 UTC (`strategy/htf_session.py`), pero es exclusivamente una unidad de troceo para bloques HTF de la estrategia — no tiene ninguna relación con P&L, límites, estadísticas ni resets diarios.

**B.** (No aplica — la respuesta a A es "no".)

**C. ¿Qué convención temporal usa el bot que sería coherente reutilizar para BOT-032?**
UTC real (`datetime.now(timezone.utc)`) es la única convención de "ahora"/reloj que el bot ya usa de forma consistente para todo lo que no es señal/HTF/watchers de barras (logs, `_started_at`, ventanas de `/history`, `_aciertos_pct()`). Para los timestamps de los deals en sí (`d.time`), el precedente ya sentado en todo el bot es tratarlos sin corrección de offset — igual que se tratan velas, `time_setup` y `time` de posiciones en el camino de señal.

**D. ¿Qué timestamps deberíamos usar para determinar qué deals pertenecen al día actual, sin introducir una convención distinta al resto del bot?**
`deal.time` (o `deal.time_msc` si se necesita precisión de milisegundos), tal como los entrega `history_deals_get()`, sin restarle `_offset_seconds` — exactamente el mismo tratamiento que ya reciben en `_aciertos_pct()` y en `/history`. La frontera de "día" en sí (si se define en UTC real de medianoche a medianoche, o en algún otro ancla) es una decisión de diseño que esta auditoría deliberadamente no toma.

**E. ¿Hay riesgo de que MT5, el broker, Python y el bot interpreten distinto la frontera del día?**
Sí, potencialmente — ver sección 8. Hoy el riesgo es latente (no hay frontera de día que interpretar), pero se activa en cuanto BOT-032 defina una. El offset medido hoy es negligible (-1.86s), pero no hay ninguna garantía en el código de que se mantenga así indefinidamente, y el ancla de sesión HTF de 22:00 UTC está explícitamente documentada como no validada contra cambios de horario de verano.

**F. ¿El reinicio del proceso/aplicación afecta algún estado relacionado con fechas o tiempo?**
No, porque no existe ningún estado de ese tipo hoy (ver sección 6). El único dato persistente en disco (`score_store`) es agnóstico de fecha; todo lo demás se recalcula desde MT5 en cada reconexión.
