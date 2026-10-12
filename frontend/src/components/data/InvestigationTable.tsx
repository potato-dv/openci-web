import type { Investigation } from "../../types/api";
import { StatusBadge } from "../ui/StatusBadge";
import { PriorityBadge } from "../ui/PriorityBadge";
import { RowActions } from "../ui/RowActions";

type InvestigationTableProps = {
  items: Investigation[];
  onSelect?: (item: Investigation) => void;
};

export function InvestigationTable({
  items,
  onSelect,
}: InvestigationTableProps) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Reference</th>
            <th>Subject</th>
            <th>Address</th>
            <th>Assigned agent</th>
            <th>Status</th>
            <th>Priority</th>
            {onSelect && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="reference">
                {onSelect ? (
                  <button
                    type="button"
                    className="table-link"
                    onClick={() => onSelect(item)}
                  >
                    {item.reference_number}
                  </button>
                ) : (
                  item.reference_number
                )}
              </td>
              <td>{item.subject_name}</td>
              <td>{item.address_display || item.legacy_address || "—"}</td>
              <td>{item.assigned_agent_name ?? "Unassigned"}</td>
              <td>
                <StatusBadge status={item.status} />
              </td>
              <td><PriorityBadge priority={item.priority} /></td>
              {onSelect && <td><RowActions label={item.reference_number}>
                <button type="button" role="menuitem" onClick={() => onSelect(item)}>View details</button>
              </RowActions></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
