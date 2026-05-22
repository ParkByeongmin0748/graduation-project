# Airport CCTV 프로젝트 정리

## 프로젝트 구조

```
Desktop/
├── airport_cctv/              ← 백엔드 (Python + FastAPI)
│   ├── main.py                ← FastAPI 서버 + 비전 워커
│   ├── config.py              ← 전체 설정값
│   ├── state.py               ← 스레드 공유 전역 상태
│   ├── events.py              ← 이벤트 감지 엔진
│   ├── clips.py               ← 이벤트 클립 저장
│   ├── logger.py              ← CSV 로그 기록
│   ├── power.py               ← 전력 모니터링
│   ├── prometheus_metrics.py  ← Prometheus 메트릭 노출 (추가됨)
│   ├── prometheus.yml         ← Prometheus 수집 설정 (추가됨)
│   ├── docker-compose.yml     ← Prometheus + Grafana 실행 (추가됨)
│   └── models/
│       ├── yolo11n.engine     ← TensorRT 변환 완료 (평소 모드)
│       └── yolo11s.engine     ← TensorRT 변환 완료 (EVENT 모드)
│
└── airport_cctv_frontend/     ← 프론트엔드 (React + Vite)
    └── src/
        ├── pages/             ← 9개 페이지
        ├── components/        ← 공통 컴포넌트
        ├── hooks/             ← usePolling, usePrometheus
        └── api/               ← client.js, dashboardApi.js
```

---

## 동작 모드 (자동 전환)

| 모드  | 조건              | FPS | 이미지 크기 | 추론 주기    | 전력       |
|-------|-------------------|-----|------------|-------------|-----------|
| IDLE  | 사람 없음          | 10  | 416px      | 6프레임마다  | 절전 (NVP1) |
| WATCH | 사람 감지됨        | 15  | 416px      | 3프레임마다  | 중간 (NVP2) |
| ALERT | 경고 상황          | 20  | 416px      | 2프레임마다  | 중간 (NVP2) |
| EVENT | 이벤트 발생        | 20  | 640px      | 매 프레임    | 최고 (NVP0) |

---

## 감지 이벤트 5종

| 이벤트          | 조건                              | 레벨  | Debounce |
|----------------|-----------------------------------|-------|----------|
| Enter / Exit   | 중앙 세로선 좌↔우 이동             | -     | 1.2초    |
| RestrictedZone | 오른쪽 68~98% 구역 진입            | EVENT | 5초      |
| CrowdDensity   | CZ-1 내 3명↑ → 1초→ALERT, 3초→EVENT | EVENT | 8초   |
| Loitering      | 동일 위치 15초→ALERT, 30초→EVENT   | EVENT | 60초     |
| FallDetected   | 바운딩박스 비율 0.65↓→1.5↑ 급변   | EVENT | 10초     |

---

## API 엔드포인트

| 경로                       | 설명                          |
|---------------------------|-------------------------------|
| `GET /`                   | 내장 HTML 대시보드             |
| `GET /video_feed`         | MJPEG 실시간 스트림            |
| `GET /metrics`            | 전체 실시간 메트릭 (JSON)      |
| `GET /events`             | 전체 이벤트 목록               |
| `GET /clip/{filename}`    | 이벤트 클립 파일               |
| `GET /summary`            | 런 요약 JSON                  |
| `GET /api/dashboard/summary`   | 대시보드 요약            |
| `GET /api/events/recent`       | 최근 5개 이벤트          |
| `GET /api/power-mode/snapshot` | 전력/모드 히스토리       |
| `GET /prometheus`         | Prometheus 메트릭 (추가됨)    |

---

## 프론트엔드 페이지 (9개)

| 페이지           | 경로               | 내용                                      |
|-----------------|--------------------|-------------------------------------------|
| Dashboard       | `/dashboard`       | 요약카드 + 라이브 프리뷰 + 이벤트 + 전력차트 |
| Live Monitoring | `/live-monitoring` | MJPEG 스트림 + 모드/전력/리소스 실시간     |
| Events          | `/events`          | 타입별 필터 + 이벤트 테이블 + 클립 링크    |
| Clips           | `/clips`           | 클립 목록 + 인앱 비디오 플레이어           |
| Zones           | `/zones`           | SVG 구역 시각화 + 파라미터 설명            |
| Model/Power     | `/model-power`     | 전력/모드 차트 + 모드별 설정 비교          |
| Reports         | `/reports`         | 모드별 통계 + Prometheus 트렌드 차트       |
| System Status   | `/system-status`   | CPU/GPU 사용률 + 온도 + 연결상태           |
| Settings        | `/settings`        | API 주소 + 파라미터 목록                  |

