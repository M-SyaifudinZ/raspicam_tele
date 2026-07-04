import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    _GPIO_OK = True
except ImportError:
    logger.warning("RPi.GPIO unavailable — GPIO in mock mode")
    _GPIO_OK = False


class GpioHandler:
    def __init__(self, pin_door: int, pin_button: int, pin_siren: int,
                 pin_led_status: int, pin_led_alarm: int):
        self._pin_door = pin_door
        self._pin_button = pin_button
        self._pin_siren = pin_siren
        self._pin_led_status = pin_led_status
        self._pin_led_alarm = pin_led_alarm

        self._on_door_open: Optional[Callable] = None
        self._on_door_close: Optional[Callable] = None
        self._on_bypass: Optional[Callable] = None
        self._siren_active = False
        self._lock = threading.Lock()

        self._setup()

    def _setup(self):
        if not _GPIO_OK:
            return
        GPIO.setup(self._pin_door, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self._pin_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self._pin_siren, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self._pin_led_status, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self._pin_led_alarm, GPIO.OUT, initial=GPIO.LOW)
        GPIO.add_event_detect(self._pin_door, GPIO.BOTH,
                              callback=self._door_cb, bouncetime=200)
        GPIO.add_event_detect(self._pin_button, GPIO.FALLING,
                              callback=self._button_cb, bouncetime=300)
        logger.info("GPIO configured")

    def set_door_callbacks(self, on_open: Callable, on_close: Callable):
        self._on_door_open = on_open
        self._on_door_close = on_close

    def set_bypass_callback(self, callback: Callable):
        self._on_bypass = callback

    def _door_cb(self, channel):
        if not _GPIO_OK:
            return
        is_open = GPIO.input(self._pin_door) == GPIO.HIGH
        if is_open and self._on_door_open:
            self._on_door_open()
        elif not is_open and self._on_door_close:
            self._on_door_close()

    def _button_cb(self, channel):
        if self._on_bypass:
            self._on_bypass()

    @property
    def is_door_open(self) -> bool:
        if _GPIO_OK:
            return GPIO.input(self._pin_door) == GPIO.HIGH
        return False

    @property
    def is_siren_active(self) -> bool:
        return self._siren_active

    def siren_on(self):
        with self._lock:
            self._siren_active = True
        if _GPIO_OK:
            GPIO.output(self._pin_siren, GPIO.HIGH)
            GPIO.output(self._pin_led_alarm, GPIO.HIGH)
        logger.warning("Siren ON")

    def siren_off(self):
        with self._lock:
            self._siren_active = False
        if _GPIO_OK:
            GPIO.output(self._pin_siren, GPIO.LOW)
            GPIO.output(self._pin_led_alarm, GPIO.LOW)
        logger.info("Siren OFF")

    def set_status_led(self, state: bool):
        if _GPIO_OK:
            GPIO.output(self._pin_led_status, GPIO.HIGH if state else GPIO.LOW)

    def cleanup(self):
        if _GPIO_OK:
            self.siren_off()
            GPIO.cleanup()
