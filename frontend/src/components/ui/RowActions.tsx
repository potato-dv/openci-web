import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

type RowActionsProps = {
  label: string;
  children: ReactNode;
};

export function RowActions({ label, children }: RowActionsProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useLayoutEffect(() => {
    if (!open) return;

    function updatePosition() {
      const trigger = triggerRef.current;
      const menu = menuRef.current;
      if (!trigger || !menu) return;

      const triggerRect = trigger.getBoundingClientRect();
      const menuRect = menu.getBoundingClientRect();
      const gap = 3;
      const edge = 8;
      const left = Math.max(
        edge,
        Math.min(
          triggerRect.right - menuRect.width,
          window.innerWidth - menuRect.width - edge,
        ),
      );
      const below = triggerRect.bottom + gap;
      const top = Math.min(
        Math.max(edge, below),
        Math.max(edge, window.innerHeight - menuRect.height - edge),
      );

      menu.style.top = `${top}px`;
      menu.style.left = `${left}px`;
    }

    updatePosition();
    menuRef.current
      ?.querySelector<HTMLElement>("[role='menuitem']:not(:disabled)")
      ?.focus();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target;
      if (
        target instanceof Node &&
        (triggerRef.current?.contains(target) ||
          menuRef.current?.contains(target))
      )
        return;
      setOpen(false);
    }

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        return;
      }

      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const items = Array.from(
        menuRef.current?.querySelectorAll<HTMLElement>(
          "[role='menuitem']:not(:disabled)",
        ) ?? [],
      );
      if (!items.length) return;
      event.preventDefault();
      const currentIndex = items.indexOf(document.activeElement as HTMLElement);
      const nextIndex =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? items.length - 1
            : event.key === "ArrowDown"
              ? (currentIndex + 1) % items.length
              : currentIndex <= 0
                ? items.length - 1
                : currentIndex - 1;
      items[nextIndex]?.focus();
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Tab") setOpen(false);
  }

  return (
    <>
      <div className="row-actions">
        <button
          ref={triggerRef}
          type="button"
          className="row-actions-trigger"
          aria-label={`Actions for ${label}`}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={menuId}
          onKeyDown={(event) => {
            if (["Enter", " ", "ArrowDown"].includes(event.key)) {
              event.preventDefault();
              event.stopPropagation();
              setOpen(true);
            }
          }}
          onClick={() => {
            setOpen(!open);
          }}
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor">
            <circle cx="4" cy="10" r="1.5" />
            <circle cx="10" cy="10" r="1.5" />
            <circle cx="16" cy="10" r="1.5" />
          </svg>
        </button>
      </div>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            id={menuId}
            ref={menuRef}
            className="row-actions-menu"
            role="menu"
            aria-label={`Actions for ${label}`}
            onClick={() => setOpen(false)}
            onKeyDown={onMenuKeyDown}
          >
            {children}
          </div>,
          document.body,
        )}
    </>
  );
}
