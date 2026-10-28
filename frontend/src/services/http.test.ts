import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson } from "./http";

function jsonResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("shared API request handling", () => {
  it("keeps bearer auth, JSON payloads, and abort signals on the request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { saved: true }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await expect(
      requestJson<{ saved: boolean }>("/example", {
        method: "POST",
        token: "session-token",
        signal: controller.signal,
        body: JSON.stringify({ value: 3 }),
      }),
    ).resolves.toEqual({ saved: true });

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(options.headers);
    expect(url).toContain("/example");
    expect(headers.get("Authorization")).toBe("Bearer session-token");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(options.body).toBe(JSON.stringify({ value: 3 }));
    expect(options.signal).toBe(controller.signal);
  });

  it("preserves structured dependency errors for route planning", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(503, {
          detail: {
            code: "planning_dependencies_unavailable",
            blocking_reasons: ["osrm_unavailable"],
          },
        }),
      ),
    );

    const error = await requestJson("/planning/runs", { token: "session-token" })
      .catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "planning_dependencies_unavailable",
      blockingReasons: ["osrm_unavailable"],
    });
  });
});
