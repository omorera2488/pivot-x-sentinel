# BOT-032 — Kill switch / máxima pérdida diaria

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Commit base:** `1070982` (`docs(backlog): close BOT-008 optimization line, freeze candidates for OOS`)
**Commit de esta tarea:** el commit que introduce este mismo archivo — mensaje `feat: BOT-032 daily loss kill switch` en `main` (hash exacto queda fijado recién al commitear; ver `git log --oneline -1` sobre este commit). El release `v1.1.0` (VERSION + CHANGELOG cortado) queda en un commit posterior separado, `release: v1.1.0 -- ...`.

Este documento es **autocontenido**: contiene contexto, diseño final, cómo se calculó cada cosa, resultado real de los tests, y el estado de git/versión, para que otra persona (o ChatGPT recibiendo solo este archivo) entienda qué se hizo sin depender de la conversación de Claude Code.

---

## Resumen ejecutivo

Se implementó BOT-032: un kill switch que bloquea la colocación de **operaciones nuevas** cuando el P&L neto realizado del día operativo alcanza un límite configurable, sin tocar la estrategia ni las posiciones ya abiertas. Antes de escribir código se hicieron dos auditorías de solo lectura (ver `docs/reports/AUDIT-BOT032_day_definition.md`) que establecieron que el bot **no tenía ningún concepto de "día"** — solo ventanas móviles de N días — y que el calendario del panel agrupaba por hora local del navegador. Ambos huecos se resolvieron con un **día operativo timezone-aware** definido en el backend (`America/Costa_Rica` vía `zoneinfo`), consumido tanto por el kill switch como por el calendario, para que nunca puedan mostrar números distintos por usar fronteras horarias diferentes.

El bot **nunca se detiene** por esto — el `run()` sigue vivo, las posiciones abiertas siguen gestionándose con normalidad (SL/TP, `orden_viva`, `caduca`, `max_bars_trade`); solo se bloquea `_place_order()`. El P&L se recalcula siempre desde `mt5.history_deals_get()` (nunca un contador en memoria), reusando la reconciliación segura que ya tenía `GET /history` para deals de cierre manual sin magic propio. El override diario persiste en disco (sobrevive reinicios/upgrades) y se invalida solo por comparación de fecha, sin timers.

**12 de 12 tests pasan** (9 preexistentes + 3 nuevos archivos). No se tocó ninguna línea de `strategy/` (EMA, HTF, pivotes, armado, scoring, señal) — cero riesgo de regresión de estrategia por construcción, no solo por test.

---

## Contexto

- `BACKLOG.md` (categoría "Gestión de riesgo") tenía a BOT-032 como próxima US activa, con 3 preguntas de diseño explícitamente abiertas: cómo medir la "pérdida acumulada", qué pasa con las posiciones abiertas, y dónde vive la config/cómo se expone el estado. Las tres se resuelven en este documento (ver también la entrada actualizada de `BACKLOG.md`).
- Antes de tocar código se hicieron dos auditorías de solo lectura, a pedido explícito del usuario:
  1. **`docs/reports/AUDIT-BOT032_day_definition.md`** — determinó que el bot usa dos sistemas de tiempo en paralelo (UTC real para logs/`/history`/`_aciertos_pct`; hora de servidor MT5 sin corregir para velas/órdenes/posiciones/deals), que **no existe ningún concepto de "día"** hoy, y que `/history` (`api/app.py`) ya resuelve correctamente el bug de "deal de cierre manual sin magic propio" mientras que `_aciertos_pct()` (`execution/src/bot.py`) NO lo resuelve.
  2. Comprobación puntual de `panel/calendar.html`: agrupa por **hora local del navegador/PC** (`new Date(t.time*1000).getFullYear()/getMonth()/getDate()`, todos getters en timezone local de JavaScript) — confirmado con el ejemplo pedido: un deal a las `2026-09-15 02:00 UTC` se mostraba en el día 14 en una PC configurada en Costa Rica (UTC-6), no el 15.
