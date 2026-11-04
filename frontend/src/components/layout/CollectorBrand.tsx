type CollectorBrandProps = {
  variant: "sidebar" | "auth";
};

export function CollectorBrand({ variant }: CollectorBrandProps) {
  return (
    <span className={`collector-brand collector-brand--${variant}`}>
      <strong>
        <img
          className="collector-brand-mark"
          src="/collector-mark.svg"
          alt=""
          aria-hidden="true"
        />
        <span aria-hidden="true">ollector</span>
        <span className="collector-brand-accessible">Collector</span>
      </strong>
      <small>Field operations</small>
    </span>
  );
}
