import type { Investigation } from "../../types/api";
import { StatusBadge } from "../ui/StatusBadge";
import { PriorityBadge } from "../ui/PriorityBadge";
import { RowActions } from "../ui/RowActions";
import { InvestigationSubjectCell } from "./InvestigationSubjectCell";
import { formatUserName } from "../../utils/userName";

type InvestigationTableProps = {
  items: Investigation[];
  onSelect?: (item: Investigation) => void;
  onSubjectOpen?: (item: Investigation) => void;
};

export function InvestigationTable({
  items,
  onSelect,
  onSubjectOpen,
}: InvestigationTableProps) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
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
              <td>
                <InvestigationSubjectCell
                  subjectName={item.subject_name}
                  referenceNumber={item.reference_number}
                  onOpen={
                    onSubjectOpen
                      ? () => onSubjectOpen(item)
                      : onSelect
                        ? () => onSelect(item)
                        : undefined
                  }
                />
              </td>
              <td>{item.address_display || item.legacy_address || "—"}</td>
              <td>{item.assigned_agent_name ? formatUserName(item.assigned_agent_name) : "Unassigned"}</td>
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
