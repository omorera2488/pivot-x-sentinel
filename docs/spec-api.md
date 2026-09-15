# API local (Fase 5)

**Objetivo:** exponer el estado del bot de la Fase 4 por HTTP, consultable con curl/Postman sin abrir el panel.

Implementada en [/api](../api) (`api/app.py`, FastAPI). Un solo proceso — la API y el bot corren juntos (decisión de Fase 0: sin procesos paralelos, sin "shadow"); el loop del bot corre en un thread de background que la API arranca/para.

## 1. Endpoints

| Método | Ruta | Qué devuelve | Depende de que el bot esté corriendo |
|---|---|---|---|
| GET | `/status` | Si el bot está corriendo, símbolo/perfil/magic/`dry_run`/parámetros activos, `operating_timezone` (BOT-032, siempre presente) y `kill_switch` (BOT-032, `null` si nunca arrancó esta sesión) | No (da nulls si nunca arrancó) |
| POST | `/start` | Arranca el bot (conecta, replay de arranque, lanza el thread). Body: `symbol`, `profile`, `magic`, `poll_interval_s`, `live` (default `false` = dry-run), `daily_max_loss_enabled`/`daily_max_loss_usd`/`acknowledge_daily_loss_override` (BOT-032, ver §6) | — |
| POST | `/stop` | Para el bot (señal + `join` del thread) | Sí (409 si no está corriendo) |
| GET | `/account` | `balance`/`equity`/`margin`/etc. — `mt5.account_info()` tal cual | No |
| GET | `/positions` | Posiciones abiertas, filtradas por `symbol`+`magic` (query params, con default) | No |
| GET | `/orders` | Órdenes pendientes, mismo filtro | No |
| GET | `/history?days=N` | Deals cerrados de los últimos N días, mismo filtro | No |
| GET | `/events?limit=N` | Log de eventos del bot en memoria (últimos `N`, tope 1000) | Sí (vacío si nunca arrancó) |

`/positions`, `/orders`, `/history` **no** requieren que el bot esté corriendo — leen directo de MT5 filtrando por `symbol`/`magic` (default `XAUUSDm`/`900001`, overrideables por query string). Esto es a propósito: el criterio de aceptación pide poder consultar el estado desde afuera, y las posiciones/órdenes reales existen en el bróker independientemente de si el proceso del bot sigue vivo en este momento.

## 2. Arquitectura: un solo proceso, un lock

La API y el bot comparten el mismo proceso Python. Dos threads pueden llamar a la API de MT5 al mismo tiempo (el loop del bot en `execution/src/bot.py` y los handlers HTTP) — el paquete `MetaTrader5` no garantiza ser thread-safe frente a eso, así que ambos pasan por el mismo lock (`execution.src.mt5_utils.mt5_lock`) antes de cualquier llamada a `mt5.*`.

## 3. Seguridad — solo localhost, sin autenticación

Pensada para correr en la misma máquina que la terminal MT5, consultada por el panel (Fase 6) o por vos con curl — no como servicio expuesto a otras máquinas. Por eso:

- Sin autenticación.
- Se sirve con `--host 127.0.0.1` (no `0.0.0.0`) — ver comando de arranque en `api/README.md`.
- CORS abierto (`allow_origins=["*"]`) para que el panel en dev (otro puerto) pueda pegarle sin fricción — no es una medida de seguridad, es solo para no bloquear al frontend local.

**Si en algún momento hace falta exponer esto fuera de la máquina local, hay que agregar autenticación antes — no está pensado para eso tal como está.**

## 4. `/start` y `dry_run`

`POST /start` con `"live": true` (default) arranca el bot operando de una contra la cuenta que tengas conectada en MT5 — igual que `python execution/scripts/run_bot.py` sin `--dry-run` (ver `docs/spec-live-execution.md`). Mandar `"live": false` hace que el bot calcule señales/timeouts/concurrencia pero solo loguee, sin mandar órdenes — útil para validar una configuración nueva. Qué cuenta está conectada (demo o real) es decisión de quien loguea la terminal MT5, la API no lo consulta ni lo restringe.

## 5. Decisiones abiertas

1. **Persistencia del log de eventos** — hoy vive en memoria (`bot.events`, tope 1000 entradas), se pierde si el proceso se reinicia. Si hace falta historial más largo, pasar a un archivo append-only — no implementado todavía porque no hizo falta para el criterio de aceptación de esta fase.
2. **Autenticación** — deliberadamente ausente (§3), a agregar si la API deja de ser solo-localhost.
3. **Un solo bot por proceso** — `/start` rechaza si ya hay uno corriendo (409). Correr dos perfiles a la vez (ej. 1m y 5m simultáneos) necesitaría permitir múltiples instancias, no contemplado en esta fase.

## 6. Kill switch de pérdida diaria (BOT-032)

**No hay ningún mecanismo de configuración persistida server-side todavía** (§5.1 aplica igual acá) — `daily_max_loss_enabled`/`daily_max_loss_usd` solo existen en el body de `POST /start`, igual que cualquier otro parámetro de `StrategyParams`. Por eso el chequeo de "arranque con el límite ya alcanzado" (ver `docs/spec-live-execution.md` §12) vive DENTRO del handler de `/start`, no en un endpoint aparte.

**Campos nuevos de `StartRequest`:**

| Campo | Tipo | Default | Validación |
|---|---|---|---|
| `daily_max_loss_enabled` | bool | `false` | — |
| `daily_max_loss_usd` | float\|null | `null` | Obligatorio y `> 0` si `daily_max_loss_enabled=true` (422 si no) |
| `acknowledge_daily_loss_override` | bool | `false` | El panel lo manda `true` solo en el reintento después de que el usuario confirmó el popup |

**`POST /start` puede devolver `409` con un `detail` ESTRUCTURADO (no un string, a diferencia del resto de los 409/503 de este archivo)** cuando el límite ya está alcanzado y no hay un override válido para el día operativo actual:

```json
{
  "reason": "daily_loss_kill_switch",
  "operating_date": "2026-09-15",
  "operating_timezone": "America/Costa_Rica",
  "realized_daily_pnl": -512.34,
  "daily_max_loss_usd": 500.0
}
```

El panel (`panel/app.js::apiPost`) conserva este objeto en `err.detail` (además de un `.message` legible) precisamente para poder mostrar el popup de confirmación con estos números, en vez del banner de error genérico.

**`GET /status`** agrega, siempre que `daily_max_loss_enabled` haya sido usado alguna vez en esta sesión del bot:

```json
{
  "operating_timezone": "America/Costa_Rica",
  "kill_switch": {
    "enabled": true,
    "daily_max_loss_usd": 500.0,
    "operating_date": "2026-09-15",
    "realized_daily_pnl": -512.34,
    "triggered": true,
    "override_active": false,
    "data_unavailable": false
  }
}
```

`kill_switch` es `null` si nunca se creó un `LiveExecutionBot` en esta sesión del proceso (igual que `symbol`/`params`/etc. de más arriba). `operating_timezone` SIEMPRE está presente (no depende de que haya un bot) — es la fuente de verdad que `panel/calendar.html` consume para agrupar por día operativo sin depender de la timezone del navegador.
