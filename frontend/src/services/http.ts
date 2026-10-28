import type { PlanningDependency } from "@/types/api";

// In development, route API requests through Vite so the browser stays on the
// frontend origin. Production builds use the explicitly configured API URL.
const API_URL =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.DEV ? "" : "http://localhost:8000");

type RequestOptions = RequestInit & {
  token?: string;
};

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

export async function requestJson<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return undefined as T;
  }

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
