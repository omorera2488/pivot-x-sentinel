# API local (Fase 5)

**Objetivo:** exponer el estado del bot de la Fase 4 por HTTP, consultable con curl/Postman sin abrir el panel.

Implementada en [/api](../api) (`api/app.py`, FastAPI). Un solo proceso — la API y el bot corren juntos (decisión de Fase 0: sin procesos paralelos, sin "shadow"); el loop del bot corre en un thread de background que la API arranca/para.

## 1. Endpoints

| Método | Ruta | Qué devuelve | Depende de que el bot esté corriendo |
|---|---|---|---|
| GET | `/status` | Si el bot está corriendo, símbolo/perfil/magic/`dry_run`/parámetros activos | No (da nulls si nunca arrancó) |
| POST | `/start` | Arranca el bot (conecta, replay de arranque, lanza el thread). Body: `symbol`, `profile`, `magic`, `poll_interval_s`, `live` (default `false` = dry-run) | — |
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