- El prompt de implementación (`Prompt — BOT 032 Kill Switch Máxima pérdida diaria.md`) pidió explícitamente: no modificar la estrategia, reusar la identificación segura de `/history`, día operativo timezone-aware definido en backend (no "UTC-6" hardcodeado), calendario y kill switch usando la MISMA definición de día, no cerrar posiciones abiertas, override diario persistente, fail-safe explícito, y el flujo completo de versión/release/git al final.
- Se usó **plan mode** antes de escribir código: se lanzaron 3 agentes de exploración en paralelo (config/UI existente, versionado/release/instalador, tests/reconciliación de deals/documentación) y se le hicieron 2 preguntas de diseño al usuario antes de empezar — ver "Decisiones confirmadas" abajo.

---

## Decisiones confirmadas por el usuario antes de implementar

1. **El kill switch nunca detiene el `run()` del bot.** Al alcanzar la pérdida máxima: se bloquean únicamente nuevas operaciones/órdenes, el loop sigue activo, las posiciones abiertas mantienen toda su gestión normal (SL/TP, `orden_viva`, `caduca`, `max_bars_trade`, watchers). El panel muestra "Detenido por máxima pérdida diaria" como estado distinto. Al confirmar "Iniciar de todas formas" se levanta el bloqueo y se activa el override por el resto del día operativo. Se pidió agregar un guard antes del envío final de cualquier nueva orden para evitar race conditions.
2. **Flujo completo sin pausas adicionales**, siempre que todo pase: instalador nuevo, VERSION/CHANGELOG/Release Notes, revisión de `git status`/`git diff`, commit en `main`, tag, push de `main` y del tag. Si algo falla, no se hace commit/tag/push y se reporta el problema puntual.

---

## Diseño final

### 1. Día operativo — `execution/src/operating_day.py` (nuevo)

```python
DEFAULT_OPERATING_TIMEZONE = "America/Costa_Rica"

def operating_day_bounds_utc(now_utc, tz_name=DEFAULT_OPERATING_TIMEZONE):
    tz = ZoneInfo(tz_name)
    local_now = now_utc.astimezone(tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = local_midnight.astimezone(timezone.utc)
    end_utc = (local_midnight + timedelta(days=1)).astimezone(timezone.utc)
    return start_utc, end_utc, local_midnight.date()
```

Un día operativo es `[00:00:00, 00:00:00 del día siguiente)` hora LOCAL de una timezone IANA, convertido de vuelta a UTC real — todo el cálculo lo hace `zoneinfo` (stdlib), nunca se resta "6 horas" a mano. Esto es lo que permite que la misma arquitectura siga siendo correcta si algún día se usa otra timezone con horario de verano, sin tocar aritmética.

**Riesgo real detectado y resuelto:** Windows no trae la base de datos IANA como Linux/macOS. Se verificó en esta misma máquina que un Python 3.10 sin el paquete `tzdata` instalado lanza `ZoneInfoNotFoundError` al pedir `ZoneInfo("America/Costa_Rica")`. Se agregó `tzdata` a `execution/requirements.txt` y explícitamente a `HIDDEN_IMPORTS` en `packaging/pivot_x_sentinel.spec` (el hook `hook-zoneinfo.py` de `pyinstaller-hooks-contrib` ya lo agrega solo en Windows, pero se dejó explícito para no depender en silencio de esa cadena de hooks de terceros, mismo criterio que las líneas de `uvicorn` ya existentes en ese archivo). **Verificado con una build real de PyInstaller** (ver sección "Build del instalador" abajo): el hook `hook-tzdata.py` corrió y los archivos de zona horaria, incluido `America/Costa_Rica`, quedaron en `dist/pivot-x-sentinel/_internal/tzdata/zoneinfo/`.

### 2. Identificación segura de deals propios — `execution/src/mt5_utils.py` (extendido)

Se extrajo la lógica de dos pasadas que vivía inline en `api/app.py::history()` a una función pura y reusable:

