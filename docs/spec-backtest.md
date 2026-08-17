# Especificación del backtest de Oro con costos reales (Fase 3)

Motor de backtest que implementa exactamente [docs/spec-estrategia.md](spec-estrategia.md) (versión corregida, no el Pine original) sobre datos reales de XAUUSD, con un modelo de costos realista y una prueba de robustez, para responder una sola pregunta antes de tocar código de ejecución en vivo: **¿existe una ventaja (edge) después de costos?**

---

## 1. Principio: agnóstico de bróker

El bot final (Fase 4+) debe poder correr contra cualquier bróker que ofrezca `MetaTrader5`, no solo Exness. Esta especificación se escribe con eso en mente:

- **Ningún valor de spread/comisión/swap se hardcodea.** Se leen en tiempo de ejecución desde la terminal MT5 conectada (`symbol_info`, y el campo `spread` que trae cada vela de `copy_rates`).
- **El símbolo exacto es un parámetro de configuración, no una constante.** Cada bróker nombra el Oro distinto (`XAUUSD`, `XAUUSDm`, `XAUUSD.a`, etc.). El motor debe resolverlo buscando entre `mt5.symbols_get()` los que contengan `XAU` y validar contra el símbolo configurado, no asumir un nombre fijo.
- Exness (cuenta Standard, servidor `Exness-MT5Trial11`, symbol `XAUUSDm`) es el **caso concreto usado para validar** que el motor funciona con datos y costos reales — no el diseño final.

---

## 2. Fuente de datos

### 2.1 Origen

Historial propio de MT5 vía `MetaTrader5.copy_rates_range` (paquete oficial, ya decidido en Fase 0), desde la misma terminal/cuenta que luego se usará en vivo. Ventaja sobre un proveedor externo: mismo timestamp/timezone, mismo símbolo, y el spread histórico real del bróker viaja con cada vela (§3.1) — nada que homogeneizar entre backtest y vivo.

### 2.2 Profundidad de historial disponible (medida en la cuenta de validación, 2026-08-17)

Sondeada en vivo contra `Exness-MT5Trial11` / `XAUUSDm`:

| Timeframe | Historial disponible |
|---|---|
| M1 | ~103 días (desde 2026-05-06) |
| M5 | ~1.4 años (desde 2025-03-19) |
| M15 | ~4 años (desde 2022-05-24) |
| H1 / D1 | ~4.3 años (desde 2021-10-27) |

**Decisión:** el barrido de la Fase 3 arranca en **M5** (`chartTF = M5`), heredando como punto de partida los defaults del Pine `5m EMA y Pivotes ZS`: `emaPeriods = 12`, bloque HTF `periodos = 400` minutos. M1 queda pendiente de validar más adelante, cuando haya más historial acumulado (sigue corriendo en la cuenta real/demo, así que la ventana de 103 días solo crece) o se decida sumar una fuente M1 más profunda. Esto es un supuesto de esta especificación, no una limitación del motor: el motor de backtest debe ser agnóstico del timeframe (parámetro `chartTF`), para poder correr M1 sin cambios el día que haya datos suficientes.

**Importante — esta tabla es un dato de UNA cuenta/servidor puntual, no una propiedad de MT5 en general.** Antes de correr el barrido real, el motor debe repetir este sondeo de profundidad contra la cuenta que se vaya a usar, porque puede variar entre servidores/tipos de cuenta del mismo bróker.

### 2.3 Descarga por chunks

`copy_rates_range` en este servidor devuelve como máximo ~100.000 velas por llamada (coincide con `terminal_info().maxbars`); pedir un rango que abarque más velas que eso no falla con un error claro, devuelve datos corruptos/repetidos (un único bar "fantasma" que no corresponde al rango pedido — verificado empíricamente). El motor de descarga debe:

1. Trabajar hacia atrás en ventanas de tamaño fijo (ej. 90 días para M5) desde "ahora" hasta el inicio deseado.
2. Concatenar y luego deduplicar por `time` (evita solapes en los bordes de cada ventana).
3. Cortar la descarga y avisar (no fallar en silencio) si una ventana devuelve 0 o 1 velas — es la señal de haber llegado al límite real de historial del servidor (§2.2), no un rango vacío por fin de semana/feriado.
4. Persistir el resultado crudo (parquet o csv) en `/backtests/data/`, versionado por símbolo + timeframe + fecha de descarga, para no tener que re-descargar en cada corrida del barrido.

