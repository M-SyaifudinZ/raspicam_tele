import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, device: int = 0, width: int = 1920, height: int = 1080,
                 capture_dir: str = "captures"):
        self._device = device
        self._width = width
        self._height = height
        self._capture_dir = Path(capture_dir)
        self._capture_dir.mkdir(parents=True, exist_ok=True)
        self._opened = False

    def open(self):
        try:
            result = subprocess.run(
                ["rpicam-hello", "--list-cameras"],
                capture_output=True, text=True, timeout=10,
            )
            logger.debug(result.stdout)
        except FileNotFoundError:
            raise RuntimeError(
                "rpicam-apps not found. Install with: sudo apt install -y rpicam-apps"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timed out checking for camera (rpicam-hello)")

        self._opened = True
        logger.info(f"Camera opened at {self._width}x{self._height} (via rpicam-still)")

    def _flush_buffer(self):
        # No-op: rpicam-still captures fresh each call, no persistent buffer to flush.
        pass

    def capture_and_save(self) -> Tuple[Optional[np.ndarray], Optional[str]]:
        if not self._opened:
            return None, None

        filename = f"capture_{int(time.time())}.jpg"
        path = str(self._capture_dir / filename)

        cmd = [
            "rpicam-still",
            "-o", path,
            "--width", str(self._width),
            "--height", str(self._height),
            "--immediate",
            "--nopreview",
            "-n",  # no preview window
            "--timeout", "1000",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            logger.error("Camera capture failed: rpicam-still timed out")
            return None, None

        if result.returncode != 0 or not Path(path).exists():
            stderr = result.stderr.decode(errors="ignore").strip()
            logger.error(f"Camera capture failed: {stderr}")
            return None, None

        frame = cv2.imread(path)
        if frame is None:
            logger.error("Camera capture failed: could not read saved image")
            return None, None

        logger.debug(f"Saved: {path}")
        return frame, path

    def close(self):
        self._opened = False
        logger.info("Camera closed")
