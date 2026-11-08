import { Search } from "lucide-react";

export function WorkspaceSearchField({
  value, onChange, placeholder, className = "", label = "Search",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
  label?: string;
}) {
  return (
    <label className={className}>
      <span>{label}</span>
      <span className="relative block">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[#8593aa]" aria-hidden="true" />
        <input className="!pl-9" type="search" value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      </span>
    </label>
  );
}
