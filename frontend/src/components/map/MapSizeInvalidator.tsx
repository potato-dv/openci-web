import { useEffect } from "react";
import { useMap } from "react-leaflet";

/** Keep Leaflet's viewport and tile grid in sync when its container is revealed or resized. */
export function MapSizeInvalidator() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    const dialog = container.closest("dialog");
    let frame: number | null = null;
    let retry: number | null = null;

    const invalidateSize = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        map.invalidateSize({ pan: false, debounceMoveend: true });
        if (retry !== null) window.clearTimeout(retry);
        retry = window.setTimeout(() => {
          retry = null;
          map.invalidateSize({ pan: false, debounceMoveend: true });
        }, 160);
      });
    };

    invalidateSize();
    window.addEventListener("resize", invalidateSize);
    document.addEventListener("visibilitychange", invalidateSize);
    dialog?.addEventListener("transitionend", invalidateSize);

    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(invalidateSize);
    resizeObserver?.observe(container);
    if (container.parentElement)
      resizeObserver?.observe(container.parentElement);

    const dialogObserver =
      dialog && typeof MutationObserver !== "undefined"
        ? new MutationObserver(invalidateSize)
        : null;
    dialogObserver?.observe(dialog!, {
      attributes: true,
      attributeFilter: ["open"],
    });

    return () => {
      resizeObserver?.disconnect();
      dialogObserver?.disconnect();
      window.removeEventListener("resize", invalidateSize);
      document.removeEventListener("visibilitychange", invalidateSize);
      dialog?.removeEventListener("transitionend", invalidateSize);
      if (frame !== null) cancelAnimationFrame(frame);
      if (retry !== null) window.clearTimeout(retry);
    };
  }, [map]);

  return null;
}
