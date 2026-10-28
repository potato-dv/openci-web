import { useState } from "react";
import { ZoomIn, ZoomOut } from "lucide-react";
import { useMap, useMapEvents } from "react-leaflet";

export function MapZoomControls() {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());

  useMapEvents({
    zoomend: () => setZoom(map.getZoom()),
  });

  return (
    <div className="map-zoom-controls" aria-label="Map zoom controls">
      <button
        type="button"
        aria-label="Zoom in"
        title="Zoom in"
        disabled={zoom >= map.getMaxZoom()}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          map.zoomIn();
        }}
      >
        <ZoomIn size={18} aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        title="Zoom out"
        disabled={zoom <= map.getMinZoom()}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          map.zoomOut();
        }}
      >
        <ZoomOut size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
