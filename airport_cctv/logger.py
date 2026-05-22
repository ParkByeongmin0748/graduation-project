# logger.py
import csv
import json
import logging
import time
from typing import Any, Dict, Optional

from config import (
    RUN_ID,
    CSV_LOG_PATH,
    RUNTIME_LOG_PATH,
    SUMMARY_JSON_PATH,
)

import state

logger = logging.getLogger("auto_tuner")


# =========================
# 내부 유틸
# =========================
def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read().strip().replace("\x00", "")
    except Exception:
        return None


def detect_device_model() -> str:
    for path in [
        "/proc/device-tree/model",
        "/sys/firmware/devicetree/base/model",
    ]:
        value = read_text_file(path)
        if value:
            return value

    return "Unknown Jetson"


# =========================
# CSV 로그 / 요약
# =========================
CSV_HEADER = [
    "timestamp",
    "mode",
    "fps",
    "inference_ms",
    "person_count",
    "crowd_count",
    "crowd_zone_id",
    "crowd_duration_sec",
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
    if state.csv_initialized:
        return

    with open(CSV_LOG_PATH, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_HEADER)

    state.csv_initialized = True
    logger.info("CSV log path: %s", CSV_LOG_PATH)


def update_mode_stats(snapshot: Dict[str, Any]) -> None:
    mode = snapshot.get("current_mode")

    if mode not in state.mode_stats:
        return

    stats = state.mode_stats[mode]

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

    for mode, stats in state.mode_stats.items():
        samples = stats["samples"]

        fps_avg = round(stats["fps_sum"] / samples, 2) if samples else None
        infer_avg = round(stats["infer_sum"] / samples, 2) if samples else None

        if stats["power_count"]:
            power_avg = round(stats["power_sum"] / stats["power_count"], 3)
        else:
            power_avg = None

        result["modes"][mode] = {
            "samples": samples,
            "avg_fps": fps_avg,
            "avg_inference_ms": infer_avg,
            "avg_power_w": power_avg,
        }

    with state.state_lock:
        result["enter_count"] = state.latest_metrics["enter_count"]
        result["exit_count"] = state.latest_metrics["exit_count"]
        result["event_count"] = state.latest_metrics["event_count"]

    return result


def write_summary_json() -> None:
    summary = build_summary()

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def csv_logger_worker() -> None:
    init_csv_log()

    while not state.stop_event.is_set():
        with state.state_lock:
            last_update = state.latest_metrics.get("last_update", 0.0)

            if not last_update or last_update <= 0:
                snapshot = None
            else:
                snapshot = dict(state.latest_metrics)

        if snapshot is not None:
            row = [
                time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(snapshot["last_update"]),
                ),
                snapshot.get("current_mode"),
                snapshot.get("fps"),
                snapshot.get("inference_ms"),
                snapshot.get("person_count"),
                snapshot.get("crowd_count"),
                snapshot.get("crowd_zone_id"),
                snapshot.get("crowd_duration_sec"),
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