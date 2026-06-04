# acredita-monitor

Monitor de cambios para la página de Acredita EMS:

https://acredita.anep.edu.uy/acreditaEMS.html

El script compara el HTML completo de la página contra un estado previo guardado en `page_state.txt`. Si detecta un cambio real, envía una alerta por Telegram y actualiza el estado.

## Requisitos

- Python 3
- requests
- beautifulsoup4
- Un bot de Telegram
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Instalación local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Usar `.env.example` como referencia y exportar las variables antes de ejecutar modos que envían Telegram:

```bash
export TELEGRAM_BOT_TOKEN="token-del-bot"
export TELEGRAM_CHAT_ID="chat-id"
```

## Uso

Modo normal de monitoreo:

```bash
python monitor.py check
```

Primera ejecución:

- crea `page_state.txt`
- no envía alerta

Ejecuciones siguientes:

- si el HTML completo no cambió, no envía nada
- si cualquier parte del HTML cambió, envía alerta por Telegram y actualiza `page_state.txt`

Modo heartbeat:

```bash
python monitor.py heartbeat
```

Este modo valida que la página responde correctamente y siempre envía un mensaje diario por Telegram.

Modo de prueba de Telegram:

```bash
python monitor.py test
```

Envía:

```text
✅ Acredita Monitor funcionando correctamente.
```

## Mensajes

Cambio detectado:

```text
⚠️ Cambió la página de Acredita EMS.

H1 actual:
...

Revisar:
https://acredita.anep.edu.uy/acreditaEMS.html
```

Heartbeat:

```text
✅ Monitor Acredita EMS funcionando.

La página responde correctamente.
H1 actual:
...
```

## GitHub Actions

El workflow está en `.github/workflows/monitor.yml`.

Configurar estos secretos en el repositorio:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

El workflow:

- ejecuta `check` cada 5 minutos con cron `*/5 * * * *`
- ejecuta `heartbeat` todos los días a las 11:00 UTC con cron `0 11 * * *`
- permite ejecución manual con `workflow_dispatch`
- usa `permissions: contents: write`
- commitea automáticamente `page_state.txt` cuando el estado cambia

Nota: los cron de GitHub Actions usan UTC.
