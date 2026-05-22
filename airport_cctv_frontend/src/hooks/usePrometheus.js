import { useEffect, useState } from "react";

const PROMETHEUS_BASE = "http://localhost:9090";

// range query: 최근 N분 데이터를 step 간격으로 가져오기
export function usePrometheusRange(query, rangeMinutes = 10, stepSec = 5) {
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function fetch_data() {
      const end = Math.floor(Date.now() / 1000);
      const start = end - rangeMinutes * 60;
      const url =
        `${PROMETHEUS_BASE}/api/v1/query_range` +
        `?query=${encodeURIComponent(query)}` +
        `&start=${start}&end=${end}&step=${stepSec}`;

      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Prometheus 응답 오류");
        const json = await res.json();

        const result = json?.data?.result?.[0]?.values ?? [];
        const formatted = result.map(([ts, val]) => ({
          time: new Date(ts * 1000).toLocaleTimeString("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
          value: parseFloat(parseFloat(val).toFixed(2)),
        }));

        if (mounted) {
          setData(formatted);
          setError(null);
        }
      } catch (e) {
        if (mounted) setError(e.message);
      }
    }

    fetch_data();
    const timer = setInterval(fetch_data, stepSec * 1000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [query, rangeMinutes, stepSec]);

  return { data, error };
}
