import { expect, it } from "vitest";
import { leafletPositions, routeColor, routeLineStyles } from "./mapTypes";
it("converts GeoJSON longitude/latitude order exactly once", () => {
  expect(
    leafletPositions({
      type: "LineString",
      coordinates: [
        [121.0494, 14.6507],
        [121.1, 14.7],
      ],
    }),
  ).toEqual([
    [14.6507, 121.0494],
    [14.7, 121.1],
  ]);
});

it("uses the same solid Google blue for every route regardless of ordering", () => {
  const route = (agent_id: number) => ({
    agent_id,
    agent_name: `Agent ${agent_id}`,
    geometry: null,
  });
  const firstOrder = routeLineStyles([route(7), route(42)]);
  const reverseOrder = routeLineStyles([route(42), route(7)]);

  expect(routeColor(7)).toBe("#4285f4");
  expect(routeColor(42)).toBe("#4285f4");
  expect(firstOrder.get(7)).toEqual({ color: "#4285f4" });
  expect(firstOrder.get(42)).toEqual(reverseOrder.get(42));
});
