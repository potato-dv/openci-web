import { useCallback, useEffect, useState } from "react";
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    data: T | null;
    error: string;
    loading: boolean;
  }>({ data: null, error: "", loading: true });
  useEffect(() => {
    const controller = new AbortController();
    // Start on the next microtask so StrictMode cleanup can cancel the first load.
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setState((current) => ({ ...current, error: "", loading: true }));
      return load(controller.signal)
        .then((data) => {
          if (!controller.signal.aborted)
            setState({ data, error: "", loading: false });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setState({
              data: null,
              error:
                error instanceof Error
                  ? error.message
                  : "Could not load this page. Try again.",
              loading: false,
            });
        });
    });
    return () => controller.abort();
  }, [load, revision]);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  return { ...state, refresh };
}