```python
def filter_own_deals(deals, magic, symbol):
    if not deals:
        return []
    mis_posiciones = {d.position_id for d in deals
                       if d.entry == mt5.DEAL_ENTRY_IN and d.magic == magic and d.symbol == symbol}
    return [d for d in deals if d.position_id in mis_posiciones]
```

Mismo comportamiento exacto que antes (ancla en el deal de apertura para no perder el deal de cierre manual sin magic propio). `api/app.py::history()` ahora llama a esta función en vez de repetir el comprehension — cero cambio de contrato, confirmado por regresión (`api/test_start_mt5_validation.py` sigue pasando sin cambios). Esta extracción es la única "refactorización" del código existente en toda la tarea, y es la mínima necesaria para que el kill switch reuse la lógica segura sin duplicar (y potencialmente desincronizar) el bug ya resuelto. `_aciertos_pct()` (que tiene el filtro más simple, sin esta protección) **no se tocó** — queda fuera de alcance de esta US.

### 3. Cálculo del P&L diario — `execution/src/kill_switch.py` (nuevo)

```python
POSITION_LOOKBACK_DAYS = 60

def daily_realized_pnl(symbol, magic, day_start_utc, day_end_utc, lookback_days=POSITION_LOOKBACK_DAYS):
    wide_from = day_end_utc - timedelta(days=lookback_days)
    deals = mt5.history_deals_get(wide_from, day_end_utc)
    if deals is None:
        return None
    own = filter_own_deals(deals, magic, symbol)
    closed_today = [d for d in own
                    if d.entry == mt5.DEAL_ENTRY_OUT and day_start_utc.timestamp() <= d.time < day_end_utc.timestamp()]
    return sum((d.profit or 0.0) + (d.swap or 0.0) + (d.commission or 0.0) + getattr(d, "fee", 0.0)
               for d in closed_today)
```

Dos ventanas distintas a propósito: una AMPLIA (60 días) para poder identificar la posición de una operación que cerró hoy pero abrió antes de hoy (si no, `filter_own_deals` no vería el deal de apertura y perdería la atribución), y una ANGOSTA (el día operativo) para decidir qué deals de cierre cuentan como "realizados hoy". Nunca usa P&L flotante de `positions_get()`. Devuelve `None` (nunca `0.0`) si MT5 no responde.

### 4. Persistencia del override — `execution/src/kill_switch_store.py` (nuevo)

Un archivo JSON por `{symbol}_{magic}` bajo `user_data_root()/execution/data/kill_switch/` (mismo mecanismo de `execution/src/score_store.py`, sobrevive reinicios de la app y upgrades del instalador porque `packaging/installer.iss::CurStepChanged` solo borra `_internal`, nunca `user_data_root()`). A diferencia de `score_store` (JSONL append-only, un log), acá solo importa el ÚLTIMO valor — un JSON simple sobreescrito:

```json
{"override_operating_date": "2026-09-15"}
```

`load_override_date()`/`record_override()`. El P&L **nunca** se persiste acá — se recalcula siempre desde MT5. La validez del override se deriva comparando esta fecha contra la fecha operativa actual en cada evaluación — un día operativo nuevo lo invalida solo, sin ningún timer.

### 5. Guard en el motor — `execution/src/bot.py`

