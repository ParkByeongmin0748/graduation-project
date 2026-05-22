# state.py
import queue
import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from config import (
    RUN_ID,
    CSV_LOG_PATH,
    RUNTIME_LOG_PATH,
    SUMMARY_JSON_PATH,
    MODE_CONFIG,
    ENABLE_DVFS,
    MAX_EVENTS,
    MAX_CLIP_QUEUE,
)

# =========================
# 공유 상태
# =========================
state_lock = threading.Lock()
clip_queue: "queue.Queue[dict]" = queue.Queue(maxsize=MAX_CLIP_QUEUE)

latest_jpeg: Optional[bytes] = None
latest_raw_jpeg: Optional[bytes] = None
stop_event = threading.Event()

latest_metrics: Dict[str, Any] = {
    "model_path": None,
    "model_name": None,
    "model_size": None,
    "model_precision": None,
    "run_id": RUN_ID,
    "fps": 0.0,
    "person_count": 0,
    "inference_ms": 0.0,
    "cpu_usage_percent": None,
    "gpu_usage_percent": None,
    "cpu_temp_c": None,
    "gpu_temp_c": None,
    "board_power_w": None,
    "power_source": None,
    "rail_vdd_in_w": None,
    "rail_cpu_gpu_cv_w": None,
    "rail_soc_w": None,
    "last_update": 0.0,
    "camera_ok": False,
    "model_ok": False,
    "enter_count": 0,
    "exit_count": 0,
    "event_count": 0,
    "current_mode": "WATCH",
    "event_level": "NONE",
    "event_reason": None,
    "event_type": None,
    "roi_id": None,
    "crowd_count": 0,
    "crowd_zone_id": None,
    "crowd_duration_sec": 0.0,
    # 배회 감지
    "loiter_tracks": {},          # {track_id: duration_sec}
    # 낙상 감지
    "fall_track_id": None,
    "imgsz": MODE_CONFIG["WATCH"]["imgsz"],
    "infer_every_n": MODE_CONFIG["WATCH"]["infer_every_n"],
    "dvfs_enabled": ENABLE_DVFS,
    "loop_ms": 0.0,
    "capture_ms": 0.0,
    "annotate_ms": 0.0,
    "jpeg_ms": 0.0,
    "clip_queue_size": 0,
    "csv_path": CSV_LOG_PATH,
    "runtime_log_path": RUNTIME_LOG_PATH,
    "summary_json_path": SUMMARY_JSON_PATH,
}

event_log: Deque[Dict[str, Any]] = deque(maxlen=MAX_EVENTS)
frame_buffer: Deque[Dict[str, Any]] = deque()
active_clip_jobs: List[Dict[str, Any]] = []

track_histories: Dict[int, Dict[str, Any]] = {}
crowd_zone_states = {}
frame_index = 0
current_mode = "WATCH"
event_seq = 0

last_boxes: List[Tuple[int, int, int, int, float, Optional[int]]] = []
last_person_count = 0
last_inference_ms = 0.0
last_person_seen_ts = 0.0
last_event_ts = 0.0

csv_initialized = False

mode_stats = {
    "IDLE": {"samples": 0, "fps_sum": 0.0, "power_sum": 0.0, "infer_sum": 0.0, "power_count": 0},
    "WATCH": {"samples": 0, "fps_sum": 0.0, "power_sum": 0.0, "infer_sum": 0.0, "power_count": 0},
    "ALERT": {"samples": 0, "fps_sum": 0.0, "power_sum": 0.0, "infer_sum": 0.0, "power_count": 0},
    "EVENT": {"samples": 0, "fps_sum": 0.0, "power_sum": 0.0, "infer_sum": 0.0, "power_count": 0},
}