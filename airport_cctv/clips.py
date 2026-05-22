# clips.py
import logging
import os
import subprocess
import time
from typing import Any, Dict, List

import cv2

import config
from config import (
    CLIP_DIR,
    PRE_EVENT_SEC,
    POST_EVENT_SEC,
)

import state
from database import update_event_clip

logger = logging.getLogger("auto_tuner")


def queue_clip_job(event_id: int, event_type: str, track_id: int, event_ts: float) -> None:
    with state.state_lock:
        pre_frames = [
            item["frame"].copy()
            for item in state.frame_buffer
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

    state.active_clip_jobs.append(job)


def finalize_clip_job(job: Dict[str, Any]) -> None:
    raw_filename = (
        f"event_{job['event_id']}_{job['event_type'].lower()}_"
        f"{int(job['event_ts'])}_raw.mp4"
    )
    raw_filepath = os.path.join(CLIP_DIR, raw_filename)

    final_filename = (
        f"event_{job['event_id']}_{job['event_type'].lower()}_"
        f"{int(job['event_ts'])}.mp4"
    )
    final_filepath = os.path.join(CLIP_DIR, final_filename)

    with state.state_lock:
        fps = state.latest_metrics.get("fps", 20.0) or 20.0

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
                "-i",
                raw_filepath,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
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

    clip_url = f"/clip/{clip_filename}"

    with state.state_lock:
        for ev in state.event_log:
            if ev["id"] == job["event_id"]:
                ev["clip_filename"] = clip_filename
                ev["clip_url"] = clip_url
                ev["clip_ready"] = True
                break

    update_event_clip(job["event_id"], clip_filename, clip_url)

    logger.info("[CLIP] saved: %s", clip_path)


def clip_writer_worker() -> None:
    while not state.stop_event.is_set():
        try:
            job = state.clip_queue.get(timeout=0.5)
        except Exception:
            continue

        try:
            finalize_clip_job(job)

        except Exception as e:
            logger.exception("clip writer failed: %s", e)

        finally:
            state.clip_queue.task_done()


def update_clip_jobs(current_frame) -> None:
    now = time.time()
    finished: List[Dict[str, Any]] = []

    for job in state.active_clip_jobs:
        if job["done"]:
            continue

        if now <= job["post_until"]:
            job["frames"].append(current_frame.copy())
        else:
            job["done"] = True
            finished.append(job)

    for job in finished:
        state.active_clip_jobs.remove(job)

        try:
            state.clip_queue.put_nowait(job)

        except Exception:
            logger.warning(
                "clip queue full - dropping clip for event_id=%s",
                job["event_id"],
            )


def _cleanup_clips() -> None:
    now = time.time()
    max_age_sec = config.MAX_CLIP_AGE_DAYS * 86400
    max_size_bytes = int(config.MAX_CLIP_SIZE_GB * 1024 ** 3)

    # 1. 기간 초과 클립 삭제
    deleted_old = 0
    for fname in os.listdir(CLIP_DIR):
        fpath = os.path.join(CLIP_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if now - os.path.getmtime(fpath) > max_age_sec:
            try:
                os.remove(fpath)
                deleted_old += 1
            except Exception:
                pass

    # 2. 용량 초과 시 오래된 순으로 삭제
    clips = []
    for fname in os.listdir(CLIP_DIR):
        fpath = os.path.join(CLIP_DIR, fname)
        if os.path.isfile(fpath):
            clips.append((os.path.getmtime(fpath), fpath))

    clips.sort()
    total_size = sum(os.path.getsize(p) for _, p in clips)

    deleted_size = 0
    while total_size > max_size_bytes and clips:
        mtime, oldest = clips.pop(0)
        try:
            sz = os.path.getsize(oldest)
            os.remove(oldest)
            total_size -= sz
            deleted_size += 1
        except Exception:
            pass

    if deleted_old or deleted_size:
        logger.info(
            "[CLEANUP] age=%d size=%d clips removed (total_size=%.1fMB)",
            deleted_old,
            deleted_size,
            total_size / 1024 / 1024,
        )


def clip_cleanup_worker() -> None:
    while not state.stop_event.is_set():
        try:
            _cleanup_clips()
        except Exception as e:
            logger.exception("clip cleanup error: %s", e)

        interval = config.CLIP_CLEANUP_INTERVAL_SEC
        for _ in range(interval * 2):
            if state.stop_event.is_set():
                break
            time.sleep(0.5)


def trim_frame_buffer() -> None:
    now = time.time()

    while state.frame_buffer and (now - state.frame_buffer[0]["ts"] > PRE_EVENT_SEC + 0.7):
        state.frame_buffer.popleft()