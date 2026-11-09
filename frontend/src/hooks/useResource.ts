import { useCallback, useEffect, useRef, useState } from "react";
import { useRealtimeContext } from "@/realtime/RealtimeContext";

export type ResourceOptions<T> = {
  refetchOnFocus?: boolean;
  refetchOnReconnect?: boolean;
  staleTimeMs?: number;
  refetchInterval?: number | false | ((data: T | null) => number | false);
  pauseWhenHidden?: boolean;
  resourceKeys?: readonly string[];
};

type ResourceState<T> = {
  data: T | null;
  error: string;
  loading: boolean;
  lastUpdatedAt: number | null;
};

export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  options: ResourceOptions<T> = {},
) {
  const { subscribeResources } = useRealtimeContext();
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: "",
    loading: true,
    lastUpdatedAt: null,
  });
  const requestIdRef = useRef(0);
  const inFlightRef = useRef(false);
  const queuedRefreshRef = useRef(false);
  const lastUpdatedAtRef = useRef<number | null>(null);
  const lastAutomaticRefreshAtRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    inFlightRef.current = true;
    queuedRefreshRef.current = false;
    setState((current) => ({ ...current, error: "", loading: true }));

    // Start on the next microtask so StrictMode cleanup can cancel the first load.
    void (async () => {
      try {
        if (controller.signal.aborted) return;
        const data = await load(controller.signal);
        if (controller.signal.aborted || requestId !== requestIdRef.current) return;
        const updatedAt = Date.now();
        lastUpdatedAtRef.current = updatedAt;
        setState({ data, error: "", loading: false, lastUpdatedAt: updatedAt });
      } catch (error: unknown) {
        if (controller.signal.aborted || requestId !== requestIdRef.current) return;
        setState((current) => ({
          ...current,
          error:
            error instanceof Error
              ? error.message
              : "Could not load this page. Try again.",
          loading: false,
        }));
      } finally {
        if (requestId === requestIdRef.current) {
          inFlightRef.current = false;
          if (queuedRefreshRef.current) {
            queuedRefreshRef.current = false;
            setRevision((value) => value + 1);
          }
        }
      }
    })();

    return () => controller.abort();
  }, [load, revision]);

  const refresh = useCallback(() => {
    if (inFlightRef.current) {
      // A successful local mutation must be reflected even if a read was already running.
      queuedRefreshRef.current = true;
      return;
    }
    setRevision((value) => value + 1);
  }, []);

  const refreshAutomatically = useCallback(() => {
    if (inFlightRef.current) {
      // An event may have committed after the current REST read began.
      queuedRefreshRef.current = true;
      return;
    }
    const now = Date.now();
    if (now - lastAutomaticRefreshAtRef.current < 500) return;
    lastAutomaticRefreshAtRef.current = now;
    setRevision((value) => value + 1);
  }, []);

  const {
    refetchOnFocus = false,
    refetchOnReconnect = false,
    staleTimeMs = 30_000,
    refetchInterval = false,
    pauseWhenHidden = true,
    resourceKeys = [],
  } = options;
  const resourceKeySignature = resourceKeys.join("\u001f");
  const intervalMs = typeof refetchInterval === "function"
    ? refetchInterval(state.data)
    : refetchInterval;

  useEffect(() => {
    if (!resourceKeySignature) return;
    return subscribeResources(resourceKeySignature.split("\u001f"), refreshAutomatically);
  }, [refreshAutomatically, resourceKeySignature, subscribeResources]);

  useEffect(() => {
    if (!refetchOnFocus && !refetchOnReconnect) return;

    const refreshIfStale = () => {
      if (document.visibilityState !== "visible" || inFlightRef.current) return;
      const lastFreshAt = lastUpdatedAtRef.current ?? 0;
      if (Date.now() - lastFreshAt < staleTimeMs) return;
      refreshAutomatically();
    };

    if (refetchOnFocus) {
      window.addEventListener("focus", refreshIfStale);
      document.addEventListener("visibilitychange", refreshIfStale);
    }
    if (refetchOnReconnect) window.addEventListener("online", refreshIfStale);

    return () => {
      window.removeEventListener("focus", refreshIfStale);
      document.removeEventListener("visibilitychange", refreshIfStale);
      window.removeEventListener("online", refreshIfStale);
    };
  }, [
    refetchOnFocus,
    refetchOnReconnect,
    refreshAutomatically,
    staleTimeMs,
  ]);

  useEffect(() => {
    if (!intervalMs || intervalMs < 1) return;
    const timer = window.setInterval(() => {
      if (pauseWhenHidden && document.visibilityState !== "visible") return;
      refreshAutomatically();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs, pauseWhenHidden, refreshAutomatically]);

  return {
    ...state,
    refreshing: state.loading && state.data !== null,
    refresh,
  };
}
