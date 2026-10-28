import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
export function useDirtyForm(dirty: boolean) {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (!dirty) return;
    const message = "Leave this form? Your unsaved changes will be lost.";
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const click = (event: MouseEvent) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
        return;
      const link = (event.target as HTMLElement).closest(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        link &&
        !link.target &&
        link.href !== window.location.href &&
        !window.confirm(message)
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const pop = () => {
      if (!window.confirm(message))
        navigate(`${location.pathname}${location.search}${location.hash}`, {
          replace: true,
        });
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", click, true);
    window.addEventListener("popstate", pop);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", click, true);
      window.removeEventListener("popstate", pop);
    };
  }, [dirty, location.pathname, location.search, location.hash, navigate]);
}
