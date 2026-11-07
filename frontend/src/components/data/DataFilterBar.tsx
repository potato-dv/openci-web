import type { PropsWithChildren } from "react";

export const dataFilterFieldClassName =
  "min-w-[120px] flex-[1_1_120px] md:flex-[0_1_160px]";

export const dataFilterSearchClassName =
  "min-w-0 basis-full md:min-w-[220px] md:flex-1";

export function DataFilterBar({ children }: PropsWithChildren) {
  return (
    <div className="mb-5 flex flex-wrap items-end gap-3" role="group" aria-label="Filters">
      {children}
    </div>
  );
}
