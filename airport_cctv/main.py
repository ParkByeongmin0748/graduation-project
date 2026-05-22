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
import state
import config
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

import numpy as np

if not hasattr(np, "bool"):
    np.bool = bool

import cv2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse, Response
from ultralytics import YOLO
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from prometheus_metrics import update_prometheus_metrics


from config import (
    CAMERA_INDEX,
    MODEL_CONFIG,
    MODEL_PATH,
    TRACKER_CONFIG,
    TARGET_CLASS_ID,
    CONF_THRES,
    JPEG_QUALITY,
    CAP_WIDTH,
    CAP_HEIGHT,
    CAP_FPS,
    LINE_X_RATIO,
    LINE_COLOR,
    LINE_THICKNESS,
    MAX_EVENTS,
    PRE_EVENT_SEC,
    POST_EVENT_SEC,
    MAX_CLIP_QUEUE,
    TRACK_STALE_SEC,
    TRACK_SIDE_STABLE_FRAMES,
    EVENT_DEBOUNCE_SEC_PER_TRACK,
    ENABLE_DVFS,
    LOW_POWER_NVP_MODE,
    MID_POWER_NVP_MODE,
    HIGH_POWER_NVP_MODE,
    TARGET_DISPLAY_FPS,
    MODE_CONFIG,
    ENABLE_SYSFS_POWER,
    POWER_HWMON_CANDIDATES,
    POWER_CHANNELS,
    LOG_DIR,
    CLIP_DIR,
    RUN_ID,
    CSV_LOG_PATH,
    RUNTIME_LOG_PATH,
    SUMMARY_JSON_PATH,
)
from state import (
    state_lock,
    clip_queue,
    latest_jpeg,
    latest_raw_jpeg,
    stop_event,
    latest_metrics,
    event_log,
    frame_buffer,
    active_clip_jobs,
    track_histories,
    frame_index,
    current_mode,
    event_seq,
    last_boxes,
    last_person_count,
    last_inference_ms,
    last_person_seen_ts,
    last_event_ts,
    csv_initialized,
    mode_stats,
)
from power import (
    apply_power_mode,
    tegrastats_worker,
    power_sysfs_worker,
)
from logger import (
    csv_logger_worker,
    build_summary,
)
from clips import (
    queue_clip_job,
    clip_writer_worker,
    clip_cleanup_worker,
    update_clip_jobs,
    trim_frame_buffer,
)
import database
from events import (
    get_box_side,
    cleanup_stale_tracks,
    update_crossing_event,
    evaluate_airport_events,
)
import logging

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 원본 프레임 JPEG (오버레이 없음 — 구역 편집기용)
latest_raw_jpeg: Optional[bytes] = None


# =========================
# 구역 설정 영속화
# =========================
def _zones_to_dict() -> Dict[str, Any]:
    return {
        "restricted":      config.RESTRICTED_ZONES,
        "crowd":           config.CROWD_ZONES,
        "loiter":          config.LOITER_ZONES,
        "line_x_ratio":    config.LINE_X_RATIO,
        "line_angle_deg":  config.LINE_ANGLE_DEG,
        "line_length_ratio": config.LINE_LENGTH_RATIO,
    }