- `LiveExecutionBot.__init__` agrega `daily_max_loss_enabled: bool = False, daily_max_loss_usd: float | None = None` como parámetros **nombrados explícitos** (no parte de `**param_overrides`/`StrategyParams` — es protección del motor de ejecución, no un parámetro de estrategia; `strategy/engine.py` y `strategy/profiles.py` quedan intocados).
- `_refresh_kill_switch_state()`: si `daily_max_loss_enabled` es `False`, no hace nada (costo cero, comportamiento actual intacto). Si está activado, calcula el día operativo, pide `daily_realized_pnl()`, actualiza `_kill_switch_triggered` (fail-safe si `None`), y refresca `_kill_switch_override_active` comparando la fecha del override persistido contra la fecha operativa actual. Loguea SOLO en transiciones de estado (no en cada loop, ver `[BOT-032]` en los mensajes).
- **Punto exacto del guard** (pedido explícito del usuario, punto 18 del prompt): en `run()`, `_refresh_kill_switch_state()` se llama **ANTES** de `poll_once()`, dentro del mismo bloque `with mt5_lock:` — así cualquier orden que se coloque en ESE ciclo ya usó el P&L más fresco disponible antes de tocar el bróker. Dentro de `process_closed_bar()`, el guard (`_kill_switch_blocking()`) se agregó junto al chequeo de concurrencia existente, con el mismo estilo de log ("Señal descartada: kill switch de perdida diaria activo"). El resto de `process_closed_bar()` (EMA/HTF/armado vía `signal_engine.process_bar`, `_watch_open`, `_watch_pending`) sigue ejecutándose exactamente igual, disparado o no.
- **Latencia residual documentada:** una pérdida realizada DENTRO del mismo ciclo (ej. un cierre por tiempo en `_watch_open`, que corre después del refresh) recién se refleja en el ciclo siguiente — como máximo `poll_interval_s` (10s típico). Es el mismo orden de magnitud que la diferencia ya existente entre `_watch_pending` (por vela) y `_watch_pending_live` (por tick) — no hay forma de tener P&L perfectamente instantáneo sin consultar MT5 después de cada watcher individual, y ese nivel de latencia ya es intrínseco al resto del bot.
- `kill_switch_status()` expone el snapshot completo para `GET /status`.

### 6. Gate en `api/app.py`

No existe ningún mecanismo de configuración persistida server-side hoy (confirmado por la exploración previa: todo lo que no es `StrategyParams` viaja en el body de `POST /start` + `localStorage` del lado del navegador). Por eso `daily_max_loss_enabled`/`daily_max_loss_usd`/`acknowledge_daily_loss_override` son campos nuevos de `StartRequest`, validados con un `model_validator` de Pydantic (monto obligatorio y `> 0` si está habilitado — 422 si no).

`_kill_switch_gate(req)` corre **dentro de `/start`, antes de crear el `LiveExecutionBot`**:

1. Si está desactivado, no hace nada (ni siquiera llama a MT5).
2. Si está activado: resuelve el símbolo real, calcula el día operativo, pide el P&L.
3. Si el P&L es `None` (fail-safe) o `<= -daily_max_loss_usd` (disparado): revisa si ya hay un override válido para HOY.
   - Sin override válido y sin `acknowledge_daily_loss_override` → `HTTPException(409, detail={reason, operating_date, operating_timezone, realized_daily_pnl, daily_max_loss_usd})` — **no se crea el bot, no se lanza ningún thread**. Esto resuelve directamente el caso "arranque con el límite ya alcanzado" (punto 14 del prompt): un reinicio de la app no puede evadir la protección, porque el P&L se recalcula desde MT5 en ese mismo instante, nunca desde un contador en memoria.
   - Con override válido o `acknowledge_daily_loss_override=True` → graba/confirma el override (idempotente) y deja seguir el flujo normal de `/start`.

`GET /status` agrega `operating_timezone` (siempre presente, aunque no haya bot corriendo esta sesión) y `kill_switch` (el snapshot de `kill_switch_status()`, o `null` si `_bot is None`).

### 7. Panel

