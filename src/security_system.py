import logging
import subprocess
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from config import AppConfig
from src.camera import Camera
from src.detector import DetectionType, DetectionResult, YoloDetector
from src.gpio_handler import GpioHandler
from src.ld2410 import LD2410, LD2410Frame
from src.emergency_poll import EmergencyPoll
from src.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class SecuritySystem:
    def __init__(self, config: AppConfig):
        self._cfg = config
        self._alarm_active = False
        self._door_timer: Optional[threading.Timer] = None
        self._last_detection_time = 0.0
        self._last_vehicle_count = 0
        self._state_lock = threading.Lock()
        self._detect_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="detect")
        self._telegram = TelegramClient(config.telegram.token)
        self._camera = Camera(
            device=config.camera.device,
            width=config.camera.width,
            height=config.camera.height,
            capture_dir=config.system.capture_dir,
        )
        self._detector = YoloDetector(
            model_path=config.detector.model_path,
            input_size=config.detector.input_size,
            confidence_threshold=config.detector.confidence_threshold,
        )
        self._gpio = GpioHandler(
            pin_door=config.gpio.door_sensor,
            pin_button=config.gpio.bypass_button,
            pin_siren=config.gpio.siren,
            pin_led_status=config.gpio.led_status,
            pin_led_alarm=config.gpio.led_alarm,
        )
        self._ld2410 = LD2410(
            port=config.ld2410.port,
            baudrate=config.ld2410.baudrate,
        )
        self._emergency = EmergencyPoll(
            url=config.emergency.url,
            device_id=config.emergency.device_id,
            api_key=config.emergency.api_key,
            poll_interval_sec=config.emergency.poll_interval_sec,
        )
    # ── helpers ──────────────────────────────────────────────────────────────

    def _all_chats(self) -> List[str]:
        ids = [self._cfg.telegram.personal_chat_id]
        ids.extend(self._cfg.telegram.group_chat_ids)
        return [i for i in ids if i]

    def _personal(self) -> str:
        return self._cfg.telegram.personal_chat_id

    # ── motion / detection ───────────────────────────────────────────────────

    def _on_motion(self, frame: LD2410Frame):
        with self._detect_lock:
            now = time.monotonic()
            if now - self._last_detection_time < self._cfg.system.detection_cooldown_sec:
                return
            self._last_detection_time = now
        self._executor.submit(self._process_detection, frame)

    def _process_detection(self, frame: LD2410Frame):
        # NOTE: fungsi ini jalan di dalam ThreadPoolExecutor via .submit().
        # Kalau exception di sini tidak ditangkap sendiri, exception itu akan
        # HILANG DIAM-DIAM (tidak pernah tercetak di log) karena Future-nya
        # tidak pernah di-.result() di manapun. Makanya seluruh isi fungsi
        # dibungkus try/except supaya error aslinya selalu kelihatan di log.
        try:
            logger.info(f"Processing: {frame.state_label} @ {frame.detect_distance}cm")
            t0 = time.monotonic()
            img, path = self._camera.capture_and_save()
            t1 = time.monotonic()
            if img is None or path is None:
                logger.error("Capture failed, skipping detection")
                return

            result: DetectionResult = self._detector.detect(img)
            t2 = time.monotonic()
            logger.info(f"Timing: capture={t1 - t0:.2f}s detect={t2 - t1:.2f}s")

            self._check_vehicle_count_change(result.vehicle_count)

            if result.type == DetectionType.PERSON:
                logger.warning(f"HUMAN DETECTED (conf={result.confidence:.2f})")
                self._telegram.send_message(self._personal(), "⚠️ TERDETEKSI MANUSIA")
                self._telegram.send_photo(self._personal(), path, caption="Deteksi manusia")

            elif result.type == DetectionType.VEHICLE:
                logger.warning(f"VEHICLE DETECTED: {result.label} (conf={result.confidence:.2f})")
                self._telegram.send_message(
                    self._personal(), f"🚗 TERDETEKSI KENDARAAN: {result.label}"
                )
                self._telegram.send_photo(
                    self._personal(), path, caption=f"Deteksi {result.label}"
                )

            else:
                logger.info("Motion: bukan manusia atau kendaraan")
                self._telegram.send_message(
                    self._personal(), "ℹ️ Ada gerak tapi bukan orang atau kendaraan"
                )

        except Exception:
            logger.error(
                "Exception di _process_detection (sebelumnya hilang tanpa jejak):\n"
                + traceback.format_exc()
            )
    def _check_vehicle_count_change(self, current_count: int):
        with self._state_lock:
            previous_count = self._last_vehicle_count
            self._last_vehicle_count = current_count

        if current_count < previous_count:
            logger.warning(f"Kendaraan keluar terdeteksi: {previous_count} -> {current_count}")
            self._telegram.send_message(
                self._personal(),
            f"🚗➡️ Kendaraan KELUAR terdeteksi ({previous_count} → {current_count})"
            )

    # ── door alarm ───────────────────────────────────────────────────────────

    def _on_door_open(self):
        logger.info("Door OPEN — timer dimulai")
        self._gpio.set_status_led(True)
        with self._state_lock:
            if self._door_timer:
                self._door_timer.cancel()
            timeout = self._cfg.system.door_alarm_timeout_sec
            self._door_timer = threading.Timer(timeout, self._trigger_door_alarm)
            self._door_timer.daemon = True
            self._door_timer.start()

    def _on_door_close(self):
        logger.info("Door CLOSED")
        with self._state_lock:
            if self._door_timer:
                self._door_timer.cancel()
                self._door_timer = None
        if not self._alarm_active:
            self._gpio.set_status_led(False)

    def _trigger_door_alarm(self):
        logger.warning("ALARM: pintu terbuka > 1 menit")
        self._gpio.siren_on()
        with self._state_lock:
            self._alarm_active = True
            self._door_timer = None
        self._telegram.broadcast_message(
            self._all_chats(),
            "🚨 ALARM! Pintu terbuka lebih dari 1 menit tanpa respons!"
        )

    def _on_emergency_broadcast(self, device: str):
        logger.warning(f"Emergency broadcast diterima dari {device} -> sirine aktif")
        self._gpio.siren_on()
        with self._state_lock:
            self._alarm_active = True
        self._telegram.broadcast_message(
            self._all_chats(),
            f"🚨 EMERGENCY! Broadcast darurat dari {device}"
        )

    def _cancel_alarm(self):
        with self._state_lock:
            if self._door_timer:
                self._door_timer.cancel()
                self._door_timer = None
            self._alarm_active = False
        self._gpio.siren_off()
        self._gpio.set_status_led(False)
        logger.info("Alarm cancelled")
        if self._gpio.is_door_open:
            logger.info("Pintu masih terbuka setelah /matialarm — timer dimulai ulang")
            self._on_door_open()

    # ── telegram commands ────────────────────────────────────────────────────

    def _cmd_matialarm(self, chat_id: str):
        self._cancel_alarm()
        self._telegram.send_message(chat_id, "✅ Alarm dimatikan")

    def _cmd_status(self, chat_id: str):
        frame = self._ld2410.last_frame
        door = "Terbuka" if self._gpio.is_door_open else "Tertutup"
        siren = "AKTIF 🔊" if self._gpio.is_siren_active else "OFF"
        ld = (
            f"{frame.state_label}, {frame.detect_distance} cm"
            if frame else "Tidak ada data"
        )
        msg = (
            f"📊 STATUS SISTEM\n"
            f"🚪 Pintu   : {door}\n"
            f"🔊 Sirine  : {siren}\n"
            f"📡 LD2410  : {ld}"
        )
        self._telegram.send_message(chat_id, msg)

    def _cmd_foto(self, chat_id: str):
        _, path = self._camera.capture_and_save()
        if path:
            self._telegram.send_photo(chat_id, path, caption="📸 Foto manual")
        else:
            self._telegram.send_message(chat_id, "❌ Gagal mengambil foto")

    def _cmd_restart(self, chat_id: str):
        self._telegram.send_message(chat_id, "🔄 Merestart service...")
        subprocess.Popen(["sudo", "systemctl", "restart", "security.service"])

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        logger.info("Starting SecuritySystem...")
        self._camera.open()
        self._detector.load()

        self._gpio.set_door_callbacks(self._on_door_open, self._on_door_close)
        self._gpio.set_bypass_callback(self._cancel_alarm)

        if self._gpio.is_door_open:
            logger.warning("Pintu sudah terbuka saat startup — memulai timer")
            self._on_door_open()

        self._ld2410.set_motion_callback(self._on_motion)
        self._ld2410.start()

        self._emergency.set_emergency_callback(self._on_emergency_broadcast)
        self._emergency.start()

        self._telegram.register_command("/matialarm", self._cmd_matialarm)
        self._telegram.register_command("/status", self._cmd_status)
        self._telegram.register_command("/foto", self._cmd_foto)
        self._telegram.register_command("/restart", self._cmd_restart)
        self._telegram.start_polling()

        self._gpio.set_status_led(True)
        logger.info("System running")

    def stop(self):
        logger.info("Stopping SecuritySystem...")
        self._ld2410.stop()
        self._emergency.stop()
        self._telegram.stop_polling()
        self._executor.shutdown(wait=False)
        self._camera.close()
        self._gpio.cleanup()
