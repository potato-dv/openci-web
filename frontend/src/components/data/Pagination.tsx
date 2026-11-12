import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../ui/Primitives";
import { WorkspaceSelect } from "../ui/WorkspaceSelect";
export function Pagination({
  page,
  pageSize,
  total,
  onChange,
  onSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
  onSizeChange: (size: number) => void;
}) {
  return (
    <nav
      className="flex flex-col gap-4 pt-5 text-xs text-openci-text-muted sm:flex-row sm:items-center sm:justify-between"
      aria-label="Pagination"
    >
      <span className="whitespace-nowrap text-[12px] tabular-nums">
        {total
          ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`
          : "0 records"}
      </span>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-3 sm:justify-end">
        <WorkspaceSelect
          label="Rows per page"
          value={String(pageSize)}
          onValueChange={(value) => onSizeChange(Number(value))}
          options={[25, 50, 100].map((size) => ({
            value: String(size),
            label: String(size),
          }))}
          compact
          inlineLabel
        />
        <span className="min-w-[84px] whitespace-nowrap text-center text-[12px] font-medium tabular-nums text-[#354968]">
          Page {page} of {Math.max(1, Math.ceil(total / pageSize))}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            aria-label="Previous page"
            title="Previous page"
            disabled={page <= 1}
            onClick={() => onChange(page - 1)}
            className="size-8! min-h-8! rounded-md! p-0!"
          >
            <ChevronLeft size={16} aria-hidden="true" />
          </Button>
          <Button
            aria-label="Next page"
            title="Next page"
            disabled={page * pageSize >= total}
            onClick={() => onChange(page + 1)}
            className="size-8! min-h-8! rounded-md! p-0!"
          >
            <ChevronRight size={16} aria-hidden="true" />
          </Button>
        </div>
      </div>
    </nav>
  );
}
