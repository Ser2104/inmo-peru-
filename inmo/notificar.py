import httpx

from . import config


def telegram(texto):
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        print(texto)
        return False
    for _ in range(3):
        try:
            httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
                       json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texto[:4000], "disable_web_page_preview": True},
                       timeout=30).raise_for_status()
            return True
        except httpx.HTTPError:
            continue
    print(texto)
    return False
