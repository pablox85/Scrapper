import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = "https://acredita.anep.edu.uy/acreditaEMS.html"
STATE_FILE = Path("page_state.txt")
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


def enviar_telegram(mensaje: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise TelegramError(
            "Faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID en variables de entorno."
        )

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensaje,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(endpoint, data=payload, timeout=TIMEOUT_SECONDS)
    except requests.Timeout as exc:
        raise TelegramError("Timeout al enviar mensaje por Telegram.") from exc
    except requests.RequestException as exc:
        raise TelegramError(f"Error de red al enviar Telegram: {exc}") from exc

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


def run_check() -> int:
    html_text, html_bytes = fetch_page()
    page = parse_page(html_text)

    print(f"Página consultada correctamente: {URL}")
    print(f"H1 actual: {page['h1']}")
    print(f"Texto visible extraído: {len(page['visible_text'])} caracteres")
    print(f"HTML extraído: {len(html_bytes)} bytes")

    if not STATE_FILE.exists():
        STATE_FILE.write_bytes(html_bytes)
        print(f"Primera ejecución. Estado creado en {STATE_FILE}. No se envía alerta.")
        return 0

    previous_html = STATE_FILE.read_bytes()

    if previous_html == html_bytes:
        print("Sin cambios. No se envía alerta.")
        return 0

    enviar_telegram(CHANGE_MESSAGE.format(h1=page["h1"], url=URL))
    STATE_FILE.write_bytes(html_bytes)
    print("Cambio detectado. Alerta enviada y estado actualizado.")
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


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"

    try:
        if mode == "check":
            return run_check()
        if mode == "heartbeat":
            return run_heartbeat()
        if mode == "test":
            return run_test()

        print("Uso: python monitor.py [check|heartbeat|test]", file=sys.stderr)
        return 2
    except TelegramError as exc:
        print(f"Fallo de Telegram: {exc}", file=sys.stderr)
        return 1
    except MonitorError as exc:
        print(f"Fallo del monitor: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
