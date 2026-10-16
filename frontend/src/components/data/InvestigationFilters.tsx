import type {
  InvestigationPriority,
  InvestigationStatus,
} from "../../types/api";

type InvestigationFiltersProps = {
  query: string;
  status: InvestigationStatus | "all";
  priority: InvestigationPriority | "all";
  onQueryChange: (value: string) => void;
  onStatusChange: (value: InvestigationStatus | "all") => void;
  onPriorityChange: (value: InvestigationPriority | "all") => void;
  onReset: () => void;
};

const statuses: InvestigationStatus[] = [
  "pending",
  "assigned",
  "in_progress",
  "under_review",
  "returned_for_correction",
  "completed",
];

export function InvestigationFilters({
  query,
  status,
  priority,
  onQueryChange,
  onStatusChange,
  onPriorityChange,
  onReset,
}: InvestigationFiltersProps) {
  const hasActiveFilters =
    query.trim().length > 0 || status !== "all" || priority !== "all";

  return (
    <div className="investigation-filters" aria-label="Investigation filters">
      <label className="filter-search">
        <span>Search</span>
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Reference, subject, or address"
        />
      </label>

      <label>
        <span>Status</span>
        <select
          value={status}
          onChange={(event) =>
            onStatusChange(event.target.value as InvestigationStatus | "all")
          }
        >
          <option value="all">All statuses</option>
          {statuses.map((item) => (
            <option key={item} value={item}>
              {item.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span>Priority</span>
        <select
          value={priority}
          onChange={(event) =>
            onPriorityChange(
              event.target.value as InvestigationPriority | "all",
            )
          }
        >
          <option value="all">All priorities</option>
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
      </label>

      <button
        type="button"
        className="secondary-button toolbar-button filter-reset"
        onClick={onReset}
        disabled={!hasActiveFilters}
      >
        Clear filters
      </button>
    </div>
  );
}
