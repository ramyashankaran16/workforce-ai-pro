import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Run an async fetcher and track loading, data and error.
 *
 * The `active` flag guards against a state update after unmount, which is what
 * produces the "state update on unmounted component" warning when someone
 * navigates away mid-request.
 */
export function useApi(fetcher, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const active = useRef(true);

  const run = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetcher(...args);
        if (active.current) setData(result);
        return result;
      } catch (err) {
        if (active.current) setError(err);
        throw err;
      } finally {
        if (active.current) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    deps
  );

  useEffect(() => {
    active.current = true;
    if (immediate) run().catch(() => {});
    return () => {
      active.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, refetch: run, setData };
}

/** Poll an endpoint on an interval, pausing while the tab is hidden. */
export function usePolling(fetcher, intervalMs = 30000, deps = []) {
  const state = useApi(fetcher, deps);

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") {
        state.refetch().catch(() => {});
      }
    };
    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);

  return state;
}
