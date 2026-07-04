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

PERSON_CLASS_ID = 0
VEHICLE_CLASS_IDS = {1, 2, 3, 5, 7}  # bicycle, car, motorcycle, bus, truck
VEHICLE_LABELS = {1: "Sepeda", 2: "Mobil", 3: "Motor", 5: "Bus", 7: "Truk"}


class DetectionType(Enum):
    NONE = "none"
    PERSON = "person"
    VEHICLE = "vehicle"


@dataclass
class DetectionResult:
    type: DetectionType
    label: str = ""
    confidence: float = 0.0


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
            self._interpreter = tflite.Interpreter(model_path=self._model_path)
            self._interpreter.allocate_tensors()
            self._input_idx = self._interpreter.get_input_details()[0]["index"]
            self._output_idx = self._interpreter.get_output_details()[0]["index"]
            self._loaded = True
            logger.info(f"YOLO loaded: {self._model_path}")
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
        return np.expand_dims(img, axis=0)

    def _postprocess(self, output: np.ndarray) -> DetectionResult:
        # YOLOv8n TFLite: [1, 84, 8400] -> transpose -> [8400, 84]
        # cols 0-3: bbox, cols 4-83: COCO 80 class scores
        detections = output[0].T
        class_scores = detections[:, 4:]

        person_conf = float(np.max(class_scores[:, PERSON_CLASS_ID]))
        logger.debug(f"Person conf: {person_conf:.3f}")
        if person_conf >= self._threshold:
            return DetectionResult(DetectionType.PERSON, "Manusia", person_conf)

        best_conf, best_id = 0.0, -1
        for cid in VEHICLE_CLASS_IDS:
            conf = float(np.max(class_scores[:, cid]))
            if conf > best_conf:
                best_conf, best_id = conf, cid

        logger.debug(f"Vehicle conf: {best_conf:.3f} class={best_id}")
        if best_conf >= self._threshold:
            return DetectionResult(
                DetectionType.VEHICLE,
                VEHICLE_LABELS.get(best_id, "Kendaraan"),
                best_conf,
            )

        return DetectionResult(DetectionType.NONE)
