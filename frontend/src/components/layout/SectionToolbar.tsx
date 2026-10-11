import type { ReactNode } from "react";

type SectionToolbarProps = {
  title: string;
  description: string;
  actions?: ReactNode;
};

export function SectionToolbar({
  title,
  description,
  actions,
}: SectionToolbarProps) {
  return (
    <div className="section-toolbar">
      <div className="section-toolbar-copy">
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions && <div className="section-toolbar-actions">{actions}</div>}
    </div>
  );
}
