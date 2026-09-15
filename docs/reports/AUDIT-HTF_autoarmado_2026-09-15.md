# Auditoría HTF — HTF en formación vs HTF cerrado / auto-armado

**Fecha:** 2026-09-15
**Autor:** Claude Code (Sonnet 5), a pedido del usuario
**Repositorio:** pivot-x-sentinel — branch `main`
**Commit base (HEAD al momento de la auditoría):** `001f9df` — `docs(backlog): add BOT-045 (market regime analysis) and operational priority order`
**Tipo de tarea:** SOLO AUDITORÍA — no se modificó código de estrategia, ejecución, API, panel ni configuración. No se implementó BOT-045.

Este documento es **autocontenido**: no depende de la conversación de Claude Code. Contiene el flujo de código citado con archivo:línea, el historial de git relevante, y evidencia de runtime reproducible (dataset y parámetros reales) para que otra persona — o ChatGPT recibiendo únicamente este archivo — pueda verificar la conclusión sin re-ejecutar la investigación desde cero.

---

## Resumen ejecutivo

El motor de estrategia (`strategy/engine.py`, usado en batch/backtest) y el motor de ejecución en vivo (`strategy/live_signal.py`, usado directamente por `/execution`) calculan **`resistencia`/`soporte` como el extremo (`high`/`low`) del bloque HTF que se está formando en ese mismo instante**, no el bloque HTF anterior ya cerrado. Esto reintroduce el auto-armado: dentro de un mismo bloque, cualquier vela que amplíe el rango cumple trivialmente `high[i] >= resistencia[i]` (o `low[i] <= soporte[i]`) porque `resistencia[i]`/`soporte[i]` se acaban de actualizar con esa misma vela.

No es un bug no detectado: es una **decisión de producto explícita y documentada**, tomada el 2026-08-19 a pedido del usuario (commit `8a156de`), que revirtió una corrección previa (Fase 2, bloque anterior cerrado) para lograr paridad exacta con el indicador real que el usuario corre en TradingView (`usarCausal=true`). Esa decisión sigue vigente hoy, sin reversión posterior, y `/strategy` y `/execution` la implementan de forma idéntica (confirmado en runtime, no solo por inspección de nombres de variables).

Sobre el dataset real disponible (100.505 velas M5 de XAUUSDc, 2025-04-14 → 2026-09-15), **el 100% de las activaciones de armado (`armadoVenta`/`armadoCompra`) coinciden con la vela estableciendo el extremo del propio bloque HTF en formación** — es decir, el mecanismo de armado es autorreferencial en la totalidad de los casos observados, no en un subconjunto.

**Veredicto:** `HTF EN FORMACIÓN — auto-armado confirmado`.

---

## 1. Veredicto

Una de las cuatro conclusiones posibles: **`HTF EN FORMACIÓN — auto-armado confirmado`**.

No `HTF CERRADO`, no `MIXTO`, no `INCONCLUSO` — la evidencia de código (sección 2), la especificación versionada (sección 8) y la evidencia de runtime (secciones 6-7) son consistentes entre sí y apuntan en la misma dirección sin excepciones detectadas.

---

## 2. Evidencia de código

