import logging
import signal
import sys
import time
from pathlib import Path

from config import CONFIG
from src.security_system import SecuritySystem


def _setup_logging(log_dir: str):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.FileHandler(f"{log_dir}/security.log")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _validate_config():
    if not CONFIG.telegram.token:
        sys.exit("ERROR: BOT_TOKEN tidak di-set di .env")
    if not CONFIG.telegram.personal_chat_id:
        sys.exit("ERROR: PERSONAL_CHAT_ID tidak di-set di .env")


def main():
    _setup_logging(CONFIG.system.log_dir)
    _validate_config()

    system = SecuritySystem(CONFIG)

    def _shutdown(sig, frame):
        logging.getLogger(__name__).info(f"Signal {sig}, shutdown...")
        system.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    system.start()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
