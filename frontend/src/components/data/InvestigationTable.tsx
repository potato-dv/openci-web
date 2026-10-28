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
}: Props) {
  const navigate = useNavigate();
  function heading(label: string, column: string) {
    return (
      <th
        scope="col"
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
            className="sort-button"
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
      </th>
    );
  }
  return (
    <>
      <div className="table-wrap investigation-desktop">
        <table className="investigation-table">
          <caption className="sr-only">Investigation records</caption>
          <thead>
            <tr>
              {heading("Reference / subject", "reference_number")}
              <th scope="col">Location</th>
              {heading("Priority", "priority")}
              {heading("Status", "status")}
              <th scope="col">Assigned agent</th>
              {heading("Created", "created_at")}
              <th scope="col" className="actions-heading">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link
                    className="record-identity"
                    to={`/investigations/${item.id}`}
                  >
                    <strong>{item.reference_number}</strong>
                    <span title={item.subject_name}>{item.subject_name}</span>
                  </Link>
                </td>
                <td className="location-cell">
                  <span title={item.address_display}>
                    {item.address_display || item.legacy_address || "—"}
                  </span>
                  {!item.location_confirmed && (
                    <small>Location unconfirmed</small>
                  )}
                </td>
                <td>
                  <PriorityBadge priority={item.priority} />
                </td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
                <td>{item.assigned_agent_name || "Unassigned"}</td>
                <td className="nowrap">{date(item.created_at)}</td>
                <td>
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
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="investigation-mobile">
        {items.map((item) => (
          <li key={item.id}>
            <Link to={`/investigations/${item.id}`}>
              <strong>{item.reference_number}</strong>
              <span>{item.subject_name}</span>
              <small>{item.address_display || item.legacy_address}</small>
              <div>
                <StatusBadge status={item.status} />
                <PriorityBadge priority={item.priority} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
