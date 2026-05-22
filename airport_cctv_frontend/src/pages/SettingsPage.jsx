import { useState, useEffect } from "react";
import { Save, CheckCircle, AlertCircle, Info, HardDrive } from "lucide-react";
import SectionCard from "../components/SectionCard.jsx";
import { API_BASE_URL } from "../api/dashboardApi.js";
import { getConfig, patchConfig } from "../api/dashboardApi.js";

const PARAM_META = {
  LOITER_ALERT_SEC:           { label: "배회 → ALERT 임계 (초)",     type: "float", min: 1,   max: 300  },
  LOITER_EVENT_SEC:           { label: "배회 → EVENT 임계 (초)",     type: "float", min: 1,   max: 600  },
  LOITER_EVENT_DEBOUNCE_SEC:  { label: "배회 이벤트 Debounce (초)",  type: "float", min: 1,   max: 600  },
  CROWD_PERSON_THRESHOLD:     { label: "군중 임계 인원 (명)",         type: "int",   min: 2,   max: 20   },
  CROWD_ALERT_HOLD_SEC:       { label: "군중 → ALERT 지속 (초)",     type: "float", min: 0.5, max: 30   },
  CROWD_EVENT_HOLD_SEC:       { label: "군중 → EVENT 지속 (초)",     type: "float", min: 0.5, max: 60   },
  CROWD_EVENT_DEBOUNCE_SEC:   { label: "군중 이벤트 Debounce (초)",  type: "float", min: 1,   max: 300  },
  RESTRICTED_EVENT_DEBOUNCE_SEC: { label: "금지구역 Debounce (초)",  type: "float", min: 1,   max: 120  },
  FALL_ASPECT_RATIO_THRESHOLD:{ label: "낙상 감지 비율 (w/h >)",     type: "float", min: 1.0, max: 3.0  },
  FALL_NORMAL_RATIO:          { label: "정상 서있는 비율 (w/h <)",   type: "float", min: 0.3, max: 1.0  },
  FALL_EVENT_DEBOUNCE_SEC:    { label: "낙상 이벤트 Debounce (초)",  type: "float", min: 1,   max: 120  },
  WATCH_HOLD_SEC:             { label: "WATCH 홀드 시간 (초)",        type: "float", min: 1,   max: 60   },
  EVENT_HOLD_SEC:             { label: "EVENT 홀드 시간 (초)",        type: "float", min: 1,   max: 60   },
  CONF_THRES:                 { label: "YOLO 신뢰도 임계값",          type: "float", min: 0.1, max: 0.9  },
  MAX_CLIP_SIZE_GB:           { label: "클립 최대 용량 (GB)",         type: "float", min: 0.5, max: 50   },
  MAX_CLIP_AGE_DAYS:          { label: "클립 보관 기간 (일)",         type: "int",   min: 1,   max: 365  },
};

const EVENT_PARAMS = [
  "LOITER_ALERT_SEC", "LOITER_EVENT_SEC", "LOITER_EVENT_DEBOUNCE_SEC",
  "CROWD_PERSON_THRESHOLD", "CROWD_ALERT_HOLD_SEC", "CROWD_EVENT_HOLD_SEC", "CROWD_EVENT_DEBOUNCE_SEC",
  "RESTRICTED_EVENT_DEBOUNCE_SEC",
  "FALL_ASPECT_RATIO_THRESHOLD", "FALL_NORMAL_RATIO", "FALL_EVENT_DEBOUNCE_SEC",
  "WATCH_HOLD_SEC", "EVENT_HOLD_SEC", "CONF_THRES",
];

const CLIP_PARAMS = ["MAX_CLIP_SIZE_GB", "MAX_CLIP_AGE_DAYS"];

function ParamInput({ paramKey, value, onChange }) {
  const meta = PARAM_META[paramKey];
  if (!meta) return null;
  const step = meta.type === "int" ? 1 : 0.1;

  return (
    <div className="setting-row">
      <div>
        <div className="setting-label">{meta.label}</div>
        <div className="setting-desc" style={{ fontSize: 11, color: "#6b7280" }}>
          {paramKey} &nbsp;·&nbsp; 범위 {meta.min} ~ {meta.max}
        </div>
      </div>
      <div className="setting-control">
        <input
          type="number"
          step={step}
          min={meta.min}
          max={meta.max}
          value={value ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            onChange(paramKey, raw === "" ? "" : meta.type === "int" ? parseInt(raw, 10) : parseFloat(raw));
          }}
          style={{
            background: "#0f141a",
            border: "1px solid #374151",
            borderRadius: 8,
            color: "#e5e7eb",
            padding: "6px 10px",
            width: 100,
            textAlign: "right",
            fontSize: 14,
          }}
        />
      </div>
    </div>
  );
}

