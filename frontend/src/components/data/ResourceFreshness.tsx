import { LoaderCircle } from "lucide-react";

export function ResourceFreshness({
  loading,
  lastUpdatedAt,
  className = "",
}: {
  loading: boolean;
  lastUpdatedAt: number | null;
  className?: string;
}) {
  if (!loading && lastUpdatedAt === null) return null;

  const label = lastUpdatedAt === null
    ? "Loading"
    : `Updated ${new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
      }).format(lastUpdatedAt)}`;

  return (
    <span
      className={`inline-flex min-h-8 items-center gap-1.5 text-xs text-[#71819a] ${className}`}
      role={loading ? "status" : undefined}
      aria-live={loading ? "polite" : undefined}
      title={lastUpdatedAt === null ? undefined : new Date(lastUpdatedAt).toLocaleString()}
    >
      {loading && <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />}
      {loading && lastUpdatedAt !== null ? "Updating" : label}
    </span>
  );
}
