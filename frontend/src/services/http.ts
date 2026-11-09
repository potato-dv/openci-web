import type { PlanningDependency } from "@/types/api";

// In development, route API requests through Vite so the browser stays on the
// frontend origin. Production builds use the explicitly configured API URL.
const API_URL =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? "" : "http://localhost:8000");

export function realtimeWebSocketUrl() {
  const configured = import.meta.env.VITE_REALTIME_URL;
  const apiBase = API_URL.replace(/\/$/, "");
  const address = configured || `${apiBase}/ws`;
  const url = new URL(address, window.location.href);
  url.protocol = url.protocol === "https:" || url.protocol === "wss:" ? "wss:" : "ws:";
  return url.toString();
}

type RequestOptions = RequestInit & {
  token?: string;
};

type AuthMessage = { type: "session-ended"; code?: string };

export class ApiError extends Error {
  status: number;
  code?: string;
  blockingReasons: PlanningDependency[];

  constructor(
    message: string,
    status: number,
    details: { code?: string; blockingReasons?: PlanningDependency[] } = {},
  ) {
    super(message);
    this.status = status;
    this.code = details.code;
    this.blockingReasons = details.blockingReasons ?? [];
  }
}

let currentAccessToken = "";
let expectedUserId: number | null = null;
let expectedSessionId: string | null = null;
let refreshPromise: Promise<string> | null = null;
let authChannel: BroadcastChannel | null = null;

function authEvents(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  if (!authChannel) {
    authChannel = new BroadcastChannel("openci-auth-session");
    authChannel.onmessage = (event: MessageEvent<AuthMessage>) => {
      if (event.data?.type === "session-ended") {
        window.dispatchEvent(
          new CustomEvent("openci:reauth-required", {
            detail: { code: event.data.code ?? "session_revoked", remote: true },
          }),
        );
      }
    };
  }
  return authChannel;
}

function requireReauthentication(code: string, broadcast = false) {
  currentAccessToken = "";
  window.dispatchEvent(
    new CustomEvent("openci:reauth-required", { detail: { code } }),
  );
  if (broadcast) authEvents()?.postMessage({ type: "session-ended", code });
}

export function setCurrentAccessToken(token: string, userId: number) {
  currentAccessToken = token;
  expectedUserId = userId;
  expectedSessionId = accessTokenSessionId(token);
}

export function getCurrentAccessToken() {
  return currentAccessToken;
}

export function clearCurrentAccessToken() {
  currentAccessToken = "";
  expectedUserId = null;
  expectedSessionId = null;
}

export function notifyOtherTabsOfLogout() {
  authEvents()?.postMessage({ type: "session-ended", code: "session_revoked" });
}

export function subscribeToReauthenticationRequired(
  listener: (detail: { code: string; remote?: boolean }) => void,
) {
  const handle = (event: Event) => {
    const detail = (event as CustomEvent<{ code?: string; remote?: boolean }>).detail;
    listener({ code: detail?.code ?? "session_revoked", remote: detail?.remote });
  };
  window.addEventListener("openci:reauth-required", handle);
  // Ensure this tab also receives terminal sign-out notifications from peers.
  authEvents();
  return () => window.removeEventListener("openci:reauth-required", handle);
}

// Decode only routing claims to detect an account or session change across
// tabs. The server remains the authority for token validity and permissions.
function accessTokenClaims(token: string): { sub?: unknown; sid?: unknown } | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="))) as {
      sub?: unknown;
      sid?: unknown;
    };
  } catch {
    return null;
  }
}

export function accessTokenSubject(token: string): number | null {
  const decoded = accessTokenClaims(token);
  if (!decoded) return null;
  const subject = Number(decoded.sub);
  return Number.isInteger(subject) && subject > 0 ? subject : null;
}

export function accessTokenSessionId(token: string): string | null {
  const sessionId = accessTokenClaims(token)?.sid;
  return typeof sessionId === "string" && sessionId.length > 0 ? sessionId : null;
}

function isAuthEndpoint(path: string) {
  return path === "/users/login" || path === "/users/refresh" || path === "/users/logout";
}

function isSessionEndCode(code?: string) {
  return ["session_idle", "session_expired", "session_revoked", "session_missing"].includes(code ?? "");
}