function SettingsPage() {
  const [values, setValues]     = useState({});
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [status, setStatus]     = useState(null); // { ok: bool, msg: string }

  useEffect(() => {
    getConfig()
      .then((data) => { setValues(data); setLoading(false); })
      .catch(() => { setLoading(false); setStatus({ ok: false, msg: "설정 로드 실패 — 백엔드 연결 확인" }); });
  }, []);

  function handleChange(key, val) {
    setValues((prev) => ({ ...prev, [key]: val }));
    setStatus(null);
  }

  async function handleSave(keys) {
    setSaving(true);
    setStatus(null);
    const subset = {};
    keys.forEach((k) => { if (values[k] !== undefined && values[k] !== "") subset[k] = values[k]; });
    try {
      const result = await patchConfig(subset);
      if (Object.keys(result.errors || {}).length > 0) {
        setStatus({ ok: false, msg: `저장 오류: ${JSON.stringify(result.errors)}` });
      } else {
        setValues((prev) => ({ ...prev, ...result.changed }));
        setStatus({ ok: true, msg: "저장 완료 (즉시 적용됨)" });
        setTimeout(() => setStatus(null), 3000);
      }
    } catch (e) {
      setStatus({ ok: false, msg: `저장 실패: ${e.message}` });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      {status && (
        <div
          className={`info-strip ${status.ok ? "green" : "red"}`}
          style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}
        >
          {status.ok ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {status.msg}
        </div>
      )}

      <div className="settings-grid">
        {/* ── 연결 설정 (읽기 전용) ── */}
        <SectionCard title="연결 설정">
          <div className="setting-row">
            <div className="setting-label">백엔드 API 주소</div>
            <div className="setting-value-chip">{API_BASE_URL}</div>
          </div>
          <div className="setting-row">
            <div className="setting-label">MJPEG 스트림</div>
            <div className="setting-value-chip">{API_BASE_URL}/video_feed</div>
          </div>
          <div className="setting-row">
            <div className="setting-label">폴링 주기</div>
            <div className="setting-value-chip">메트릭: 1초 / 이벤트: 2초</div>
          </div>
        </SectionCard>

        {/* ── 시스템 정보 (읽기 전용) ── */}
        <SectionCard title="시스템 정보">
          {[
            ["플랫폼",      "Jetson Xavier NX"],
            ["AI 프레임워크", "YOLO11 + TensorRT FP16"],
            ["추적기",      "ByteTrack"],
            ["전력 측정",   "INA3221 sysfs + tegrastats"],
          ].map(([label, val]) => (
            <div key={label} className="setting-row">
              <div className="setting-label">{label}</div>
              <div className="setting-value-chip">{val}</div>
            </div>
          ))}
        </SectionCard>

        {/* ── 이벤트 파라미터 (편집 가능) ── */}
        <SectionCard
          title="이벤트 파라미터"
          action={
            <button
              onClick={() => handleSave(EVENT_PARAMS)}
              disabled={saving || loading}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "#2563eb", color: "#fff",
                border: "none", borderRadius: 8,
                padding: "6px 14px", cursor: "pointer", fontSize: 13,
                opacity: (saving || loading) ? 0.5 : 1,
              }}
            >
              <Save size={14} />
              {saving ? "저장 중..." : "저장"}
            </button>
          }
        >
          {loading ? (
            <div className="info-strip blue">설정 로드 중...</div>
          ) : (
            EVENT_PARAMS.map((k) => (
              <ParamInput key={k} paramKey={k} value={values[k]} onChange={handleChange} />
            ))
          )}
        </SectionCard>

        {/* ── 클립 관리 (편집 가능) ── */}
        <SectionCard
          title="클립 자동 정리"
          action={
            <button
              onClick={() => handleSave(CLIP_PARAMS)}
              disabled={saving || loading}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "#2563eb", color: "#fff",
                border: "none", borderRadius: 8,
                padding: "6px 14px", cursor: "pointer", fontSize: 13,
                opacity: (saving || loading) ? 0.5 : 1,
              }}
            >
              <HardDrive size={14} />
              {saving ? "저장 중..." : "적용"}
            </button>
          }
        >
          <div className="info-strip blue" style={{ marginBottom: 12 }}>
            <Info size={14} />
            5분마다 실행 — 기간 초과 클립 삭제 후 용량 초과 시 오래된 순 삭제
          </div>
          {loading ? (
            <div className="info-strip blue">설정 로드 중...</div>
          ) : (
            CLIP_PARAMS.map((k) => (
              <ParamInput key={k} paramKey={k} value={values[k]} onChange={handleChange} />
            ))
          )}
        </SectionCard>

        {/* ── API 엔드포인트 목록 (읽기 전용) ── */}
        <SectionCard title="API 엔드포인트 목록">
          {[
            ["GET /metrics",                   "전체 시스템 메트릭"],
            ["GET /events",                    "전체 이벤트 로그"],
            ["GET /api/config",                "현재 설정 조회"],
            ["PATCH /api/config",              "설정 변경 (즉시 적용)"],
            ["GET /api/events/stats",          "DB 누적 이벤트 통계"],
            ["GET /api/dashboard/summary",     "대시보드 요약"],
            ["GET /api/events/recent",         "최근 5개 이벤트"],
            ["GET /api/power-mode/snapshot",   "전력/모드 히스토리"],
            ["GET /api/system/status",         "시스템 상태"],
            ["GET /video_feed",                "MJPEG 실시간 스트림"],
            ["GET /clip/{filename}",           "이벤트 클립 파일"],
            ["GET /prometheus",                "Prometheus 메트릭"],
          ].map(([ep, desc]) => (
            <div key={ep} className="setting-row" style={{ alignItems: "flex-start" }}>
              <div className="setting-value-chip" style={{ fontFamily: "monospace", fontSize: 11 }}>{ep}</div>
              <div className="setting-desc" style={{ textAlign: "right" }}>{desc}</div>
            </div>
          ))}
        </SectionCard>
      </div>
    </div>
  );
}

export default SettingsPage;
