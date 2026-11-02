import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  clearCurrentAccessToken,
  requestJson,
  setCurrentAccessToken,
} from "./http";

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
  clearCurrentAccessToken();
});

function jwtFor(subject: number, sessionId = "test-session-id") {
  const payload = btoa(JSON.stringify({ sub: String(subject), sid: sessionId }))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
  return `header.${payload}.signature`;
}

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

  it("sends login requests with credentials and the CSRF request header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { access_token: "jwt" }));
    vi.stubGlobal("fetch", fetchMock);

    await requestJson("/users/login", { method: "POST", body: JSON.stringify({}) });

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(options.credentials).toBe("include");
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("1");
    expect(new Headers(options.headers).has("Authorization")).toBe(false);
  });

  it("refreshes an expired access token once and retries with the new token", async () => {
    const refreshedToken = jwtFor(7);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: { code: "access_token_expired" } }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: refreshedToken, token_type: "bearer" }))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    setCurrentAccessToken("expired-token", 7);

    await expect(requestJson("/protected", { token: "stale-prop-token" })).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const [, refreshOptions] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(refreshOptions.credentials).toBe("include");
    expect(new Headers(refreshOptions.headers).get("X-CSRF-Token")).toBe("1");
    const [, retryOptions] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(new Headers(retryOptions.headers).get("Authorization")).toBe(`Bearer ${refreshedToken}`);
  });

  it("does not refresh for unrelated 401 responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(401, { detail: { code: "invalid_credentials" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    setCurrentAccessToken("current-token", 7);

    await expect(requestJson("/protected")).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("requires sign-in instead of switching to a different account from another tab", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: { code: "access_token_expired" } }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: jwtFor(8), token_type: "bearer" }));
    vi.stubGlobal("fetch", fetchMock);
    setCurrentAccessToken("expired-token", 7);

    await expect(requestJson("/protected")).rejects.toMatchObject({
      code: "session_account_changed",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not silently adopt a different session for the same account", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: { code: "access_token_expired" } }))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: jwtFor(7, "other-session"), token_type: "bearer" }));
    vi.stubGlobal("fetch", fetchMock);
    setCurrentAccessToken(jwtFor(7, "current-session"), 7);

    await expect(requestJson("/protected")).rejects.toMatchObject({
      code: "session_account_changed",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
