============================================================
  pivot-x-sentinel -- bot de trading para Oro (XAUUSD) en MT5
============================================================

Este archivo se abre solo al terminar la instalacion. Volves a encontrarlo
en la carpeta de instalacion (accesible desde el acceso directo del menu
Inicio, click derecho -> "Abrir ubicacion del archivo") o desde el acceso
directo "pivot-x-sentinel - Leeme" que el instalador dejo junto al del bot.


------------------------------------------------------------
1) AVISO DE RIESGO -- LEER ANTES DE ARRANCAR
------------------------------------------------------------
Este bot OPERA EN VIVO POR DEFECTO: manda ordenes reales contra la cuenta
que tengas conectada en tu terminal MT5, sea demo o real -- esa eleccion se
hace al loguear la cuenta en MT5, el bot no la restringe ni la consulta.

Trading algoritmico implica riesgo real de perdida de capital. Que cuenta
usar, con que parametros, y si operar en vivo o en modo simulado (dry-run)
es responsabilidad de quien lo ejecuta.

Antes de arriesgar capital real: proba primero contra una cuenta DEMO, y/o
con la opcion "dry-run" del panel (calcula todo y solo loguea que haria,
sin mandar ninguna orden).


------------------------------------------------------------
2) REQUISITO PREVIO -- MetaTrader 5 ya instalado en ESTA PC
------------------------------------------------------------
Este instalador NO instala ni configura MetaTrader 5. Antes de abrir el bot
necesitas, en esta misma PC:

  a) Tener el terminal de MetaTrader 5 de tu broker instalado.
  b) Haber logueado ahi la cuenta (demo o real) contra la que queres operar.
  c) Dejar ese terminal MT5 ABIERTO mientras el bot corre -- el bot se
     conecta a la terminal ya abierta, no abre una sesion propia.
  d) En MT5: Herramientas -> Opciones -> Expert Advisors -> tildar
     "Permitir trading algoritmico" (o el bot no va a poder mandar ordenes).

Si el simbolo de Oro de tu broker no se llama exactamente "XAUUSD" (por
ejemplo "XAUUSDm", "XAUUSDc", "GOLD"), no hace falta que hagas nada: el bot
lo resuelve solo al conectar.


------------------------------------------------------------
3) COMO ABRIRLO
------------------------------------------------------------
Menu Inicio -> "pivot-x-sentinel". Se abre una ventanita de control con:

  - Abrir panel   -> abre el dashboard en tu navegador
                     (http://127.0.0.1:8000/panel/). Desde ahi se arranca,
                     se para y se configura el bot -- ver seccion 4.
  - Ver logs      -> muestra/oculta lo que el proceso va imprimiendo
                     (conexion a MT5, ordenes, avisos, errores). Sirve para
                     ver que esta pasando sin depender del navegador.
  - Cerrar todo   -> para el bot (si estaba corriendo) y cierra todo de
                     forma prolija. Cerrar la "X" de la ventana hace lo
                     mismo -- no queda nada corriendo en segundo plano sin
                     que se vea.

IMPORTANTE: cerrar esta ventana NO cancela ni cierra las ordenes/posiciones
que ya esten abiertas en tu cuenta MT5 -- esas viven en el broker, no en
este proceso. Si el bot esta corriendo, la ventana te avisa antes de cerrar.

La primera vez que abras el bot, Windows puede mostrar un aviso de
"Windows protegio su PC" (SmartScreen) por ser una app sin firma digital
comercial -- click en "Mas info" -> "Ejecutar de todas formas".


------------------------------------------------------------
4) CONFIGURAR Y ARRANCAR EL BOT (desde el panel -> Configuracion)
------------------------------------------------------------
El bot NO arranca solo al abrir la app -- hay que arrancarlo a proposito
desde el panel, pestaña "Configuracion":

  - Symbol            Simbolo a operar (default XAUUSD). Podes escribir el
                       generico ("XAUUSD") o el nombre exacto de tu broker.
  - Perfil            "1m" o "5m" -- dos configuraciones de la estrategia
                       (EMA + pivotes/soportes-resistencias), cada una
                       calibrada sobre timeframes distintos. "5m" es el que
                       mas se uso en pruebas.
  - Magic number       Identificador numerico de las ordenes de ESTE bot
                       (default 900001) -- sirve para distinguirlas de otras
                       ordenes/EAs en la misma cuenta. No hace falta
                       tocarlo salvo que corras mas de una instancia contra
                       la misma cuenta.
  - Modo               "En vivo" manda ordenes reales. "Dry-run" calcula
                       todo (señales, timeouts, concurrencia) pero SOLO
                       loguea lo que haria -- no manda nada al broker. Usar
                       dry-run para validar una configuracion nueva antes de
                       arriesgar capital.
  - Poll interval (s)  Cada cuanto revisa el mercado (default 10s).
  - Parametros avanzados (opcionales -- si se dejan vacios usa el default
    del perfil elegido): periodo de EMA, tamaño del bloque de pivotes en
    minutos, buffer de validacion, risk/reward, cuantas operaciones
    concurrentes por direccion, barras de validez de una entrada pendiente,
    lote fijo, y si la entrada/orden se recalcula vela a vela ("viva") o
    queda fija una vez colocada.

