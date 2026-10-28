import { useCallback } from "react";
import { Link, useSearchParams } from "react-router";
import { useSession } from "@/app/session";
import { getReportQueue } from "@/features/reports/api";
import { useResource } from "@/hooks/useResource";
import { PageHeader } from "@/components/layout/PageHeader";
import { Pagination } from "@/components/data/Pagination";
import { PriorityBadge } from "@/components/ui/PriorityBadge";
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
  const key = params.toString();
  const value = params.get("status") ?? "submitted";
  const resource = useResource(
    useCallback(
      (signal) => getReportQueue(token, new URLSearchParams(key), signal),
      [token, key],
    ),
  );
  function update(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    if (name !== "page") next.delete("page");
    setParams(next, { replace: name === "q" });
  }
  return (
    <>
      <PageHeader
        title="Reports"
        description="Review submitted findings and follow correction requests."
        actions={<Button onClick={resource.refresh}>Refresh</Button>}
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
        <div className="data-filters">
          <label className="filter-search">
            Search
            <input
              type="search"
              value={params.get("q") ?? ""}
              placeholder="Reference, subject, or address"
              onChange={(event) => update("q", event.target.value)}
            />
          </label>
          <label>
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
          <label>
            Order
            <select
              value={params.get("direction") ?? "asc"}
              onChange={(event) => update("direction", event.target.value)}
            >
              <option value="asc">Oldest first</option>
              <option value="desc">Newest first</option>
            </select>
          </label>
        </div>
        {resource.error && (
          <InlineAlert onRetry={resource.refresh}>{resource.error}</InlineAlert>
        )}
        {resource.loading ? (
          <Skeleton />
        ) : resource.data?.items.length ? (
          <>
            <div className="table-wrap desktop-data">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Investigation</th>
                    <th scope="col">Agent</th>
                    <th scope="col">Version</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Submitted / updated</th>
                    <th scope="col">Status</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {resource.data.items.map((item) => (
                    <tr key={item.report_id}>
                      <td>
                        <Link
                          className="record-identity"
                          to={`/investigations/${item.investigation_id}#report`}
                        >
                          <strong>{item.reference_number}</strong>
                          <span>{item.subject_name}</span>
                        </Link>
                      </td>
                      <td>{item.assigned_agent_name ?? item.author_name}</td>
                      <td>{item.version}</td>
                      <td>
                        <PriorityBadge priority={item.priority} />
                      </td>
                      <td>
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
                      </td>
                      <td>{item.status.replaceAll("_", " ")}</td>
                      <td>
                        <Link
                          to={`/investigations/${item.investigation_id}#report`}
                        >
                          {value === "submitted"
                            ? "Review report"
                            : "View report"}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
          <EmptyState title="No reports in this queue">
            Reports matching this status and search will appear here.
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
      </section>
    </>
  );
}