function canReplayRequest(options: RequestOptions) {
  const body = options.body;
  if (body === undefined || body === null || typeof body === "string") return true;
  if (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) return true;
  if (typeof FormData !== "undefined" && body instanceof FormData) return true;
  if (typeof Blob !== "undefined" && body instanceof Blob) return true;
  return false;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    const structuredDetail =
      data?.detail &&
      typeof data.detail === "object" &&
      !Array.isArray(data.detail)
        ? data.detail
        : null;
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail
              .map((item: { msg?: string }) => item.msg)
              .filter(Boolean)
              .join("; ")
          : typeof structuredDetail?.message === "string"
            ? structuredDetail.message
            : typeof structuredDetail?.code === "string"
              ? structuredDetail.code
              : "The request could not be completed.";
    throw new ApiError(detail, response.status, {
      code:
        typeof structuredDetail?.code === "string"
          ? structuredDetail.code
          : undefined,
      blockingReasons: Array.isArray(structuredDetail?.blocking_reasons)
        ? structuredDetail.blocking_reasons
        : [],
    });
  }

  return data as T;
}

async function rawRequest<T>(
  path: string,
  options: RequestOptions,
  tokenOverride?: string,
): Promise<T> {
  const { token: passedToken, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers);
  const authEndpoint = isAuthEndpoint(path);

  if (requestOptions.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const bearer = tokenOverride ?? (currentAccessToken || passedToken || "");
  if (!authEndpoint && bearer) headers.set("Authorization", `Bearer ${bearer}`);
  if (authEndpoint) headers.set("X-CSRF-Token", "1");

  const response = await fetch(`${API_URL}${path}`, {
    ...requestOptions,
    headers,
    ...(authEndpoint ? { credentials: "include" as const } : {}),
  });
  return parseResponse<T>(response);
}

async function postRefreshOnce(): Promise<string> {
  const data = await rawRequest<{ access_token: string }>("/users/refresh", {
    method: "POST",
  });
  const subject = accessTokenSubject(data.access_token);
  const sessionId = accessTokenSessionId(data.access_token);
  if (
    !subject ||
    !sessionId ||
    (expectedUserId !== null && subject !== expectedUserId) ||
    (expectedSessionId !== null && sessionId !== expectedSessionId)
  ) {
    requireReauthentication("session_account_changed");
    throw new ApiError(
      "The signed-in session changed in another tab. Sign in again to continue.",
      401,
      { code: "session_account_changed" },
    );
  }
  currentAccessToken = data.access_token;
  if (expectedUserId === null) expectedUserId = subject;
  if (expectedSessionId === null) expectedSessionId = sessionId;
  return data.access_token;
}

function withRefreshLock<T>(operation: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.locks?.request) {
    return navigator.locks.request("openci-auth-refresh", operation);
  }
  return operation();
}

export function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = withRefreshLock(async () => {
    try {
      return await postRefreshOnce();
    } catch (error) {
      if (error instanceof ApiError && error.code === "refresh_conflict") {
        await new Promise((resolve) => window.setTimeout(resolve, 150));
        try {
          return await postRefreshOnce();
        } catch (retryError) {
          if (retryError instanceof ApiError && isSessionEndCode(retryError.code)) {
            requireReauthentication(retryError.code ?? "session_revoked", true);
          } else if (retryError instanceof ApiError && retryError.code === "refresh_conflict") {
            requireReauthentication("refresh_conflict");
          }
          throw retryError;
        }
      }
      if (error instanceof ApiError && isSessionEndCode(error.code)) {
        requireReauthentication(error.code ?? "session_revoked", true);
      }
      throw error;
    }
  }).finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

export async function requestJson<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const tokenAtStart = currentAccessToken || options.token || "";
  try {
    return await rawRequest<T>(path, options);
  } catch (error) {
    if (
      !(error instanceof ApiError) ||
      error.status !== 401 ||
      error.code !== "access_token_expired" ||
      isAuthEndpoint(path) ||
      options.signal?.aborted ||
      !canReplayRequest(options) ||
      !tokenAtStart
    ) {
      if (error instanceof ApiError && isSessionEndCode(error.code)) {
        requireReauthentication(error.code ?? "session_revoked", true);
      }
      throw error;
    }

    const freshToken = await refreshAccessToken();
    if (options.signal?.aborted) throw error;
    return rawRequest<T>(path, options, freshToken);
  }
}

export async function logoutRemoteSession() {
  notifyOtherTabsOfLogout();
  try {
    await rawRequest<void>("/users/logout", { method: "POST", keepalive: true });
  } catch {
    // Local logout still completes if the server cannot be reached.
  }
}
