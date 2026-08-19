# panel

Frontend del dashboard: tarjetas de estado (bot, estrategia activa, conexión MT5), balance/equity, curva de capital, tabla de operaciones, log de eventos, configuración (con selector de estrategia), historial completo y calendario de resultados. Implementa [docs/spec-panel.md](../docs/spec-panel.md).

HTML/CSS/JS planos, sin build step ni dependencias externas — consume la API de [/api](../api) por `fetch()`. Servido por el mismo proceso (montado en `api/app.py` bajo `/panel`).

## Uso

Con la API corriendo (`uvicorn api.app:app --host 127.0.0.1 --port 8000`, ver `api/README.md`):

```
http://127.0.0.1:8000/panel/
```

## Páginas

- `index.html` — panel principal: estado del bot, estrategia activa, cuenta, curva de capital, últimas 20 operaciones, últimos eventos. Botones iniciar/detener.
- `config.html` — selector de perfil (1m/5m) + todos los parámetros de `StrategyParams` editables. Guardar detiene el bot si estaba corriendo.
- `history.html` — historial completo de operaciones cerradas (de MT5), con export a CSV.
- `calendar.html` — resultado por día, calculado agrupando el historial de MT5 por día local.
