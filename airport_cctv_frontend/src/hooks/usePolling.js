import { useEffect, useState } from "react";
import { apiGet } from "../api/client";

export function usePolling(path, intervalMs = 1000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const result = await apiGet(path);
        if (mounted) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (mounted) {
          setError(e);
          setLoading(false);
        }
      }
    }

    load();
    const timer = setInterval(load, intervalMs);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [path, intervalMs]);

  return { data, error, loading };
}
