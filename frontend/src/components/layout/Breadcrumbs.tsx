type BreadcrumbsProps = {
  parentLabel: string;
  currentLabel: string;
  onParentClick: () => void;
};

export function Breadcrumbs({
  parentLabel,
  currentLabel,
  onParentClick,
}: BreadcrumbsProps) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        <li>
          <button type="button" className="breadcrumb-link" onClick={onParentClick}>
            {parentLabel}
          </button>
        </li>
        <li className="breadcrumb-current" aria-current="page">
          {currentLabel}
        </li>
      </ol>
    </nav>
  );
}