- **`panel/config.html`**: nuevo par checkbox ("Activar máxima pérdida diaria") + número (USD), siguiendo EXACTAMENTE el patrón visual/JS ya usado para `una_operacion_a_la_vez`/`max_concurrent_por_direccion` (mismo markup `.setting`, mismo patrón de habilitar/deshabilitar el input numérico, agregado a la constante `FIELDS`). Validación duplicada del lado del cliente (mensaje directo, sin el prefijo engañoso de "No se pudo conectar con la API" que usa `showError()` para errores de conectividad real).
- **`panel/app.js`**: `apiPost()` ahora conserva el `detail` estructurado de un 409 en `err.detail` (antes solo generaba un string, y un objeto se convertía en `"[object Object]"`) — cambio mínimo y retrocompatible, ningún llamador que solo lea `err.message` se rompe.
- **`panel/index.html`**: el click en "Iniciar bot" ahora pasa por `attemptStart()`; si el backend responde 409 con `reason: "daily_loss_kill_switch"`, se muestra un bloque de confirmación (mismo estilo visual que el `err-banner` existente) con los números reales y dos botones ("Cancelar" / "Iniciar de todas formas"). Un banner NUEVO y separado (no reemplaza el badge ACTIVO/DETENIDO existente, porque el proceso puede seguir corriendo) muestra "DETENIDO — Máxima pérdida diaria alcanzada" + P&L + límite mientras `kill_switch.triggered && !kill_switch.override_active`.
- **`panel/calendar.html`**: reemplazado el agrupamiento por `new Date(...).getFullYear()/getMonth()/getDate()` (hora LOCAL del navegador) por un helper `operatingDateParts()` basado en `Intl.DateTimeFormat(..., {timeZone: tz})`, con `tz` obtenido de `GET /status`'s `operating_timezone` — el backend es la única fuente de verdad, la timezone del navegador nunca decide la frontera. Se aplica tanto al agrupamiento de trades por día como al mes inicial mostrado al cargar la página.

---

## Cómo se calcula el P&L diario (resumen para quien solo lea esta sección)

`profit + swap + commission + fee` de cada deal de CIERRE (`DEAL_ENTRY_OUT`) de una posición identificada como propia (mismo criterio que `GET /history`: el deal de APERTURA de esa posición tiene el `magic`+`symbol` del bot, sin importar qué `magic` traiga el deal de cierre — así una posición cerrada a mano desde el terminal MT5 sigue contando), cuyo `time` cae dentro de `[00:00:00, 24:00:00)` hora local de `America/Costa_Rica`, convertido a UTC real. Ganancias y pérdidas del mismo día se compensan (ejemplo verificado en test: `+$120 -$300 -$220 = -$400`). Nunca incluye P&L flotante de posiciones abiertas. Se recalcula desde cero en cada evaluación — no hay ningún acumulador que sobreviva en memoria.

---

## Cómo se evita depender del timezone del navegador

El backend expone `operating_timezone` (el string IANA, ej. `"America/Costa_Rica"`) en `GET /status` sin necesitar que haya un bot corriendo. El panel (`calendar.html`) lo lee UNA vez y lo pasa explícitamente a `Intl.DateTimeFormat(..., {timeZone: operating_timezone})` para cada timestamp — los navegadores modernos traen la base de datos IANA completa vía ICU, así que esto funciona sin importar la configuración regional/horaria del sistema operativo del cliente. Cambiar la timezone del navegador/SO no cambia ni un solo día calculado, porque el cálculo nunca usa el reloj/zona del navegador — solo usa el string que le mandó el backend.

---

## Punto exacto donde se bloquean nuevas operaciones

`execution/src/bot.py::process_closed_bar()`, en la rama donde ya se determinó que hay una señal válida y hay cupo de concurrencia — justo antes de calificar/colocar la orden:

```python
elif self._kill_switch_blocking():
    self._log("Señal descartada: kill switch de perdida diaria activo")
else:
    ...  # _score_entry() + _place_order()
```

`_kill_switch_blocking()` lee el estado ya refrescado al INICIO del ciclo actual (`_refresh_kill_switch_state()`, llamado en `run()` antes de `poll_once()`) — nunca se recalcula el P&L en medio del procesamiento de una barra. Es el único punto de todo el código que llama a `_place_order()` para una señal nueva (los watchers de timeout/invalidación de pendientes/posiciones abiertas son código completamente separado y no pasan por este guard).

---

## Qué ocurre con operaciones abiertas

