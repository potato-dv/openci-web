import { Modal } from "@/components/ui/Modal";
import type { ActivityLogItem } from "@/types/api";
import { date, time } from "@/utils/format";

function humanize(value: string) {
  return value.replaceAll(".", " ").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function ActivityLogDetailsModal({
  item,
  onClose,
}: {
  item: ActivityLogItem | null;
  onClose: () => void;
}) {
  return (
    <Modal
      open={Boolean(item)}
      title={item?.summary ?? "Activity details"}
      onClose={onClose}
      size="wide"
    >
      {item && (
        <div className="grid gap-5">
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-[0.08em] text-openci-text-muted">When · PHT</dt>
              <dd className="mt-1 text-sm text-openci-text">{date(item.created_at)} · {time(item.created_at)}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-[0.08em] text-openci-text-muted">Actor</dt>
              <dd className="mt-1 text-sm text-openci-text">{item.actor_name ?? "System or deleted account"}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-[0.08em] text-openci-text-muted">Action</dt>
              <dd className="mt-1 text-sm text-openci-text">{humanize(item.action)}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium uppercase tracking-[0.08em] text-openci-text-muted">Record</dt>
              <dd className="mt-1 break-words text-sm text-openci-text">{item.record_label}</dd>
            </div>
          </dl>

          <section aria-labelledby="activity-detail-fields" className="grid gap-3 border-t border-openci-border pt-4">
            <h3 id="activity-detail-fields" className="m-0 text-sm font-semibold text-openci-text">Recorded information</h3>
            {item.detail_fields.length ? (
              <dl className="grid gap-3">
                {item.detail_fields.map((field) => (
                  <div key={field.key} className="grid gap-1 rounded-lg border border-openci-border bg-openci-surface-muted px-3 py-2 sm:grid-cols-[minmax(150px,0.35fr)_minmax(0,1fr)] sm:items-start sm:gap-4">
                    <dt className="text-xs font-semibold text-openci-text-muted">{field.label}</dt>
                    <dd className="m-0 break-words text-sm text-openci-text">
                      {field.value}
                      {field.redacted && <span className="ml-2 text-xs text-openci-text-muted">Hidden for privacy</span>}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="m-0 text-sm text-openci-text-muted">No additional structured information was recorded.</p>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
