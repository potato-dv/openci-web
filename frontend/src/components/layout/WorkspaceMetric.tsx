import type { ElementType } from "react";
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router";
import { Card } from "@/components/ui/card";

export function WorkspaceMetric({ label, value, to, icon: Icon }: {
  label: string;
  value?: number;
  to: string;
  icon: ElementType;
}) {
  return (
    <Card className="group min-w-0 rounded-2xl border border-blue-100 bg-gradient-to-b from-white via-blue-50 to-blue-100 shadow-sm transition-[border-color,box-shadow] hover:border-blue-200 hover:shadow-md">
      <Link to={to} className="block min-h-[132px] p-5 text-[#1b3153] no-underline focus-visible:rounded-xl focus-visible:outline-2 focus-visible:outline-[#3261c5]">
        <span className="flex items-start justify-between gap-2 text-[#71829e]">
          <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
          <ArrowUpRight size={16} className="transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden="true" />
        </span>
        <strong className="mt-4 block text-[29px] font-semibold leading-none tracking-[-0.035em] tabular-nums text-[#172d50]">{value ?? "—"}</strong>
        <span className="mt-2 block text-[12px] font-medium text-[#63748d]">{label}</span>
      </Link>
    </Card>
  );
}
