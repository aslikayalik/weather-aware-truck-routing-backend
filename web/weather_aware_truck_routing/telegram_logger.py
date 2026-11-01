import logging
import requests
import time

class TelegramLogHandler(logging.Handler):
    last_sent = 0

    def __init__(self, bot_token, chat_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot_token = bot_token
        self.chat_id = chat_id

    def emit(self, record):
        log_entry = self.format(record)
        if self.bot_token and self.chat_id:
            now = time.time()
            if now - TelegramLogHandler.last_sent < 1:  # send at most 1 message per second
                return
            TelegramLogHandler.last_sent = now
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": log_entry,
                "parse_mode": "Markdown"
            }
            try:
                requests.post(url, data=data, timeout=5)
            except Exception:
                pass  # A failure here must not break logging