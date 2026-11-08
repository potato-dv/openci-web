import type { ReactNode } from "react";
import { Link } from "react-router";
export function PageHeader({
  title,
  actions,
  parent,
}: {
  title: string;
  actions?: ReactNode;
  parent?: { to: string; label: string };
}) {
  return (
    <>
      <header data-page-header className="sr-only">
        {parent && (
          <nav aria-label="Breadcrumb">
            <Link to={parent.to}>{parent.label}</Link>
            <span aria-hidden="true"> / </span>
            <span aria-current="page">{title}</span>
          </nav>
        )}
        <h1>{title}</h1>
      </header>
      {actions && (
        <div
          data-page-actions
          className="mb-4 flex flex-wrap items-center justify-end gap-2"
        >
          {actions}
        </div>
      )}
    </>
  );
}
