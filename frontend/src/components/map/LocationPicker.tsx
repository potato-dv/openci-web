import { useState, useRef, useEffect, useCallback } from "react";
import { divIcon } from "leaflet";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import { renderToStaticMarkup } from "react-dom/server";
import { MapPin, Search } from "lucide-react";
import { searchLocations } from "@/features/locations/api";
import type { GeocodeCandidate, RoutePoint } from "../../types/api";
import { Button, FormField, InlineAlert } from "../ui/Primitives";
import { MapZoomControls } from "./MapZoomControls";
import { MapSizeInvalidator } from "./MapSizeInvalidator";
import "leaflet/dist/leaflet.css";
import "../../styles/maps.css";
export type ConfirmedPoint = RoutePoint & {
  source: "manual" | "nominatim";
  provider_ref: string | null;
};
function PointEditor({
  point,
  onChange,
}: {
  point: RoutePoint | null;
  onChange: (point: RoutePoint) => void;
}) {
  useMapEvents({
    click: (event) =>
      onChange({ latitude: event.latlng.lat, longitude: event.latlng.lng }),
  });
  return point ? (
    <Marker
      draggable
      position={[point.latitude, point.longitude]}
      icon={divIcon({
        className: "location-pin",
        html: renderToStaticMarkup(
          <MapPin size={34} fill="#eef0ff" stroke="#4f5abd" />,
        ),
        iconSize: [34, 40],
        iconAnchor: [17, 34],
      })}
      eventHandlers={{
        dragend: (event) => {
          const pos = event.target.getLatLng();
          onChange({ latitude: pos.lat, longitude: pos.lng });
        },
      }}
      title="Adjust selected location"
    />
  ) : null;
}
export function LocationPicker({
  token,
  initial = null,
  initialQuery = "",
  onConfirm,
  onDirty,
}: {
  token: string;
  initial?: ConfirmedPoint | null;
  initialQuery?: string;
  onConfirm: (point: ConfirmedPoint) => void | Promise<void>;
  onDirty?: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [point, setPoint] = useState<ConfirmedPoint | null>(initial);
  const [coords, setCoords] = useState({
    latitude: initial ? String(initial.latitude) : "",
    longitude: initial ? String(initial.longitude) : "",
  });
  const [candidates, setCandidates] = useState<GeocodeCandidate[]>([]);
  const [searched, setSearched] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(Boolean(initial));
  const [mapVersion, setMapVersion] = useState(0);
  const [tileVersion, setTileVersion] = useState(0);
  const [tileStatus, setTileStatus] = useState<"loading" | "loaded" | "failed">(
    "loading",
  );
  const request = useRef<AbortController | null>(null);
  const tileTimeout = useRef<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => () => request.current?.abort(), []);
  const clearTileTimeout = useCallback(() => {
    if (tileTimeout.current !== null) {
      window.clearTimeout(tileTimeout.current);
      tileTimeout.current = null;
    }
  }, []);
  const startTileTimeout = useCallback(() => {
    clearTileTimeout();
    tileTimeout.current = window.setTimeout(() => {
      tileTimeout.current = null;
      setTileStatus((current) => (current === "loading" ? "failed" : current));
    }, 10000);
  }, [clearTileTimeout]);
  useEffect(() => {
    startTileTimeout();
    return clearTileTimeout;
  }, [mapVersion, tileVersion, startTileTimeout, clearTileTimeout]);
  function select(next: ConfirmedPoint, recenter = false) {
    setPoint(next);
    setCoords({
      latitude: String(next.latitude),
      longitude: String(next.longitude),
    });
    setConfirmed(false);
    onDirty?.();
    if (recenter) {
      setTileStatus("loading");
      setMapVersion((value) => value + 1);
    }
  }
  async function search() {
    if (query.trim().length < 3) {
      setError("Enter at least three characters to search.");
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setSearching(true);
    setError("");
    try {
      const results = await searchLocations(token, query, controller.signal);
      if (!controller.signal.aborted) {
        setCandidates(results);
        setSearched(true);
      }
    } catch (error) {
      if (!controller.signal.aborted)
        setError(
          error instanceof Error
            ? error.message
            : "Address search failed. Try again.",
        );
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }
  function coordinates(axis: "latitude" | "longitude", value: string) {
    const next = { ...coords, [axis]: value };
    setCoords(next);
    setConfirmed(false);
    onDirty?.();
    const lat = Number(next.latitude),
      lon = Number(next.longitude);
    if (
      next.latitude.trim() &&
      next.longitude.trim() &&
      Number.isFinite(lat) &&
      Number.isFinite(lon) &&
      Math.abs(lat) <= 90 &&
      Math.abs(lon) <= 180
    )
      setPoint({
        latitude: lat,
        longitude: lon,
        label: "Manually selected point",
        source: "manual",
        provider_ref: null,
      });
    else setPoint(null);
  }
  return (
    <fieldset className="location-picker" disabled={confirming}>
      <div className="location-search">
        <FormField
          label="Search Philippine address"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void search();
            }
          }}
          placeholder="Street, barangay, city or landmark"
        />
        <Button onClick={() => void search()} disabled={searching}>
          <Search size={16} aria-hidden="true" />
          {searching ? "Searching…" : "Find address"}
        </Button>
      </div>
      {error && <InlineAlert>{error}</InlineAlert>}
      {candidates.length > 0 && (
        <ul className="location-results" aria-label="Address suggestions">
          {candidates.map((candidate) => (
            <li key={candidate.provider_ref ?? candidate.label}>
              <Button
                onClick={() =>
                  select({ ...candidate, source: "nominatim" }, true)
                }
              >
                {candidate.label}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {searched && !candidates.length && (
        <InlineAlert variant="info">
          No address matched. Refine the search or select a verified point on
          the map.
        </InlineAlert>
      )}
      <p className="form-hint">
        Select a result, click the map, or drag the pin. Confirm the exact point
        before saving.
      </p>
      <div className="location-picker-map">
        <MapContainer
          key={mapVersion}
          center={point ? [point.latitude, point.longitude] : [12.5, 122]}
          zoom={point ? 16 : 6}
          zoomControl={false}
          scrollWheelZoom
        >
          <MapSizeInvalidator />
          <MapZoomControls />
          <TileLayer
            key={tileVersion}
            url={
              import.meta.env.VITE_MAP_TILE_URL ||
              "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            }
            attribution={
              import.meta.env.VITE_MAP_TILE_ATTRIBUTION ||
              '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }
            eventHandlers={{
              loading: () => {
                setTileStatus("loading");
                startTileTimeout();
              },
              load: () => {
                clearTileTimeout();
                setTileStatus((current) =>
                  current === "failed" ? current : "loaded",
                );
              },
              tileerror: () => {
                clearTileTimeout();
                setTileStatus("failed");
              },
            }}
          />
          <PointEditor
            point={point}
            onChange={(next) =>
              select({
                ...next,
                label: "Manually selected point",
                source: "manual",
                provider_ref: null,
              })
            }
          />
        </MapContainer>
      </div>
      {tileStatus === "failed" && (
        <InlineAlert
          variant="warning"
          onRetry={() => {
            setTileStatus("loading");
            setTileVersion((version) => version + 1);
          }}
        >
          Map imagery did not load. The selected point and coordinates are still
          available. Check your connection or retry the map tiles.
        </InlineAlert>
      )}
      <div className="form-grid">
        <FormField
          label="Latitude"
          type="number"
          step="any"
          min={-90}
          max={90}
          value={coords.latitude}
          onChange={(event) => coordinates("latitude", event.target.value)}
        />
        <FormField
          label="Longitude"
          type="number"
          step="any"
          min={-180}
          max={180}
          value={coords.longitude}
          onChange={(event) => coordinates("longitude", event.target.value)}
        />
      </div>
      {point?.label && <p className="selected-location">{point.label}</p>}
      <div className="location-confirm">
        <Button
          variant="primary"
          disabled={!point || confirmed || confirming}
          onClick={() => {
            if (point) {
              setConfirming(true);
              setError("");
              Promise.resolve(onConfirm(point))
                .then(() => setConfirmed(true))
                .catch((error: unknown) =>
                  setError(
                    error instanceof Error
                      ? error.message
                      : "Could not confirm the selected point. Try again.",
                  ),
                )
                .finally(() => setConfirming(false));
            }
          }}
        >
          {confirming
            ? "Confirming…"
            : confirmed
              ? "Point confirmed"
              : "Confirm selected point"}
        </Button>
        <span className="form-hint">
          {confirmed
            ? "Ready to save. This is a configured location."
            : "The point has not been confirmed."}
        </span>
      </div>
    </fieldset>
  );
}
