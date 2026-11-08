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
      className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 pt-5 text-xs text-openci-text-muted md:flex md:items-center md:justify-end"
      aria-label="Pagination"
    >
      <span className="self-center md:mr-auto">
        {total
          ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`
          : "0 records"}
      </span>
      <WorkspaceSelect
        className="w-[106px] md:w-[116px]"
        label="Rows per page"
        value={String(pageSize)}
        onValueChange={(value) => onSizeChange(Number(value))}
        options={[25, 50, 100].map((size) => ({ value: String(size), label: String(size) }))}
        compact
      />
      <div className="col-span-2 flex items-center justify-between gap-2 border-t border-[#edf1f6] pt-3 md:col-auto md:border-0 md:pt-0">
        <Button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
        <span className="whitespace-nowrap">Page {page} of {Math.max(1, Math.ceil(total / pageSize))}</span>
        <Button disabled={page * pageSize >= total} onClick={() => onChange(page + 1)}>Next</Button>
      </div>
    </nav>
  );
}
