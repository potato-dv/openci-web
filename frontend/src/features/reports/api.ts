import type { PageResult, Report, ReportInput, ReportQueueItem, RevisitRequest, Review, RouteAttempt } from "@/types/api";
import { requestJson } from "@/services/http";

type RouteAction = { work_date: string; route_revision: number };
export type UnableToProceedPayload = RouteAction & {
  reason: "no_contact_person" | "nobody_at_location" | "requested_later_visit" | "other";
  notes?: string | null;
  contact_available_from?: string | null;
  contact_available_until?: string | null;
};

export function startInvestigation(token: string, investigationId: number, action: RouteAction) {
  return requestJson<{ investigation_id: number; route_revision: number; started: boolean }>(
    `/investigations/${investigationId}/start`,
    { method: "POST", token, body: JSON.stringify(action) },
  );
}

export function unableToProceed(token: string, investigationId: number, action: UnableToProceedPayload) {
  return requestJson<RouteAttempt>(`/investigations/${investigationId}/unable-to-proceed`, {
    method: "POST", token, body: JSON.stringify(action),
  });
}

export function finalizeNoContactReport(
  token: string,
  investigationId: number,
  eventId: number,
  action: RouteAction,
) {
  return requestJson<RouteAttempt>(`/investigations/${investigationId}/no-contact-report`, {
    method: "POST", token,
    body: JSON.stringify({ ...action, event_id: eventId }),
  });
}

export function getReportQueue(
  token: string,
  params: URLSearchParams,
  signal?: AbortSignal,
) {
  return requestJson<PageResult<ReportQueueItem>>(
    `/reports/review-queue?${params}`,
    { token, signal },
  );
}

export function getReport(token: string, investigationId: number) {
  return requestJson<Report | null>(
    `/investigations/${investigationId}/report`,
    { token },
  );
}

export function getReportVersions(token: string, investigationId: number) {
  return requestJson<Report[]>(`/investigations/${investigationId}/reports`, {
    token,
  });
}

export function saveReport(
  token: string,
  investigationId: number,
  report: ReportInput,
  routeAction: RouteAction,
) {
  const params = new URLSearchParams({ work_date: routeAction.work_date });
  return requestJson<Report>(`/investigations/${investigationId}/report?${params}`, {
    method: "PUT",
    token,
    headers: { "X-Route-Revision": String(routeAction.route_revision) },
    body: JSON.stringify(report),
  });
}

export function submitReport(token: string, investigationId: number, routeAction: RouteAction) {
  const params = new URLSearchParams({ work_date: routeAction.work_date });
  return requestJson<Report>(
    `/investigations/${investigationId}/report/submit?${params}`,
    { method: "POST", token, headers: { "X-Route-Revision": String(routeAction.route_revision) } },
  );
}

export function getRevisitRequest(token: string, investigationId: number) {
  return requestJson<RevisitRequest | null>(
    `/investigations/${investigationId}/revisit-request`,
    { token },
  );
}

export function requestRevisit(token: string, investigationId: number) {
  return requestJson<RevisitRequest>(
    `/investigations/${investigationId}/revisit-request`,
    { method: "POST", token },
  );
}

export function getReviews(token: string, investigationId: number) {
  return requestJson<Review[]>(`/investigations/${investigationId}/reviews`, {
    token,
  });
}

export function reviewReport(
  token: string,
  investigationId: number,
  decision: Review["decision"],
  comments?: string,
) {
  return requestJson<Review>(`/investigations/${investigationId}/reviews`, {
    method: "POST",
    token,
    body: JSON.stringify({ decision, comments }),
  });
}