def save_zones_json() -> None:
    try:
        with open(config.ZONES_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(_zones_to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("구역 설정 저장 실패: %s", exc)


def load_zones_json() -> None:
    if not os.path.isfile(config.ZONES_JSON_PATH):
        return
    try:
        with open(config.ZONES_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "restricted" in data:
            config.RESTRICTED_ZONES = data["restricted"]
        if "crowd" in data:
            config.CROWD_ZONES = data["crowd"]
        if "loiter" in data:
            config.LOITER_ZONES = data["loiter"]
        if "line_x_ratio" in data:
            config.LINE_X_RATIO = float(data["line_x_ratio"])
        if "line_angle_deg" in data:
            config.LINE_ANGLE_DEG = float(data["line_angle_deg"])
        if "line_length_ratio" in data:
            config.LINE_LENGTH_RATIO = max(0.1, min(1.0, float(data["line_length_ratio"])))
        logger.info("구역 설정 로드: %s", config.ZONES_JSON_PATH)
    except Exception as exc:
        logger.warning("구역 설정 로드 실패: %s", exc)





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
    if person_count > 0:
        state.last_person_seen_ts = now_ts

    with state.state_lock:
        event_level = state.latest_metrics.get("event_level")

    if event_level == "EVENT":
        state.last_event_ts = now_ts
        return "EVENT"

    if now_ts - state.last_event_ts <= config.EVENT_HOLD_SEC:
        return "EVENT"

    if event_level == "ALERT":
        return "ALERT"

    if now_ts - state.last_person_seen_ts <= config.WATCH_HOLD_SEC:
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






# =========================
# 오버레이 유틸
# =========================
def _zone_fill(frame, x1, y1, x2, y2, color, alpha=0.10):
    ov = frame.copy()
    cv2.rectangle(ov, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)


def _label_box(frame, text, x, y, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs, th = 0.40, 1
    (tw, tH), bl = cv2.getTextSize(text, font, fs, th)
    cv2.rectangle(frame, (x, y - tH - 3), (x + tw + 6, y + bl), color, -1)
    cv2.putText(frame, text, (x + 3, y), font, fs, (255, 255, 255), th, cv2.LINE_AA)


def _dashed_line(frame, x1, y1, x2, y2, color=(50, 220, 50), dash=12, gap=7):
    """Draw a dashed line between two points using config.LINE_THICKNESS."""
    import math as _math
    length = _math.hypot(x2 - x1, y2 - y1)
    if length < 1:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    thickness = max(1, int(config.LINE_THICKNESS))
    pos = 0.0
    drawing = True
    while pos < length:
        seg = dash if drawing else gap
        end = min(pos + seg, length)
        if drawing:
            sx, sy = int(x1 + dx * pos), int(y1 + dy * pos)
            ex, ey = int(x1 + dx * end), int(y1 + dy * end)
            cv2.line(frame, (sx, sy), (ex, ey), color, thickness)
        pos = end
        drawing = not drawing


# =========================
# 오버레이 메인 (깔끔하게 재설계)
# =========================
def draw_overlay(frame, boxes, person_count, fps, inference_ms, sys_metrics):
    import math as _math
    h, w = frame.shape[:2]
    line_x = int(w * config.LINE_X_RATIO)
    _angle_rad = _math.radians(config.LINE_ANGLE_DEG)
    _len = max(0.05, min(1.0, config.LINE_LENGTH_RATIO))
    _half_h = (h / 2) * _len
    _y_top = int(h / 2 - _half_h)
    _y_bot = int(h / 2 + _half_h)
    _lx_top = int(line_x + (_y_top - h / 2) * _math.tan(_angle_rad))
    _lx_bot = int(line_x + (_y_bot - h / 2) * _math.tan(_angle_rad))

    mode        = sys_metrics.get("current_mode", "IDLE")
    event_level = sys_metrics.get("event_level", "NONE")
    event_reason = sys_metrics.get("event_reason") or ""
    loiter_tracks = sys_metrics.get("loiter_tracks", {})
    event_type  = sys_metrics.get("event_type")

    # ── 1. 구역 오버레이 ───────────────────────────────
    # Restricted Zone — 빨강
    for roi in config.RESTRICTED_ZONES:
        rx1, ry1, rx2, ry2 = roi["rect"]
        x1, y1, x2, y2 = int(rx1*w), int(ry1*h), int(rx2*w), int(ry2*h)
        _zone_fill(frame, x1, y1, x2, y2, (0, 0, 200), 0.12)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 2)
        _label_box(frame, roi.get("name", "Restricted Zone"), x1 + 4, y1 + 16, (0, 0, 180))

    # Crowd Zone — 시안
    for roi in config.CROWD_ZONES:
        rx1, ry1, rx2, ry2 = roi["rect"]
        x1, y1, x2, y2 = int(rx1*w), int(ry1*h), int(rx2*w), int(ry2*h)
        _zone_fill(frame, x1, y1, x2, y2, (200, 160, 0), 0.09)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 200), 2)
        _label_box(frame, roi.get("name", "Crowd Zone"), x1 + 4, y1 + 16, (0, 150, 150))

    # Loitering Zone — 노랑 (전체 화면이 아닐 때만)
    for roi in config.LOITER_ZONES:
        rx1, ry1, rx2, ry2 = roi["rect"]
        if rx1 == 0.0 and ry1 == 0.0 and rx2 == 1.0 and ry2 == 1.0:
            continue
        x1, y1, x2, y2 = int(rx1*w), int(ry1*h), int(rx2*w), int(ry2*h)
        _zone_fill(frame, x1, y1, x2, y2, (0, 180, 220), 0.08)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (30, 200, 240), 2)
        _label_box(frame, roi.get("name", "Loitering Zone"), x1 + 4, y1 + 16, (20, 140, 170))

    # Flow Line — 초록 점선 (각도·길이 지원)
    _dashed_line(frame, _lx_top, _y_top, _lx_bot, _y_bot)

    # ── 2. 바운딩 박스 ─────────────────────────────────
    for x1, y1, x2, y2, conf, track_id in boxes:
        bw, bh = x2 - x1, y2 - y1
        aspect = bw / bh if bh > 0 else 0
        is_fallen = (event_type == "FallDetected") or (aspect >= config.FALL_ASPECT_RATIO_THRESHOLD)
        loiter_sec = loiter_tracks.get(track_id, 0) if track_id is not None else 0

        if is_fallen:
            box_color = (0, 0, 230)
        elif loiter_sec >= config.LOITER_ALERT_SEC:
            box_color = (0, 120, 255)
        else:
            box_color = (50, 220, 50)

        cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)

        if track_id is not None:
            parts = [f"ID {track_id}"]
            if loiter_sec >= 1:
                parts.append(f"{loiter_sec:.0f}s")
            if is_fallen:
                parts.append("FALL!")
            _label_box(frame, " ".join(parts), x1, max(18, y1 - 1), box_color)

    # ── 3. CAM 정보 박스 (좌상단) ──────────────────────
    cv2.rectangle(frame, (0, 0), (215, 50), (10, 14, 22), -1)
    cv2.putText(frame, "CAM 01 - GATE A1", (7, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, time.strftime("%Y-%m-%d  %H:%M:%S"), (7, 37),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 185, 215), 1, cv2.LINE_AA)

    # ── 4. REC 표시 (우상단) ───────────────────────────
    cv2.circle(frame, (w - 58, 14), 5, (0, 0, 220), -1)
    cv2.putText(frame, "REC", (w - 49, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

    # ── 5. 하단 상태바 ─────────────────────────────────
    cv2.rectangle(frame, (0, h - 26), (w, h), (10, 14, 22), -1)
    MODE_LABELS = {"IDLE": "IDLE", "WATCH": "WATCH", "ALERT": "ALERT", "EVENT": "EVENT"}
    status_txt = f"{MODE_LABELS.get(mode, mode)}  |  FPS {fps:.1f}  |  {person_count}P  |  {inference_ms:.0f}ms"
    cv2.putText(frame, status_txt, (8, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (155, 180, 205), 1, cv2.LINE_AA)

    # ── 6. 이벤트 경보 배너 ────────────────────────────
    if event_level in ("ALERT", "EVENT"):
        EV_COL = {"ALERT": (0, 120, 255), "EVENT": (0, 0, 210)}
        ev_col = EV_COL.get(event_level, (0, 0, 210))
        ov2 = frame.copy()
        cv2.rectangle(ov2, (0, 50), (w, 74), ev_col, -1)
        cv2.addWeighted(ov2, 0.70, frame, 0.30, 0, frame)
        cv2.putText(frame, f"  {event_level}: {event_reason}", (8, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2, cv2.LINE_AA)

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
    global latest_jpeg, latest_raw_jpeg, frame_index, last_boxes, last_person_count, last_inference_ms

    fps_history: deque = deque(maxlen=30)  # 최근 30프레임 평균으로 FPS 스무딩

    logger.info("Loading TensorRT models...")
    models = {}
    for mode_name, model_info in MODEL_CONFIG.items():
        model_path = model_info["model_path"]
        if model_path not in models:
            logger.info("Loading model for %s: %s", mode_name, model_path)
            models[model_path] = YOLO(model_path, task="detect")
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
        line_x = int(w * config.LINE_X_RATIO)

        with state_lock:
            latest_power_w = latest_metrics.get("board_power_w")

        desired_mode = decide_mode(time.time(), last_person_count, latest_power_w)
        switch_mode_if_needed(desired_mode)

        cfg = MODE_CONFIG[current_mode]
        imgsz = cfg["imgsz"]
        infer_every_n = cfg["infer_every_n"]
        model_key = cfg.get("model_key", current_mode)
        model_info = MODEL_CONFIG[model_key]
        model_path = model_info["model_path"]
        model = models[model_path]

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
                            update_crossing_event(track_id, x1, x2, y1, y2, line_x, h)

                    person_count = len(person_boxes)

            cleanup_stale_tracks()
            event_result = evaluate_airport_events(person_boxes, w, h)
            infer_t1 = time.time()
            inference_ms = (infer_t1 - infer_t0) * 1000.0
            last_boxes = person_boxes
            last_person_count = person_count
            last_inference_ms = inference_ms

            if person_count > 0:
                state.last_person_seen_ts = time.time()

        else:
            person_boxes = last_boxes
            person_count = last_person_count
            inference_ms = last_inference_ms

        now = time.time()
        loop_dt = now - prev_loop_end
        instant_fps = 1.0 / max(loop_dt, 1e-6)
        fps_history.append(instant_fps)
        fps = sum(fps_history) / len(fps_history)  # 30프레임 이동평균
        prev_loop_end = now

        ann_t0 = time.time()
        with state_lock:
            latest_metrics["clip_queue_size"] = clip_queue.qsize()
            snapshot_metrics = dict(latest_metrics)

        update_prometheus_metrics(snapshot_metrics)

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

        # 원본 프레임 JPEG (오버레이 없음)
        ok_raw, encoded_raw = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ok_raw:
            latest_raw_jpeg = encoded_raw.tobytes()

        loop_ms = (time.time() - loop_start) * 1000.0
        annotate_ms = (ann_t1 - ann_t0) * 1000.0
        jpeg_ms = (jpg_t1 - jpg_t0) * 1000.0

        with state_lock:
            latest_metrics["model_path"] = model_path
            latest_metrics["model_name"] = model_info["model_name"]
            latest_metrics["model_size"] = model_info["model_size"]
            latest_metrics["model_precision"] = model_info["precision"]
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


@app.get("/prometheus")
def prometheus_metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/events")
def events():
    with state_lock:
        return JSONResponse({"events": list(event_log)})


power_mode_history = deque(maxlen=60)


def _safe_round(value, digits=2, default=None):
    try:
        if value is None:
            return default
        return round(float(value), digits)
    except Exception:
        return default


def _normalize_event_type(ev: Dict[str, Any]) -> str:
    raw_type = ev.get("type") or ev.get("event_type") or ev.get("event_reason") or "Event"
    reason = ev.get("event_reason")
    if reason and raw_type in ["Event", "ALERT", "EVENT"]:
        return str(reason)
    return str(raw_type)


def _normalize_severity(ev: Dict[str, Any]) -> str:
    raw = ev.get("severity") or ev.get("level") or ev.get("event_level")
    if raw in ["EVENT", "High"]:
        return "High"
    if raw in ["ALERT", "Medium"]:
        return "Medium"
    return raw or "Low"


def _absolute_clip_url(clip_url: Optional[str]) -> Optional[str]:
    if not clip_url:
        return None
    if clip_url.startswith("http://") or clip_url.startswith("https://"):
        return clip_url
    return clip_url if clip_url.startswith("/") else f"/{clip_url}"


@app.get("/api/dashboard/summary")
def api_dashboard_summary():
    with state_lock:
        m = dict(latest_metrics)
        events_count = len(event_log)

    current_mode_value = m.get("current_mode", "IDLE")
    camera_ok = bool(m.get("camera_ok", False))
    model_ok = bool(m.get("model_ok", False))
    power_w = _safe_round(m.get("board_power_w"), 2)

    return {
        "currentMode": current_mode_value,
        "activeCameras": 1 if camera_ok else 0,
        "totalCameras": 1,
        "todaysEvents": events_count,
        "averagePower": f"{power_w}W" if power_w is not None else "-",
        "systemHealth": "Normal" if camera_ok and model_ok else "Check",
        "fps": _safe_round(m.get("fps"), 2),
        "inferenceMs": _safe_round(m.get("inference_ms"), 2),
        "personCount": m.get("person_count", 0),
        "eventLevel": m.get("event_level", "NONE"),
        "eventReason": m.get("event_reason"),
        "streamUrl": "/video_feed",
    }


@app.get("/api/events/recent")
def api_recent_events():
    with state_lock:
        events_snapshot = list(event_log)[-5:][::-1]

    result = []
    for index, ev in enumerate(events_snapshot):
        clip_url = _absolute_clip_url(ev.get("clip_url"))
        result.append(
            {
                "id": ev.get("id") or ev.get("event_id") or ev.get("seq") or index + 1,
                "type": _normalize_event_type(ev),
                "camera": ev.get("camera") or ev.get("camera_name") or "Gate A1 / Cam 01",
                "time": ev.get("time") or ev.get("timestamp") or "-",
                "severity": _normalize_severity(ev),
                "clip_url": clip_url,
                "clip_ready": bool(ev.get("clip_ready", False)),
            }
        )

    return result


@app.get("/api/power-mode/snapshot")
def api_power_mode_snapshot():
    with state_lock:
        m = dict(latest_metrics)

    power_w = _safe_round(m.get("board_power_w"), 2, 0)
    mode = m.get("current_mode", "IDLE")

    power_mode_history.append(
        {
            "time": short_time_str(time.time()),
            "power": power_w,
            "mode": mode,
        }
    )

    return list(power_mode_history)


@app.get("/api/system/status")
def api_system_status():
    with state_lock:
        m = dict(latest_metrics)

    return {
        "camera_ok": bool(m.get("camera_ok", False)),
        "model_ok": bool(m.get("model_ok", False)),
        "current_mode": m.get("current_mode", "IDLE"),
        "fps": m.get("fps"),
        "inference_ms": m.get("inference_ms"),
        "board_power_w": m.get("board_power_w"),
        "last_update": m.get("last_update"),
    }


# =========================
# Config API
# =========================
MUTABLE_CONFIG_KEYS: Dict[str, type] = {
    "LOITER_ALERT_SEC": float,
    "LOITER_EVENT_SEC": float,
    "LOITER_EVENT_DEBOUNCE_SEC": float,
    "CROWD_PERSON_THRESHOLD": int,
    "CROWD_ALERT_HOLD_SEC": float,
    "CROWD_EVENT_HOLD_SEC": float,
    "CROWD_EVENT_DEBOUNCE_SEC": float,
    "RESTRICTED_EVENT_DEBOUNCE_SEC": float,
    "FALL_ASPECT_RATIO_THRESHOLD": float,
    "FALL_NORMAL_RATIO": float,
    "FALL_EVENT_DEBOUNCE_SEC": float,
    "WATCH_HOLD_SEC": float,
    "EVENT_HOLD_SEC": float,
    "CONF_THRES": float,
    "MAX_CLIP_SIZE_GB": float,
    "MAX_CLIP_AGE_DAYS": int,
}


@app.get("/api/config")
def get_config():
    return {k: getattr(config, k) for k in MUTABLE_CONFIG_KEYS}


from fastapi import Body

@app.patch("/api/config")
async def patch_config(updates: Dict[str, Any] = Body(...)):
    changed = {}
    errors = {}
    for key, value in updates.items():
        if key not in MUTABLE_CONFIG_KEYS:
            errors[key] = "not allowed"
            continue
        try:
            typed_value = MUTABLE_CONFIG_KEYS[key](value)
            setattr(config, key, typed_value)
            changed[key] = typed_value
        except (ValueError, TypeError) as e:
            errors[key] = str(e)
    return {"changed": changed, "errors": errors}


@app.get("/api/events/stats")
def api_events_stats():
    return database.get_db_stats()


# =========================
# Zones API
# =========================
@app.get("/api/zones")
def get_zones():
    return _zones_to_dict()


@app.patch("/api/zones")
async def patch_zones(updates: Dict[str, Any] = Body(...)):
    if "restricted" in updates:
        config.RESTRICTED_ZONES = updates["restricted"]
    if "crowd" in updates:
        config.CROWD_ZONES = updates["crowd"]
    if "loiter" in updates:
        config.LOITER_ZONES = updates["loiter"]
    if "line_x_ratio" in updates:
        try:
            config.LINE_X_RATIO = float(updates["line_x_ratio"])
        except (ValueError, TypeError):
            pass
    if "line_angle_deg" in updates:
        try:
            config.LINE_ANGLE_DEG = float(updates["line_angle_deg"])
        except (ValueError, TypeError):
            pass
    if "line_length_ratio" in updates:
        try:
            config.LINE_LENGTH_RATIO = max(0.1, min(1.0, float(updates["line_length_ratio"])))
        except (ValueError, TypeError):
            pass
    save_zones_json()
    return _zones_to_dict()


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


def mjpeg_generator_raw():
    while not stop_event.is_set():
        frame = latest_raw_jpeg
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


@app.get("/video_feed_raw")
def video_feed_raw():
    """원본 프레임 스트림 (오버레이 없음 — 구역 편집기용)"""
    return StreamingResponse(
        mjpeg_generator_raw(),
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
    threading.Thread(target=clip_cleanup_worker, daemon=True).start()
    threading.Thread(target=vision_worker, daemon=True).start()
    logger.info("Background threads started")


# =========================
# 시작 시 초기화
# =========================
load_zones_json()        # 마지막 저장된 구역 설정 복원
database.init_db()

_restored = database.load_recent_events()
if _restored:
    _sorted = sorted(_restored, key=lambda e: e["id"])
    for ev in _sorted:
        state.event_log.appendleft(ev)
    state.event_seq = max(ev["id"] for ev in _sorted)
    state.latest_metrics["event_count"] = len(_sorted)
    state.latest_metrics["enter_count"] = sum(1 for ev in _sorted if ev["type"] == "Enter")
    state.latest_metrics["exit_count"] = sum(1 for ev in _sorted if ev["type"] == "Exit")
    logger.info("[DB] restored %d events (latest id=%d)", len(_sorted), state.event_seq)

start_background_threads()
