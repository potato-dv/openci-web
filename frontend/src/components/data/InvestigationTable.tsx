import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from "@/components/ui/table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Link, useNavigate } from "react-router";
import type { Investigation } from "../../types/api";
import { StatusBadge } from "../ui/StatusBadge";
import { PriorityBadge } from "../ui/PriorityBadge";
import { RowActions } from "../ui/RowActions";
import { RecordIdentity } from "./RecordIdentity";
import { date } from "../../utils/format";
type Props = {
  items: Investigation[];
  canManage?: boolean;
  sort?: string;
  direction?: string;
  onSort?: (column: string) => void;
  onTrash?: (item: Investigation) => void;
  onUnassign?: (item: Investigation) => void;
  onSubmitAutomaticAssignment?: (item: Investigation) => void;
  automaticAssignmentBusyId?: number | null;
  automaticAssignmentSubmittedId?: number | null;
  onSelect?: (item: Investigation) => void;
  onSubjectOpen?: (item: Investigation) => void;
};
export function InvestigationTable({
  items,
  canManage = false,
  sort,
  direction,
  onSort,
  onTrash,
  onUnassign,
  onSubmitAutomaticAssignment,
  automaticAssignmentBusyId,
  automaticAssignmentSubmittedId,
}: Props) {
  const navigate = useNavigate();
  function heading(label: string, column: string, className?: string) {
    return (
      <TableHead
        scope="col"
        className={className}
        aria-sort={
          sort === column
            ? direction === "asc"
              ? "ascending"
              : "descending"
            : undefined
        }
      >
        {onSort ? (
          <button
            className={`sort-button gap-1.5 rounded-md px-1 py-1 text-[11px] font-semibold text-[#64748b] hover:bg-[#edf3fb] hover:text-[#2857ae] ${className?.includes("text-right") ? "ml-auto" : ""}`}
            type="button"
            onClick={() => onSort(column)}
          >
            {label}
            {sort === column ? (
              direction === "asc" ? (
                <ArrowUp aria-hidden="true" size={13} />
              ) : (
                <ArrowDown aria-hidden="true" size={13} />
              )
            ) : (
              <ArrowUpDown aria-hidden="true" size={13} />
            )}
          </button>
        ) : (
          label
        )}
      </TableHead>
    );
  }
  return (
    <>
      <div className="hidden max-w-full overflow-x-auto rounded-lg border border-[#e2e8f1] md:block">
        <Table className="investigation-table min-w-[960px] table-fixed">
          <TableCaption className="sr-only">Investigation records</TableCaption>
          <colgroup>
            <col className="w-[25%]" />
            <col className="w-[22%]" />
            <col className="w-[9%]" />
            <col className="w-[12%]" />
            <col className="w-[16%]" />
            <col className="w-[9%]" />
            <col className="w-[7%]" />
          </colgroup>
          <TableHeader>
            <TableRow>
              {heading("Investigation", "reference_number")}
              <TableHead scope="col">Location</TableHead>
              {heading("Priority", "priority")}
              {heading("Status", "status")}
              <TableHead scope="col">Assigned agent</TableHead>
              {heading("Created", "created_at", "text-right")}
              <TableHead scope="col" className="actions-heading text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell><RecordIdentity subject={item.subject_name} reference={item.reference_number} to={`/investigations/${item.id}`} /></TableCell>
                <TableCell className="location-cell">
                  <span title={item.address_display}>
                    {item.address_display || item.legacy_address || "—"}
                  </span>
                  {!item.location_confirmed && (
                    <small>Location unconfirmed</small>
                  )}
                </TableCell>
                <TableCell>
                  <PriorityBadge priority={item.priority} />
                </TableCell>
                <TableCell>
                  <StatusBadge status={item.status} reopenOn={item.reopen_on} />
                </TableCell>
                <TableCell>
                  {item.assigned_agent_name ? (
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#e9f0fb] text-[10px] font-semibold text-[#3665b2]" aria-hidden="true">{item.assigned_agent_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase()}</span>
                      <span className="min-w-0 truncate" title={item.assigned_agent_name}>{item.assigned_agent_name}</span>
                    </span>
                  ) : <span className="text-[#8a98ac]">Unassigned</span>}
                  {item.manual_assignment_required && <small className="mt-1 block text-[10px] text-[#9a641e]">Manual assignment required</small>}
                </TableCell>
                <TableCell className="whitespace-nowrap text-right text-openci-text-muted">{date(item.created_at)}</TableCell>
                <TableCell className="text-right">
                  <RowActions label={item.reference_number}>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => navigate(`/investigations/${item.id}`)}
                    >
                      {" "}
                      View details{" "}
                    </button>
                    {canManage && (
                      <>
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() =>
                            navigate(`/investigations/${item.id}/edit`)
                          }
                        >
                          {" "}
                          Edit investigation{" "}
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() =>
                            navigate(`/investigations/${item.id}#assignment`)
                          }
                        >
                          {" "}
                          Manual assignment{" "}
                        </button>
                        {onSubmitAutomaticAssignment && canSubmitAutomaticAssignment(item) && automaticAssignmentSubmittedId !== item.id && (
                          <button
                            type="button"
                            role="menuitem"
                            disabled={automaticAssignmentBusyId != null}
                            onClick={() => onSubmitAutomaticAssignment(item)}
                          >
                            {automaticAssignmentBusyId === item.id ? "Submitting…" : "Submit to auto-assign"}
                          </button>
                        )}
                        {onUnassign && canUnassign(item) && (
                          <button type="button" role="menuitem" onClick={() => onUnassign(item)}>Unassign agent</button>
                        )}
                        {onTrash && (
                          <button
                            type="button"
                            role="menuitem"
                            className="danger-menu-item"
                            onClick={() => onTrash(item)}
                          >
                            Move to Trash
                          </button>
                        )}
                      </>
                    )}
                  </RowActions>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ul className="m-0 grid list-none gap-3 p-0 md:hidden" aria-label="Investigation records">
        {items.map((item) => (
          <li key={item.id} className="rounded-lg border border-[#e2e8f1] bg-white p-4">
            <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
              <Link className="min-w-0 flex-1 no-underline" to={`/investigations/${item.id}`}>
                <strong className="block truncate text-[14px] font-semibold text-[#1d3558]">{item.subject_name}</strong>
                <span className="mt-0.5 block truncate font-mono text-[11px] text-[#72829b]" title={item.reference_number}>{item.reference_number}</span>
              </Link>
              <StatusBadge status={item.status} reopenOn={item.reopen_on} />
            </div>
            <p className="mb-3 mt-3 text-[12px] text-[#657792]">{item.address_display || item.legacy_address || "Address unavailable"}</p>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#edf1f6] pt-3">
              <PriorityBadge priority={item.priority} />
              <span className="text-[11px] text-[#6b7d96]">{item.assigned_agent_name || "Unassigned"}</span>
            </div>
            {item.manual_assignment_required && <p className="mb-0 mt-2 text-[11px] text-[#8a580e]">Choose an agent manually</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              {canManage && onUnassign && canUnassign(item) && (
                <button
                  type="button"
                  className="danger-button compact-button investigation-unassign-button"
                  aria-label={`Unassign ${item.reference_number} from agent`}
                  onClick={() => onUnassign(item)}
                >
                  Unassign
                </button>
              )}
              {canManage &&
                onSubmitAutomaticAssignment &&
                canSubmitAutomaticAssignment(item) &&
                automaticAssignmentSubmittedId !== item.id && (
                  <button
                    type="button"
                    className="secondary-button compact-button investigation-unassign-button"
                    aria-label={`Submit ${item.reference_number} for automatic assignment`}
                    onClick={() => onSubmitAutomaticAssignment(item)}
                    disabled={automaticAssignmentBusyId != null}
                  >
                    {automaticAssignmentBusyId === item.id
                      ? "Submitting…"
                      : "Submit to auto-assign"}
                  </button>
                )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function canUnassign(item: Investigation) {
  return (
    item.assigned_agent_id != null &&
    (item.status === "pending" || item.status === "assigned")
  );
}

function canSubmitAutomaticAssignment(item: Investigation) {
  return (
    item.manual_assignment_required === true &&
    item.assigned_agent_id == null &&
    item.status === "pending"
  );
}
