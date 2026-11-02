import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MapAgent, MapInvestigation, MapRoute } from "./mapTypes";

const { markerMock, polylineMock, useMapEventsMock } = vi.hoisted(() => ({
  markerMock: vi.fn<(...args: unknown[]) => null>(() => null),
  polylineMock: vi.fn<(...args: unknown[]) => null>(() => null),
  useMapEventsMock: vi.fn<(...args: unknown[]) => undefined>(() => undefined),
}));

vi.mock("react-leaflet", () => ({
  MapContainer: () => null,
  Marker: markerMock,
  Polygon: () => null,
  Polyline: polylineMock,
  TileLayer: () => null,
  Tooltip: () => null,
  useMap: () => ({}),
  useMapEvents: useMapEventsMock,
}));

import {
  AgentMarker,
  BackgroundSelectionReset,
  InvestigationMarker,
  RouteLayer,
} from "./OperationsMap";
import { routesForSelection } from "./routeSelection";

const agent: MapAgent = {
  id: 7,
  name: "Avery Santos",
  start: { latitude: 14.6, longitude: 121, label: "Office" },
};

const investigation: MapInvestigation = {
  id: 11,
  reference_number: "INV-0011",
  address_display: "12 Example Street",
  latitude: 14.65,
  longitude: 121.05,
  priority: "high",
  status: "assigned",
  agent_id: 7,
  sequence: 1,
};

const route: MapRoute = {
  agent_id: 7,
  agent_name: "Avery Santos",
  geometry: {
    type: "LineString",
    coordinates: [
      [121, 14.6],
      [121.05, 14.65],
    ],
  },
};

describe("OperationsMap selection events", () => {
  beforeEach(() => {
    markerMock.mockClear();
    polylineMock.mockClear();
    useMapEventsMock.mockClear();
  });

  it("clears selection when the map background is clicked", () => {
    const onSelect = vi.fn();
    render(<BackgroundSelectionReset onSelect={onSelect} />);

    const handlers = useMapEventsMock.mock.calls[0][0] as {
      click: () => void;
    };
    handlers.click();

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("keeps marker clicks from bubbling into the map background handler", () => {
    const onSelect = vi.fn();
    render(
      <>
        <AgentMarker
          agent={agent}
          selected={false}
          index={0}
          onSelect={onSelect}
        />
        <InvestigationMarker
          item={investigation}
          selected={false}
          included
          color="#3659cc"
          onSelect={onSelect}
        />
      </>,
    );

    expect(markerMock).toHaveBeenCalledTimes(2);
    for (const [props] of markerMock.mock.calls) {
      expect(
        (props as unknown as { bubblingMouseEvents: boolean })
          .bubblingMouseEvents,
      ).toBe(false);
    }
  });

  it("keeps route line clicks focused on the route", () => {
    const onSelect = vi.fn();
    render(
      <RouteLayer
        route={route}
        style={{ color: "#3659cc" }}
        selected={false}
        onSelect={onSelect}
      />,
    );

    const [props] = polylineMock.mock.calls[0];
    const pathOptions = (
      props as unknown as {
        pathOptions: { bubblingMouseEvents: boolean };
      }
    ).pathOptions;
    expect(pathOptions.bubblingMouseEvents).toBe(false);
    (
      props as unknown as { eventHandlers: { click: () => void } }
    ).eventHandlers.click();
    expect(onSelect).toHaveBeenCalledWith({ type: "agent", id: 7 });
  });

  it("shows all routes without selection and only the selected agent route otherwise", () => {
    const secondRoute: MapRoute = {
      ...route,
      agent_id: 8,
      agent_name: "Jordan Lee",
    };
    const routes = [route, secondRoute];
    const unassignedInvestigation = {
      ...investigation,
      id: 12,
      agent_id: null,
    };

    expect(routesForSelection(routes, null, [investigation])).toEqual(routes);
    expect(
      routesForSelection(routes, { type: "agent", id: 7 }, [investigation]),
    ).toEqual([route]);
    expect(
      routesForSelection(
        routes,
        { type: "investigation", id: investigation.id },
        [investigation],
      ),
    ).toEqual([route]);
    expect(
      routesForSelection(routes, { type: "agent", id: 8 }, [investigation]),
    ).toEqual([secondRoute]);
    expect(
      routesForSelection(
        routes,
        { type: "investigation", id: unassignedInvestigation.id },
        [unassignedInvestigation],
      ),
    ).toEqual([]);
  });
});
