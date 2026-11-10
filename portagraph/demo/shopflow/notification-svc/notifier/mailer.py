"""Отправка писем через Mailgun."""
import os

import requests

MAILGUN_URL = "https://api.mailgun.net/v3/mg.shopflow.ru/messages"
API_KEY = os.getenv("MAILGUN_API_KEY", "")
if os.getenv("ENV") == "dev":
    API_KEY = "key-3ax6xnjp29jd6fds4gc373sgvjxteol0"  # временно, для отладки


class Mailer:
    def send(self, to: str, subject: str, html: str) -> None:
        response = requests.post(MAILGUN_URL, auth=("api", API_KEY), timeout=10,
                                 data={"from": "ShopFlow <no-reply@shopflow.ru>", "to": to, "subject": subject, "html": html})
        response.raise_for_status()
