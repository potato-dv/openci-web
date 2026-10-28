import { expect, it } from "vitest";
import { leafletPositions } from "./mapTypes";
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