---

## 3. Modelo de costos

### 3.1 Spread

Cada vela que devuelve `copy_rates` trae un campo `spread` (en puntos del símbolo, ej. `point = 0.001` en `XAUUSDm`) — es el spread vigente al cierre de esa vela, no una constante inventada. Verificado: en `XAUUSDm` promedia ~260 puntos (~US$0,26) en operación normal, con rango 240–340 puntos observado.

**Aplicación:** al resolver un llenado (§5.3 de la especificación de estrategia) y al resolver la salida (TP/SL/tiempo), se descuenta medio spread de esa vela en contra de la posición en cada cruce:

```
spread_price = spread_puntos_de_la_vela * point

precio_entrada_ajustado = dir < 0 ? entry - spread_price/2 : entry + spread_price/2
precio_salida_ajustado  = dir < 0 ? precio_salida + spread_price/2 : precio_salida - spread_price/2
```

Es decir: vender siempre al lado bid (peor para el vendedor), comprar siempre al lado ask (peor para el comprador), tanto al entrar como al salir — un spread completo de costo por operación redonda, tal como se pagaría en la realidad.

**Fallback:** si un bróker/símbolo no completa el campo `spread` en sus velas (ocurre con algunos feeds ECN "raw"), el motor debe aceptar un `spreadFallbackPts` constante configurable y advertir explícitamente en el reporte que se está usando un valor asumido, no medido.

### 3.2 Comisión

No es un dato consultable por API en MT5 (no está en `symbol_info` ni se puede derivar sin haber operado). Se modela como parámetro explícito `commissionPerLot` (US$, por lote, round-turn), a cargo del usuario completarlo según los términos de su cuenta.

**Cuenta de validación (Exness Standard):** las cuentas "Standard" de Exness son spread-only, sin comisión aparte — se asume `commissionPerLot = 0` para XAUUSDm, **pendiente de confirmar contra los términos publicados de la cuenta** (no hay operaciones en el historial de esta cuenta todavía para verificarlo empíricamente).

### 3.3 Swap

`symbol_info(symbol).swap_long` / `.swap_short` están en puntos por lote por noche (`swap_mode = SYMBOL_SWAP_MODE_POINTS` en la cuenta de validación); se convierten a US$ vía `trade_tick_value`:

```
swap_usd_por_lote_por_noche = swap_puntos * tick_value
```

Medido en la cuenta de validación: `swap_long ≈ -US$53,74` por lote 1.0 por noche, `swap_short = US$0`. Estos valores **fluctúan** (dependen de tasas de interés) — el snapshot actual sirve para arrancar el barrido, pero no es válido asumirlo constante en una muestra de 1.4 años. El motor debe:

- Aplicar swap una vez por cada rollover (00:00 hora del bróker) que la posición pase abierta, según la dirección (`swap_long` si `dir > 0`, `swap_short` si `dir < 0`).
- Aplicar el swap **triple** el miércoles a jueves (convención estándar del mercado FX/CFD para compensar el fin de semana) — a confirmar contra la política específica de Exness antes de dar el resultado del backtest por válido.
- Como MT5 no expone historial de swap día a día, usar el valor vigente (`symbol_info` al momento de correr el backtest) de forma constante para toda la muestra, dejando explícito en el reporte que es una aproximación — no hay forma de obtener el swap histórico real vía esta API.

### 3.4 Tamaño de posición

Lote fijo configurable (`fixedLot`, ej. `0.01`), igual para todas las operaciones del barrido inicial — aísla la calidad de la señal del money management (decisión ya tomada con el usuario). El dimensionamiento por riesgo variable queda para la Fase 8 (checklist antes de pasar a real), no para este barrido.

---

## 4. Barrido de parámetros

Parámetros a barrer (todos ya definidos en `spec-estrategia.md`):

