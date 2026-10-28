import type { ReactNode } from "react";
import { Link } from "react-router";
export function PageHeader({
  title,
  description,
  actions,
  parent,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  parent?: { to: string; label: string };
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between sm:gap-5">
      <div className="min-w-0">
        {parent && (
          <nav
            aria-label="Breadcrumb"
            className="mb-3 text-xs text-openci-text-muted"
          >
            <Link to={parent.to}>{parent.label}</Link>
            <span aria-hidden="true"> / </span>
            <span aria-current="page">{title}</span>
          </nav>
        )}
        <h1 className="m-0 text-[20px] leading-[1.3] font-[650] tracking-[-0.025em]">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 mb-0 text-[13px] text-openci-text-muted">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-end gap-2">{actions}</div>
      )}
    </header>
  );
}