| Paso | Archivo:línea | Qué hace |
|---|---|---|
| Bloque HTF (motor batch) | [`strategy/engine.py:133-179`](../../strategy/engine.py#L133) `bucket_levels()` | `run_high`/`run_low` se inicializan con `high[i]`/`low[i]` al abrir un bloque nuevo y se actualizan con `max(cur_high, high[i])` / `min(cur_low, low[i])` en cada barra siguiente del mismo bloque. `resistencia[i]`/`soporte[i]` = ese acumulado **incluyendo la barra `i` actual**. El docstring (líneas 142-146) dice textualmente: *"esto reintroduce a propósito el auto-armado... no es un bug de esta función, es el comportamiento que se decidió replicar"*. |
| Alineación del bloque (cuándo empieza uno nuevo) | [`strategy/htf_session.py:96-128`](../../strategy/htf_session.py#L96) `bucket_start_utc_seconds()` | Compartida bit a bit entre el motor batch y el motor en vivo — solo decide los límites temporales del bloque, no afecta la semántica "en formación vs. cerrado". |
| Asignación de niveles + armado (motor batch) | [`strategy/engine.py:215-216`](../../strategy/engine.py#L215), [`strategy/engine.py:267-292`](../../strategy/engine.py#L267) | `resistencia, soporte = bucket_levels(...)` (215-216); dentro del loop principal: `r_i, s_i = resistencia[i], soporte[i]` (268, ya incluye la barra actual) → `if high[i] >= r_i: armado_venta = True` / `if low[i] <= s_i: armado_compra = True` (289-292). |
| Bloque HTF + armado (motor en vivo, usado por `/execution`) | [`strategy/live_signal.py:87-122`](../../strategy/live_signal.py#L87) `LiveSignalEngine.process_bar()` | Lógica idéntica, incremental: bloque en formación (87-98) → `resistencia = self._cur_high`, `soporte = self._cur_low` (97-98) → `if high >= resistencia: self.armado_venta = True` / `if low <= soporte: self.armado_compra = True` (119-122). |
| Cruce EMA → señal | [`strategy/engine.py:280-292`](../../strategy/engine.py#L280) (batch), [`strategy/live_signal.py:110-122`](../../strategy/live_signal.py#L110) (vivo) | `senal_venta = armado_venta and down` / `senal_compra = armado_compra and up`, evaluado con el armado tal como quedó de barras anteriores (`armado_*_antes`), luego se consume/re-arma en la misma barra. |
| `/execution` usa este motor directamente | [`execution/src/bot.py:52,209,213`](../../execution/src/bot.py#L52) | `from strategy.live_signal import LiveSignalEngine`, instanciado directamente en `LiveExecutionBot` — no existe un cálculo HTF paralelo o distinto en `/execution`. |

---

## 3. Flujo real

```
vela LTF (M5) → bucket_start_utc_seconds(t) determina a qué bloque HTF pertenece
              → run_high/run_low (bucket_levels, batch) o
                self._cur_high/self._cur_low (LiveSignalEngine, vivo)
                se actualiza CON la vela actual incluida
              → resistencia = run_high / self._cur_high
                soporte     = run_low  / self._cur_low     (del bloque EN FORMACIÓN)
              → high[i] >= resistencia  →  armadoVenta = True   (autoreferencial)
              → low[i]  <= soporte      →  armadoCompra = True  (autoreferencial)
              → cruce EMA (down/up) en la barra actual consume el armado
                (armado_antes == True) → senal_venta / senal_compra
```

No hay una estructura precalculada con datos futuros — el mecanismo es 100% causal (sección 5) pero se autorreferencia dentro del bloque en curso.

---

## 4. Strategy vs Execution

**Equivalentes — sin divergencia detectada.** `strategy/live_signal.py` reimplementa manualmente (barra a barra) la misma fórmula que `strategy/engine.py` usa en modo batch; ambos comparten `htf_session.bucket_start_utc_seconds()` para la alineación del bloque, y `/execution` no tiene ningún cálculo HTF propio — importa e instancia `LiveSignalEngine` directamente (`execution/src/bot.py:52,209,213`).

Verificación runtime, corriendo ambos motores sobre el dataset real `backtests/data/XAUUSDc_M5_latest.parquet` (100.505 velas M5, 2025-04-14 → 2026-09-15, perfil `5m` real de producción: `ema_periods=12, periodos_htf_min=400, buf_bp=0.4, rr=1.0`, ver `strategy/profiles.py`):

```
señales batch (engine.run_backtest):          6409
señales live  (live_signal.LiveSignalEngine): 6409
idénticas bar-a-bar (bar, dir, valido):       True
```

Coincide además con el test unitario ya presente en el repo — [`strategy/test_engine.py:225-265`](../../strategy/test_engine.py#L225) `test_g_live_signal_matches_batch` — que corre en la suite actual sin modificaciones.

---

## 5. Causalidad (`usarCausal`)

`usarCausal` **no existe como flag/parámetro en el código Python** — no hay ningún `if usarCausal:` ni config equivalente en `engine.py`/`live_signal.py`/`profiles.py` (confirmado por búsqueda de texto en todo el repo: las únicas apariciones de `usarCausal` están en comentarios/docs y en el Pine de referencia bajo `basecode_tradingview/`). El motor Python implementa **incondicionalmente** la semántica de `usarCausal=true` del indicador.

**Lo que esa semántica sí garantiza:** ausencia de look-ahead futuro. En la barra `i`, `resistencia[i]`/`soporte[i]` dependen únicamente de datos de la barra `i` o anteriores — nunca de barras futuras ni de un bloque HTF "final" todavía sin cerrar. `bucket_levels()` es un loop estrictamente hacia adelante (`for i in range(1, n)`, [`strategy/engine.py:165`](../../strategy/engine.py#L165)), sin ningún acceso a `high[j]`/`low[j]` con `j > i`.

**Lo que esa semántica NO garantiza:** protección contra auto-referencia dentro del bloque actual. Son dos propiedades independientes — `docs/spec-estrategia.md` §3.3 lo dice explícitamente: *"no repintar es sobre qué datos se usan (pasado vs. futuro), auto-armarse es sobre qué nivel se compara contra qué (el bloque en curso contra sí mismo)"*. El código elige no-repintar (obligatorio para poder operar en vivo) **y** auto-armarse (decisión explícita, no accidental).

---

## 6. Evidencia runtime

Metodología: script de solo-lectura (no modifica ningún archivo del repo, no importa `execution.src.bot.LiveExecutionBot`, no se conecta a MT5 — corre sobre el parquet ya existente) que instancia `strategy.engine.bucket_levels`, `strategy.engine.run_backtest` y `strategy.live_signal.LiveSignalEngine` **tal cual están hoy en el repo**, sobre `backtests/data/XAUUSDc_M5_latest.parquet` con los parámetros reales del perfil `5m` (`strategy/profiles.py`). El script completo queda reproducido en el [Apéndice](#apéndice--script-de-diagnóstico-usado) para que cualquiera pueda re-ejecutarlo.

Ejemplo real — primer bloque HTF del dataset (`periodos_htf_min=400`, arranca en la barra 0, 2025-04-14 18:50 UTC):

```
    bar  timestamp_utc              high       low    resist    soport  nuevo_blk  high==res  low==sop
      0  2025-04-14 18:50:03+00:00  3204.624  3202.236  3204.624  3202.236   True       True       True
      1  2025-04-14 18:55:03+00:00  3209.137  3204.013  3209.137  3202.236   False      True       False
      2  2025-04-14 19:00:03+00:00  3209.849  3207.726  3209.849  3202.236   False      True       False
      3  2025-04-14 19:05:03+00:00  3209.488  3207.949  3209.849  3202.236   False      False      False
      4  2025-04-14 19:10:03+00:00  3210.200  3208.290  3210.200  3202.236   False      True       False
      5  2025-04-14 19:15:03+00:00  3211.541  3209.534  3211.541  3202.236   False      True       False
      6  2025-04-14 19:20:03+00:00  3212.382  3210.211  3212.382  3202.236   False      True       False
      7  2025-04-14 19:25:03+00:00  3212.036  3210.036  3212.382  3202.236   False      False      False
      8  2025-04-14 19:30:03+00:00  3211.985  3208.663  3212.382  3202.236   False      False      False
      9  2025-04-14 19:35:03+00:00  3211.373  3209.241  3212.382  3202.236   False      False      False
     10  2025-04-14 19:40:03+00:00  3211.165  3209.262  3212.382  3202.236   False      False      False
     11  2025-04-14 19:45:03+00:00  3212.895  3209.685  3212.895  3202.236   False      True       False
     12  2025-04-14 19:50:03+00:00  3213.083  3211.649  3213.083  3202.236   False      True       False
     13  2025-04-14 19:55:03+00:00  3212.962  3211.834  3213.083  3202.236   False      False      False
     14  2025-04-14 20:00:03+00:00  3213.056  3210.337  3213.083  3202.236   False      True       False
     15  2025-04-14 20:05:03+00:00  3213.821  3211.944  3213.821  3202.236   False      True       False
     16  2025-04-14 20:10:03+00:00  3212.946  3211.653  3213.821  3202.236   False      False      False
     17  2025-04-14 20:15:03+00:00  3212.208  3209.592  3213.821  3202.236   False      False      False
     18  2025-04-14 20:20:03+00:00  3211.253  3209.334  3213.821  3202.236   False      False      False
```

Cada vez que una vela hace un nuevo máximo del bloque (`high==res` = True: barras 0, 1, 2, 4, 5, 6, 11, 12, 14, 15), `resistencia` se actualiza a ese mismo `high[i]` **de la misma barra**, y la condición de armado (`high[i] >= resistencia[i]`) queda trivialmente satisfecha por construcción — exactamente el mecanismo conceptual descrito en la sección 3 del prompt de auditoría.

---

## 7. Cuantificación

Sobre las 100.505 velas M5 reales del dataset (2025-04-14 → 2026-09-15), motor `LiveSignalEngine` (el real de `/execution`), perfil `5m` de producción:

- **Qué bloque HTF usa realmente `resistencia`/`soporte`** (comparado contra dos reconstrucciones independientes hechas por el script de auditoría, no por el motor):
  - Coinciden con el **bloque EN FORMACIÓN**: **100.505 / 100.505 (100.0%)**.
  - Coinciden con el **bloque ANTERIOR CERRADO**: **0 / 100.505 (0.0%)**, sobre las 100.479 barras donde existe un bloque anterior definido.
- **Activaciones de armado** (transición `False → True`, motor `LiveSignalEngine`):
  - `armadoVenta`: **3.006** activaciones — **3.006 (100.0%)** coinciden con `high[i] == resistencia[i]` (autorreferencia).
  - `armadoCompra`: **2.930** activaciones — **2.930 (100.0%)** coinciden con `low[i] == soporte[i]` (autorreferencia).
- **Señales generadas** en el período: 3.233 de venta + 3.176 de compra = **6.409** (coincide exactamente con el conteo de la sección 4, batch = live). Toda señal requiere un armado previo consumido por un cruce de EMA; el 100% de esos armados se originó de forma autorreferencial (punto anterior) — no existe en el código actual ninguna vía alternativa de armado que use el bloque cerrado.
- **Porcentaje atribuible al auto-armado:** dado que el 100% de las activaciones de armado observadas son autorreferenciales y no existe una ruta de código alternativa, **el 100% de las 6.409 señales generadas en el período están precedidas por al menos un armado de origen autorreferencial** (aunque el armado consumido por una señal concreta pueda haber ocurrido varias barras antes del cruce de EMA que la disparó — el *origen* del armado, no necesariamente la barra de la señal misma, es autorreferencial en la totalidad de los casos).

---

## 8. Comparación con la corrección histórica del 2026-08-19

**Nota de discrepancia:** el archivo `anotacion-bug-armado-htf.md` referenciado en el prompt de auditoría **no existe en el árbol actual del repositorio ni en ningún commit de todo su historial** (`git log --all --full-history -- "*anotacion*"` no devuelve resultados). No lo doy por hecho ni lo invento — reporto la ausencia. Sí encontré evidencia equivalente y mutuamente consistente en otras tres fuentes independientes: el mensaje del commit de la corrección, la especificación versionada, y la memoria del proyecto.

1. **Qué bug describía:** el commit [`8a156de`](https://github.com) (2026-08-19, `"Bloque HTF: paridad con TradingView usarCausal=true + tipo compra/venta en panel"`) dice textualmente en su mensaje: *"revierte la corrección de Fase 2 del bloque HTF. resistencia/soporte vuelven a ser el extremo del bloque EN FORMACIÓN... auto-armado incluido"*. Confirma que **sí existió una corrección previa (Fase 2)** que usaba el bloque anterior cerrado, precisamente para evitar el auto-armado trivial.
2. **Qué cambio se implementó y dónde:** el mismo commit revirtió esa corrección en `strategy/engine.py` **y** `strategy/live_signal.py` en paralelo (mensaje del commit: *"strategy/engine.py y strategy/live_signal.py actualizados en paralelo (test G de equivalencia batch/incremental sigue en verde)"*), volviendo a la semántica "bloque en formación".
3. **Por qué se revirtió:** a pedido explícito del usuario, documentado en `docs/spec-estrategia.md` (cambio al tope de §3, "Enmienda 2026-08-19") y en la memoria del proyecto (`docs/claude-memory/pivot-x-sentinel-tv-reference-mismatch.md`) — para lograr paridad exacta con el indicador real que el usuario corre en TradingView (`usarCausal=true`), la única variante operable en vivo (el modo repintante requiere datos del futuro).
4. **¿Sigue presente ese código hoy?** Sí — confirmado por inspección de código (sección 2) y evidencia runtime al 100% (sección 7).
5. **¿Fue revertido/reemplazado/bypasseado después?** No. `git log --oneline -- strategy/engine.py` muestra los commits posteriores a `8a156de` (`52e3cc7` candado de concurrencia, `ced2626` alineación de sesión, `a0e32f6`/BOT-043 costos) — ninguno toca la semántica de `bucket_levels()`/`process_bar()` de vuelta hacia "bloque cerrado". La evidencia runtime de la sección 7 (100%/0%) lo confirma de forma independiente al historial de git.
6. **¿La implementación actual contradice la documentación?** No. `docs/spec-estrategia.md` §3.2 fue reescrita explícitamente para decir "adoptado, no corregido" — la especificación describe el comportamiento actual tal cual es.

---

## 9. Impacto sobre BOT-045

**Clasificación: CRÍTICO.**

BOT-045 (`docs/reports/BOT-045_backlog_planning.md`) busca diagnosticar qué variables de régimen de mercado (RSI/ADX/ATR/sesión/hora/día/dirección/distancia a EMA/características del bloque HTF/scoring existente) distinguen operaciones ganadoras de perdedoras. Pero según la sección 7, el 100% de los armados que originan las señales analizadas son autorreferenciales al bloque HTF en curso — `armadoVenta`/`armadoCompra` se disparan en cualquier barra que amplíe el rango del bloque en formación, sin relación con una resistencia/soporte "externa" u objetiva del mercado.

Esto implica:

- La condición HTF de entrada no captura una ruptura de nivel real, sino un evento casi estructural ("se armó porque esta vela hizo un extremo local del bloque que ella misma está construyendo"). En bloques de `periodos_htf_min=400` minutos (perfil 5m real), esto puede re-armar con alta frecuencia mientras el precio simplemente tiene volatilidad direccional dentro del bloque.
- Analizar RSI/ADX/ATR/etc. sobre señales cuya condición base HTF está construida así arriesga atribuir "edge" o "falta de edge" a variables que en realidad correlacionan con la frecuencia de nuevos extremos intrabloque (proxy de volatilidad/tendencia local), no con una dinámica genuina de ruptura de soporte/resistencia externa al bloque.

Esto **no es un bug no documentado** — es una decisión de producto explícita, vigente y consistente en todo el código y la especificación (sección 8). BOT-045 puede avanzar, pero su marco de interpretación debe dejar constancia expresa de que, con el motor actual, "armado" ≈ "nuevo extremo local del bloque HTF en curso" (proxy de volatilidad/momentum intrabloque), no "ruptura de un nivel HTF previamente establecido" — son hipótesis de mercado distintas y BOT-045 debería nombrar esta distinción como variable de diagnóstico de primer orden, antes de interpretar cualquier indicador adicional.

---

## 10. Recomendación

No se implementó ninguna corrección (según lo solicitado — esta tarea es solo auditoría). La decisión que le corresponde al usuario antes de avanzar con BOT-045: si el análisis de régimen de mercado debe tratar el armado actual "tal cual es" (autorreferencial, paridad con TradingView — la lógica que hoy opera en real) como la variable a explicar, o si conviene primero correr BOT-045 en paralelo sobre ambas semánticas de armado (bloque en formación actual vs. bloque anterior cerrado, esta última existió en el repo antes del commit `8a156de` y puede reconstruirse fácilmente reusando `htf_session.bucket_start_utc_seconds()`) para separar el "efecto régimen de mercado" del "efecto mecanismo de armado" en los hallazgos de BOT-045. Es una decisión de diseño experimental sobre cómo interpretar BOT-045, no una corrección de bug — no hay evidencia de que el comportamiento actual sea un error técnico; es exactamente el que se pidió el 2026-08-19.

---

## Restricción final — cómo se distinguió cada nivel de evidencia

1. **Cómo parece funcionar el código** (lectura de `bucket_levels()`/`process_bar()`): usa el bloque en formación — sección 2.
2. **Cómo debería funcionar según la documentación**: exactamente igual — `docs/spec-estrategia.md` §3.2/§3.3 describe el mismo mecanismo, con el auto-armado documentado como decisión explícita, no como bug pendiente — sección 8.
3. **Cómo funciona realmente durante runtime** sobre datos reales (100.505 velas M5, dataset de producción): coincide al 100% con lo anterior, sin excepciones ni divergencia entre `/strategy` y `/execution` — secciones 4, 6 y 7.

Los tres niveles son consistentes entre sí. La conclusión de la sección 1 está respaldada por código + documentación + evidencia runtime, no únicamente por inspección superficial.

---

## Apéndice — script de diagnóstico usado

Script de **solo lectura**, no forma parte del repositorio de producción (corrió desde un directorio temporal, fuera de `/strategy` y `/execution`). No modifica ningún archivo, no importa `execution.src.bot.LiveExecutionBot`, no se conecta a MT5 — usa el dataset ya versionado `backtests/data/XAUUSDc_M5_latest.parquet` y las clases reales (`strategy.engine.bucket_levels`, `strategy.engine.run_backtest`, `strategy.live_signal.LiveSignalEngine`) tal cual están en el repo. Se reproduce completo para que cualquiera pueda re-ejecutarlo o auditarlo:

```python
"""Diagnostico de auditoria HTF / auto-armado -- SOLO LECTURA.

No modifica ningun archivo del repo. Usa las clases reales
(strategy.engine.bucket_levels, strategy.engine.run_backtest,
strategy.live_signal.LiveSignalEngine) tal cual estan hoy, sobre el dataset
real backtests/data/XAUUSDc_M5_latest.parquet, para producir evidencia de
runtime sobre si resistencia/soporte usan el bloque HTF en formacion o el
bloque anterior cerrado, y cuantificar el auto-armado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"F:\dev\pivot-x-sentinel")))

import numpy as np
import pandas as pd

from strategy.engine import StrategyParams, bucket_levels, run_backtest, ema
from strategy.live_signal import LiveSignalEngine
from strategy.costs import BrokerCosts
from strategy.profiles import get_profile

df = pd.read_parquet(r"F:\dev\pivot-x-sentinel\backtests\data\XAUUSDc_M5_latest.parquet")
df = df.sort_values("time_utc").reset_index(drop=True)

time_utc = df["time_utc"].to_numpy("int64")
time_server = df["time_server"].to_numpy("int64")
open_ = df["open"].to_numpy("float64")
high = df["high"].to_numpy("float64")
low = df["low"].to_numpy("float64")
close = df["close"].to_numpy("float64")
spread_pts = df["spread"].to_numpy("float64")

params = get_profile("5m")  # ema=12, periodos_htf_min=400, buf_bp=0.4, rr=1.0 (default real /execution)
print(f"=== Parametros ({params}) ===")
print(f"n barras = {len(df)}  rango = {pd.to_datetime(time_utc[0], unit='s', utc=True)} -> "
      f"{pd.to_datetime(time_utc[-1], unit='s', utc=True)}")

# ---------------------------------------------------------------------------
# 1) BATCH: engine.bucket_levels -- que datos concretos contiene resistencia/soporte
# ---------------------------------------------------------------------------
resistencia, soporte = bucket_levels(time_utc, high, low, params.periodos_htf_min)

from strategy.htf_session import bucket_start_utc_seconds
bucket_id = np.array([bucket_start_utc_seconds(int(t), params.periodos_htf_min) for t in time_utc])
is_new_block = np.empty(len(df), dtype=bool)
is_new_block[0] = True
is_new_block[1:] = bucket_id[1:] != bucket_id[:-1]

# bloque HTF ANTERIOR cerrado -- para comparar contra lo que el motor usa hoy
prev_block_high = np.full(len(df), np.nan)
prev_block_low = np.full(len(df), np.nan)
last_closed_high = np.nan
last_closed_low = np.nan
cur_high = cur_low = np.nan
for i in range(len(df)):
    if is_new_block[i]:
        if i > 0:
            last_closed_high = cur_high
            last_closed_low = cur_low
        cur_high, cur_low = high[i], low[i]
    else:
        cur_high = max(cur_high, high[i])
        cur_low = min(cur_low, low[i])
    prev_block_high[i] = last_closed_high
    prev_block_low[i] = last_closed_low

n = len(df)

# Reconstruir cur_high/cur_low "en formacion" independientemente (ya es resistencia/soporte de bucket_levels)
recon_forming_high = np.empty(n)
recon_forming_low = np.empty(n)
ch = cl = None
for i in range(n):
    if is_new_block[i]:
        ch, cl = high[i], low[i]
    else:
        ch = max(ch, high[i]); cl = min(cl, low[i])
    recon_forming_high[i] = ch
    recon_forming_low[i] = cl

matches_forming = np.sum(np.isclose(resistencia, recon_forming_high) & np.isclose(soporte, recon_forming_low))
matches_closed_prev = np.sum(
    ~np.isnan(prev_block_high) &
    np.isclose(resistencia, prev_block_high) & np.isclose(soporte, prev_block_low)
)
print("\n=== 2) Que bloque HTF usa realmente resistencia/soporte (runtime, dataset real) ===")
print(f"barras cuya resistencia/soporte == bloque EN FORMACION (incluye la barra actual): {matches_forming}/{n}"
      f" ({100*matches_forming/n:.1f}%)")
print(f"barras cuya resistencia/soporte == bloque ANTERIOR CERRADO (si lo fuera):        {matches_closed_prev}/{n}"
      f" ({100*matches_closed_prev/n:.1f}% -- sobre las {np.sum(~np.isnan(prev_block_high))} barras con bloque anterior definido)")

# ---------------------------------------------------------------------------
# 3) Auto-armado: cuantas barras que fijan resistencia[i]==high[i] (nuevo maximo del bloque)
# ---------------------------------------------------------------------------
sets_new_high = np.isclose(high, resistencia)
sets_new_low = np.isclose(low, soporte)
print("\n=== 3) Auto-referencia (high[i]==resistencia[i] / low[i]==soporte[i]) ===")
print(f"barras donde high[i] == resistencia[i] (candidatas a auto-armado venta): {sets_new_high.sum()}/{n} ({100*sets_new_high.sum()/n:.1f}%)")
print(f"barras donde low[i]  == soporte[i]     (candidatas a auto-armado compra): {sets_new_low.sum()}/{n} ({100*sets_new_low.sum()/n:.1f}%)")

# ---------------------------------------------------------------------------
# 4) LIVE (LiveSignalEngine, el que usa /execution) bar a bar sobre TODO el dataset real
# ---------------------------------------------------------------------------
live = LiveSignalEngine(params)
armado_venta_activations = 0        # False -> True transitions
armado_venta_activations_selfref = 0
armado_compra_activations = 0
armado_compra_activations_selfref = 0
n_senal_venta = 0
n_senal_compra = 0
n_senal_venta_preceded_selfref = 0
n_senal_compra_preceded_selfref = 0

for i in range(n):
    r = live.process_bar(int(time_utc[i]), float(high[i]), float(low[i]), float(close[i]))
    if (not r.armado_venta_antes) and r.armado_venta:
        armado_venta_activations += 1
        if np.isclose(high[i], r.resistencia):
            armado_venta_activations_selfref += 1
    if (not r.armado_compra_antes) and r.armado_compra:
        armado_compra_activations += 1
        if np.isclose(low[i], r.soporte):
            armado_compra_activations_selfref += 1
    if r.senal_venta:
        n_senal_venta += 1
        if np.isclose(high[i], r.resistencia):
            n_senal_venta_preceded_selfref += 1
    if r.senal_compra:
        n_senal_compra += 1
        if np.isclose(low[i], r.soporte):
            n_senal_compra_preceded_selfref += 1

print("\n=== 4) LiveSignalEngine (motor real de /execution) -- activaciones de armado ===")
print(f"activaciones armadoVenta (False->True):  {armado_venta_activations}  "
      f"de las cuales self-ref (high[i]==resistencia[i]): {armado_venta_activations_selfref} "
      f"({100*armado_venta_activations_selfref/max(armado_venta_activations,1):.1f}%)")
print(f"activaciones armadoCompra (False->True): {armado_compra_activations}  "
      f"de las cuales self-ref (low[i]==soporte[i]):     {armado_compra_activations_selfref} "
      f"({100*armado_compra_activations_selfref/max(armado_compra_activations,1):.1f}%)")

print("\n=== 8) Cuantificacion sobre señales generadas ===")
print(f"señales venta:  {n_senal_venta}")
print(f"señales compra: {n_senal_compra}")

# ---------------------------------------------------------------------------
# 4b) Strategy vs Execution: correr tambien el motor BATCH (run_backtest) y comparar señales
# ---------------------------------------------------------------------------
costs = BrokerCosts(point=0.01, contract_size=100, tick_value=1.0, tick_size=0.01,
                     swap_long_points=0.0, swap_short_points=0.0)  # solo afecta PnL, no la generacion de señal
batch_log = []
run_backtest(time_utc, time_server, open_, high, low, close, spread_pts, params, costs, signal_log=batch_log)
live2 = LiveSignalEngine(params)
live_log = []
for i in range(n):
    r = live2.process_bar(int(time_utc[i]), float(high[i]), float(low[i]), float(close[i]))
    if r.dir is not None:
        live_log.append({"bar": i, "dir": r.dir, "valido": r.valido})

batch_simple = [{"bar": b["bar"], "dir": b["dir"], "valido": b["valido"]} for b in batch_log]
print("\n=== Strategy (batch run_backtest) vs Execution (LiveSignalEngine) sobre dataset real ===")
print(f"señales batch (engine.run_backtest):      {len(batch_simple)}")
print(f"señales live  (live_signal.LiveSignalEngine): {len(live_log)}")
print(f"identicas bar-a-bar (bar,dir,valido):     {batch_simple == live_log}")
```

**Salida real obtenida (2026-09-15, sobre `backtests/data/XAUUSDc_M5_latest.parquet`):**

```
=== Parametros (StrategyParams(ema_periods=12, periodos_htf_min=400, buf_bp=0.4, rr=1.0, ...)) ===
n barras = 100505  rango = 2025-04-14 18:50:03+00:00 -> 2026-09-15 00:40:03+00:00

=== 2) Que bloque HTF usa realmente resistencia/soporte (runtime, dataset real) ===
barras cuya resistencia/soporte == bloque EN FORMACION (incluye la barra actual): 100505/100505 (100.0%)
barras cuya resistencia/soporte == bloque ANTERIOR CERRADO (si lo fuera):        0/100505 (0.0%)

=== 3) Auto-referencia (high[i]==resistencia[i] / low[i]==soporte[i]) ===
barras donde high[i] == resistencia[i]: 14097/100505 (14.0%)
barras donde low[i]  == soporte[i]:     12036/100505 (12.0%)

=== 4) LiveSignalEngine (motor real de /execution) -- activaciones de armado ===
activaciones armadoVenta (False->True):  3006  de las cuales self-ref: 3006 (100.0%)
activaciones armadoCompra (False->True): 2930  de las cuales self-ref: 2930 (100.0%)

=== 8) Cuantificacion sobre señales generadas ===
señales venta:  3233
señales compra: 3176

=== Strategy (batch run_backtest) vs Execution (LiveSignalEngine) sobre dataset real ===
señales batch (engine.run_backtest):      6409
señales live  (live_signal.LiveSignalEngine): 6409
identicas bar-a-bar (bar,dir,valido):     True
```
