import type { ComponentProps, ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function WorkspacePanel({
  title, description, action, children, className, bodyClassName, ...props
}: ComponentProps<"section"> & {
  title?: string;
  description?: string;
  action?: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <Card className={cn("mb-5 overflow-hidden rounded-xl border-[#dce4ef] bg-white shadow-[0_2px_12px_rgba(22,45,86,0.035)]", className)} {...props}>
      {(title || action) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e5eaf2] px-5 py-4 md:px-6">
          <div className="min-w-0">
            {title && <h2 className="m-0 text-[15px] font-semibold tracking-[-0.01em] text-[#1a2d4c]">{title}</h2>}
            {description && <p className="mb-0 mt-1 text-xs text-[#63748e]">{description}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={cn("min-w-0 p-5 md:p-6", bodyClassName)}>{children}</div>
    </Card>
  );
}

export function WorkspaceMobileList({ className, ...props }: ComponentProps<"ul">) {
  return <ul className={cn("m-0 grid list-none gap-3 p-0 md:hidden [&>li]:rounded-lg [&>li]:border [&>li]:border-[#e2e8f1] [&>li]:bg-white [&>li]:p-4", className)} {...props} />;
}