Nada distinto de lo que ya pasaba: `_watch_open()` (cierre por `max_bars_trade`) y `_watch_pending()`/`_watch_pending_live()` (invalidación de pendientes por `tpAntes`/`muerto`/`caduca`) se siguen llamando en cada ciclo, disparado o no el kill switch — el guard nuevo está estrictamente después de esas llamadas en `process_closed_bar()` y solo afecta la rama de "colocar una orden nueva". Ninguna posición se cierra, ningún SL/TP se modifica, ninguna orden pendiente se cancela por el solo hecho de que el kill switch se disparó.

---

## Cómo funciona el popup y el override

1. Usuario activa el kill switch en Configuración y pulsa "Iniciar bot".
2. `POST /start` evalúa el P&L del día operativo actual ANTES de crear el bot. Si ya está por debajo del límite y no hay un override válido para hoy, responde `409` con los números reales — el panel muestra el popup de confirmación en vez de arrancar.
3. "Cancelar" solo cierra el popup — el bot sigue detenido, no se graba nada.
4. "Iniciar de todas formas" reintenta `POST /start` con `acknowledge_daily_loss_override: true` — el backend graba el override (fecha operativa actual) y arranca el bot normalmente.
5. Mientras el override siga siendo válido para el día operativo actual, un P&L que empeore después NO vuelve a disparar el popup, ni un ciclo de `/stop` + `/start` posterior ese mismo día (la validez se decide comparando la fecha del override contra la fecha operativa actual, no reconstruyendo el evento).
6. Al cambiar de día operativo, la fecha guardada deja de coincidir con la actual automáticamente — el override deja de aplicar sin ninguna acción explícita de "reset".

---

## Cómo se persiste el override

`execution/src/kill_switch_store.py`, un archivo JSON (`{"override_operating_date": "..."}`) por `{symbol}_{magic}` bajo `user_data_root()`. Sobrevive: reinicio del bot (thread), reinicio de la aplicación completa (proceso), y upgrades del instalador (`packaging/installer.iss::CurStepChanged` solo borra `{app}\_internal`, nunca `user_data_root()`, que es `{app}` mismo, su carpeta hermana). El P&L en sí NUNCA se persiste — MT5/`history_deals_get()` sigue siendo la única fuente de verdad de eso.

---

## Comportamiento ante restart

- **P&L:** se reconstruye siempre desde `mt5.history_deals_get()` — un restart no lo resetea a `$0`, porque nunca vivió en memoria para empezar. Cubierto por `test_kill_switch.py` (el cálculo es una función pura sobre lo que devuelve MT5, no hay estado de proceso involucrado).
- **Override activo:** persiste en disco, se relee en cada evaluación — un restart con override ya confirmado hoy sigue sin mostrar el popup. Cubierto por `test_kill_switch.py::test_h_override_persists_and_expires_on_new_day` (simula un "restart" releyendo desde el archivo en disco en vez de una variable en memoria) y por `api/test_start_kill_switch.py` (flujo completo vía `_kill_switch_gate`).
- **Límite ya alcanzado antes de arrancar:** cubierto por `api/test_start_kill_switch.py::test_g_start_blocked_leaves_no_bot`, que confirma que `api_app.start()` levanta el 409 ANTES de crear cualquier `LiveExecutionBot` — ningún thread llega a arrancar.

---

## Cambios realizados al calendario

`panel/calendar.html` reemplazó CADA uso de `new Date(t.time*1000).getFullYear()/getMonth()/getDate()`/`getDay()` (hora local del navegador) por un helper `operatingDateParts()` (`Intl.DateTimeFormat` con `timeZone` explícito, tomado de `GET /status`). Efecto directo: el P&L que el calendario le asigna a un día operativo determinado ahora corresponde EXACTAMENTE al mismo conjunto de operaciones que usaría el kill switch para ese mismo día — antes podían diferir cerca de la medianoche según la timezone configurada en la PC del usuario (confirmado en la comprobación puntual previa a esta implementación).

