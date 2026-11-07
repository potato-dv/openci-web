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
    <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0">
        {parent && (
          <nav
            aria-label="Breadcrumb"
            className="mb-3 text-[13px] text-openci-text-muted"
          >
            <Link to={parent.to}>{parent.label}</Link>
            <span aria-hidden="true"> / </span>
            <span aria-current="page">{title}</span>
          </nav>
        )}
        <h1 className="m-0 text-[26px] leading-[1.25] font-[650] tracking-[-0.025em] max-[767px]:text-[23px]">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 mb-0 max-w-[72ch] text-sm leading-[1.5] text-openci-text-muted">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">{actions}</div>
      )}
    </header>
  );
}
