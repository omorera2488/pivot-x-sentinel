# api

Servidor local (FastAPI) que expone el estado del bot de [/execution](../execution) por HTTP: balance/equity, posiciones abiertas y pendientes, histórico de operaciones, log de eventos, y control de iniciar/detener el bot. Implementa [docs/spec-api.md](../docs/spec-api.md).

Corre en el mismo proceso que el bot — sin procesos paralelos (decisión de Fase 0). El loop del bot vive en un thread de background que esta API arranca/para.

## Instalar

```
pip install -r requirements.txt
```

## Uso

```
uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Docs interactivas (Swagger) en `http://127.0.0.1:8000/docs` — vienen gratis con FastAPI, útiles para probar los endpoints a mano sin curl.

```bash
curl -s http://127.0.0.1:8000/account
curl -s -X POST http://127.0.0.1:8000/start -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSDm","profile":"5m"}'
curl -s http://127.0.0.1:8000/status
curl -s http://127.0.0.1:8000/events
curl -s -X POST http://127.0.0.1:8000/stop
```

`live` es `true` por default — el bot manda órdenes reales contra lo que tengas conectado en MT5 (demo o real, esa elección se hace al loguear la cuenta en la terminal). Pasar `"live":false` si por ahora solo querés que calcule y loguee, sin operar. Ver `docs/spec-api.md` §4.

Solo bindea a localhost, sin autenticación — pensada para uso personal en la misma máquina que la terminal MT5 (`docs/spec-api.md` §3).