---

## Prometheus / Grafana 모니터링

### 노출 메트릭 목록

| 메트릭명                  | 타입    | 설명                              |
|--------------------------|---------|-----------------------------------|
| `cctv_fps`               | Gauge   | FPS (30프레임 이동평균)            |
| `cctv_person_count`      | Gauge   | 감지 인원 수                       |
| `cctv_inference_ms`      | Gauge   | YOLO 추론 시간 (ms)               |
| `cctv_board_power_w`     | Gauge   | 전체 전력 (W)                     |
| `cctv_rail_vdd_in_w`     | Gauge   | VDD_IN 레일 (W)                   |
| `cctv_rail_cpu_gpu_cv_w` | Gauge   | CPU_GPU_CV 레일 (W)               |
| `cctv_cpu_usage_percent` | Gauge   | CPU 사용률 (%)                    |
| `cctv_gpu_usage_percent` | Gauge   | GPU 사용률 (%)                    |
| `cctv_cpu_temp_c`        | Gauge   | CPU 온도 (°C)                     |
| `cctv_gpu_temp_c`        | Gauge   | GPU 온도 (°C)                     |
| `cctv_mode{mode="..."}`  | Gauge   | 현재 모드 (현재 모드만 1, 나머지 0) |
| `cctv_event_level`       | Gauge   | 이벤트 레벨 (0=NONE 1=ALERT 2=EVENT) |
| `cctv_crowd_count`       | Gauge   | 혼잡구역 인원 수                   |
| `cctv_event_total`       | Counter | 총 이벤트 수 (누적)               |
| `cctv_enter_total`       | Counter | 총 입장 수 (누적)                 |
| `cctv_exit_total`        | Counter | 총 퇴장 수 (누적)                 |

### 유용한 PromQL 쿼리

```promql
cctv_fps                          # 현재 FPS
cctv_board_power_w                # 현재 전력
cctv_cpu_temp_c                   # CPU 온도
cctv_gpu_usage_percent            # GPU 사용률
cctv_person_count                 # 감지 인원
rate(cctv_event_total[1m])        # 분당 이벤트 발생률
cctv_mode                         # 모드별 타임라인
```

---

## 실행 명령어

### 백엔드 (Jetson)

```bash
cd /home/parkbyeongmin/Desktop/airport_cctv

# 라이브러리 설치 (최초 1회)
.venv/bin/pip install prometheus_client

# 실행
sudo .venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 프론트엔드 (Jetson 또는 노트북)

```bash
cd /home/parkbyeongmin/Desktop/airport_cctv_frontend
npm run dev
# 브라우저: http://localhost:5173
```

### Prometheus + Grafana (노트북 Docker)

```bash
cd /home/parkbyeongmin/Desktop/airport_cctv
docker-compose up -d

# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000  (admin / admin)
```

### 데모/발표용 빌드 (Vite 서버 없이 Jetson 하나로)

```bash
# 프론트엔드 빌드
cd airport_cctv_frontend
npm run build

# 빌드 결과물 복사
cp -r dist/ ../airport_cctv/static/
```

main.py에 3줄 추가:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
# 접속: http://192.168.116.228:8000/static/index.html
```

---

## 수정된 버그 목록

| 파일              | 버그                              | 수정 내용                        |
|------------------|-----------------------------------|----------------------------------|
| `logger.py`      | CSV row 순서가 헤더와 불일치       | 헤더 순서에 맞게 row 재정렬      |
| `state.py`       | `current_mode` 키 중복 정의       | 중복 제거                        |
| `EventsPage.jsx` | 클립 URL에 IP 하드코딩            | `buildApiUrl()` 함수로 교체      |
| `main.py`        | FPS가 매 프레임 즉각 계산돼 튀어보임 | 30프레임 이동평균으로 스무딩     |
| `main.py`        | "명" → OpenCV가 한글 렌더링 못 함  | "P" (persons)로 변경             |

---

## 환경 정보

- **디바이스**: NVIDIA Jetson Xavier NX
- **IP**: 192.168.116.228
- **Python venv**: `/home/parkbyeongmin/Desktop/airport_cctv/.venv`
- **Node.js**: v20 이상 필요 (nvm으로 설치)
- **백엔드 포트**: 8000
- **프론트엔드 포트**: 5173
- **Grafana 포트**: 3000
- **Prometheus 포트**: 9090
