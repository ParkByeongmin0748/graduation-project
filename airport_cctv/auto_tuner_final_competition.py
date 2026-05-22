#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jetson Xavier / Jetson NX Auto Tuner
- FastAPI dashboard + MJPEG stream
- YOLO track + line crossing event detection
- Event clip save
- tegrastats + INA3221(sysfs) power monitor
- Timestamped CSV logging / runtime logging
- Mode summary endpoint
- Safer event debounce / track stabilization
- Basic adaptive tuner

실행 예시:
    sudo .venv/bin/python3 auto_tuner_final_competition.py
또는
    sudo .venv/bin/python3 -m uvicorn auto_tuner_final_competition:app --host 0.0.0.0 --port 8000
"""

import csv
import glob
import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from ultralytics import YOLO


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

LINE_X_RATIO = 0.50
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
# 튜너 / 전력
# =========================
ENABLE_DVFS = True

# Xavier에서 실제 nvpmodel 값 확인 후 필요 시 수정
LOW_POWER_NVP_MODE = 1
MID_POWER_NVP_MODE = 2
HIGH_POWER_NVP_MODE = 0

WATCH_HOLD_SEC = 5.0
EVENT_HOLD_SEC = 3.0

TARGET_DISPLAY_FPS = {
    "IDLE": 15.0,
    "WATCH": 20.0,
    "EVENT": 20.0,
}

MODE_CONFIG: Dict[str, Dict[str, Any]] = {
    "IDLE": {
        "imgsz": 416,
        "infer_every_n": 3,
        "nvpmodel_mode": LOW_POWER_NVP_MODE,
        "jetson_clocks": False,
    },
    "WATCH": {
        "imgsz": 512,
        "infer_every_n": 2,
        "nvpmodel_mode": MID_POWER_NVP_MODE,
        "jetson_clocks": False,
    },
    "EVENT": {
        "imgsz": 640,
        "infer_every_n": 1,
        "nvpmodel_mode": HIGH_POWER_NVP_MODE,
        "jetson_clocks": True,
    },
}

ENABLE_SYSFS_POWER = True
POWER_HWMON_CANDIDATES = [
    "/sys/bus/i2c/devices/7-0040/hwmon/hwmon*",
    "/sys/bus/i2c/drivers/ina3221/7-0040/hwmon/hwmon*",
    "/sys/class/hwmon/hwmon*",
]
POWER_CHANNELS = [1, 2, 3]  # VDD_IN / VDD_CPU_GPU_CV / VDD_SOC

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(RUNTIME_LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto_tuner")


# =========================
# 전역 상태
# =========================
app = FastAPI(title="Jetson Xavier Auto Tuner")

state_lock = threading.Lock()
clip_queue: "queue.Queue[dict]" = queue.Queue(maxsize=MAX_CLIP_QUEUE)

latest_jpeg: Optional[bytes] = None
stop_event = threading.Event()

latest_metrics: Dict[str, Any] = {
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
    "EVENT": {"samples": 0, "fps_sum": 0.0, "power_sum": 0.0, "infer_sum": 0.0, "power_count": 0},
}


# =========================
# 유틸
# =========================
def _avg(nums: List[Optional[float]]) -> Optional[float]:
    nums = [float(n) for n in nums if n is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def short_time_str(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read().strip().replace("\x00", "")
    except Exception:
        return None


def run_cmd_quiet(cmd: List[str]) -> bool:
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.warning("command failed: %s | %s", " ".join(cmd), e)
        return False


def limit_fps(mode_name: str, loop_start_ts: float) -> None:
    target_fps = TARGET_DISPLAY_FPS[mode_name]
    target_dt = 1.0 / max(target_fps, 1.0)
    elapsed = time.time() - loop_start_ts
    remain = target_dt - elapsed
    if remain > 0:
        time.sleep(remain)


def detect_device_model() -> str:
    for path in ["/proc/device-tree/model", "/sys/firmware/devicetree/base/model"]:
        value = read_text_file(path)
        if value:
            return value
    return "Unknown Jetson"


# =========================
# DVFS / 모드
# =========================
def apply_power_mode(mode_name: str) -> None:
    cfg = MODE_CONFIG[mode_name]
    if not ENABLE_DVFS:
        return

    nvp_mode = cfg["nvpmodel_mode"]
    use_clocks = cfg["jetson_clocks"]

    run_cmd_quiet(["nvpmodel", "-m", str(nvp_mode)])
    if use_clocks:
        run_cmd_quiet(["jetson_clocks"])
    
def switch_mode_if_needed(desired_mode: str) -> None:
    global current_mode
    if desired_mode == current_mode:
        return

    current_mode = desired_mode
    apply_power_mode(current_mode)

    with state_lock:
        latest_metrics["current_mode"] = current_mode
        latest_metrics["imgsz"] = MODE_CONFIG[current_mode]["imgsz"]
        latest_metrics["infer_every_n"] = MODE_CONFIG[current_mode]["infer_every_n"]

    logger.info("[TUNER] mode -> %s", current_mode)


def decide_mode(now_ts: float, person_count: int, latest_power_w: Optional[float]) -> str:
    global last_person_seen_ts, last_event_ts

    if person_count > 0:
        last_person_seen_ts = now_ts

    if now_ts - last_event_ts <= EVENT_HOLD_SEC:
        return "EVENT"

    if now_ts - last_person_seen_ts <= WATCH_HOLD_SEC:
        if latest_power_w is not None and latest_power_w > 7.5:
            return "WATCH"
        return "WATCH"

    return "IDLE"


# =========================
# CSV 로그 / 요약
# =========================
CSV_HEADER = [
    "timestamp",
    "mode",
    "fps",
    "inference_ms",
    "person_count",
    "imgsz",
    "infer_every_n",
    "cpu_usage_percent",
    "gpu_usage_percent",
    "cpu_temp_c",
    "gpu_temp_c",
    "board_power_w",
    "power_source",
    "rail_vdd_in_w",
    "rail_cpu_gpu_cv_w",
    "rail_soc_w",
    "loop_ms",
    "capture_ms",
    "annotate_ms",
    "jpeg_ms",
    "clip_queue_size",
    "enter_count",
    "exit_count",
    "event_count",
]


def init_csv_log() -> None:
    global csv_initialized
    if csv_initialized:
        return

    with open(CSV_LOG_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_HEADER)

    csv_initialized = True
    logger.info("CSV log path: %s", CSV_LOG_PATH)


def update_mode_stats(snapshot: Dict[str, Any]) -> None:
    mode = snapshot.get("current_mode")
    if mode not in mode_stats:
        return

    stats = mode_stats[mode]
    stats["samples"] += 1
    stats["fps_sum"] += float(snapshot.get("fps") or 0.0)
    stats["infer_sum"] += float(snapshot.get("inference_ms") or 0.0)

    power_w = snapshot.get("board_power_w")
    if power_w is not None:
        stats["power_sum"] += float(power_w)
        stats["power_count"] += 1


def build_summary() -> Dict[str, Any]:
    result = {
        "run_id": RUN_ID,
        "generated_at": now_str(),
        "device_model": detect_device_model(),
        "csv_path": CSV_LOG_PATH,
        "runtime_log_path": RUNTIME_LOG_PATH,
        "modes": {},
    }

    for mode, stats in mode_stats.items():
        samples = stats["samples"]
        fps_avg = round(stats["fps_sum"] / samples, 2) if samples else None
        infer_avg = round(stats["infer_sum"] / samples, 2) if samples else None
        power_avg = round(stats["power_sum"] / stats["power_count"], 3) if stats["power_count"] else None

        result["modes"][mode] = {
            "samples": samples,
            "avg_fps": fps_avg,
            "avg_inference_ms": infer_avg,
            "avg_power_w": power_avg,
        }

    with state_lock:
        result["enter_count"] = latest_metrics["enter_count"]
        result["exit_count"] = latest_metrics["exit_count"]
        result["event_count"] = latest_metrics["event_count"]

    return result


def write_summary_json() -> None:
    summary = build_summary()
    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def csv_logger_worker() -> None:
    init_csv_log()

    while not stop_event.is_set():
        with state_lock:
            last_update = latest_metrics.get("last_update", 0.0)
            if not last_update or last_update <= 0:
                snapshot = None
            else:
                snapshot = dict(latest_metrics)

        if snapshot is not None:
            row = [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot["last_update"])),
                snapshot.get("current_mode"),
                snapshot.get("fps"),
                snapshot.get("inference_ms"),
                snapshot.get("person_count"),
                snapshot.get("imgsz"),
                snapshot.get("infer_every_n"),
                snapshot.get("cpu_usage_percent"),
                snapshot.get("gpu_usage_percent"),
                snapshot.get("cpu_temp_c"),
                snapshot.get("gpu_temp_c"),
                snapshot.get("board_power_w"),
                snapshot.get("power_source"),
                snapshot.get("rail_vdd_in_w"),
                snapshot.get("rail_cpu_gpu_cv_w"),
                snapshot.get("rail_soc_w"),
                snapshot.get("loop_ms"),
                snapshot.get("capture_ms"),
                snapshot.get("annotate_ms"),
                snapshot.get("jpeg_ms"),
                snapshot.get("clip_queue_size"),
                snapshot.get("enter_count"),
                snapshot.get("exit_count"),
                snapshot.get("event_count"),
            ]

            with open(CSV_LOG_PATH, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)

            update_mode_stats(snapshot)
            write_summary_json()

        time.sleep(1.0)


# =========================
# tegrastats 파싱
# =========================
def parse_power_from_tegrastats(line: str) -> Dict[str, Optional[Any]]:
    result: Dict[str, Optional[Any]] = {"power_w": None, "source": None}

    for pat in [r"(VDD_IN)\s+(\d+)mW/(\d+)mW", r"(POM_5V_IN)\s+(\d+)mW/(\d+)mW"]:
        m = re.search(pat, line)
        if m:
            result["power_w"] = round(int(m.group(2)) / 1000.0, 3)
            result["source"] = m.group(1)
            return result

    rail_names = ["VDD_CPU_GPU_CV", "VDD_SOC", "VDDQ_VDD2_1V8AO", "GPU", "CPU", "SOC", "CV"]
    total_mw = 0
    found_any = False
    for rail in rail_names:
        m = re.search(rf"({rail})\s+(\d+)mW/(\d+)mW", line)
        if m:
            total_mw += int(m.group(2))
            found_any = True

    if found_any:
        result["power_w"] = round(total_mw / 1000.0, 3)
        result["source"] = "TEGRSTATS_SUM_RAILS"

    return result


def parse_tegrastats_line(line: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}

    cpu_match = re.search(r"CPU\s+\[(.*?)\]", line)
    if cpu_match:
        cpu_items = cpu_match.group(1).split(",")
        cpu_utils = []
        for item in cpu_items:
            m = re.search(r"(\d+)%", item.strip())
            if m:
                cpu_utils.append(int(m.group(1)))
        data["cpu_usage_percent"] = _avg(cpu_utils)

    gpu_match = re.search(r"GR3D_FREQ\s+(\d+)%", line)
    if gpu_match:
        data["gpu_usage_percent"] = int(gpu_match.group(1))

    cpu_temp_match = re.search(r"\bCPU@([0-9.]+)C", line)
    if cpu_temp_match:
        data["cpu_temp_c"] = float(cpu_temp_match.group(1))

    gpu_temp_match = re.search(r"\bGPU@([0-9.]+)C", line)
    if gpu_temp_match:
        data["gpu_temp_c"] = float(gpu_temp_match.group(1))

    power_info = parse_power_from_tegrastats(line)
    if power_info["power_w"] is not None:
        data["board_power_w"] = power_info["power_w"]
        data["power_source"] = power_info["source"]

    return data


def tegrastats_worker() -> None:
    cmd = ["tegrastats", "--interval", "1000"]
    proc = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None

        for line in proc.stdout:
            if stop_event.is_set():
                break
            parsed = parse_tegrastats_line(line)
            if not parsed:
                continue
            with state_lock:
                for key, value in parsed.items():
                    if key == "board_power_w" and str(latest_metrics.get("power_source", "")).startswith("SYSFS"):
                        continue
                    if key == "power_source" and str(latest_metrics.get("power_source", "")).startswith("SYSFS"):
                        continue
                    latest_metrics[key] = value

    except Exception as e:
        logger.warning("tegrastats worker failed: %s", e)
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass


# =========================
# sysfs INA3221 전력 읽기
# =========================
def find_power_hwmon() -> Optional[str]:
    found = []
    for pattern in POWER_HWMON_CANDIDATES:
        for p in glob.glob(pattern):
            if read_text_file(os.path.join(p, "name")) == "ina3221":
                found.append(p)
    found = sorted(set(found))
    return found[0] if found else None


def read_power_channel(base: str, ch: int) -> Optional[Dict[str, Any]]:
    label = read_text_file(os.path.join(base, f"in{ch}_label"))
    voltage = read_text_file(os.path.join(base, f"in{ch}_input"))
    current = read_text_file(os.path.join(base, f"curr{ch}_input"))
    enable = read_text_file(os.path.join(base, f"in{ch}_enable"))

    if label is None and voltage is None and current is None:
        return None

    voltage_mV = safe_float(voltage)
    current_mA = safe_float(current)

    power_w = None
    if voltage_mV is not None and current_mA is not None:
        power_w = round((voltage_mV * current_mA) / 1_000_000.0, 3)

    return {
        "label": label or f"CH{ch}",
        "enable": enable,
        "voltage_mV": voltage_mV,
        "current_mA": current_mA,
        "power_w": power_w,
    }


def read_board_power_from_sysfs() -> Dict[str, Any]:
    result = {
        "board_power_w": None,
        "power_source": None,
        "rail_vdd_in_w": None,
        "rail_cpu_gpu_cv_w": None,
        "rail_soc_w": None,
    }

    base = find_power_hwmon()
    if not base:
        result["power_source"] = "SYSFS_NOT_FOUND"
        return result

    rails: Dict[str, Optional[float]] = {}
    total_w = 0.0
    found_any = False

    for ch in POWER_CHANNELS:
        info = read_power_channel(base, ch)
        if not info:
            continue
        rails[info["label"]] = info["power_w"]
        if info["power_w"] is not None:
            total_w += info["power_w"]
            found_any = True

    result["rail_vdd_in_w"] = rails.get("VDD_IN")
    result["rail_cpu_gpu_cv_w"] = rails.get("VDD_CPU_GPU_CV")
    result["rail_soc_w"] = rails.get("VDD_SOC")

    if result["rail_vdd_in_w"] is not None:
        result["board_power_w"] = result["rail_vdd_in_w"]
        result["power_source"] = "SYSFS_VDD_IN"
    elif found_any:
        result["board_power_w"] = round(total_w, 3)
        result["power_source"] = "SYSFS_SUM"
    else:
        result["power_source"] = "SYSFS_NO_DATA"

    return result


def power_sysfs_worker() -> None:
    if not ENABLE_SYSFS_POWER:
        return

    while not stop_event.is_set():
        try:
            info = read_board_power_from_sysfs()
            with state_lock:
                if info.get("board_power_w") is not None:
                    latest_metrics["board_power_w"] = info["board_power_w"]
                    latest_metrics["power_source"] = info["power_source"]

                latest_metrics["rail_vdd_in_w"] = info.get("rail_vdd_in_w")
                latest_metrics["rail_cpu_gpu_cv_w"] = info.get("rail_cpu_gpu_cv_w")
                latest_metrics["rail_soc_w"] = info.get("rail_soc_w")
        except Exception as e:
            logger.warning("sysfs power worker failed: %s", e)

        time.sleep(1.0)


# =========================
# 이벤트 / 트래킹
# =========================
def get_box_side(x1: int, x2: int, line_x: int) -> str:
    if x2 < line_x:
        return "left"
    if x1 > line_x:
        return "right"
    return "overlap"


def cleanup_stale_tracks(max_age_sec: float = TRACK_STALE_SEC) -> None:
    now = time.time()
    dead_ids = []
    for track_id, info in track_histories.items():
        if now - info["last_seen"] > max_age_sec:
            dead_ids.append(track_id)
    for track_id in dead_ids:
        track_histories.pop(track_id, None)


def queue_clip_job(event_id: int, event_type: str, track_id: int, event_ts: float) -> None:
    with state_lock:
        pre_frames = [
            item["frame"].copy()
            for item in frame_buffer
            if item["ts"] >= event_ts - PRE_EVENT_SEC
        ]

    if not pre_frames:
        return

    h, w = pre_frames[0].shape[:2]
    job = {
        "event_id": event_id,
        "event_type": event_type,
        "track_id": track_id,
        "event_ts": event_ts,
        "post_until": event_ts + POST_EVENT_SEC,
        "frames": pre_frames,
        "width": w,
        "height": h,
        "done": False,
    }
    active_clip_jobs.append(job)


def finalize_clip_job(job: Dict[str, Any]) -> None:
    raw_filename = f"event_{job['event_id']}_{job['event_type'].lower()}_{int(job['event_ts'])}_raw.mp4"
    raw_filepath = os.path.join(CLIP_DIR, raw_filename)

    final_filename = f"event_{job['event_id']}_{job['event_type'].lower()}_{int(job['event_ts'])}.mp4"
    final_filepath = os.path.join(CLIP_DIR, final_filename)

    with state_lock:
        fps = latest_metrics.get("fps", 20.0) or 20.0
    fps = max(5.0, min(30.0, float(fps)))

    writer = cv2.VideoWriter(
        raw_filepath,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (job["width"], job["height"]),
    )
    try:
        for frame in job["frames"]:
            if frame is None:
                continue
            if frame.shape[1] != job["width"] or frame.shape[0] != job["height"]:
                frame = cv2.resize(frame, (job["width"], job["height"]))
            writer.write(frame)
    finally:
        writer.release()

    ffmpeg_ok = False
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", raw_filepath,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                final_filepath,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ffmpeg_ok = True
    except Exception as e:
        logger.warning("ffmpeg re-encode failed: %s", e)

    if ffmpeg_ok:
        clip_filename = final_filename
        clip_path = final_filepath
        try:
            os.remove(raw_filepath)
        except Exception:
            pass
    else:
        clip_filename = raw_filename
        clip_path = raw_filepath

    with state_lock:
        for ev in event_log:
            if ev["id"] == job["event_id"]:
                ev["clip_filename"] = clip_filename
                ev["clip_url"] = f"/clip/{clip_filename}"
                ev["clip_ready"] = True
                break

    logger.info("[CLIP] saved: %s", clip_path)


def clip_writer_worker() -> None:
    while not stop_event.is_set():
        try:
            job = clip_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            finalize_clip_job(job)
        except Exception as e:
            logger.exception("clip writer failed: %s", e)
        finally:
            clip_queue.task_done()


def add_event(event_type: str, track_id: int, event_ts: float) -> None:
    global event_seq, last_event_ts

    event_seq += 1
    eid = event_seq
    last_event_ts = event_ts

    item = {
        "id": eid,
        "type": event_type,
        "track_id": track_id,
        "time": short_time_str(event_ts),
        "timestamp": event_ts,
        "clip_filename": None,
        "clip_url": None,
        "clip_ready": False,
    }

    with state_lock:
        event_log.appendleft(item)
        latest_metrics["event_count"] += 1
        if event_type == "Enter":
            latest_metrics["enter_count"] += 1
        elif event_type == "Exit":
            latest_metrics["exit_count"] += 1

    logger.info("[EVENT] %s | track=%s | event_id=%s | %s", event_type, track_id, eid, short_time_str(event_ts))
    queue_clip_job(eid, event_type, track_id, event_ts)


def update_crossing_event(track_id: int, x1: int, x2: int, line_x: int) -> None:
    now = time.time()
    current_side = get_box_side(x1, x2, line_x)

    if track_id not in track_histories:
        stable = current_side if current_side in ("left", "right") else None
        track_histories[track_id] = {
            "stable_side": stable,
            "last_seen": now,
            "side_candidate": current_side,
            "candidate_count": 1,
            "last_event_ts": 0.0,
        }
        return

    info = track_histories[track_id]
    info["last_seen"] = now

    if current_side == "overlap":
        return

    if info["side_candidate"] == current_side:
        info["candidate_count"] += 1
    else:
        info["side_candidate"] = current_side
        info["candidate_count"] = 1

    if info["candidate_count"] < TRACK_SIDE_STABLE_FRAMES:
        return

    prev_stable = info.get("stable_side")
    new_stable = current_side

    if prev_stable is None:
        info["stable_side"] = new_stable
        return

    if prev_stable == new_stable:
        return

    if now - float(info.get("last_event_ts", 0.0)) < EVENT_DEBOUNCE_SEC_PER_TRACK:
        info["stable_side"] = new_stable
        return

    if prev_stable == "left" and new_stable == "right":
        add_event("Exit", track_id, now)
        info["last_event_ts"] = now
    elif prev_stable == "right" and new_stable == "left":
        add_event("Enter", track_id, now)
        info["last_event_ts"] = now

    info["stable_side"] = new_stable


def update_clip_jobs(current_frame) -> None:
    now = time.time()
    finished: List[Dict[str, Any]] = []

    for job in active_clip_jobs:
        if job["done"]:
            continue
        if now <= job["post_until"]:
            job["frames"].append(current_frame.copy())
        else:
            job["done"] = True
            finished.append(job)

    for job in finished:
        active_clip_jobs.remove(job)
        try:
            clip_queue.put_nowait(job)
        except queue.Full:
            logger.warning("clip queue full - dropping clip for event_id=%s", job["event_id"])


def trim_frame_buffer() -> None:
    now = time.time()
    while frame_buffer and (now - frame_buffer[0]["ts"] > PRE_EVENT_SEC + 0.7):
        frame_buffer.popleft()


# =========================
# 오버레이
# =========================
def draw_overlay(frame, boxes, person_count, fps, inference_ms, sys_metrics):
    h, w = frame.shape[:2]
    line_x = int(w * LINE_X_RATIO)

    cv2.line(frame, (line_x, 0), (line_x, h), LINE_COLOR, LINE_THICKNESS)
    cv2.putText(
        frame,
        "left->right = Exit / right->left = Enter",
        (max(10, line_x + 10), 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        LINE_COLOR,
        2,
        cv2.LINE_AA,
    )

    for x1, y1, x2, y2, conf, track_id in boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

        side = get_box_side(x1, x2, line_x)
        label = f"person {conf:.2f}" if track_id is None else f"ID {track_id} {conf:.2f} [{side}]"
        cv2.putText(
            frame,
            label,
            (x1, max(22, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    lines = [
        f"Mode: {sys_metrics.get('current_mode')}",
        f"FPS: {fps:.2f}",
        f"Infer: {inference_ms:.1f} ms",
        f"Persons: {person_count}",
        f"IMGSZ: {sys_metrics.get('imgsz')} / N:{sys_metrics.get('infer_every_n')}",
        f"Enter: {sys_metrics.get('enter_count')}  Exit: {sys_metrics.get('exit_count')}",
        f"CPU: {sys_metrics.get('cpu_usage_percent')}%  GPU: {sys_metrics.get('gpu_usage_percent')}%",
        f"CPU T: {sys_metrics.get('cpu_temp_c')}C  GPU T: {sys_metrics.get('gpu_temp_c')}C",
        f"Power: {sys_metrics.get('board_power_w')} W ({sys_metrics.get('power_source')})",
        f"VDD_IN: {sys_metrics.get('rail_vdd_in_w')}W  CPU_GPU_CV: {sys_metrics.get('rail_cpu_gpu_cv_w')}W",
        f"VDD_SOC: {sys_metrics.get('rail_soc_w')}W  ClipQ: {sys_metrics.get('clip_queue_size')}",
    ]

    y = 56
    for text in lines:
        cv2.putText(
            frame,
            text,
            (15, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 25

    return frame


# =========================
# 비전 워커
# =========================
def configure_camera(cap: cv2.VideoCapture) -> None:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAP_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    except Exception:
        pass


def vision_worker() -> None:
    global latest_jpeg, frame_index, last_boxes, last_person_count, last_inference_ms, last_person_seen_ts

    logger.info("Loading model: %s", MODEL_PATH)
    model = YOLO(MODEL_PATH)

    with state_lock:
        latest_metrics["model_ok"] = True

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_V4L2)
    configure_camera(cap)

    if not cap.isOpened():
        logger.error("Camera open failed")
        return

    with state_lock:
        latest_metrics["camera_ok"] = True

    apply_power_mode(current_mode)
    prev_loop_end = time.time()

    while not stop_event.is_set():
        loop_start = time.time()

        t_cap0 = time.time()
        ok, frame = cap.read()
        t_cap1 = time.time()

        if not ok or frame is None:
            time.sleep(0.03)
            continue

        capture_ms = (t_cap1 - t_cap0) * 1000.0
        frame_index += 1

        h, w = frame.shape[:2]
        line_x = int(w * LINE_X_RATIO)

        with state_lock:
            latest_power_w = latest_metrics.get("board_power_w")

        desired_mode = decide_mode(time.time(), last_person_count, latest_power_w)
        switch_mode_if_needed(desired_mode)

        cfg = MODE_CONFIG[current_mode]
        imgsz = cfg["imgsz"]
        infer_every_n = cfg["infer_every_n"]

        if current_mode == "WATCH":
            with state_lock:
                current_fps = latest_metrics.get("fps", 0.0) or 0.0
                current_power = latest_metrics.get("board_power_w")
            if current_fps < 55 and current_power is not None and current_power > 6.0:
                infer_every_n = 3
            elif current_fps > 70:
                infer_every_n = 2

        do_infer = (frame_index % max(int(infer_every_n), 1) == 0)
        infer_t0 = time.time()

        if do_infer:
            results = model.track(
                source=frame,
                conf=CONF_THRES,
                imgsz=imgsz,
                classes=[TARGET_CLASS_ID],
                verbose=False,
                device=0,
                persist=True,
                tracker=TRACKER_CONFIG,
            )

            person_boxes: List[Tuple[int, int, int, int, float, Optional[int]]] = []
            person_count = 0

            if results and len(results) > 0:
                r = results[0]
                if r.boxes is not None and len(r.boxes) > 0:
                    ids = None
                    if r.boxes.id is not None:
                        ids = r.boxes.id.int().cpu().tolist()

                    xyxy_list = r.boxes.xyxy.cpu().tolist()
                    conf_list = r.boxes.conf.cpu().tolist()
                    cls_list = r.boxes.cls.int().cpu().tolist()

                    for i, (xyxy, conf, cls_id) in enumerate(zip(xyxy_list, conf_list, cls_list)):
                        if cls_id != TARGET_CLASS_ID:
                            continue

                        x1, y1, x2, y2 = map(int, xyxy)
                        track_id = ids[i] if ids is not None and i < len(ids) else None

                        person_boxes.append((x1, y1, x2, y2, float(conf), track_id))
                        if track_id is not None:
                            update_crossing_event(track_id, x1, x2, line_x)

                    person_count = len(person_boxes)

            cleanup_stale_tracks()
            infer_t1 = time.time()
            inference_ms = (infer_t1 - infer_t0) * 1000.0

            last_boxes = person_boxes
            last_person_count = person_count
            last_inference_ms = inference_ms

            if person_count > 0:
                last_person_seen_ts = time.time()

        else:
            person_boxes = last_boxes
            person_count = last_person_count
            inference_ms = last_inference_ms

        now = time.time()
        loop_dt = now - prev_loop_end
        fps = 1.0 / max(loop_dt, 1e-6)
        prev_loop_end = now

        ann_t0 = time.time()
        with state_lock:
            latest_metrics["clip_queue_size"] = clip_queue.qsize()
            snapshot_metrics = dict(latest_metrics)

        annotated = draw_overlay(
            frame=frame.copy(),
            boxes=person_boxes,
            person_count=person_count,
            fps=fps,
            inference_ms=inference_ms,
            sys_metrics=snapshot_metrics,
        )
        ann_t1 = time.time()

        frame_buffer.append({"ts": now, "frame": annotated.copy()})
        trim_frame_buffer()
        update_clip_jobs(annotated)

        jpg_t0 = time.time()
        ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        jpg_t1 = time.time()

        if ok:
            with state_lock:
                latest_jpeg = encoded.tobytes()

        loop_ms = (time.time() - loop_start) * 1000.0
        annotate_ms = (ann_t1 - ann_t0) * 1000.0
        jpeg_ms = (jpg_t1 - jpg_t0) * 1000.0

        with state_lock:
            latest_metrics["fps"] = round(fps, 2)
            latest_metrics["person_count"] = person_count
            latest_metrics["inference_ms"] = round(inference_ms, 2)
            latest_metrics["last_update"] = now
            latest_metrics["current_mode"] = current_mode
            latest_metrics["imgsz"] = imgsz
            latest_metrics["infer_every_n"] = infer_every_n
            latest_metrics["loop_ms"] = round(loop_ms, 2)
            latest_metrics["capture_ms"] = round(capture_ms, 2)
            latest_metrics["annotate_ms"] = round(annotate_ms, 2)
            latest_metrics["jpeg_ms"] = round(jpeg_ms, 2)
            latest_metrics["clip_queue_size"] = clip_queue.qsize()

        limit_fps(current_mode, loop_start)

    cap.release()


# =========================
# 웹 UI
# =========================
INDEX_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>Jetson Xavier Auto Tuner Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; background:#0f141a; color:#eef2f7; margin:0; }
    .wrap { max-width: 1580px; margin: 0 auto; padding: 20px; }
    h1 { margin: 0 0 16px; }
    .grid { display:grid; grid-template-columns: 2fr 1fr; gap:16px; }
    .card { background:#1a222c; border-radius:18px; padding:16px; box-shadow: 0 8px 24px rgba(0,0,0,.24); }
    img, video { width:100%; border-radius:12px; background:#000; }
    .metrics { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
    .metric { background:#0f141a; border-radius:12px; padding:12px; min-height:76px; }
    .label { font-size:12px; color:#9bb0c3; margin-bottom:6px; }
    .value { font-size:24px; font-weight:bold; }
    .small { font-size:12px; color:#9bb0c3; margin-top:8px; }
    .ok { color:#6ee7b7; }
    .bad { color:#f87171; }
    .event-wrap { margin-top:14px; }
    .event-title { font-weight:bold; margin-bottom:8px; }
    .event-list { display:flex; flex-direction:column; gap:8px; max-height:410px; overflow:auto; }
    .event-item { background:#0f141a; border-radius:12px; padding:10px 12px; display:flex; justify-content:space-between; align-items:center; cursor:pointer; border:1px solid transparent; }
    .event-item:hover { border-color:#3b82f6; }
    .badge-enter, .badge-exit { display:inline-block; padding:4px 8px; border-radius:999px; color:#fff; font-size:12px; font-weight:bold; margin-right:8px; }
    .badge-enter { background:#16a34a; }
    .badge-exit { background:#2563eb; }
    .clip-status-ready { color:#6ee7b7; font-size:12px; }
    .clip-status-wait  { color:#fbbf24; font-size:12px; }
    .player-title { margin-top:12px; margin-bottom:8px; font-weight:bold; }
    @media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Jetson Xavier Auto Tuner Dashboard</h1>
    <div class="grid">
      <div class="card">
        <img src="/video_feed" alt="video stream">
        <div class="player-title">이벤트 클립 재생</div>
        <video id="clip_player" controls></video>
        <div class="small" id="clip_info">이벤트를 클릭하면 클립이 재생됩니다.</div>
      </div>

      <div class="card">
        <div class="metrics">
          <div class="metric"><div class="label">현재 모드</div><div class="value" id="current_mode">-</div></div>
          <div class="metric"><div class="label">전력(W)</div><div class="value" id="board_power_w">-</div></div>
          <div class="metric"><div class="label">전력 소스</div><div class="value" id="power_source">-</div></div>
          <div class="metric"><div class="label">VDD_IN / CPU_GPU_CV</div><div class="value" id="rail_pair">-</div></div>
          <div class="metric"><div class="label">사람 수</div><div class="value" id="person_count">-</div></div>
          <div class="metric"><div class="label">FPS</div><div class="value" id="fps">-</div></div>
          <div class="metric"><div class="label">추론시간(ms)</div><div class="value" id="inference_ms">-</div></div>
          <div class="metric"><div class="label">입력 크기 / 추론주기</div><div class="value" id="imgsz_pair">-</div></div>
          <div class="metric"><div class="label">CPU 사용률(%)</div><div class="value" id="cpu_usage_percent">-</div></div>
          <div class="metric"><div class="label">GPU 사용률(%)</div><div class="value" id="gpu_usage_percent">-</div></div>
          <div class="metric"><div class="label">CPU 온도(°C)</div><div class="value" id="cpu_temp_c">-</div></div>
          <div class="metric"><div class="label">GPU 온도(°C)</div><div class="value" id="gpu_temp_c">-</div></div>
          <div class="metric"><div class="label">Enter / Exit</div><div class="value" id="enter_exit_pair">-</div></div>
          <div class="metric"><div class="label">Loop / JPEG(ms)</div><div class="value" id="timing_pair">-</div></div>
          <div class="metric"><div class="label">카메라</div><div class="value" id="camera_ok">-</div></div>
          <div class="metric"><div class="label">모델</div><div class="value" id="model_ok">-</div></div>
        </div>

        <div class="small" id="last_update">업데이트 대기중...</div>
        <div class="small" id="run_info">-</div>

        <div class="event-wrap">
          <div class="event-title">최근 이벤트 (클릭하면 클립 재생)</div>
          <div class="event-list" id="event_list"></div>
        </div>
      </div>
    </div>
  </div>

<script>
function setText(id, text) {
  document.getElementById(id).textContent = (text === null || text === undefined) ? "-" : text;
}

async function refreshMetrics() {
  try {
    const r = await fetch('/metrics');
    const m = await r.json();

    setText('current_mode', m.current_mode);
    setText('board_power_w', m.board_power_w);
    setText('power_source', m.power_source);
    setText('rail_pair', `${m.rail_vdd_in_w ?? '-'} / ${m.rail_cpu_gpu_cv_w ?? '-'}`);
    setText('person_count', m.person_count);
    setText('fps', m.fps);
    setText('inference_ms', m.inference_ms);
    setText('imgsz_pair', `${m.imgsz ?? '-'} / ${m.infer_every_n ?? '-'}`);
    setText('cpu_usage_percent', m.cpu_usage_percent);
    setText('gpu_usage_percent', m.gpu_usage_percent);
    setText('cpu_temp_c', m.cpu_temp_c);
    setText('gpu_temp_c', m.gpu_temp_c);
    setText('enter_exit_pair', `${m.enter_count ?? '-'} / ${m.exit_count ?? '-'}`);
    setText('timing_pair', `${m.loop_ms ?? '-'} / ${m.jpeg_ms ?? '-'}`);

    const cam = document.getElementById('camera_ok');
    cam.textContent = m.camera_ok ? 'OK' : 'FAIL';
    cam.className = 'value ' + (m.camera_ok ? 'ok' : 'bad');

    const model = document.getElementById('model_ok');
    model.textContent = m.model_ok ? 'OK' : 'FAIL';
    model.className = 'value ' + (m.model_ok ? 'ok' : 'bad');

    const dt = m.last_update ? new Date(m.last_update * 1000) : null;
    document.getElementById('last_update').textContent =
      dt ? ('마지막 업데이트: ' + dt.toLocaleTimeString()) : '업데이트 없음';

    document.getElementById('run_info').textContent =
      `run_id=${m.run_id} | clip_queue=${m.clip_queue_size} | csv=${m.csv_path}`;
  } catch (e) {
    console.error(e);
  }
}

function playClip(url, title) {
  const player = document.getElementById('clip_player');
  const info = document.getElementById('clip_info');
  player.pause();
  player.removeAttribute('src');
  player.load();
  const finalUrl = url + '?t=' + Date.now();
  player.src = finalUrl;
  player.load();
  player.play().catch(() => {});
  info.textContent = title;
}

async function refreshEvents() {
  try {
    const r = await fetch('/events');
    const data = await r.json();
    const root = document.getElementById('event_list');
    root.innerHTML = '';

    if (!data.events || data.events.length === 0) {
      root.innerHTML = '<div class="small">아직 이벤트 없음</div>';
      return;
    }

    data.events.forEach(ev => {
      const div = document.createElement('div');
      div.className = 'event-item';
      div.onclick = () => {
        if (ev.clip_ready && ev.clip_url) {
          playClip(ev.clip_url, `Event ${ev.id} | ${ev.type} | ID ${ev.track_id} | ${ev.time}`);
        } else {
          alert('아직 클립 저장 중입니다.');
        }
      };

      const left = document.createElement('div');
      const badge = document.createElement('span');
      badge.className = ev.type === 'Enter' ? 'badge-enter' : 'badge-exit';
      badge.textContent = ev.type;

      const text = document.createElement('span');
      text.textContent = `Event ${ev.id} | ID ${ev.track_id} | ${ev.time}`;

      left.appendChild(badge);
      left.appendChild(text);

      const right = document.createElement('div');
      right.className = ev.clip_ready ? 'clip-status-ready' : 'clip-status-wait';
      right.textContent = ev.clip_ready ? 'clip ready' : 'saving...';

      div.appendChild(left);
      div.appendChild(right);
      root.appendChild(div);
    });
  } catch (e) {
    console.error(e);
  }
}

setInterval(refreshMetrics, 1000);
setInterval(refreshEvents, 1000);
refreshMetrics();
refreshEvents();
</script>
</body>
</html>
"""


