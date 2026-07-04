import logging
import threading
import time
from typing import Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    def __init__(self, token: str):
        self._token = token
        self._last_update_id = 0
        self._handlers: Dict[str, Callable[[str], None]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _url(self, method: str) -> str:
        return _API.format(token=self._token, method=method)

    def _post(self, method: str, **kwargs) -> Optional[dict]:
        try:
            resp = requests.post(self._url(method), timeout=(10, 35), **kwargs)
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram error [{method}]: {data.get('description')}")
                return None
            return data["result"]
        except requests.RequestException as e:
            logger.error(f"Telegram request error [{method}]: {e}")
            return None

    def send_message(self, chat_id: str, text: str) -> bool:
        return self._post("sendMessage", json={"chat_id": chat_id, "text": text}) is not None

    def send_photo(self, chat_id: str, photo_path: str, caption: str = "") -> bool:
        try:
            with open(photo_path, "rb") as f:
                result = self._post(
                    "sendPhoto",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": f},
                )
            return result is not None
        except OSError as e:
            logger.error(f"Cannot open photo {photo_path}: {e}")
            return False

    def broadcast_message(self, chat_ids: List[str], text: str):
        for cid in chat_ids:
            self.send_message(cid, text)

    def broadcast_photo(self, chat_ids: List[str], photo_path: str, caption: str = ""):
        for cid in chat_ids:
            self.send_photo(cid, photo_path, caption)

    def register_command(self, command: str, handler: Callable[[str], None]):
        self._handlers[command] = handler

    def start_polling(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="TGPoll")
        self._thread.start()

    def stop_polling(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _poll_loop(self):
        while self._running:
            try:
                updates = self._post(
                    "getUpdates",
                    json={
                        "offset": self._last_update_id + 1,
                        "timeout": 30,
                        "allowed_updates": ["message"],
                    },
                )
                if updates:
                    for update in updates:
                        self._last_update_id = update["update_id"]
                        self._dispatch(update)
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                time.sleep(5)

    def _dispatch(self, update: dict):
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text.startswith("/"):
            return
        command = text.split()[0].split("@")[0]
        handler = self._handlers.get(command)
        if handler:
            try:
                handler(chat_id)
            except Exception as e:
                logger.error(f"Handler '{command}' error: {e}")
