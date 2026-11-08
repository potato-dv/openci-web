import type { PropsWithChildren } from "react";

export const dataFilterFieldClassName =
  "min-w-[120px] flex-[1_1_120px] md:flex-[0_1_160px]";

export const dataFilterSearchClassName =
  "min-w-0 basis-full md:min-w-[220px] md:flex-1";

export function DataFilterBar({ children }: PropsWithChildren) {
  return (
    <div
      className="mb-5 flex flex-wrap items-end gap-3 border-b border-[#e8edf4] pb-5 [&_input]:h-10 [&_input]:rounded-lg [&_input]:border-[#d6e0ed] [&_input]:bg-white [&_input]:px-3 [&_input]:text-[12px] [&_input]:shadow-[0_1px_2px_rgba(22,43,77,0.03)] [&_label]:gap-1.5 [&_label]:text-[11px] [&_label]:text-[#66758b]"
      role="group"
      aria-label="Filters"
    >
      {children}
    </div>
  );
}
