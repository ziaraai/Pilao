"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, errorMessage } from "./api";

type Result<T> = {
  key: string;
  data?: T;
  error: string | null;
  status?: number;
};

/**
 * Load ``path`` from the API. ``pollWhile`` re-fetches every few seconds while it returns
 * true (background jobs: indexing, AI reading, DCE processing, analysis).
 */
export function useApi<T>(
  path: string | null,
  pollWhile?: (data: T) => boolean,
) {
  const [result, setResult] = useState<Result<T>>({ key: "", error: null });
  const [last, setLast] = useState<T | undefined>(undefined);
  const [tick, setTick] = useState(0);
  const poll = useRef(pollWhile);
  useEffect(() => {
    poll.current = pollWhile;
  });
  const key = `${path}#${tick}`;

  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        setResult({ key, data, error: null });
        setLast(data);
        if (poll.current?.(data))
          timer = setTimeout(() => setTick((t) => t + 1), 3000);
      })
      .catch((err: unknown) => {
        if ((err as Error).name === "AbortError") return;
        setResult({
          key,
          error: errorMessage(err),
          status: err instanceof ApiError ? err.status : 0,
        });
      });
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [path, tick, key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((data: T) => setLast(data), []);
  return {
    data: last, // keeps showing the previous data while a reload is in flight
    error: result.key === key ? result.error : null,
    status: result.key === key ? result.status : undefined,
    loading: path !== null && result.key !== key,
    reload,
    setData,
  };
}

/** Run a mutation with a busy flag and a French error message. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async <R>(fn: () => Promise<R>): Promise<R | undefined> => {
      setBusy(true);
      setError(null);
      try {
        return await fn();
      } catch (err) {
        setError(errorMessage(err));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [],
  );
  return { busy, error, setError, run };
}
