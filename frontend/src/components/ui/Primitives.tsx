import {
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { AlertCircle, Inbox, X } from "lucide-react";
import { Modal } from "./Modal";
import { Button as ShadcnButton } from "./button";
import { friendlyError } from "../../utils/format";
export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  return (
    <ShadcnButton
      type="button"
      variant={variant === "primary" ? "default" : variant === "danger" ? "destructive" : "outline"}
      size="lg"
      className={`${variant}-button ${className}`}
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
  return (
    <div
      className="skeleton"
      role="status"
      aria-label="Loading content"
      aria-busy="true"
    >
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} />
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
  return (
    <div
      className={`inline-alert alert-${variant}`}
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
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((item, index) => (
        <button
          key={item.value}
          type="button"
          id={`tab-${label.replaceAll(" ", "-")}-${item.value}`}
          role="tab"
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
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Modal open={open} title={title} onClose={onClose} className="drawer">
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
