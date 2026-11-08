export function PersonIdentity({ name, detail }: { name: string; detail?: string }) {
  const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  return (
    <span className="flex min-w-0 items-center gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#eaf0fc] text-[11px] font-semibold text-[#3562b2]" aria-hidden="true">{initials}</span>
      <span className="min-w-0 flex-1">
        <strong className="block truncate text-[12px] font-semibold text-[#233b5c]" title={name}>{name}</strong>
        {detail && <small className="mt-0.5 block truncate text-[10px] text-[#8190a7]" title={detail}>{detail}</small>}
      </span>
    </span>
  );
}
