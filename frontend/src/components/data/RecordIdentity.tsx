import { ClipboardList } from "lucide-react";
import { Link } from "react-router";

export function RecordIdentity({ subject, reference, to }: { subject: string; reference: string; to: string }) {
  return (
    <Link to={to} className="group flex min-w-0 items-center gap-3 no-underline">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-[#dbe7f8] bg-[#f0f5ff] text-[#3970c7]"><ClipboardList className="size-4" aria-hidden="true" /></span>
      <span className="min-w-0 flex-1">
        <strong className="block truncate text-[12px] font-semibold text-[#223958] group-hover:text-[#2b5eb9]" title={subject}>{subject}</strong>
        <span className="mt-0.5 block truncate font-mono text-[10px] text-[#8090a8]" title={reference}>{reference}</span>
      </span>
    </Link>
  );
}
