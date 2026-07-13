import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

#forcepush

URL = "https://acredita.anep.edu.uy/acreditaES.html"
STATE_FILE = Path("page_state.txt")
SURVEY_URL = "https://encuestas.anep.edu.uy/limesurvey/index.php/364232?lang=es"
TELEGRAM_OFFSET_FILE = Path("telegram_offset.txt")
TIMEOUT_SECONDS = 20

CHANGE_MESSAGE = """⚠️ Cambió la página de Acredita EMS.

H1 actual:
{h1}

Revisar:
{url}"""

HEARTBEAT_MESSAGE = """✅ Monitor Acredita EMS funcionando.

La página responde correctamente.
H1 actual:
{h1}"""

TEST_MESSAGE = "✅ Prueba manual de Telegram desde GitHub Actions."

FORCE_CHANGE_MESSAGE = """⚠️ PRUEBA DE ALERTA

Cambio detectado correctamente.

H1 actual:
{h1}

URL:
{url}"""

SURVEY_AVAILABLE_MESSAGE = """🚨 Encuesta de ANEP  disponible.

https://encuestas.anep.edu.uy/limesurvey/index.php/364232?lang=es"""
SURVEY_UNAVAILABLE_MESSAGE = "No Carga"

FORCED_STATE = b"__forced_acredita_monitor_state_for_integration_test__"


class MonitorError(Exception):
    pass


class TelegramError(MonitorError):
    pass


