# Panel web (Fase 6)

**Objetivo:** interfaz visual, inspirada en el dashboard del bot "M1 Pivotes 15" (capturas de referencia del usuario) pero simplificada a la arquitectura de un solo proceso — sin las tarjetas de "shadow" u otros procesos que no correspondan acá (decisión de Fase 0).

Implementado en [/panel](../panel): HTML/CSS/JS planos, sin build step, consumiendo la API de la Fase 5 (`/api`) por `fetch()`. Servido por el mismo proceso — `api/app.py` monta `/panel` como estático (`api/app.py` §"panel estatico").

**Estilo (paleta, layout, disposición de la barra de acciones) copiado a propósito del dashboard real en `C:\Dev\tradingbot\src\tradingbot\dashboard\app.py`** (el mismo bot de las capturas), a pedido explícito del usuario — variables de color, el contenedor `<main>` centrado con ancho máximo, y la grilla de 4 columnas con tarjetas que ocupan 1/2/3/4 columnas (`wide`/`wide3`/`full`) en vez de filas de grillas separadas. Solo el CSS/HTML se tomó de esa referencia — la lógica de negocio, los endpoints y los datos que consume el panel son propios de este proyecto (`/api`, §3 más abajo), no se copió nada de `tradingbot`.

## 1. Diferencias deliberadas contra la referencia

- **Sin tarjeta "Shadow candidato".** El proyecto de referencia corre un proceso "shadow" candidato en paralelo al bot real; acá no existe ese concepto (Fase 0: "sin shadow candidato, sin procesos paralelos"). La fila de tarjetas de estado pasa de 3 a 3 igual, pero reemplazando Shadow por una tarjeta **Estrategia** — sin dejar un hueco vacío y agregando algo que sí hace falta (ver §2).
- **Sin los campos de "pivote candidato"** (`WINDOW`/`STRUCTURE`, fuente del pivote, estructura local, supervivencia mínima, etc.) en Configuración — son de la lógica de detección de pivotes de la referencia, no de `spec-estrategia.md`. Los campos de Configuración acá son los de `StrategyParams` (`strategy/engine.py`) tal cual.
- Historial y calendario se calculan **con datos reales de MT5** (`GET /history`), no con una base propia — igual que en la referencia, confirmado explícitamente por el usuario.

## 2. Indicador de estrategia activa

Pedido explícito del usuario: se debe poder elegir la estrategia en Configuración y verse cuál está en uso en el panel principal.

- **Configuración** (`config.html`): selector de perfil (`1m`/`5m`) que precarga sus defaults (`GET /profiles`, fuente única de verdad: `strategy/profiles.py`) — todos los campos quedan editables después de elegir.
- **Panel principal** (`index.html`): tarjeta "Estrategia" (perfil + EMA/bloque/R:R/modo) y el subtítulo del header ("Control local · Perfil {X}") — ambos reflejan el perfil realmente cargado en el bot (`GET /status`), no la configuración pendiente sin aplicar.

## 3. De dónde sale cada dato

| Sección | Fuente |
|---|---|
| Balance/Equity | `GET /account` |
| Bot corriendo/detenido, perfil, parámetros | `GET /status` |
| Posiciones/pendientes | `GET /positions`, `GET /orders` |
| Resultado total, ganadas/perdidas, efectividad, curva de capital, últimas operaciones, historial completo, calendario | `GET /history` (deals con `entry === DEAL_ENTRY_OUT`, que es donde MT5 asienta el profit/swap/comisión realizado de cada operación cerrada) |
| Flotante | suma de `profit` de `GET /positions` (P&L no realizado de lo abierto) |
| Últimos eventos | `GET /events` |

Nada de esto vive en una base de datos propia — todo se recalcula en el navegador a partir de lo que devuelve la API en cada refresco (cada 10s en el panel principal).

## 4. Configuración pendiente vs. configuración activa

`POST /start` no persiste "qué vas a correr la próxima vez" — solo lo que está corriendo ahora. La pantalla de Configuración guarda el formulario en `localStorage` del navegador (`pxs_pending_config`) y el botón "Iniciar bot" del panel principal lo manda tal cual a `/start`. Guardar cambios en Configuración **detiene el bot si estaba corriendo** (mismo patrón que la referencia) — hay que volver a "Iniciar bot" a mano para aplicar.

Esto es deliberadamente simple (localStorage, no una tabla de configuración en el backend) — coherente con el alcance acotado pedido para esta etapa del proyecto.

## 5. Decisiones abiertas

1. **`dry_run`/`live` en Configuración**: el checkbox "Operar en vivo" existe y funciona, con advertencia visible, pero no tiene una confirmación extra tipo modal — el cuidado de no activarlo por accidente queda en quien usa el panel.
2. **Un solo bot a la vez** (heredado de la Fase 5, `/start` devuelve 409 si ya hay uno corriendo) — correr 1m y 5m en simultáneo necesitaría permitir múltiples instancias, no contemplado.
3. **Responsive**: pensado para escritorio (como la referencia); en pantallas angostas los grids caen a una columna pero no se probó exhaustivamente en mobile.
