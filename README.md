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

##Instalasi

1. Install pyenv & Python 3.11

Raspberry Pi OS terbaru (berbasis Debian Trixie) hanya menyediakan Python 3.13 secara default, dan versi ini tidak kompatibel dengan tflite-runtime. Gunakan pyenv untuk menginstall Python 3.11 tanpa mengubah Python sistem:

bashsudo apt update
sudo apt install -y make build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev curl git \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

curl https://pyenv.run | bash

Tambahkan ke ~/.bashrc:

bashexport PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"

Reload shell:

bashsource ~/.bashrc

Install Python 3.11 (proses compile, ±10-15 menit di Pi 4):

bashpyenv install 3.11.9

2. Clone repo & buat virtual environment

bashgit clone https://github.com/M-SyaifudinZ/raspicam_tele.git
cd raspicam_tele
~/.pyenv/versions/3.11.9/bin/python3 -m venv venv
source venv/bin/activate

3. Install dependencies

bashpip install -r requirements.txt


Semua dependency (numpy, opencv-python-headless, tflite-runtime, dll) memiliki prebuilt wheel di piwheels untuk Python 3.11 di aarch64, sehingga tidak perlu compile dari source.



4. Enable UART untuk sensor LD2410 & disable Bluetooth

LD2410 berkomunikasi lewat UART dengan baudrate tinggi (256000). Raspberry Pi 4 punya dua UART: PL011 (stabil) dan mini-UART (kurang stabil di baudrate tinggi, dan biasanya dipakai Bluetooth secara default). Agar LD2410 memakai UART penuh yang stabil, Bluetooth perlu di-nonaktifkan:

bashsudo raspi-config

Masuk ke: Interface Options → Serial Port


"Would you like a login shell to be accessible over serial?" → No
"Would you like the serial port hardware to be enabled?" → Yes


Lalu edit config boot:

bashsudo nano /boot/firmware/config.txt

Tambahkan baris:

dtoverlay=disable-bt

Reboot:

bashsudo reboot

Setelah reboot, pastikan /dev/serial0 mengarah ke ttyAMA0 (bukan ttyS0):

bashls -l /dev/serial0

5. Wiring LD2410

LD2410Raspberry Pi 4VCC5V (Pin 2 atau 4)GNDGND (Pin 6, dst.)TXRX — GPIO15 (Pin 10)RXTX — GPIO14 (Pin 8)

⚠️ TX dan RX harus disilang (TX ke RX, bukan TX ke TX).

6. Konfigurasi environment variables

Copy file contoh env, lalu sesuaikan:

bashcp .env.example .env
nano .env

Isi minimal yang perlu diset:

TELEGRAM_BOT_TOKEN=isi_token_bot_kamu
LD2410_PORT=/dev/serial0
LD2410_BAUDRATE=256000
CAMERA_WIDTH=640
CAMERA_HEIGHT=480


Resolusi kamera default 640x480 karena sensor CSI sering gagal start pipeline (unicam: Failed to start media pipeline) saat diminta resolusi tinggi (1920x1080) secara langsung lewat OpenCV/V4L2. Jika ingin resolusi lebih tinggi, naikkan bertahap (mis. 1280x720) dan uji stabilitasnya dulu.



7. Jalankan

bashsource venv/bin/activate
python main.py

Testing sensor LD2410 secara terpisah

Untuk mengetes sensor LD2410 saja tanpa menjalankan kamera/YOLO/GPIO/Telegram:

bashpython test_ld2410.py

Troubleshooting

ModuleNotFoundError: No module named 'serial'

Virtual environment belum aktif. Jalankan source venv/bin/activate sebelum menjalankan script.

RuntimeError: Failed to add edge detection

Bug kompatibilitas RPi.GPIO dengan kernel Linux 6.6+. Solusinya adalah mengganti RPi.GPIO dengan rpi-lgpio (drop-in replacement, tidak perlu ubah kode):

bashpip uninstall RPi.GPIO -y
pip install rpi-lgpio

serial.serialutil.SerialException: could not open port /dev/ttyAMA0

Pastikan LD2410_PORT di .env diset ke /dev/serial0, bukan hardcode /dev/ttyAMA0, karena penamaan device UART bisa berbeda tergantung konfigurasi board.

Sensor LD2410 connect tapi tidak ada data terbaca

Kemungkinan besar UART masih memakai mini-UART (ttyS0) yang tidak stabil di baudrate tinggi. Pastikan langkah "Enable UART & disable Bluetooth" di atas sudah dilakukan, dan cek wiring TX/RX tidak terbalik.

unicam: Failed to start media pipeline: -22 / Camera capture failed

Bisa disebabkan oleh dua hal:


Resolusi tidak didukung — gunakan resolusi default 640x480 di .env.
Undervoltage — cek dengan vcgencmd get_throttled. Jika hasilnya bukan 0x0, atau muncul Undervoltage detected! di dmesg -T, ganti power supply dengan adaptor resmi Raspberry Pi 4 (5.1V/3A) dan gunakan kabel USB-C yang berkualitas.


Telegram Read timed out sesekali

Wajar untuk metode getUpdates (long-polling). Jika hanya terjadi sesekali dan bot tetap berjalan normal, tidak perlu dikhawatirkan. Jika terjadi terus-menerus, cek koneksi internet Pi.

Known Issues


numpy dipin ke 1.26.4 — versi ini membutuhkan Python <3.13, karena itu setup wajib menggunakan Python 3.11 via pyenv.
Resolusi kamera default 640x480 untuk menghindari kegagalan pipeline unicam dan mengurangi beban yang bisa memicu undervoltage.

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
