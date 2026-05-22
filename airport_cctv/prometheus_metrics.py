# prometheus_metrics.py
from prometheus_client import Counter, Gauge

# ── 성능 ──────────────────────────────────────
fps_gauge           = Gauge("cctv_fps",          "FPS (30프레임 이동평균)")
person_count_gauge  = Gauge("cctv_person_count", "감지 인원 수")
inference_ms_gauge  = Gauge("cctv_inference_ms", "YOLO 추론 시간 (ms)")
loop_ms_gauge       = Gauge("cctv_loop_ms",      "전체 루프 시간 (ms)")

# ── 전력 ──────────────────────────────────────
board_power_gauge       = Gauge("cctv_board_power_w",      "전체 전력 소비 (W)")
rail_vdd_in_gauge       = Gauge("cctv_rail_vdd_in_w",      "VDD_IN 레일 (W)")
rail_cpu_gpu_cv_gauge   = Gauge("cctv_rail_cpu_gpu_cv_w",  "CPU_GPU_CV 레일 (W)")
rail_soc_gauge          = Gauge("cctv_rail_soc_w",         "SOC 레일 (W)")

# ── CPU / GPU ─────────────────────────────────
cpu_usage_gauge = Gauge("cctv_cpu_usage_percent", "CPU 사용률 (%)")
gpu_usage_gauge = Gauge("cctv_gpu_usage_percent", "GPU 사용률 (%)")
cpu_temp_gauge  = Gauge("cctv_cpu_temp_c",        "CPU 온도 (°C)")
gpu_temp_gauge  = Gauge("cctv_gpu_temp_c",        "GPU 온도 (°C)")

# ── 모드 (라벨로 구분: 현재 모드만 1, 나머지 0) ──
mode_gauge = Gauge("cctv_mode", "현재 동작 모드", ["mode"])
for _m in ["IDLE", "WATCH", "ALERT", "EVENT"]:
    mode_gauge.labels(mode=_m).set(0)

# ── 이벤트 레벨 (0=NONE / 1=ALERT / 2=EVENT) ──
event_level_gauge = Gauge("cctv_event_level", "이벤트 레벨 (0=NONE 1=ALERT 2=EVENT)")

# ── 군중 ──────────────────────────────────────
crowd_count_gauge    = Gauge("cctv_crowd_count",        "혼잡구역 인원 수")
crowd_duration_gauge = Gauge("cctv_crowd_duration_sec", "혼잡 지속 시간 (s)")

# ── 이벤트 누적 카운터 ────────────────────────
event_total_counter = Counter("cctv_event_total",  "총 이벤트 수")
enter_total_counter = Counter("cctv_enter_total",  "총 입장 수")
exit_total_counter  = Counter("cctv_exit_total",   "총 퇴장 수")

_prev = {"event": 0, "enter": 0, "exit": 0}


def update_prometheus_metrics(snapshot: dict) -> None:
    """latest_metrics 스냅샷을 받아서 Prometheus 게이지를 갱신"""

    def _set(gauge, key):
        v = snapshot.get(key)
        if v is not None:
            gauge.set(float(v))

    _set(fps_gauge,           "fps")
    _set(person_count_gauge,  "person_count")
    _set(inference_ms_gauge,  "inference_ms")
    _set(loop_ms_gauge,       "loop_ms")
    _set(board_power_gauge,   "board_power_w")
    _set(rail_vdd_in_gauge,   "rail_vdd_in_w")
    _set(rail_cpu_gpu_cv_gauge, "rail_cpu_gpu_cv_w")
    _set(rail_soc_gauge,      "rail_soc_w")
    _set(cpu_usage_gauge,     "cpu_usage_percent")
    _set(gpu_usage_gauge,     "gpu_usage_percent")
    _set(cpu_temp_gauge,      "cpu_temp_c")
    _set(gpu_temp_gauge,      "gpu_temp_c")
    _set(crowd_count_gauge,   "crowd_count")
    _set(crowd_duration_gauge,"crowd_duration_sec")

    # 모드: 현재 모드만 1
    current_mode = snapshot.get("current_mode", "IDLE")
    for m in ["IDLE", "WATCH", "ALERT", "EVENT"]:
        mode_gauge.labels(mode=m).set(1 if m == current_mode else 0)

    # 이벤트 레벨 숫자 변환
    level_map = {"NONE": 0, "ALERT": 1, "EVENT": 2}
    event_level_gauge.set(level_map.get(snapshot.get("event_level", "NONE"), 0))

    # 카운터는 증분만 추가 (Counter는 감소 불가)
    new_event = int(snapshot.get("event_count") or 0)
    new_enter = int(snapshot.get("enter_count") or 0)
    new_exit  = int(snapshot.get("exit_count")  or 0)

    if new_event > _prev["event"]:
        event_total_counter.inc(new_event - _prev["event"])
        _prev["event"] = new_event

    if new_enter > _prev["enter"]:
        enter_total_counter.inc(new_enter - _prev["enter"])
        _prev["enter"] = new_enter

    if new_exit > _prev["exit"]:
        exit_total_counter.inc(new_exit - _prev["exit"])
        _prev["exit"] = new_exit
