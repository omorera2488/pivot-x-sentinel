"""Alineacion de sesion del bloque HTF -- ver docs/spec-estrategia.md #3.1
(enmienda 2026-09-04).

Logica de SESION, deliberadamente separada de EMA/armado/señal (que siguen
viviendo en engine.py/live_signal.py sin tocar) -- este modulo solo responde
una pregunta: "a que bloque de `periodos_min` minutos pertenece este
timestamp".

--------------------------------------------------------------------------
EVIDENCIA EXPERIMENTAL (lo que reemplaza a la formula vieja)
--------------------------------------------------------------------------
La formula anterior (`bucket_id = floor(unix_minutes(t) / periodos)`,
spec-estrategia.md #3.1 previo a esta enmienda) asume bloques continuos de
exactamente `periodos` minutos alineados a la epoca Unix (1970-01-01 00:00
UTC). Se midio directamente en TradingView, con `time(str(periodos))` (la
misma expresion que usa el Pine de referencia -- ver
basecode_tradingview/"5m EMA y Pivotes ZS...".txt linea 76,
`nuevoBucket = ta.change(time(htf)) != 0`) sobre XAUUSD/OZ (feed TVC),
`periodos=800`, y dio estos limites de bloque reales:

    2026-09-02 22:00 UTC  -> bloque nuevo
    2026-09-03 11:20 UTC  -> bloque nuevo   (800 min despues de las 22:00)
    2026-09-03 22:00 UTC  -> bloque nuevo   (640 min despues de las 11:20,
                                              NO 800)

La formula vieja de epoca Unix predice bloques SIEMPRE de 800 minutos
exactos, sin importar la hora del dia -- no puede producir el salto de
640 minutos entre las 11:20 y las 22:00. Queda DESCARTADA por esta prueba de
paridad: no replica lo que TradingView efectivamente calcula para este
simbolo.

--------------------------------------------------------------------------
LA REGLA NUEVA
--------------------------------------------------------------------------
El patron observado (800, despues 640, despues 800 de nuevo) es exactamente
lo que produce TradingView al armar una resolucion intradia "no estandar"
(un numero pelado de minutos, ej. "800") sobre un simbolo con un dia de
sesion de 24hs: cada DIA de sesion (desde el inicio de sesion hasta el
inicio de la sesion siguiente, 1440 minutos) se trocea en bloques de
`periodos_min` minutos a partir del inicio de sesion, y el ULTIMO bloque del
dia se trunca en el limite de sesion en vez de completar los `periodos_min`
minutos si 1440 no es multiplo exacto de `periodos_min` (800*1=800,
1440-800=640 -> el bloque truncado que se mide).

Con eso, ancla de sesion = 22:00 UTC, `periodos_min=800`:
  - bloque 1: 22:00 -> 11:20 (800min, completo)
  - bloque 2: 11:20 -> 22:00 (640min, truncado por el limite de sesion)
  - bloque 3 (dia siguiente): 22:00 -> 11:20 ... se repite.

Coincide con los 3 limites medidos arriba, exacto.

--------------------------------------------------------------------------
SUPUESTOS PENDIENTES -- NO VALIDADOS TODAVIA
--------------------------------------------------------------------------
`DEFAULT_SESSION_ANCHOR_UTC_MIN = 22*60` (22:00 UTC) es un valor MEDIDO, no
deducido de ninguna regla general -- por eso es un parametro explicito de
`bucket_start_utc_seconds()`, no una constante escondida en el calculo de
señal. Lo que este codigo NO puede garantizar todavia:

  1. Que 22:00 UTC se mantenga durante todo el año. Es una convencion tipica
     de sesion forex/CFD ("cierre de Nueva York"), que en muchos brokers
     efectivamente SIGUE el horario de verano de EEUU (se corre a 21:00 UTC
     durante el DST europeo/21:00 vs 22:00 segun el solapamiento de DST
     EEUU/UE) -- no hay evidencia en este repo de como se comporta este
     simbolo/broker despues de un cambio de DST. La medicion se hizo en una
     sola ventana de 2 dias (2-3 septiembre 2026), sin ningun cambio de DST
     de por medio.
  2. Que 22:00 UTC valga para otros simbolos o feeds (se midio solo Oro,
     feed TVC de TradingView -- no se comparo contra el feed del broker
     XAUUSDc en MT5 directamente, mas alla de que el bot ahora usa esta
     misma regla contra ese feed).
  3. Que el broker (MT5) entregue barras de 5 minutos exactamente alineadas
     al mismo reloj -- ver `measure_broker_offset_seconds()` en
     execution/src/mt5_utils.py, que ya corrige cualquier desfase de reloj
     del SERVIDOR del broker contra UTC de verdad (algo aparte de esto:
     ese offset se midio en ~-1.86s para la cuenta actual, o sea
     practicamente cero -- no explica el desfase de 2 horas que se
     observaba antes de esta enmienda, que era 100% el ancla de sesion).

Si en algun momento se sospecha que el bloque del bot vuelve a desalinearse
con TradingView, lo primero a revisar es si el ancla de sesion sigue siendo
22:00 UTC (recomendado: repetir la medicion de este docstring apuntando
`time(str(periodos))` en TradingView contra la hora actual).
"""
from __future__ import annotations

MINUTES_PER_DAY = 24 * 60
_DAY_LEN_S = MINUTES_PER_DAY * 60

# Ancla de sesion medida empiricamente (ver docstring del modulo) -- minutos
# desde medianoche UTC. Parametro explicito, no constante escondida dentro
# del calculo de señal (bot.py/engine.py la reciben, no la reinventan).
DEFAULT_SESSION_ANCHOR_UTC_MIN = 22 * 60  # 22:00 UTC


def bucket_start_utc_seconds(
    time_utc_s: int,
    periodos_min: int,
    session_anchor_utc_min: int = DEFAULT_SESSION_ANCHOR_UTC_MIN,
) -> int:
    """Segundos unix UTC del INICIO del bloque HTF al que pertenece
    `time_utc_s`, replicando la semantica observada de `time(htf)` de
    TradingView para resoluciones intradia "no estandar" (ver docstring del
    modulo): el dia de sesion arranca en `session_anchor_utc_min` minutos
    desde medianoche UTC y se trocea en bloques de `periodos_min` minutos,
    truncando el ultimo bloque del dia en el limite de sesion siguiente.

    Funciona tanto con `int` de Python (uso en vivo, barra a barra) como con
    escalares de numpy (`int64` de un array, uso en el motor batch) -- solo
    usa +, -, // y % , que numpy soporta elemento a elemento.

    Devuelve el INICIO del bloque (no un id abstracto): comparar el valor
    entre dos barras consecutivas alcanza para detectar un bloque nuevo
    (`bucket_start(barra_i) != bucket_start(barra_i_menos_1)`), y de paso es
    directamente la hora que hay que loguear/comparar contra TradingView.
    """
    anchor_s = session_anchor_utc_min * 60
    block_len_s = periodos_min * 60

    # Segundos transcurridos desde el ultimo inicio de sesion (0 <= x < 1 dia).
    # El modulo de Python siempre devuelve el mismo signo que el divisor
    # (positivo aca), asi que esto funciona igual para timestamps anteriores
    # a la epoca de referencia (1970-01-01 22:00 UTC) sin ajuste manual.
    since_session_start = (time_utc_s - anchor_s) % _DAY_LEN_S
    session_start = time_utc_s - since_session_start

    block_index = since_session_start // block_len_s
    return session_start + block_index * block_len_s
