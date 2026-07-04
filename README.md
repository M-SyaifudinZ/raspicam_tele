# raspicam_tele — Raspberry Pi Security Unit

Sistem keamanan pintar berbasis Raspberry Pi 4 dengan deteksi manusia & kendaraan via YOLO TFLite, sensor mmWave LD2410, dan notifikasi Telegram.

## Hardware Wiring

| Komponen         | GPIO (BCM) | Keterangan                        |
|-----------------|------------|-----------------------------------|
| Magnetic Switch | 17         | Pull-up, HIGH = pintu terbuka     |
| Bypass Button   | 27         | Pull-up, FALLING = ditekan        |
| Sirine 12V      | 22         | Relay OUT, HIGH = aktif           |
| LED Status      | 23         | HIGH = aktif                      |
| LED Alarm       | 24         | HIGH = aktif                      |
| LD2410 TX       | GPIO15/RXD | UART hardware                     |
| LD2410 RX       | GPIO14/TXD | UART hardware                     |
| Kamera OV5647   | CSI        | Ribbon cable ke port CSI          |

## Setup UART untuk LD2410

```bash
# Disable Bluetooth agar /dev/ttyAMA0 bebas
echo "dtoverlay=disable-bt" | sudo tee -a /boot/config.txt
sudo systemctl disable hciuart

# Disable serial console, enable hardware UART
sudo raspi-config
# Interface Options > Serial Port > Login shell: No > Hardware: Yes

sudo reboot
```

## Instalasi

```bash
git clone https://github.com/M-SyaifudinZ/raspicam_tele
cd raspicam_tele

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Taruh model YOLO TFLite di:
# models/yolo.tflite
# Download YOLOv8n: https://github.com/ultralytics/assets/releases

cp .env.example .env
nano .env
```

## Yang Diubah di `.env`

| Key | Keterangan |
|-----|-----------|
| `BOT_TOKEN` | Token dari @BotFather |
| `PERSONAL_CHAT_ID` | ID chat pribadi (cek via @userinfobot) |
| `GROUP_CHAT_IDS` | `id1,id2` untuk grup, kosongkan jika tidak ada |
| `PIN_*` | Sesuaikan wiring fisik (BCM numbering) |
| `LD2410_PORT` | Default `/dev/ttyAMA0` |
| `TFLITE_MODEL_PATH` | Path ke file `.tflite` |
| `DETECTION_CONFIDENCE` | 0.3–0.7 (turunkan jika banyak miss) |
| `DOOR_ALARM_TIMEOUT_SEC` | Default 60 detik |
| `DETECTION_COOLDOWN_SEC` | Min interval antar deteksi, default 30 detik |

## Run Manual

```bash
source venv/bin/activate
python main.py
```

## Deploy sebagai Systemd Service

```bash
sudo cp security.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable security.service
sudo systemctl start security.service

# Monitor log
journalctl -u security.service -f
```

## Perintah Telegram Bot

| Perintah | Fungsi |
|----------|--------|
| `/matialarm` | Matikan alarm dan reset timer pintu |
| `/status` | Cek status pintu, sirine, LD2410 |
| `/foto` | Ambil foto manual dari kamera |
| `/restart` | Restart service via systemctl |

## Logika Sistem

- **LD2410 deteksi gerak** → YOLO TFLite validasi:
  - **Manusia** → kirim "TERDETEKSI MANUSIA" + foto ke Telegram pribadi
  - **Kendaraan** → kirim "TERDETEKSI KENDARAAN: [tipe]" + foto ke Telegram pribadi
  - **Bukan keduanya** → log + kirim status sederhana
- **Pintu terbuka > 1 menit** → Sirine ON + broadcast ke SEMUA Telegram
- **Bypass** (tombol fisik atau `/matialarm`) sebelum 1 menit → Sirine OFF, tanpa notif publik
