# config.py
import os
from datetime import datetime
from typing import Any, Dict

# =========================
# 기본 설정
# =========================
CAMERA_INDEX = 0
MODEL_PATH = "yolo11n.pt"
TRACKER_CONFIG = "bytetrack.yaml"
TARGET_CLASS_ID = 0  # person
CONF_THRES = 0.35
JPEG_QUALITY = 80

CAP_WIDTH = 640
CAP_HEIGHT = 480
CAP_FPS = 30

# =========================
# 공항 CCTV ROI / 라인
# =========================
LINE_X_RATIO = 0.50
LINE_ANGLE_DEG = 0.0        # 수직=0, 양수=오른쪽으로 기울기 (도)
LINE_LENGTH_RATIO = 1.0     # 라인 길이 비율 (0.1~1.0, 1.0=전체 화면 높이)
LINE_COLOR = (0, 255, 255)
LINE_THICKNESS = 2

# =========================
# 이벤트 / 클립
# =========================
MAX_EVENTS = 80
PRE_EVENT_SEC = 2.5
POST_EVENT_SEC = 2.5
MAX_CLIP_QUEUE = 12

TRACK_STALE_SEC = 3.0
TRACK_SIDE_STABLE_FRAMES = 2
EVENT_DEBOUNCE_SEC_PER_TRACK = 1.2

# =========================
# 전력 / 튜너
# =========================
ENABLE_DVFS = True

LOW_POWER_NVP_MODE = 1
MID_POWER_NVP_MODE = 2
HIGH_POWER_NVP_MODE = 0

WATCH_HOLD_SEC = 5.0
EVENT_HOLD_SEC = 3.0

TARGET_DISPLAY_FPS = {
    "IDLE": 10.0,
    "WATCH": 15.0,
    "ALERT": 20.0,
    "EVENT": 20.0,
}

MODE_CONFIG = {
    "IDLE": {
        "model_key": "IDLE",
        "imgsz": 416,
        "infer_every_n": 6,
        "nvpmodel_mode": LOW_POWER_NVP_MODE,
        "jetson_clocks": False,
    },
    "WATCH": {
        "model_key": "WATCH",
        "imgsz": 416,
        "infer_every_n": 3,
        "nvpmodel_mode": MID_POWER_NVP_MODE,
        "jetson_clocks": False,
    },
    "ALERT": {
        "model_key": "ALERT",
        "imgsz": 416,
        "infer_every_n": 2,
        "nvpmodel_mode": MID_POWER_NVP_MODE,
        "jetson_clocks": False,
    },
    "EVENT": {
        "model_key": "EVENT",
        "imgsz": 640,
        "infer_every_n": 1,
        "nvpmodel_mode": HIGH_POWER_NVP_MODE,
        "jetson_clocks": True,
    },
}
# =========================
# 전력 측정
# =========================
ENABLE_SYSFS_POWER = True

POWER_HWMON_CANDIDATES = [
    "/sys/bus/i2c/devices/7-0040/hwmon/hwmon*",
    "/sys/bus/i2c/drivers/ina3221/7-0040/hwmon/hwmon*",
    "/sys/class/hwmon/hwmon*",
]

POWER_CHANNELS = [1, 2, 3]

# =========================
# 로그 / 디렉터리
# =========================
LOG_DIR = "logs"
CLIP_DIR = "clips"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(CLIP_DIR, exist_ok=True)

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

CSV_LOG_PATH = os.path.join(LOG_DIR, f"auto_tuner_metrics_{RUN_ID}.csv")
RUNTIME_LOG_PATH = os.path.join(LOG_DIR, f"auto_tuner_runtime_{RUN_ID}.log")
SUMMARY_JSON_PATH = os.path.join(LOG_DIR, f"auto_tuner_summary_{RUN_ID}.json")
ZONES_JSON_PATH = os.path.join(LOG_DIR, "zones.json")

# =========================
# 공항 CCTV ROI 설정
# =========================
RESTRICTED_ZONES = [
    {
        "id": "RZ-1",
        "name": "Restricted Zone",
        "rect": (0.68, 0.20, 0.98, 0.95),
    }
]

RESTRICTED_EVENT_DEBOUNCE_SEC = 5.0

# =========================
# 공항 CCTV 혼잡 감지 설정
# =========================
CROWD_ZONES = [
    {
        "id": "CZ-1",
        "name": "Crowd Zone",
        "rect": (0.05, 0.20, 0.65, 0.95),
    }
]
MODEL_CONFIG = {
    "IDLE": {
        "model_path": "models/yolo11n.engine",
        "model_name": "YOLO11n TensorRT FP16",
        "model_size": "nano",
        "precision": "FP16",
    },
    "WATCH": {
        "model_path": "models/yolo11n.engine",
        "model_name": "YOLO11n TensorRT FP16",
        "model_size": "nano",
        "precision": "FP16",
    },
    "ALERT": {
        "model_path": "models/yolo11n.engine",
        "model_name": "YOLO11n TensorRT FP16",
        "model_size": "nano",
        "precision": "FP16",
    },
    "EVENT": {
        "model_path": "models/yolo11s.engine",
        "model_name": "YOLO11s TensorRT FP16",
        "model_size": "small",
        "precision": "FP16",
    },
}

CROWD_PERSON_THRESHOLD = 3
CROWD_ALERT_HOLD_SEC = 1.0
CROWD_EVENT_HOLD_SEC = 3.0
CROWD_EVENT_DEBOUNCE_SEC = 8.0

# =========================
# 배회 감지 설정
# =========================
LOITER_ZONES = [
    {
        "id": "LZ-1",
        "name": "Loitering Zone",
        "rect": (0.0, 0.0, 1.0, 1.0),  # 전체 화면
    }
]
LOITER_ALERT_SEC = 15.0        # 15초 이상 → ALERT
LOITER_EVENT_SEC = 30.0        # 30초 이상 → EVENT
LOITER_EVENT_DEBOUNCE_SEC = 60.0  # 같은 사람 이벤트 재발화 간격

# =========================
# 낙상 감지 설정
# =========================
FALL_ASPECT_RATIO_THRESHOLD = 1.5   # width/height > 1.5 → 쓰러진 상태
FALL_NORMAL_RATIO = 0.65            # width/height < 0.65 → 서있는 상태
FALL_HISTORY_FRAMES = 6             # aspect ratio 추적 프레임 수
FALL_MIN_BOX_AREA = 2500            # 너무 작은 박스 무시 (px²)
FALL_EVENT_DEBOUNCE_SEC = 10.0      # 같은 사람 낙상 이벤트 재발화 간격

# =========================
# 클립 자동 정리
# =========================
MAX_CLIP_SIZE_GB = 2.0              # 클립 디렉터리 최대 용량 (GB)
MAX_CLIP_AGE_DAYS = 7               # 최대 보관 기간 (일)
CLIP_CLEANUP_INTERVAL_SEC = 300     # 정리 주기 (초, 5분)