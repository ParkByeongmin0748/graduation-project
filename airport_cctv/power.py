# power.py
import glob
import logging
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

from config import (
    ENABLE_DVFS,
    ENABLE_SYSFS_POWER,
    MODE_CONFIG,
    POWER_CHANNELS,
    POWER_HWMON_CANDIDATES,
)

import state

logger = logging.getLogger("auto_tuner")


# =========================
# 내부 유틸
# =========================
def _avg(nums: List[Optional[float]]) -> Optional[float]:
    nums = [float(n) for n in nums if n is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


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


# =========================
# DVFS / 전력 모드 제어
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
    else:
        # 나중에 EVENT에서 내려올 때 클럭 복구용
        # 환경에 따라 --store를 먼저 해둬야 할 수도 있음
        run_cmd_quiet(["jetson_clocks", "--restore"])


# =========================
# tegrastats 파싱
# =========================
def parse_power_from_tegrastats(line: str) -> Dict[str, Optional[Any]]:
    result: Dict[str, Optional[Any]] = {"power_w": None, "source": None}

    for pat in [
        r"(VDD_IN)\s+(\d+)mW/(\d+)mW",
        r"(POM_5V_IN)\s+(\d+)mW/(\d+)mW",
    ]:
        m = re.search(pat, line)
        if m:
            result["power_w"] = round(int(m.group(2)) / 1000.0, 3)
            result["source"] = m.group(1)
            return result

    rail_names = [
        "VDD_CPU_GPU_CV",
        "VDD_SOC",
        "VDDQ_VDD2_1V8AO",
        "GPU",
        "CPU",
        "SOC",
        "CV",
    ]

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
            if state.stop_event.is_set():
                break

            parsed = parse_tegrastats_line(line)

            if not parsed:
                continue

            with state.state_lock:
                for key, value in parsed.items():
                    # sysfs 전력값이 있으면 tegrastats 전력값보다 우선
                    if key == "board_power_w" and str(state.latest_metrics.get("power_source", "")).startswith("SYSFS"):
                        continue

                    if key == "power_source" and str(state.latest_metrics.get("power_source", "")).startswith("SYSFS"):
                        continue

                    state.latest_metrics[key] = value

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
            if read_text_file(f"{p}/name") == "ina3221":
                found.append(p)

    found = sorted(set(found))

    return found[0] if found else None


def read_power_channel(base: str, ch: int) -> Optional[Dict[str, Any]]:
    label = read_text_file(f"{base}/in{ch}_label")
    voltage = read_text_file(f"{base}/in{ch}_input")
    current = read_text_file(f"{base}/curr{ch}_input")
    enable = read_text_file(f"{base}/in{ch}_enable")

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

    while not state.stop_event.is_set():
        try:
            info = read_board_power_from_sysfs()

            with state.state_lock:
                if info.get("board_power_w") is not None:
                    state.latest_metrics["board_power_w"] = info["board_power_w"]
                    state.latest_metrics["power_source"] = info["power_source"]

                state.latest_metrics["rail_vdd_in_w"] = info.get("rail_vdd_in_w")
                state.latest_metrics["rail_cpu_gpu_cv_w"] = info.get("rail_cpu_gpu_cv_w")
                state.latest_metrics["rail_soc_w"] = info.get("rail_soc_w")

        except Exception as e:
            logger.warning("sysfs power worker failed: %s", e)

        time.sleep(1.0)