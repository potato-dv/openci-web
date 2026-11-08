import {
  useContext,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
} from "react";
import { AlertCircle, Inbox, X } from "lucide-react";
import { Modal } from "./Modal";
import { Button as ShadcnButton } from "./button";
import { friendlyError } from "../../utils/format";
import { WorkspaceVisualContext } from "./WorkspaceVisualContext";
export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  const workspace = useContext(WorkspaceVisualContext);
  return (
    <ShadcnButton
      type="button"
      variant={variant === "primary" ? "default" : variant === "danger" ? "destructive" : "outline"}
      size="lg"
      className={workspace ? `${variant === "primary" ? "bg-[#3261c5] text-white hover:bg-[#2853ac]" : variant === "danger" ? "border border-[#ecc9c5] bg-[#fff1ef] text-[#a23d34] hover:bg-[#ffe8e5]" : "border border-[#cbd7e7] bg-white text-[#234061] hover:bg-[#f5f8fc]"} min-h-9 rounded-lg px-3 text-[13px] font-medium ${className}` : `${variant}-button ${className}`}
      {...props}
    />
  );
}
export function IconButton({
  label,
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      className={`icon-button ${className}`}
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
}
export function FormField({
  label,
  error,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
}) {
  const generated = useId();
  const id = props.id ?? generated;
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <input
        {...props}
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={error || hint ? `${id}-description` : undefined}
      />
      {(error || hint) && (
        <span
          id={`${id}-description`}
          className={error ? "error" : "form-hint"}
        >
          {error || hint}
        </span>
      )}
    </div>
  );
}
export function Checkbox({
  children,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { children: ReactNode }) {
  return (
    <label className="check-row">
      <input type="checkbox" {...props} />
      <span>{children}</span>
    </label>
  );
}
export function Skeleton({ rows = 5 }: { rows?: number }) {
  const workspace = useContext(WorkspaceVisualContext);
  return (
    <div
      className={workspace ? "grid gap-3 rounded-xl border border-[#e1e8f1] bg-white p-5" : "skeleton"}
      role="status"
      aria-label="Loading content"
      aria-busy="true"
    >
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className={workspace ? `block h-4 animate-pulse rounded bg-[#eaf0f7] ${index % 3 === 0 ? "w-3/5" : index % 3 === 1 ? "w-full" : "w-4/5"}` : undefined} />
      ))}
    </div>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const workspace = useContext(WorkspaceVisualContext);
  if (workspace) return (
    <div className="mx-auto flex max-w-[420px] flex-col items-center px-4 py-10 text-center">
      <span className="mb-4 grid size-11 place-items-center rounded-xl bg-[#eaf1ff] text-[#3261c5]"><Inbox aria-hidden="true" size={22} /></span>
      <h2 className="mb-1 text-[15px] font-semibold text-[#203758]">{title}</h2>
      {children && <p className="mb-0 text-[12px] leading-relaxed text-[#6a7b95]">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
  return (
    <div className="empty-content">
      <Inbox aria-hidden="true" size={24} />
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function InlineAlert({
  children,
  variant = "error",
  onRetry,
}: {
  children: ReactNode;
  variant?: "error" | "warning" | "success" | "info";
  onRetry?: () => void;
}) {
  const workspace = useContext(WorkspaceVisualContext);
  const tones = { error: "border-[#ecc9c5] bg-[#fff5f3] text-[#8e3934]", warning: "border-[#ecd5a6] bg-[#fff9ed] text-[#855b1a]", success: "border-[#bedecb] bg-[#f0faf4] text-[#176947]", info: "border-[#c5d6f5] bg-[#f1f6ff] text-[#2755a8]" };
  return (
    <div
      className={workspace ? `mb-4 flex items-start gap-3 rounded-lg border px-4 py-3 text-[13px] ${tones[variant]}` : `inline-alert alert-${variant}`}
      role={variant === "error" ? "alert" : "status"}
    >
      <AlertCircle size={17} aria-hidden="true" />
      <div>
        {typeof children === "string" ? friendlyError(children) : children}
      </div>
      {onRetry && <Button onClick={onRetry}>Retry</Button>}
    </div>
  );
}
export function Tabs({
  value,
  onChange,
  items,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  items: { value: string; label: ReactNode }[];
  label: string;
}) {
  const workspace = useContext(WorkspaceVisualContext);
  return (
    <div className={workspace ? "mb-5 flex w-fit max-w-full gap-1 overflow-x-auto rounded-lg border border-[#dfe6ef] bg-[#f2f5f9] p-1" : "tabs"} role="tablist" aria-label={label}>
      {items.map((item, index) => (
        <button
          key={item.value}
          type="button"
          id={`tab-${label.replaceAll(" ", "-")}-${item.value}`}
          role="tab"
          className={workspace ? `min-h-9 shrink-0 rounded-md border-0 px-3 text-[12px] font-medium ${value === item.value ? "bg-white text-[#2452a4] shadow-[0_1px_3px_rgba(19,37,68,0.1)]" : "bg-transparent text-[#657791] hover:text-[#254b8e]"}` : undefined}
          aria-selected={value === item.value}
          tabIndex={value === item.value ? 0 : -1}
          onClick={() => onChange(item.value)}
          onKeyDown={(event) => {
            const offset =
              event.key === "ArrowRight"
                ? 1
                : event.key === "ArrowLeft"
                  ? -1
                  : 0;
            if (offset || event.key === "Home" || event.key === "End") {
              event.preventDefault();
              const next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? items.length - 1
                    : (index + offset + items.length) % items.length;
              onChange(items[next].value);
              (
                event.currentTarget.parentElement?.children[next] as HTMLElement
              )?.focus();
            }
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
export function Drawer({
  title,
  open,
  onClose,
  children,
  contentRef,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  contentRef?: Ref<HTMLDivElement>;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      className="drawer"
      contentRef={contentRef}
    >
      {children}
    </Modal>
  );
}
export function ConfirmDialog({
  open,
  title,
  children,
  onClose,
  onConfirm,
  busy = false,
  action = "Confirm",
  danger = false,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  onConfirm: () => void;
  busy?: boolean;
  action?: string;
  danger?: boolean;
}) {
  return (
    <Modal open={open} title={title} onClose={() => !busy && onClose()}>
      <div className="confirm-dialog-copy">{children}</div>
      <div className="modal-form-actions">
        <Button onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? "Saving…" : action}
        </Button>
      </div>
    </Modal>
  );
}
export function ToastRegion({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return message ? (
    <div className="toast" role="status">
      <span>{message}</span>
      <IconButton label="Dismiss notification" onClick={onDismiss}>
        <X size={16} />
      </IconButton>
    </div>
  ) : null;
}