Con eso configurado, "Guardar y arrancar" lo pone a correr. El panel
muestra en vivo: balance/equity de la cuenta, posiciones y ordenes
pendientes, historial de operaciones cerradas, y el log de eventos del bot.

Para parar el bot (sin cerrar el proceso/ventana): boton correspondiente en
el panel, o "Cerrar todo" en la ventana de control (para las dos cosas
juntas).


------------------------------------------------------------
5) DONDE QUEDAN LOS DATOS
------------------------------------------------------------
Todo vive dentro de la carpeta de instalacion (la que elegiste, por default
%LOCALAPPDATA%\pivot-x-sentinel):

  - execution\data\scores\   Calificacion de cada entrada que coloco el bot
                              (3 factores -- divergencia/tendencia/CVP -- que
                              el panel cruza con el historial de MT5). Un
                              archivo por symbol+magic.

Los logs de cada sesion (todo lo que se imprime, incluido lo que ves en
"Ver logs") quedan en:

  %LOCALAPPDATA%\pivot-x-sentinel\logs\

Desinstalar el bot (Configuracion de Windows -> Aplicaciones, o el
"Uninstall pivot-x-sentinel" del menu Inicio) borra la carpeta de
instalacion completa, INCLUIDOS esos datos -- hace una copia aparte antes
si los queres conservar. El historial de operaciones en si (fechas, precios,
P&L) no se pierde: eso vive en tu cuenta de MT5, no en esta carpeta.


------------------------------------------------------------
6) SEGURIDAD DE RED
------------------------------------------------------------
El panel/API solo escucha en 127.0.0.1 (localhost) -- no es accesible desde
otras maquinas de tu red ni desde internet, y no tiene login/contraseña (es
un tablero personal para correr en la misma PC que la terminal MT5). No lo
expongas a internet (port forwarding, tunel, etc.) tal cual esta.


------------------------------------------------------------
7) ACTUALIZAR A UNA VERSION NUEVA
------------------------------------------------------------
Corre el instalador nuevo apuntando a la misma carpeta (el instalador lo
propone solo) -- reemplaza los archivos del programa y conserva lo que haya
en execution\data\scores\ y en los logs.


------------------------------------------------------------
8) PROBLEMAS COMUNES
------------------------------------------------------------
"No se pudo conectar a MT5" en el panel
  -> El terminal MT5 no esta abierto, o no tiene una cuenta logueada, o
     "trading algoritmico" esta desactivado (ver seccion 2).

La ventana de control dice "Servidor arrancando o no responde todavia..."
  y se queda asi
  -> Puerto 8000 ocupado por otra cosa. Cerra lo que este usando ese puerto
     o avisa para dejarlo configurable.

Windows Defender / SmartScreen marca el instalador o el .exe
  -> Comun en apps sin firma digital comercial (que cuesta dinero por año).
     No es malware -- si genera dudas, revisa el codigo fuente del proyecto.
