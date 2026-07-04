import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class TelegramConfig:
    token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    personal_chat_id: str = field(default_factory=lambda: os.getenv("PERSONAL_CHAT_ID", ""))
    group_chat_ids: List[str] = field(
        default_factory=lambda: _split_ids(os.getenv("GROUP_CHAT_IDS", ""))
    )


@dataclass
class GpioConfig:
    door_sensor: int = field(default_factory=lambda: int(os.getenv("PIN_DOOR_SENSOR", 17)))
    bypass_button: int = field(default_factory=lambda: int(os.getenv("PIN_BYPASS_BUTTON", 27)))
    siren: int = field(default_factory=lambda: int(os.getenv("PIN_SIREN", 22)))
    led_status: int = field(default_factory=lambda: int(os.getenv("PIN_LED_STATUS", 23)))
    led_alarm: int = field(default_factory=lambda: int(os.getenv("PIN_LED_ALARM", 24)))


@dataclass
class LD2410Config:
    port: str = field(default_factory=lambda: os.getenv("LD2410_PORT", "/ttyAMAO"))
    baudrate: int = field(default_factory=lambda: int(os.getenv("LD2410_BAUDRATE", 256000)))


@dataclass
class CameraConfig:
    device: int = field(default_factory=lambda: int(os.getenv("CAMERA_DEVICE", 0)))
    width: int = field(default_factory=lambda: int(os.getenv("CAMERA_WIDTH", 640)))
    height: int = field(default_factory=lambda: int(os.getenv("CAMERA_HEIGHT", 480)))


@dataclass
class DetectorConfig:
    model_path: str = field(default_factory=lambda: os.getenv("TFLITE_MODEL_PATH", "models/yolo.tflite"))
    input_size: int = 640
    confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("DETECTION_CONFIDENCE", 0.1))
    )


@dataclass
class SystemConfig:
    door_alarm_timeout_sec: int = field(
        default_factory=lambda: int(os.getenv("DOOR_ALARM_TIMEOUT_SEC", 60))
    )
    detection_cooldown_sec: int = field(
        default_factory=lambda: int(os.getenv("DETECTION_COOLDOWN_SEC", 10))
    )
    capture_dir: str = "captures"
    log_dir: str = "logs"


@dataclass
class AppConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    gpio: GpioConfig = field(default_factory=GpioConfig)
    ld2410: LD2410Config = field(default_factory=LD2410Config)
    camera: CameraConfig = field(default_factory=CameraConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    system: SystemConfig = field(default_factory=SystemConfig)


CONFIG = AppConfig()
