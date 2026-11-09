import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowUpRight } from "lucide-react";
import { useSession } from "@/app/session";
import { cancelNoContactAttempt, getNoContactReviewQueue, getReportQueue } from "@/features/reports/api";
import type { NoContactReviewItem } from "@/types/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { ResourceFreshness } from "@/components/data/ResourceFreshness";
import { WorkspaceMobileList, WorkspacePanel } from "@/components/layout/WorkspacePanel";
import {
  DataFilterBar,
  dataFilterFieldClassName,
  dataFilterSearchClassName,
} from "@/components/data/DataFilterBar";
import { Pagination } from "@/components/data/Pagination";
import { Modal } from "@/components/ui/Modal";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { RowActions } from "@/components/ui/RowActions";
import { RecordIdentity } from "@/components/data/RecordIdentity";
import { WorkspaceSearchField } from "@/components/data/WorkspaceSearchField";
import { WorkspaceSelect } from "@/components/ui/WorkspaceSelect";
import {
  Button,
  EmptyState,
  InlineAlert,
  Skeleton,
  Tabs,
} from "@/components/ui/Primitives";
import { date, time } from "@/utils/format";
export function ReportsPage() {
  const { token } = useSession();
  const [params, setParams] = useSearchParams();
  const [cancelTarget, setCancelTarget] = useState<NoContactReviewItem | null>(null);
  const [cancellingNoContact, setCancellingNoContact] = useState(false);
  const [noContactActionError, setNoContactActionError] = useState("");
  const [noContactActionMessage, setNoContactActionMessage] = useState("");
  const reportParams = new URLSearchParams();
  ["status", "q", "page", "page_size", "sort", "direction"].forEach((name) => {
    const parameter = params.get(name);
    if (parameter !== null) reportParams.set(name, parameter);
  });
  const key = reportParams.toString();
  const value = params.get("status") ?? "submitted";
  const resource = useResource(
    useCallback(
      (signal) => getReportQueue(token, new URLSearchParams(key), signal),
      [token, key],
    ),
    {
      resourceKeys: ["reports.queue"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 60_000,
    },
  );
  const noContactParams = new URLSearchParams({
    page: params.get("no_contact_page") ?? "1",
    page_size: params.get("no_contact_page_size") ?? "25",
    sort: "attempted_at",
    direction: "desc",
  });
  const search = params.get("q");
  if (search) noContactParams.set("q", search);
  const noContactKey = noContactParams.toString();
  const noContactResource = useResource(
    useCallback(
      (signal) => value === "submitted"
        ? getNoContactReviewQueue(token, new URLSearchParams(noContactKey), signal)
        : Promise.resolve(null),
      [token, noContactKey, value],
    ),
    {
      resourceKeys: ["reports.queue", "route.planning"],
      refetchOnFocus: true,
      refetchOnReconnect: true,
      staleTimeMs: 60_000,
    },
  );
  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page" && name !== "no_contact_page" && name !== "no_contact_page_size") {
      next.delete("page");
    }
    if (name !== "no_contact_page" && name !== "page" && name !== "page_size") {
      next.delete("no_contact_page");
    }
    setParams(next, { replace: name === "q" });
  }
  async function handleCancelNoContactAttempt() {
    if (!cancelTarget) return;
    setCancellingNoContact(true);
    setNoContactActionError("");
    try {
      await cancelNoContactAttempt(
        token,
        cancelTarget.investigation_id,
        cancelTarget.event_id,
      );
      setNoContactActionMessage(
        `${cancelTarget.reference_number} was cancelled for today and will be available again the next day.`,
      );
      setCancelTarget(null);
      noContactResource.refresh();
    } catch (error) {
      setNoContactActionError(
        error instanceof Error ? error.message : "Could not cancel this no-contact attempt.",
      );
    } finally {
      setCancellingNoContact(false);
    }
  }
  return (
    <>
      <PageHeader title="Reports" />
      <WorkspacePanel
        title="Review queue"
        description="Filter submissions by review state and open the investigation to act."
        action={
          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
            <ResourceFreshness
              loading={resource.refreshing || (value === "submitted" && noContactResource.refreshing)}
              lastUpdatedAt={resource.lastUpdatedAt}
            />
            <Button
              onClick={() => {
                resource.refresh();
                if (value === "submitted") noContactResource.refresh();
              }}
              disabled={resource.refreshing || (value === "submitted" && noContactResource.refreshing)}
            >
              Refresh
            </Button>
          </div>
        }
      >
        <Tabs
          label="Report status"
          value={value}
          onChange={(value) => update("status", value)}
          items={[
            { value: "submitted", label: "Awaiting review" },
            { value: "returned_for_correction", label: "Returned" },
            { value: "approved", label: "Approved" },
          ]}
        />
        <DataFilterBar>
          <WorkspaceSearchField className={dataFilterSearchClassName} value={params.get("q") ?? ""} onChange={(value) => update("q", value)} placeholder="Reference, subject, or address" />
          <WorkspaceSelect
            className={dataFilterFieldClassName}
            label="Sort"
            value={params.get("sort") ?? "submitted_at"}
            onValueChange={(value) => update("sort", value)}
            options={[{ value: "submitted_at", label: "Submitted time" }, { value: "updated_at", label: "Updated time" }, { value: "reference_number", label: "Reference" }]}
          />
          <WorkspaceSelect
            className={dataFilterFieldClassName}
            label="Order"
            value={params.get("direction") ?? "asc"}
            onValueChange={(value) => update("direction", value)}
            options={[{ value: "asc", label: "Oldest first" }, { value: "desc", label: "Newest first" }]}
          />
        </DataFilterBar>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {resource.loading && !resource.data ? (
          <Skeleton />
        ) : resource.data?.items.length ? (
          <>
            <div className="hidden max-w-full overflow-x-auto rounded-lg border border-[#e2e8f1] md:block">
              <Table className="min-w-[1000px] table-fixed">
                <colgroup>
                  <col className="w-[22%]" />
                  <col className="w-[12%]" />
                  <col className="w-[7%]" />
                  <col className="w-[13%]" />
                  <col className="w-[9%]" />
                  <col className="w-[15%]" />
                  <col className="w-[12%]" />
                  <col className="w-[10%]" />
                </colgroup>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Investigation</TableHead>
                    <TableHead scope="col">Agent</TableHead>
                    <TableHead scope="col" className="text-right">Version</TableHead>
                    <TableHead scope="col">Visit outcome</TableHead>
                    <TableHead scope="col">Priority</TableHead>
                    <TableHead scope="col">Submitted / updated</TableHead>
                    <TableHead scope="col">Status</TableHead>
                    <TableHead scope="col" className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.items.map((item) => (
                    <TableRow key={item.report_id}>
                      <TableCell><RecordIdentity subject={item.subject_name} reference={item.reference_number} to={`/investigations/${item.investigation_id}#report`} /></TableCell>
                      <TableCell className="truncate" title={item.assigned_agent_name ?? item.author_name}>{item.assigned_agent_name ?? item.author_name}</TableCell>
                      <TableCell className="text-right">{item.version}</TableCell>
                      <TableCell className="capitalize">
                        {item.visit_outcome?.replaceAll("_", " ") ?? "Not recorded"}
                      </TableCell>
                      <TableCell>
                        <PriorityBadge priority={item.priority} />
                      </TableCell>
                      <TableCell>
                        {date(
                          value === "submitted"
                            ? item.submitted_at
                            : item.updated_at,
                        )}
                        <small className="block">
                          {time(
                            value === "submitted"
                              ? item.submitted_at
                              : item.updated_at,
                          )}
                        </small>
                      </TableCell>
                      <TableCell><span className={`status-badge status-${item.status.replaceAll("_", "-")}`}>{item.status.replaceAll("_", " ")}</span></TableCell>
                      <TableCell className="text-right">
                        <Link className="inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1.5 text-[11px] font-semibold text-[#315db4] no-underline hover:bg-[#eff4fd]" to={`/investigations/${item.investigation_id}#report`} aria-label={`${value === "submitted" ? "Review" : "View"} report for ${item.reference_number}`}>
                          {value === "submitted" ? "Review" : "View"}<ArrowUpRight className="size-3.5" aria-hidden="true" />
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <WorkspaceMobileList aria-label="Report queue">
              {resource.data.items.map((item) => {
                const timestamp =
                  value === "submitted" ? item.submitted_at : item.updated_at;
                return (
                  <li key={item.report_id}>
                    <div className="mobile-row-heading">
                      <Link
                        to={`/investigations/${item.investigation_id}#report`}
                      >
                        <strong>{item.reference_number}</strong>
                      </Link>
                      <PriorityBadge priority={item.priority} />
                    </div>
                    <span>{item.subject_name}</span>
                    <dl className="mobile-row-facts">
                      <div>
                        <dt>Agent</dt>
                        <dd>{item.assigned_agent_name ?? item.author_name}</dd>
                      </div>
                      <div>
                        <dt>Visit outcome</dt>
                        <dd className="capitalize">
                          {item.visit_outcome?.replaceAll("_", " ") ?? "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt>Report</dt>
                        <dd>
                          Version {item.version} ·{" "}
                          {item.status.replaceAll("_", " ")}
                        </dd>
                      </div>
                      <div>
                        <dt>
                          {value === "submitted" ? "Submitted" : "Updated"} ·
                          PHT
                        </dt>
                        <dd>
                          {date(timestamp)} · {time(timestamp)}
                        </dd>
                      </div>
                    </dl>
                    <Link
                      className="secondary-button"
                      to={`/investigations/${item.investigation_id}#report`}
                    >
                      {value === "submitted" ? "Review report" : "View report"}
                    </Link>
                  </li>
                );
              })}
            </WorkspaceMobileList>
          </>
        ) : resource.error && !resource.data ? null : (
          <EmptyState title={value === "submitted" ? "No submitted reports in this queue" : "No reports in this queue"}>
            {value === "submitted"
              ? "Submitted reports matching this search will appear here."
              : "Reports matching this status and search will appear here."}
          </EmptyState>
        )}
        {resource.data && (
          <Pagination
            total={resource.data.total}
            page={resource.data.page}
            pageSize={resource.data.page_size}
            onChange={(page) => update("page", String(page))}
            onSizeChange={(size) => update("page_size", String(size))}
          />
        )}
      </WorkspacePanel>
        {value === "submitted" && (
          <WorkspacePanel
            title="No-contact reports and attempts"
            description="Open attempts and finalized no-contact reports scheduled for the next workday appear here."
            action={noContactResource.data && <span className="text-xs text-[#65758f]">{noContactResource.data.total} items</span>}
          >
            {noContactResource.error && !noContactResource.data ? (
              <InlineAlert onRetry={noContactResource.refresh}>
                {noContactResource.error}
              </InlineAlert>
            ) : noContactResource.loading && !noContactResource.data ? (
              <Skeleton rows={3} />
            ) : noContactResource.data?.items.length ? (
              <>
                {noContactActionMessage && (
                  <p className="success-message" role="status" aria-live="polite">
                    {noContactActionMessage}
                  </p>
                )}
                <div className="hidden max-w-full overflow-x-auto rounded-lg border border-[#e2e8f1] md:block">
                  <Table className="min-w-[1000px] table-fixed">
                    <colgroup>
                      <col className="w-[20%]" />
                      <col className="w-[13%]" />
                      <col className="w-[7%]" />
                      <col className="w-[16%]" />
                      <col className="w-[13%]" />
                      <col className="w-[12%]" />
                      <col className="w-[11%]" />
                      <col className="w-[8%]" />
                    </colgroup>
                    <TableHeader>
                      <TableRow>
                        <TableHead scope="col">Investigation</TableHead>
                        <TableHead scope="col">Assigned agent</TableHead>
                        <TableHead scope="col" className="text-right">Attempt</TableHead>
                        <TableHead scope="col">Reason</TableHead>
                        <TableHead scope="col">Attempted</TableHead>
                        <TableHead scope="col">State</TableHead>
                        <TableHead scope="col">Next workday</TableHead>
                        <TableHead scope="col" className="text-right">Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {noContactResource.data.items.map((item) => (
                        <TableRow key={item.event_id}>
                          <TableCell><RecordIdentity subject={item.subject_name} reference={item.reference_number} to={`/investigations/${item.investigation_id}#report`} /></TableCell>
                          <TableCell>{item.assigned_agent_name ?? "Unassigned"}</TableCell>
                          <TableCell className="text-right">{item.retry_number + 1}</TableCell>
                          <TableCell>
                            <span className="capitalize">{item.reason.replaceAll("_", " ")}</span>
                            {item.notes && <small className="mt-1 line-clamp-2" title={item.notes}>{item.notes}</small>}
                          </TableCell>
                          <TableCell>
                            {date(item.attempted_at)}
                            <small className="block">{time(item.attempted_at)} PHT</small>
                          </TableCell>
                          <TableCell><span className={`status-badge status-${item.state.replaceAll("_", "-")}`}>{item.state.replaceAll("_", " ")}</span></TableCell>
                          <TableCell>{item.next_work_date ?? "Not scheduled"}</TableCell>
                          <TableCell className="text-right">
                            <RowActions label={item.reference_number}>
                              <Link
                                role="menuitem"
                                to={`/investigations/${item.investigation_id}#report`}
                              >
                                Open investigation
                              </Link>
                              {item.state !== "carried_over" && (
                                <button
                                  type="button"
                                  role="menuitem"
                                  className="danger-menu-item"
                                  onClick={() => {
                                    setNoContactActionError("");
                                    setNoContactActionMessage("");
                                    setCancelTarget(item);
                                  }}
                                >
                                  Cancel attempt
                                </button>
                              )}
                            </RowActions>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <WorkspaceMobileList aria-label="No-contact attempts awaiting review">
                  {noContactResource.data.items.map((item) => (
                    <li key={item.event_id}>
                      <div className="mobile-row-heading">
                        <Link to={`/investigations/${item.investigation_id}#report`}>
                          <strong>{item.reference_number}</strong>
                        </Link>
                        <PriorityBadge priority={item.priority} />
                        <RowActions label={item.reference_number}>
                          <Link
                            role="menuitem"
                            to={`/investigations/${item.investigation_id}#report`}
                          >
                            Open investigation
                          </Link>
                          {item.state !== "carried_over" && (
                            <button
                              type="button"
                              role="menuitem"
                              className="danger-menu-item"
                              onClick={() => {
                                setNoContactActionError("");
                                setNoContactActionMessage("");
                                setCancelTarget(item);
                              }}
                            >
                              Cancel attempt
                            </button>
                          )}
                        </RowActions>
                      </div>
                      <span>{item.subject_name}</span>
                      <dl className="mobile-row-facts">
                        <div>
                          <dt>Assigned agent</dt>
                          <dd>{item.assigned_agent_name ?? "Unassigned"}</dd>
                        </div>
                        <div>
                          <dt>Attempt</dt>
                          <dd>{item.retry_number + 1}: {item.reason.replaceAll("_", " ")}</dd>
                        </div>
                        <div>
                          <dt>State</dt>
                          <dd className="capitalize">{item.state.replaceAll("_", " ")}</dd>
                        </div>
                        <div>
                          <dt>Next workday</dt>
                          <dd>{item.next_work_date ?? "Not scheduled"}</dd>
                        </div>
                        {item.notes && (
                          <div>
                            <dt>Agent notes</dt>
                            <dd>{item.notes}</dd>
                          </div>
                        )}
                        <div>
                          <dt>Attempted (PHT)</dt>
                          <dd>{date(item.attempted_at)} at {time(item.attempted_at)}</dd>
                        </div>
                      </dl>
                    </li>
                  ))}
                </WorkspaceMobileList>
                <Pagination
                  total={noContactResource.data.total}
                  page={noContactResource.data.page}
                  pageSize={noContactResource.data.page_size}
                  onChange={(page) => update("no_contact_page", String(page))}
                  onSizeChange={(size) => update("no_contact_page_size", String(size))}
                />
              </>
            ) : (
              <>
                {noContactActionMessage && (
                  <p className="success-message" role="status" aria-live="polite">
                    {noContactActionMessage}
                  </p>
                )}
                <EmptyState title="No no-contact reports or attempts">
                  Agent no-contact attempts and finalized submissions will appear here.
                </EmptyState>
              </>
            )}
          </WorkspacePanel>
        )}
      <Modal
        open={cancelTarget !== null}
        title="Cancel no-contact attempt"
        onClose={() => !cancellingNoContact && setCancelTarget(null)}
      >
        <div className="confirm-dialog-copy">
          <p>
            Cancel the no-contact attempt for <strong>{cancelTarget?.reference_number}</strong>?
          </p>
          <p>
            The investigation will be cancelled for today and made available again the next day.
          </p>
          {noContactActionError && (
            <p className="error" role="alert">{noContactActionError}</p>
          )}
          <div className="modal-form-actions">
            <button
              type="button"
              className="secondary-button toolbar-button"
              onClick={() => setCancelTarget(null)}
              disabled={cancellingNoContact}
            >
              Keep attempt
            </button>
            <button
              type="button"
              className="danger-button toolbar-button"
              onClick={() => void handleCancelNoContactAttempt()}
              disabled={cancellingNoContact}
            >
              {cancellingNoContact ? "Cancelling…" : "Cancel for today"}
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