def fetch_page() -> tuple[str, bytes]:
    try:
        response = requests.get(URL, timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise MonitorError(f"Timeout al consultar {URL}") from exc
    except requests.RequestException as exc:
        raise MonitorError(f"Error de red al consultar {URL}: {exc}") from exc

    if not 200 <= response.status_code < 300:
        raise MonitorError(f"HTTP no exitoso: {response.status_code}")

    return response.text, response.content


def survey_loads() -> bool:
    try:
        response = requests.get(SURVEY_URL, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return False

    return 200 <= response.status_code < 300


def parse_page(html: str) -> dict[str, str]:
    try:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        visible_text = soup.get_text(separator="\n", strip=True)
        h1 = extract_registration_h1(soup)
    except Exception as exc:
        raise MonitorError(f"Fallo de scraping: {exc}") from exc

    return {
        "html": html,
        "visible_text": visible_text,
        "h1": h1,
    }


def extract_registration_h1(soup: BeautifulSoup) -> str:
    h1_texts = [h1.get_text(" ", strip=True) for h1 in soup.find_all("h1")]
    h1_texts = [text for text in h1_texts if text]

    for text in h1_texts:
        lowered = text.lower()
        if "inscrip" in lowered or "acredita" in lowered:
            return text

    if len(h1_texts) > 1:
        return h1_texts[1]

    if h1_texts:
        return h1_texts[0]

    return "No se encontró H1 de inscripción."


def telegram_post(method: str, payload: dict) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        raise TelegramError("Falta TELEGRAM_BOT_TOKEN en variables de entorno.")

    endpoint = f"https://api.telegram.org/bot{token}/{method}"

    try:
        response = requests.post(endpoint, data=payload, timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise TelegramError(f"Timeout al llamar Telegram {method}.") from exc
    except requests.RequestException as exc:
        raise TelegramError(f"Error de red al llamar Telegram {method}: {exc}") from exc

    if not 200 <= response.status_code < 300:
        raise TelegramError(
            f"Telegram respondió HTTP {response.status_code}: {response.text}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise TelegramError(f"Telegram respondió JSON inválido: {response.text}") from exc

    if not body.get("ok"):
        raise TelegramError(f"Telegram respondió error: {body}")

    return body


def enviar_telegram(mensaje: str, chat_id: str | int | None = None) -> None:
    target_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not target_chat_id:
        raise TelegramError("Falta TELEGRAM_CHAT_ID en variables de entorno.")

    telegram_post(
        "sendMessage",
        {
            "chat_id": target_chat_id,
            "text": mensaje,
            "disable_web_page_preview": True,
        },
    )


def get_telegram_updates(offset: int | None = None) -> list[dict]:
    payload = {
        "timeout": 0,
        "allowed_updates": '["message"]',
    }

    if offset is not None:
        payload["offset"] = offset

    body = telegram_post("getUpdates", payload)
    return body.get("result", [])


def read_telegram_offset() -> int | None:
    if not TELEGRAM_OFFSET_FILE.exists():
        return None

    value = TELEGRAM_OFFSET_FILE.read_text(encoding="utf-8").strip()
    if not value:
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise MonitorError(f"Offset de Telegram inválido en {TELEGRAM_OFFSET_FILE}.") from exc


def write_telegram_offset(offset: int) -> None:
    TELEGRAM_OFFSET_FILE.write_text(str(offset), encoding="utf-8")


def build_telegram_test_response() -> str:
    html_text, html_bytes = fetch_page()
    page = parse_page(html_text)
    previous_html = STATE_FILE.read_bytes() if STATE_FILE.exists() else b""
    changed = previous_html != html_bytes
    status = "⚠️ La página fue modificada" if changed else "Sin cambios detectados"

    return f"""✅ Test manual Acredita EMS

H1 actual:
{page["h1"]}

Estado:
{status}

Texto visible:
{len(page["visible_text"])} caracteres

HTML:
{len(html_bytes)} bytes

URL:
{URL}"""


def is_test_command(text: str) -> bool:
    command = text.strip().split()[0].lower()
    return command == "/test" or command.startswith("/test@")


def run_acredita_check() -> None:
    html_text, html_bytes = fetch_page()
    page = parse_page(html_text)

    print(f"Página consultada correctamente: {URL}")
    print(f"H1 actual: {page['h1']}")
    print(f"Texto visible extraído: {len(page['visible_text'])} caracteres")
    print(f"HTML extraído: {len(html_bytes)} bytes")

    if not STATE_FILE.exists():
        STATE_FILE.write_bytes(html_bytes)
        print(f"Primera ejecución. Estado creado en {STATE_FILE}. No se envía alerta.")
        return

    previous_html = STATE_FILE.read_bytes()

    if previous_html == html_bytes:
        print("Sin cambios. No se envía alerta.")
        return

    enviar_telegram(CHANGE_MESSAGE.format(h1=page["h1"], url=URL))
    STATE_FILE.write_bytes(html_bytes)
    print("Cambio detectado. Alerta enviada y estado actualizado.")


def run_survey_check() -> None:
    if survey_loads():
        enviar_telegram(SURVEY_AVAILABLE_MESSAGE)
        print("Encuesta de ANEP disponible. Alerta enviada.")
        return

    enviar_telegram(SURVEY_UNAVAILABLE_MESSAGE)
    print("Encuesta de ANEP no carga. Alerta enviada.")


def run_check() -> int:
    run_acredita_check()
    run_survey_check()
    return 0


def run_heartbeat() -> int:
    html_text, _ = fetch_page()
    page = parse_page(html_text)
    enviar_telegram(HEARTBEAT_MESSAGE.format(h1=page["h1"]))
    print("Heartbeat enviado correctamente.")
    print(f"H1 actual: {page['h1']}")
    return 0


def run_test() -> int:
    enviar_telegram(TEST_MESSAGE)
    print("Telegram respondió OK. Mensaje de prueba enviado correctamente.")
    return 0


def run_force_change() -> int:
    original_state_exists = STATE_FILE.exists()
    original_state = STATE_FILE.read_bytes() if original_state_exists else None

    print("Cambio forzado para prueba")

    try:
        STATE_FILE.write_bytes(FORCED_STATE)

        html_text, html_bytes = fetch_page()
        page = parse_page(html_text)
        previous_html = STATE_FILE.read_bytes()

        print(f"Página consultada correctamente: {URL}")
        print(f"H1 actual: {page['h1']}")

        if previous_html == html_bytes:
            raise MonitorError("No se pudo forzar el cambio: el estado ficticio coincide.")

        enviar_telegram(FORCE_CHANGE_MESSAGE.format(h1=page["h1"], url=URL))
        print("Telegram OK")
        return 0
    finally:
        if original_state_exists:
            STATE_FILE.write_bytes(original_state)
        else:
            STATE_FILE.unlink(missing_ok=True)


def run_telegram_commands() -> int:
    offset = read_telegram_offset()
    updates = get_telegram_updates(offset)

    if not updates:
        print("No hay comandos nuevos de Telegram.")
        return 0

    next_offset = offset

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            next_offset = max(next_offset or 0, update_id + 1)

        message = update.get("message") or {}
        text = message.get("text") or ""
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if not text or not chat_id:
            continue

        if not is_test_command(text):
            continue

        try:
            response_message = build_telegram_test_response()
        except MonitorError as exc:
            response_message = f"""❌ Test manual Acredita EMS

Error:
{exc}

URL:
{URL}"""

        enviar_telegram(response_message, chat_id=chat_id)
        print(f"Comando /test respondido. Chat ID: {chat_id}")

    if next_offset is not None:
        write_telegram_offset(next_offset)
        get_telegram_updates(next_offset)
        print(f"Offset de Telegram actualizado: {next_offset}")

    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"

    try:
        if mode == "check":
            return run_check()
        if mode == "heartbeat":
            return run_heartbeat()
        if mode == "test":
            return run_test()
        if mode == "force-change":
            return run_force_change()
        if mode == "telegram-commands":
            return run_telegram_commands()

        print(
            "Uso: python monitor.py [check|heartbeat|test|force-change|telegram-commands]",
            file=sys.stderr,
        )
        return 2
    except TelegramError as exc:
        print(f"Fallo de Telegram: {exc}", file=sys.stderr)
        return 1
    except MonitorError as exc:
        print(f"Fallo del monitor: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
