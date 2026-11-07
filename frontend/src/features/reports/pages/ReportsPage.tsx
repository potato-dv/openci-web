import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { cancelNoContactAttempt, getNoContactReviewQueue, getReportQueue } from "@/features/reports/api";
import type { NoContactReviewItem } from "@/types/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  DataFilterBar,
  dataFilterFieldClassName,
  dataFilterSearchClassName,
} from "@/components/data/DataFilterBar";
import { Pagination } from "@/components/data/Pagination";
import { Modal } from "@/components/ui/Modal";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
import { RowActions } from "@/components/ui/RowActions";
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
      (signal) => getNoContactReviewQueue(token, new URLSearchParams(noContactKey), signal),
      [token, noContactKey],
    ),
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
      <PageHeader
        title="Reports"
        description="Review submitted findings and follow correction requests."
        actions={
          <Button
            onClick={() => {
              resource.refresh();
              noContactResource.refresh();
            }}
          >
            Refresh
          </Button>
        }
      />
      <section className="content-card">
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
          <label className={dataFilterSearchClassName}>
            Search
            <input
              type="search"
              value={params.get("q") ?? ""}
              placeholder="Reference, subject, or address"
              onChange={(event) => update("q", event.target.value)}
            />
          </label>
          <label className={dataFilterFieldClassName}>
            Sort
            <select
              value={params.get("sort") ?? "submitted_at"}
              onChange={(event) => update("sort", event.target.value)}
            >
              <option value="submitted_at">Submitted time</option>
              <option value="updated_at">Updated time</option>
              <option value="reference_number">Reference</option>
            </select>
          </label>
          <label className={dataFilterFieldClassName}>
            Order
            <select
              value={params.get("direction") ?? "asc"}
              onChange={(event) => update("direction", event.target.value)}
            >
              <option value="asc">Oldest first</option>
              <option value="desc">Newest first</option>
            </select>
          </label>
        </DataFilterBar>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {resource.loading ? (
          <Skeleton />
        ) : resource.data?.items.length ? (
          <>
            <div className="table-wrap desktop-data">
              <Table className="min-w-[1040px] table-fixed">
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
                      <TableCell>
                        <Link
                          className="record-identity"
                          to={`/investigations/${item.investigation_id}#report`}
                        >
                          <strong>{item.reference_number}</strong>
                          <span>{item.subject_name}</span>
                        </Link>
                      </TableCell>
                      <TableCell>{item.assigned_agent_name ?? item.author_name}</TableCell>
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
                        <Link
                          to={`/investigations/${item.investigation_id}#report`}
                        >
                          {value === "submitted"
                            ? "Review report"
                            : "View report"}
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <ul className="workspace-mobile-list" aria-label="Report queue">
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
            </ul>
          </>
        ) : (
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

        {value === "submitted" && (
          <section className="report-no-contact-queue" aria-labelledby="no-contact-queue-title">
            <div className="section-title">
              <div>
                <h2 id="no-contact-queue-title">No-contact reports and attempts</h2>
                <p className="report-no-contact-note">
                  Open attempts and finalized no-contact reports scheduled for the next workday appear here.
                </p>
              </div>
              {noContactResource.data && <span>{noContactResource.data.total} items</span>}
            </div>
            {noContactResource.error ? (
              <InlineAlert onRetry={noContactResource.refresh}>
                {noContactResource.error}
              </InlineAlert>
            ) : noContactResource.loading ? (
              <Skeleton rows={3} />
            ) : noContactResource.data?.items.length ? (
              <>
                {noContactActionMessage && (
                  <p className="success-message" role="status" aria-live="polite">
                    {noContactActionMessage}
                  </p>
                )}
                <div className="table-wrap desktop-data">
                  <Table className="min-w-[1040px] table-fixed">
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
                          <TableCell>
                            <Link
                              className="record-identity"
                              to={`/investigations/${item.investigation_id}#report`}
                            >
                              <strong>{item.reference_number}</strong>
                              <span>{item.subject_name}</span>
                            </Link>
                          </TableCell>
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
                <ul className="workspace-mobile-list" aria-label="No-contact attempts awaiting review">
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
                </ul>
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
          </section>
        )}
      </section>
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
