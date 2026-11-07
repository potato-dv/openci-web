import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from "@/components/ui/table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Link, useNavigate } from "react-router";
import type { Investigation } from "../../types/api";
import { StatusBadge } from "../ui/StatusBadge";
import { PriorityBadge } from "../ui/PriorityBadge";
import { RowActions } from "../ui/RowActions";
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
            className={`sort-button ${className?.includes("text-right") ? "ml-auto" : ""}`}
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
      <div className="table-wrap investigation-desktop">
        <Table className="investigation-table min-w-[940px] table-fixed">
          <TableCaption className="sr-only">Investigation records</TableCaption>
          <colgroup>
            <col className="w-[22%]" />
            <col className="w-[24%]" />
            <col className="w-[9%]" />
            <col className="w-[12%]" />
            <col className="w-[20%]" />
            <col className="w-[9%]" />
            <col className="w-[4%]" />
          </colgroup>
          <TableHeader>
            <TableRow>
              {heading("Reference / subject", "reference_number")}
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
                <TableCell>
                  <Link
                    className="record-identity"
                    to={`/investigations/${item.id}`}
                  >
                    <strong>{item.reference_number}</strong>
                    <span title={item.subject_name}>{item.subject_name}</span>
                  </Link>
                </TableCell>
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
                  <div className="investigation-assigned-agent">
                    <div className="investigation-assigned-agent-copy">
                      <span>{item.assigned_agent_name || "Unassigned"}</span>
                      {item.manual_assignment_required && (
                        <small>Manual assignment required</small>
                      )}
                    </div>
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
                  </div>
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
      <ul className="investigation-mobile">
        {items.map((item) => (
          <li key={item.id}>
            <div className="investigation-mobile-row">
              <Link to={`/investigations/${item.id}`}>
                <strong>{item.reference_number}</strong>
                <span>{item.subject_name}</span>
                <small>{item.address_display || item.legacy_address}</small>
                <div>
                  <StatusBadge status={item.status} reopenOn={item.reopen_on} />
                  <PriorityBadge priority={item.priority} />
                </div>
                {item.manual_assignment_required && (
                  <small>Choose an agent manually</small>
                )}
              </Link>
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
