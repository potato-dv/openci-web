import { Button } from "../ui/Primitives";
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
      className="flex flex-wrap items-center justify-end gap-3 pt-5 text-xs text-openci-text-muted max-[767px]:justify-start max-[767px]:gap-2"
      aria-label="Pagination"
    >
      <span className="mr-auto max-[767px]:basis-full">
        {total
          ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`
          : "0 records"}
      </span>
      <label className="flex items-center gap-2">
        Rows per page
        <select
          className="!min-h-9 !text-[13px] w-[68px]"
          value={pageSize}
          onChange={(event) => onSizeChange(Number(event.target.value))}
        >
          {[25, 50, 100].map((size) => (
            <option key={size}>{size}</option>
          ))}
        </select>
      </label>
      <Button disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Previous
      </Button>
      <span>
        Page {page} of {Math.max(1, Math.ceil(total / pageSize))}
      </span>
      <Button
        disabled={page * pageSize >= total}
        onClick={() => onChange(page + 1)}
      >
        Next
      </Button>
    </nav>
  );
}