| Parámetro | Rango de partida sugerido | Nota |
|---|---|---|
| `emaPeriods` | 8 – 25 | Centrado en el default 12 del Pine 5m |
| `periodos` (bloque HTF, minutos) | 200 – 800 | Centrado en el default 400 |
| `bufBp` | 0.2 – 3.0 | El 0.4 original está pensado para forex; para Oro puede quedar corto |
| `rr` | 0.5 – 3.0 | Sin asumir el "7" que el Pine solo dejaba anotado en un comentario, nunca como default real |
| `maxConcurrentPorDireccion` | 1 – 3 | Punto de partida 1, ver §6 de `spec-estrategia.md` |

`chartTF` fijo en `M5` para este primer barrido (§2.2). `validBars`, `ordenViva`, `maxBarsTrade` quedan en los defaults del Pine (10, `true`, 500) salvo que el barrido inicial muestre motivo para tocarlos.

**Métrica objetivo:** expectancy neta de costos por operación, en R y en US$ (con `fixedLot`), sobre el conjunto de combinaciones. Métricas secundarias a reportar por combinación: win rate, R:R real de las ganadoras/perdedoras, drawdown máximo en R, número total de operaciones (para descartar combinaciones con muestra insuficiente), y los contadores de §7 de `spec-estrategia.md` (fills, expiradas, descartadas por concurrencia vs. por stop inválido).

**Método:** grid search exhaustivo sobre la malla de arriba mientras el número de combinaciones sea manejable (`emaPeriods` × `periodos` × `bufBp` × `rr` × `maxConcurrentPorDireccion` con los rangos sugeridos ronda las ~2000-4000 combinaciones — corrible en M5 sobre 1.4 años sin problema). Si se decide ampliar rangos y el espacio crece demasiado, pasar a random search o coordinate descent antes que reducir la muestra de datos.

---

## 5. Prueba de robustez

Con ~1.4 años de M5 disponibles (§2.2), partir la muestra en **3 sub-períodos** de ~5-6 meses cada uno (fechas exactas a fijar según los datos que efectivamente se descarguen), sin solape con el período usado durante el ajuste del barrido: el barrido en sí (§4) corre sobre TODO el histórico, pero la validación de robustez recalcula la expectancy de la(s) combinación(es) ganadora(s) por separado en cada sub-período.

**Criterio de aceptación (igual al del roadmap):** la combinación ganadora debe tener expectancy neta de costos positiva en **cada uno** de los 3 sub-períodos, no solo en el agregado. Una combinación que gana en el agregado por un solo sub-período excepcional se descarta como sobreajuste, no como hallazgo válido.

---

## 6. Validación mecánica (checksum contra la especificación)

Antes de confiar en cualquier resultado del barrido, correr el motor sobre un tramo corto y conocido de datos y verificar a mano (o con un test unitario dedicado) que se cumplen las reglas mecánicas puntuales de `spec-estrategia.md` §5.5 y §7:

- Prioridad "llenado antes que expiración" cuando ambas condiciones caen en la misma barra.
- Empate SL/TP en la misma barra siempre resuelve como SL.
- El bloque HTF nunca se autoarma (el bug de §3.2 de `spec-estrategia.md` no debe reproducirse).
- El límite de concurrencia (§6 de `spec-estrategia.md`) efectivamente bloquea una señal nueva cuando ya hay `maxConcurrentPorDireccion` operaciones vivas en esa dirección.

Como ya se dejó dicho en `spec-estrategia.md` §7: **no comparar los conteos agregados contra el Pine original** — es una diferencia esperada, no un indicador de bug.

---

## 7. Decisiones abiertas (a confirmar antes de correr el barrido real)

1. **Confirmar `commissionPerLot = 0`** contra los términos publicados de la cuenta Standard de Exness (§3.2) — o contra el bróker que finalmente se use.
2. **Confirmar la política de swap triple** de Exness (día exacto, ¿miércoles o viernes según convención del bróker?) antes de dar el resultado del backtest por válido (§3.3).
3. **Fechas exactas de los 3 sub-períodos** (§5) una vez descargado el histórico real — depende de cuánto M5 efectivamente se logre bajar sin huecos.
4. **Reconfirmar la profundidad de historial** (§2.2) contra la cuenta/servidor que se use para correr el barrido real, si no es la misma cuenta de validación de este documento.
