"""
Standalone tester untuk sensor LD2410 saja.
Tidak menjalankan kamera, YOLO, GPIO, atau Telegram — cuma cek motion detected atau tidak.

Cara pakai:
    python test_ld2410.py
Tekan Ctrl+C untuk berhenti.
"""

import os
import sys
import time
import logging

from dotenv import load_dotenv

# supaya bisa import dari folder src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ld2410 import LD2410  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_ld2410")

load_dotenv()

PORT = os.getenv("LD2410_PORT", "/dev/serial0")
BAUDRATE = int(os.getenv("LD2410_BAUDRATE", "256000"))


def on_motion(frame):
    print(f"🟢 MOTION DETECTED — {frame.state_label} "
          f"(move={frame.move_distance}cm/{frame.move_energy}, "
          f"still={frame.still_distance}cm/{frame.still_energy})")


def main():
    print(f"Connecting to LD2410 on {PORT} @ {BAUDRATE} baud...")
    sensor = LD2410(port=PORT, baudrate=BAUDRATE)

    sensor.set_motion_callback(on_motion)
    sensor.start()
    print("LD2410 running. Waving your hand in front of the sensor to test.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            frame = sensor.last_frame
            if frame is not None:
                status = "🟢 MOTION" if frame.has_target else "⚪ No motion"
                print(f"{status} | {frame.state_label} "
                      f"(move={frame.move_distance}cm/{frame.move_energy}, "
                      f"still={frame.still_distance}cm/{frame.still_energy})")
            else:
                print("Waiting for data...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        sensor.stop()
        print("LD2410 stopped. Bye.")


if __name__ == "__main__":
    main()