---

## Tests agregados y resultado

Convención del repo: scripts planos con `assert` + `if __name__ == "__main__":` (no hay `pytest` instalado, ver `BACKLOG.md`). Se agregaron 3 archivos nuevos a la lista de "tests que se corren antes de un release":

- **`execution/src/test_operating_day.py`** (5 casos) — el ejemplo exacto del prompt (`2026-09-15 02:00 UTC` → día operativo `2026-09-14` en Costa Rica), límites de 24hs exactas, fronteras justo antes/después de medianoche local, y una prueba explícita de que la arquitectura NO está hardcodeada a "UTC-6" (mismo código, timezone con DST, offsets distintos según la época del año).
- **`execution/src/test_kill_switch.py`** (8 casos, fake `MetaTrader5` inyectado en `sys.modules`, mismo patrón que `test_mt5_validation.py`) — fail-safe sin datos, límite `-$499.99` no dispara / `-$500.00` sí dispara, P&L neto con ganancias y pérdidas mixtas, posición abierta sin deal de salida no cuenta, deal de cierre manual (magic=0) sigue atribuido, deal fuera del día operativo excluido, y persistencia/expiración del override.
- **`api/test_start_kill_switch.py`** (7 casos, `MetaTrader5` real con las funciones de conexión monkeypatcheadas, mismo patrón que `api/test_start_mt5_validation.py`) — feature desactivada es no-op, validación de monto obligatorio/`>0`, límites B/C, flujo completo de override (H/I/J/K/L/P del prompt), invalidación por cambio de día operativo, fail-safe, y arranque con el límite ya alcanzado dejando `_bot is None`.

Los ítems **R** (calendario y kill switch coinciden) y **S** (cambiar la timezone del navegador no cambia la clasificación) son de UI/JS puro — este repo no tiene infraestructura de test JS (sin npm/jest) y no se inventó una fuera de convención. Quedan como verificación manual: se comprobó visualmente en el navegador embebido que `config.html`/`index.html` cargan sin errores de consola, que el checkbox nuevo habilita/deshabilita el campo de monto correctamente, y que la validación cliente funciona — pero **no se ejecutó un `/start` real contra la cuenta MT5 conectada en esta máquina** (ver nota de seguridad abajo), así que el popup de confirmación en vivo y el banner de "detenido por kill switch" se verificaron por el resultado esperado de `api/test_start_kill_switch.py`, no interactuando con la cuenta real.

**Nota de seguridad:** esta máquina tiene una terminal MT5 REAL conectada (balance/operaciones reales visibles en el panel al hacer el smoke test). Deliberadamente NO se hizo click en "Iniciar bot" durante la verificación manual, para no arrancar el motor de trading real como efecto secundario de esta tarea — toda la lógica de arranque/gate se verificó vía tests automatizados con MT5 mockeado, nunca contra la cuenta real.

### Resultado de la suite completa (antes y después del cambio)

```
$ .venv/Scripts/python.exe strategy/test_engine.py            -> OK
$ .venv/Scripts/python.exe strategy/test_htf_session.py       -> OK
$ .venv/Scripts/python.exe strategy/test_diagnostics.py       -> OK
$ .venv/Scripts/python.exe strategy/test_scoring.py           -> OK
$ .venv/Scripts/python.exe strategy/test_costs.py             -> OK
$ .venv/Scripts/python.exe execution/src/test_mt5_validation.py    -> OK
$ .venv/Scripts/python.exe execution/src/test_timestamp_offset.py  -> OK
$ .venv/Scripts/python.exe execution/src/test_operating_day.py     -> OK (nuevo)
$ .venv/Scripts/python.exe execution/src/test_kill_switch.py       -> OK (nuevo)
$ .venv/Scripts/python.exe api/test_start_mt5_validation.py        -> OK
$ .venv/Scripts/python.exe api/test_start_kill_switch.py           -> OK (nuevo)
$ .venv/Scripts/python.exe scripts/test_release_lib.py             -> OK
```