# =========================
# API
# =========================
@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/metrics")
def metrics():
    with state_lock:
        return JSONResponse(dict(latest_metrics))


@app.get("/events")
def events():
    with state_lock:
        return JSONResponse({"events": list(event_log)})


@app.get("/summary")
def summary():
    return JSONResponse(build_summary())


@app.get("/summary_file")
def summary_file():
    if not os.path.isfile(SUMMARY_JSON_PATH):
        raise HTTPException(status_code=404, detail="Summary not found")
    return FileResponse(SUMMARY_JSON_PATH, media_type="application/json", filename=os.path.basename(SUMMARY_JSON_PATH))


@app.get("/clip/{filename}")
def get_clip(filename: str):
    path = os.path.join(CLIP_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


def mjpeg_generator():
    while not stop_event.is_set():
        with state_lock:
            frame = latest_jpeg
        if frame is None:
            time.sleep(0.03)
            continue
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.03)


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# =========================
# 백그라운드 스레드
# =========================
def start_background_threads() -> None:
    threading.Thread(target=tegrastats_worker, daemon=True).start()
    threading.Thread(target=power_sysfs_worker, daemon=True).start()
    threading.Thread(target=csv_logger_worker, daemon=True).start()
    threading.Thread(target=clip_writer_worker, daemon=True).start()
    threading.Thread(target=vision_worker, daemon=True).start()
    logger.info("Background threads started")


start_background_threads()
