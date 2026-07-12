import logging
import threading
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


class EmergencyPoll:
    """Polling client buat endpoint emergency lokal (plain HTTP, no TLS).
    Kalau device_id di response beda dari device sendiri, panggil callback.
    """

    def __init__(self, url: str, device_id: str, api_key: str = "", poll_interval_sec: float = 2.0):
        self._url = url
        self._device_id = device_id
        self._api_key = api_key
        self._interval = poll_interval_sec
        self._on_emergency: Optional[Callable[[str], None]] = None
        self._last_seen_device: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_emergency_callback(self, callback: Callable[[str], None]):
        self._on_emergency = callback

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="EmergencyPoll")
        self._thread.start()
        logger.info(f"Emergency polling aktif -> {self._url} (device: {self._device_id})")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        while self._running:
            try:
                resp = requests.get(self._url, headers=headers, timeout=3)

                if resp.status_code == 200:
                    device = resp.json().get("device")

                    if device and device != self._device_id:
                        # Trigger cuma sekali per "kemunculan baru", biar gak spam
                        # Telegram tiap poll cycle selama TTL emergency masih aktif
                        if device != self._last_seen_device:
                            logger.warning(f"EMERGENCY dari device lain: {device}")
                            if self._on_emergency:
                                self._on_emergency(device)
                        self._last_seen_device = device
                    else:
                        self._last_seen_device = None

                elif resp.status_code == 401:
                    logger.error("Emergency poll ditolak: 401 Unauthorized (cek EMERGENCY_API_KEY)")
                else:
                    logger.error(f"Emergency poll HTTP error: {resp.status_code}")

            except requests.RequestException as e:
                logger.error(f"Emergency poll connection error: {e}")

            time.sleep(self._interval)
