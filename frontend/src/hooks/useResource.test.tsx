import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useResource, type ResourceOptions } from "./useResource";

function ResourceView({
  load,
  options,
}: {
  load: (signal: AbortSignal) => Promise<string>;
  options: ResourceOptions<string>;
}) {
  const resource = useResource(load, options);
  return <div>{resource.data ?? (resource.loading ? "loading" : "empty")}</div>;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => {
  Reflect.deleteProperty(document, "visibilityState");
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useResource", () => {
  it("revalidates stale data on focus without starting duplicate requests", async () => {
    let now = 1_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    const refresh = deferred<string>();
    const load = vi
      .fn<(signal: AbortSignal) => Promise<string>>()
      .mockResolvedValueOnce("initial")
      .mockReturnValue(refresh.promise);

    render(
      <ResourceView
        load={load}
        options={{ refetchOnFocus: true, staleTimeMs: 500 }}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("initial")).toBeInTheDocument();

    now = 2_000;
    act(() => window.dispatchEvent(new Event("focus")));
    expect(load).toHaveBeenCalledTimes(2);

    now = 3_000;
    act(() => window.dispatchEvent(new Event("focus")));
    expect(load).toHaveBeenCalledTimes(2);

    await act(async () => refresh.resolve("updated"));
    expect(screen.getByText("updated")).toBeInTheDocument();
  });

  it("pauses interval requests while the document is hidden", async () => {
    vi.useFakeTimers();
    let visibility: DocumentVisibilityState = "hidden";
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => visibility,
    });
    const load = vi.fn<(signal: AbortSignal) => Promise<string>>().mockResolvedValue("fresh");
    render(
      <ResourceView
        load={load}
        options={{ refetchInterval: 1_000, pauseWhenHidden: true }}
      />,
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(load).toHaveBeenCalledTimes(1);

    visibility = "visible";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(load).toHaveBeenCalledTimes(2);
  });
});
