import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

try:
    import tflite_runtime.interpreter as tflite
    _TFLITE_OK = True
except ImportError:
    try:
        import tensorflow.lite.python.interpreter as tflite
        _TFLITE_OK = True
    except ImportError:
        _TFLITE_OK = False
        logger.warning("tflite_runtime tidak tersedia — mock mode (fail-open ke PERSON)")

# Numbering ini HARUS sama persis dengan urutan "names" di data.yaml model
# custom ini (bukan COCO 80-kelas standar):
#   names: ['bus', 'car', 'motorcycle', 'person', 'pickup', 'truck']
#   index:    0      1         2           3         4         5
PERSON_CLASS_ID = 3
VEHICLE_CLASS_IDS = {0, 1, 2, 4, 5}  # bus, car, motorcycle, pickup, truck
VEHICLE_LABELS = {
    0: "Bus",
    1: "Mobil",
    2: "Motor",
    4: "Pickup",
    5: "Truk",
}


class DetectionType(Enum):
    NONE = "none"
    PERSON = "person"
    VEHICLE = "vehicle"


@dataclass
class DetectionResult:
    type: DetectionType
    label: str = ""
    confidence: float = 0.0
    vehicle_count: int = 0

class YoloDetector:
    def __init__(self, model_path: str, input_size: int = 640,
                 confidence_threshold: float = 0.5):
        self._model_path = model_path
        self._input_size = input_size
        self._threshold = confidence_threshold
        self._interpreter = None
        self._input_idx: Optional[int] = None
        self._output_idx: Optional[int] = None
        self._loaded = False

    def load(self):
        if not _TFLITE_OK:
            logger.warning("TFLite unavailable, skipping model load")
            return
        try:
            # num_threads=4: Pi 4 punya 4 core, tapi default TFLite cuma
            # pakai 1 thread kalau tidak diset -> inference jadi lambat.
            self._interpreter = tflite.Interpreter(
                model_path=self._model_path, num_threads=4
            )
            self._interpreter.allocate_tensors()
            input_details = self._interpreter.get_input_details()[0]
            output_details = self._interpreter.get_output_details()[0]
            self._input_idx = input_details["index"]
            self._output_idx = output_details["index"]
            self._loaded = True
            logger.info(f"YOLO loaded: {self._model_path}")
            # Log shape & dtype asli model supaya gampang ketahuan kalau
            # tidak cocok sama asumsi di _preprocess/_postprocess di bawah
            # (float32, input 640x640, output [1,84,8400]).
            logger.info(
                f"Model input: shape={input_details['shape']} dtype={input_details['dtype']}"
            )
            logger.info(
                f"Model output: shape={output_details['shape']} dtype={output_details['dtype']}"
            )
        except Exception as e:
            logger.error(f"Model load failed: {e}")

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Prioritas: person > vehicle > none. Fail-open ke PERSON jika model tidak ada."""
        if not self._loaded or not _TFLITE_OK:
            return DetectionResult(DetectionType.PERSON, "Manusia", 1.0)

        tensor = self._preprocess(frame)
        self._interpreter.set_tensor(self._input_idx, tensor)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_idx)
        return self._postprocess(output)

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self._input_size, self._input_size))
        img = img.astype(np.float32) / 255.0
        # Model ini minta NCHW [1, 3, H, W] (channel duluan), bukan NHWC
        # [1, H, W, 3] seperti asumsi lama. HWC -> CHW dulu baru tambah axis batch.
        img = np.transpose(img, (2, 0, 1))
        return np.expand_dims(img, axis=0)

    def _postprocess(self, output: np.ndarray) -> DetectionResult:
        # Model ini export dengan NMS sudah dibakar ke graph (end2end / nms=True),
        # bukan output mentah [1, 84, 8400]. Bentuknya [1, 300, 6]: sampai 300
        # deteksi, tiap baris = [x1, y1, x2, y2, confidence, class_id].
        # Slot yang tidak terpakai biasanya diisi confidence=0, jadi aman
        # untuk dilewati/dibiarkan (bakal kalah sama threshold di bawah).
        detections = output[0]  # -> [300, 6]

        person_conf = 0.0
        best_vehicle_conf, best_vehicle_id = 0.0, -1
        vehicle_count = 0 
        for x1, y1, x2, y2, conf, class_id in detections:
            conf = float(conf)
            if conf <= 0.0:
                continue
            class_id = int(class_id)
            if class_id == PERSON_CLASS_ID:
                person_conf = max(person_conf, conf)
            elif class_id in VEHICLE_CLASS_IDS:
                if conf >= self._threshold:
                    vehicle_count += 1   # ← tambahan: hitung semua yang lolos threshold
                if conf > best_vehicle_conf:
                    best_vehicle_conf, best_vehicle_id = conf, class_id
        logger.debug(f"Person conf: {person_conf:.3f}")
        if person_conf >= self._threshold:
            return DetectionResult(DetectionType.PERSON, "Manusia", person_conf)

        logger.debug(f"Vehicle conf: {best_vehicle_conf:.3f} class={best_vehicle_id}")
        if best_vehicle_conf >= self._threshold:
            return DetectionResult(
                DetectionType.VEHICLE,
                VEHICLE_LABELS.get(best_vehicle_id, "Kendaraan"),
                best_vehicle_conf,
            )

        return DetectionResult(DetectionType.NONE, vehicle_count=vehicle_count)
