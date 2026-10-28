import type { PageResult, Report, ReportInput, ReportQueueItem, Review } from "@/types/api";
import { requestJson } from "@/services/http";

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
) {
  return requestJson<Report>(`/investigations/${investigationId}/report`, {
    method: "PUT",
    token,
    body: JSON.stringify(report),
  });
}

export function submitReport(token: string, investigationId: number) {
  return requestJson<Report>(
    `/investigations/${investigationId}/report/submit`,
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
