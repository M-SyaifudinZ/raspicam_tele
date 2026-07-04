import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import serial

logger = logging.getLogger(__name__)

FRAME_HEADER = bytes([0xF4, 0xF3, 0xF2, 0xF1])
FRAME_END = bytes([0xF8, 0xF7, 0xF6, 0xF5])


@dataclass
class LD2410Frame:
    target_state: int
    move_distance: int
    move_energy: int
    still_distance: int
    still_energy: int
    detect_distance: int

    @property
    def has_target(self) -> bool:
        return self.target_state != 0

    @property
    def state_label(self) -> str:
        return {0: "No Target", 1: "Moving", 2: "Stationary", 3: "Moving+Still"}.get(
            self.target_state, "Unknown"
        )


def _parse_frame(buf: bytearray) -> Optional[LD2410Frame]:
    pos = buf.find(FRAME_HEADER)
    if pos == -1:
        if len(buf) > 4:
            del buf[:-4]
        return None
    if pos > 0:
        del buf[:pos]
    if len(buf) < 6:
        return None

    data_len = int.from_bytes(buf[4:6], "little")
    total = 4 + 2 + data_len + 4
    if len(buf) < total:
        return None

    raw = bytes(buf[:total])
    del buf[:total]

    if raw[-4:] != FRAME_END:
        return None

    # data: [0x02][0xAA][state][move_dist 2B][move_e][still_dist 2B][still_e][det_dist 2B][0x55][0x00]
    data = raw[6: 6 + data_len]
    if len(data) < 13 or data[0] != 0x02 or data[1] != 0xAA:
        return None

    return LD2410Frame(
        target_state=data[2],
        move_distance=int.from_bytes(data[3:5], "little"),
        move_energy=data[5],
        still_distance=int.from_bytes(data[6:8], "little"),
        still_energy=data[8],
        detect_distance=int.from_bytes(data[9:11], "little"),
    )


class LD2410:
    def __init__(self, port: str, baudrate: int = 256000):
        self._port = port
        self._baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_motion: Optional[Callable[[LD2410Frame], None]] = None
        self._last_frame: Optional[LD2410Frame] = None
        self._lock = threading.Lock()

    def set_motion_callback(self, callback: Callable[[LD2410Frame], None]):
        self._on_motion = callback

    @property
    def last_frame(self) -> Optional[LD2410Frame]:
        with self._lock:
            return self._last_frame

    def start(self):
        self._serial = serial.Serial(self._port, baudrate=self._baudrate, timeout=1)
        logger.info(f"LD2410 connected on {self._port}")
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True, name="LD2410")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()

    def _read_loop(self):
        buf = bytearray()
        while self._running:
            try:
                waiting = self._serial.in_waiting
                if waiting:
                    buf.extend(self._serial.read(waiting))
                    frame = _parse_frame(buf)
                    if frame:
                        with self._lock:
                            self._last_frame = frame
                        if frame.has_target and self._on_motion:
                            self._on_motion(frame)
                else:
                    time.sleep(0.05)
            except serial.SerialException as e:
                logger.error(f"LD2410 serial error: {e}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"LD2410 error: {e}")