**12/12 OK.** Se corrió la misma suite completa como línea base ANTES de tocar ningún archivo (9/9 OK) y de nuevo al final (12/12 OK) — cero regresión. No se modificó ninguna línea de `strategy/` (EMA, HTF, pivotes, armado, scoring, generación de señal) ni de `strategy/live_signal.py` — no aplica correr `scripts/diagnose_signal_parity.py` (diagnóstico manual de paridad de señal contra TradingView) porque no hay ningún cambio que pudiera afectar la señal.

---

## Riesgos, limitaciones y decisiones técnicas a conocer

1. **`tzdata` en Windows** (ver sección de diseño #1) — mitigado (requirement + hidden import explícito + build de PyInstaller verificado), pero vale la pena un smoke test manual del instalador final antes de confiar en él para operar (ver más abajo).
2. **Latencia de hasta `poll_interval_s`** entre una pérdida que se realiza y el kill switch reflejándola (documentado en `docs/spec-live-execution.md` §12) — inherente a la arquitectura de polling del bot, mismo orden de magnitud que otras latencias ya existentes.
3. **`_aciertos_pct()` no se corrigió** — sigue usando el filtro de una sola pasada (sin la protección de deal de cierre manual). Quedó deliberadamente fuera de alcance de esta US (no se pidió, y tocarlo hubiera sido un cambio no solicitado a `strategy.scoring`/CVP). Podría valer la pena un ticket aparte si se quiere unificar.
4. **R/S del checklist de tests son verificación manual, no automatizada** — ver sección de tests arriba.
5. **No se ejecutó un arranque real del bot contra la cuenta MT5 conectada** en esta máquina durante la verificación manual, por seguridad (ver nota arriba) — toda la lógica de gate/popup/override se validó con MT5 mockeado.
6. **Se agregó `.claude/launch.json`** (no pedido explícitamente) para poder levantar `uvicorn api.app:app` y previsualizar el panel durante esta tarea — es una conveniencia de desarrollo, no afecta producción ni el instalador. `.claude/settings.local.json` (preexistente, permisos locales) NO se commiteó — es config local del entorno, no del proyecto.
7. **El "día de sesión" HTF** (`strategy/htf_session.py`, ancla 22:00 UTC) y el "día operativo" nuevo (`America/Costa_Rica`) son conceptos completamente independientes a propósito — uno trocea bloques de la estrategia, el otro define fronteras de P&L/riesgo. No se unificaron porque hacerlo sería tocar la estrategia, prohibido explícitamente para esta US.

---

## Estado de versión / release / git

- **VERSION:** `1.0.0` → `1.1.0` (MINOR — funcionalidad nueva backward-compatible; instalaciones existentes sin `daily_max_loss_enabled`/`daily_max_loss_usd` en su config guardada arrancan exactamente igual que antes, kill switch desactivado por defecto).
- **CHANGELOG.md:** entrada agregada a `[Unreleased]` → `### Added` antes de correr `scripts/build_release.py`; cortada a `[1.1.0] - <fecha>` por el propio proceso de release.
- **Build del instalador:** verificado con una build real de PyInstaller (`pyinstaller packaging/pivot_x_sentinel.spec --noconfirm --clean`) ejecutada durante esta tarea — confirmó que `hook-tzdata.py` corre y que `dist/pivot-x-sentinel/_internal/tzdata/zoneinfo/America/Costa_Rica` queda presente. El instalador final versionado (Inno Setup, `releases/v1.1.0/`) se genera como parte del flujo de release descrito en el reporte final de la tarea (fuera de este documento, que se escribió ANTES de correr el release formal — ver la respuesta final de la conversación para el detalle de artefacto/checksum/commit/tag si se completó).
- **Commits/tag:** ver la respuesta final de la tarea (commit hash, tag `v1.1.0`, y confirmación de push) — este archivo se commitea junto con el resto del cambio de BOT-032, antes del commit de release.
