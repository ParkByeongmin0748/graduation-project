# events.py
import logging
import math
import time
from collections import deque
from typing import Any, Dict, Optional

import config
from config import (
    EVENT_DEBOUNCE_SEC_PER_TRACK,
    TRACK_SIDE_STABLE_FRAMES,
    TRACK_STALE_SEC,
    FALL_HISTORY_FRAMES,
    FALL_MIN_BOX_AREA,
)

import state
from clips import queue_clip_job
from database import save_event

logger = logging.getLogger("auto_tuner")


# =========================
# 공통 유틸
# =========================
def short_time_str(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def make_empty_event_result() -> Dict[str, Optional[Any]]:
    return {
        "level": "NONE",       # NONE / ALERT / EVENT
        "reason": None,        # restricted_zone / crowd_density 등
        "event_type": None,    # RestrictedZone / CrowdDensity 등
        "track_id": None,
        "roi_id": None,
    }


def get_box_center(box):
    x1, y1, x2, y2, conf, track_id = box
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return cx, cy


def ratio_rect_to_pixel(rect, frame_w: int, frame_h: int):
    rx1, ry1, rx2, ry2 = rect

    x1 = int(rx1 * frame_w)
    y1 = int(ry1 * frame_h)
    x2 = int(rx2 * frame_w)
    y2 = int(ry2 * frame_h)

    return x1, y1, x2, y2


def point_in_rect(px: int, py: int, rect) -> bool:
    x1, y1, x2, y2 = rect
    return x1 <= px <= x2 and y1 <= py <= y2


def event_priority(result: Dict[str, Optional[Any]]) -> int:
    if result["level"] == "EVENT":
        return 2

    if result["level"] == "ALERT":
        return 1

    return 0


# =========================
# Line Crossing Event
# 기존 Enter / Exit 이벤트
# =========================
def get_box_side(x1: int, x2: int, y1: int, y2: int, line_x: int, frame_h: int) -> str:
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    angle_rad = math.radians(config.LINE_ANGLE_DEG)
    lx_at_cy = line_x + (cy - frame_h / 2) * math.tan(angle_rad)
    half_w = max((x2 - x1) // 4, 2)
    if cx < lx_at_cy - half_w:
        return "left"
    if cx > lx_at_cy + half_w:
        return "right"
    return "overlap"


def cleanup_stale_tracks(max_age_sec: float = TRACK_STALE_SEC) -> None:
    now = time.time()
    dead_ids = []

    for track_id, info in state.track_histories.items():
        last_seen = info.get("last_seen", 0.0)

        if now - last_seen > max_age_sec:
            dead_ids.append(track_id)

    for track_id in dead_ids:
        state.track_histories.pop(track_id, None)


def add_event(event_type: str, track_id: int, event_ts: float) -> None:
    state.event_seq += 1
    event_id = state.event_seq
    state.last_event_ts = event_ts

    item: Dict[str, Any] = {
        "id": event_id,
        "type": event_type,
        "track_id": track_id,
        "time": short_time_str(event_ts),
        "timestamp": event_ts,
        "clip_filename": None,
        "clip_url": None,
        "clip_ready": False,
    }

    with state.state_lock:
        state.event_log.appendleft(item)
        state.latest_metrics["event_count"] += 1

        if event_type == "Enter":
            state.latest_metrics["enter_count"] += 1

        elif event_type == "Exit":
            state.latest_metrics["exit_count"] += 1

    save_event(item)

    logger.info(
        "[EVENT] %s | track=%s | event_id=%s | %s",
        event_type,
        track_id,
        event_id,
        short_time_str(event_ts),
    )

    queue_clip_job(event_id, event_type, track_id, event_ts)


def get_or_create_track_info(track_id: int, now: float) -> Dict[str, Any]:
    if track_id not in state.track_histories:
        state.track_histories[track_id] = {
            "stable_side": None,
            "last_seen": now,
            "side_candidate": None,
            "candidate_count": 0,
            "last_event_ts": 0.0,
            "last_restricted_event_ts": 0.0,
            # 배회 감지
            "loiter_zone_entry": {},     # {zone_id: entry_ts}
            "last_loiter_event_ts": 0.0,
            # 낙상 감지
            "aspect_ratio_history": deque(maxlen=FALL_HISTORY_FRAMES),
            "was_standing": False,
            "last_fall_event_ts": 0.0,
        }

    info = state.track_histories[track_id]
    info.setdefault("stable_side", None)
    info.setdefault("side_candidate", None)
    info.setdefault("candidate_count", 0)
    info.setdefault("last_event_ts", 0.0)
    info.setdefault("last_restricted_event_ts", 0.0)
    info.setdefault("loiter_zone_entry", {})
    info.setdefault("last_loiter_event_ts", 0.0)
    info.setdefault("aspect_ratio_history", deque(maxlen=FALL_HISTORY_FRAMES))
    info.setdefault("was_standing", False)
    info.setdefault("last_fall_event_ts", 0.0)
    info["last_seen"] = now

    return info


def update_crossing_event(track_id: int, x1: int, x2: int, y1: int, y2: int, line_x: int, frame_h: int) -> None:
    now = time.time()
    current_side = get_box_side(x1, x2, y1, y2, line_x, frame_h)

    info = get_or_create_track_info(track_id, now)

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


# =========================
# Restricted Zone Event
# 제한구역 침입 이벤트
# =========================
def check_restricted_zone(person_boxes, frame_w: int, frame_h: int) -> Dict[str, Optional[Any]]:
    now = time.time()

    for box in person_boxes:
        x1, y1, x2, y2, conf, track_id = box

        # RestrictedZone은 같은 사람 반복 이벤트 방지를 위해 track_id 필요
        if track_id is None:
            continue

        cx, cy = get_box_center(box)

        for roi in config.RESTRICTED_ZONES:
            roi_rect = ratio_rect_to_pixel(roi["rect"], frame_w, frame_h)

            if not point_in_rect(cx, cy, roi_rect):
                continue

            info = get_or_create_track_info(track_id, now)
            last_restricted_ts = float(info.get("last_restricted_event_ts", 0.0))

            # 같은 사람이 제한구역에 계속 있어도 이벤트가 너무 자주 찍히지 않도록 debounce
            if now - last_restricted_ts >= config.RESTRICTED_EVENT_DEBOUNCE_SEC:
                add_event("RestrictedZone", track_id, now)
                info["last_restricted_event_ts"] = now

            return {
                "level": "EVENT",
                "reason": "restricted_zone",
                "event_type": "RestrictedZone",
                "track_id": track_id,
                "roi_id": roi["id"],
            }

    return make_empty_event_result()


# =========================
# Crowd Density Event
# 혼잡 감지 이벤트
# =========================
def count_people_in_roi(person_boxes, roi_rect) -> int:
    count = 0

    for box in person_boxes:
        cx, cy = get_box_center(box)

        if point_in_rect(cx, cy, roi_rect):
            count += 1

    return count


def check_crowd_density(person_boxes, frame_w: int, frame_h: int) -> Dict[str, Optional[Any]]:
    now = time.time()
    best_result = make_empty_event_result()

    for roi in config.CROWD_ZONES:
        roi_id = roi["id"]
        roi_rect = ratio_rect_to_pixel(roi["rect"], frame_w, frame_h)

        crowd_count = count_people_in_roi(person_boxes, roi_rect)

        zone_state = state.crowd_zone_states.setdefault(
            roi_id,
            {
                "crowd_start_ts": None,
                "last_event_ts": 0.0,
                "last_count": 0,
            },
        )

        zone_state["last_count"] = crowd_count

        if crowd_count >= config.CROWD_PERSON_THRESHOLD:
            if zone_state["crowd_start_ts"] is None:
                zone_state["crowd_start_ts"] = now

            duration = now - float(zone_state["crowd_start_ts"])

            with state.state_lock:
                state.latest_metrics["crowd_count"] = crowd_count
                state.latest_metrics["crowd_zone_id"] = roi_id
                state.latest_metrics["crowd_duration_sec"] = round(duration, 2)

            # 혼잡 상태가 일정 시간 이상 지속되면 EVENT
            if duration >= config.CROWD_EVENT_HOLD_SEC:
                last_event_ts = float(zone_state.get("last_event_ts", 0.0))

                if now - last_event_ts >= config.CROWD_EVENT_DEBOUNCE_SEC:
                    add_event("CrowdDensity", -1, now)
                    zone_state["last_event_ts"] = now

                return {
                    "level": "EVENT",
                    "reason": "crowd_density",
                    "event_type": "CrowdDensity",
                    "track_id": None,
                    "roi_id": roi_id,
                }

            # 혼잡 후보 상태가 일정 시간 이상 지속되면 ALERT
            if duration >= config.CROWD_ALERT_HOLD_SEC:
                best_result = {
                    "level": "ALERT",
                    "reason": "crowd_density_candidate",
                    "event_type": "CrowdDensityCandidate",
                    "track_id": None,
                    "roi_id": roi_id,
                }

        else:
            zone_state["crowd_start_ts"] = None

    if best_result["level"] == "NONE":
        with state.state_lock:
            state.latest_metrics["crowd_count"] = 0
            state.latest_metrics["crowd_zone_id"] = None
            state.latest_metrics["crowd_duration_sec"] = 0.0

    return best_result


# =========================
# Loitering Event
# 배회 감지 이벤트
# =========================
def check_loitering(person_boxes, frame_w: int, frame_h: int) -> Dict[str, Optional[Any]]:
    now = time.time()
    best_result = make_empty_event_result()
    best_duration = 0.0

    # 현재 프레임에서 각 구역에 있는 track_id 집합
    present_in_zone: Dict[str, set] = {zone["id"]: set() for zone in config.LOITER_ZONES}

    for box in person_boxes:
        x1, y1, x2, y2, conf, track_id = box
        if track_id is None:
            continue

        cx, cy = get_box_center(box)
        info = get_or_create_track_info(track_id, now)

        for zone in config.LOITER_ZONES:
            zone_id = zone["id"]
            zone_rect = ratio_rect_to_pixel(zone["rect"], frame_w, frame_h)

            if point_in_rect(cx, cy, zone_rect):
                present_in_zone[zone_id].add(track_id)

                # 처음 진입
                if zone_id not in info["loiter_zone_entry"]:
                    info["loiter_zone_entry"][zone_id] = now

                duration = now - info["loiter_zone_entry"][zone_id]

                # 개별 track의 배회 시간을 state에 기록
                with state.state_lock:
                    state.latest_metrics.setdefault("loiter_tracks", {})
                    state.latest_metrics["loiter_tracks"][track_id] = round(duration, 1)

                if duration >= config.LOITER_EVENT_SEC:
                    last_ts = float(info.get("last_loiter_event_ts", 0.0))
                    if now - last_ts >= config.LOITER_EVENT_DEBOUNCE_SEC:
                        add_event("Loitering", track_id, now)
                        info["last_loiter_event_ts"] = now

                    if duration > best_duration:
                        best_duration = duration
                        best_result = {
                            "level": "EVENT",
                            "reason": "loitering",
                            "event_type": "Loitering",
                            "track_id": track_id,
                            "roi_id": zone_id,
                        }

                elif duration >= config.LOITER_ALERT_SEC and best_result["level"] != "EVENT":
                    if duration > best_duration:
                        best_duration = duration
                        best_result = {
                            "level": "ALERT",
                            "reason": "loitering_candidate",
                            "event_type": "LoiteringCandidate",
                            "track_id": track_id,
                            "roi_id": zone_id,
                        }
            else:
                # 구역 이탈 시 타이머 리셋
                info["loiter_zone_entry"].pop(zone_id, None)

    # 구역에 없는 track의 loiter 기록 제거
    gone_tracks = []
    with state.state_lock:
        tracked = dict(state.latest_metrics.get("loiter_tracks", {}))
    for tid in tracked:
        in_any_zone = any(tid in present_in_zone[z["id"]] for z in config.LOITER_ZONES)
        if not in_any_zone:
            gone_tracks.append(tid)
    if gone_tracks:
        with state.state_lock:
            for tid in gone_tracks:
                state.latest_metrics.get("loiter_tracks", {}).pop(tid, None)

    return best_result


# =========================
# Fall Detection Event
# 낙상 감지 이벤트
# =========================
def check_fall_detection(person_boxes, frame_w: int, frame_h: int) -> Dict[str, Optional[Any]]:
    now = time.time()

    for box in person_boxes:
        x1, y1, x2, y2, conf, track_id = box
        if track_id is None:
            continue

        box_w = x2 - x1
        box_h = y2 - y1

        if box_w * box_h < FALL_MIN_BOX_AREA or box_h == 0:
            continue

        aspect_ratio = box_w / box_h
        info = get_or_create_track_info(track_id, now)
        info["aspect_ratio_history"].append(aspect_ratio)

        history = info["aspect_ratio_history"]
        if len(history) < 3:
            continue

        avg_ratio = sum(history) / len(history)

        # 서있는 상태 확인: 최근 기록 절반 이상이 정상 비율이면 was_standing = True
        standing_frames = sum(1 for r in history if r <= config.FALL_NORMAL_RATIO)
        if standing_frames >= len(history) // 2:
            info["was_standing"] = True

        # 이전에 서있었고, 현재 평균이 낙상 기준 초과
        if info["was_standing"] and avg_ratio >= config.FALL_ASPECT_RATIO_THRESHOLD:
            last_ts = float(info.get("last_fall_event_ts", 0.0))
            if now - last_ts >= config.FALL_EVENT_DEBOUNCE_SEC:
                add_event("FallDetected", track_id, now)
                info["last_fall_event_ts"] = now
                info["was_standing"] = False
                info["aspect_ratio_history"].clear()

            return {
                "level": "EVENT",
                "reason": "fall_detected",
                "event_type": "FallDetected",
                "track_id": track_id,
                "roi_id": None,
            }

    return make_empty_event_result()


# =========================
# Airport Event Engine
# 공항 CCTV 이벤트 통합 판단
# =========================
def evaluate_airport_events(person_boxes, frame_w: int, frame_h: int) -> Dict[str, Optional[Any]]:
    results = [
        check_restricted_zone(person_boxes, frame_w, frame_h),
        check_crowd_density(person_boxes, frame_w, frame_h),
        check_loitering(person_boxes, frame_w, frame_h),
        check_fall_detection(person_boxes, frame_w, frame_h),
    ]

    # EVENT > ALERT > NONE 우선순위, 동률이면 앞쪽(더 위험한 것) 우선
    event_result = max(results, key=event_priority)

    with state.state_lock:
        state.latest_metrics["event_level"] = event_result["level"]
        state.latest_metrics["event_reason"] = event_result["reason"]
        state.latest_metrics["event_type"] = event_result["event_type"]
        state.latest_metrics["roi_id"] = event_result["roi_id"]

    return event_result