import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

type ModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  size?: "default" | "wide";
  className?: string;
  initialFocus?: string;
};

export function Modal({
  open,
  title,
  onClose,
  children,
  size = "default",
  className = "",
  initialFocus,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const trigger = document.activeElement as HTMLElement | null;
    if (open && !dialog.open) {
      dialog.showModal();
      if (initialFocus)
        dialog.querySelector<HTMLElement>(initialFocus)?.focus();
    }
    if (open)
      return () => {
        dialog.close();
        trigger?.focus();
      };
    if (!open && dialog.open) dialog.close();
  }, [open, initialFocus]);

  const dialog = (
    <dialog
      ref={dialogRef}
      className={`app-modal app-modal-${size} ${className}`}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <header className="app-modal-header">
        <h2 id={titleId}>{title}</h2>
        <button
          type="button"
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
            <path
              d="m5 5 10 10M15 5 5 15"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>
      <div className="app-modal-content">{children}</div>
    </dialog>
  );

  return typeof document === "undefined"
    ? null
    : createPortal(dialog, document.body);
}
