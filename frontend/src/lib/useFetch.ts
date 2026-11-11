"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { errorMessage } from "@/lib/format";

/**
 * Load data when the page opens and whenever `deps` change; `reload()` fetches again.
 * Late answers from an out-of-date request are ignored, so fast typing in a search box never shows stale rows.
 * `data` keeps the previous result while a new one loads (no flicker).
 */
export function useFetch<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadRef.current()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => !cancelled && setError(errorMessage(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  // A stable object: pages can list it in effect dependencies without re-running on every render.
  return useMemo(() => ({ data, error, loading, reload }), [data, error, loading, reload]);
}

/** A value that follows `value` after it has stopped changing for `ms` (for search boxes). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}