import type { Investigation } from "../../types/api";
import { StatusBadge } from "../ui/StatusBadge";

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
            <th>Status</th>
            <th>Priority</th>
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
              <td>
                <StatusBadge status={item.status} />
              </td>
              <td className={`priority-${item.priority}`}>{item.priority}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
