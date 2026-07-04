import logging
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
        self._cap: Optional[cv2.VideoCapture] = None

    def open(self):
        self._cap = cv2.VideoCapture(self._device)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera device {self._device}")
        logger.info(f"Camera opened at {self._width}x{self._height}")

    def _flush_buffer(self):
        for _ in range(3):
            self._cap.grab()

    def capture_and_save(self) -> Tuple[Optional[np.ndarray], Optional[str]]:
        if self._cap is None:
            return None, None
        self._flush_buffer()
        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.error("Camera capture failed")
            return None, None
        filename = f"capture_{int(time.time())}.jpg"
        path = str(self._capture_dir / filename)
        cv2.imwrite(path, frame)
        logger.debug(f"Saved: {path}")
        return frame, path

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
            logger.info("Camera closed")
