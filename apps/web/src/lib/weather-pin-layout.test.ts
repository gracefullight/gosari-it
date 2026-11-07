import { describe, expect, it } from "vitest";
import { layoutWeatherPins } from "@/lib/weather-pin-layout";

const coordinates = [
  [126.5312, 33.4996],
  [126.329, 33.462],
  [126.267, 33.41],
  [126.184, 33.35],
  [126.252, 33.226],
  [126.351, 33.257],
  [126.5601, 33.2541],
  [126.72, 33.279],
  [126.831, 33.326],
  [126.91, 33.442],
  [126.852, 33.522],
  [126.634, 33.534],
];

describe("weather labels on the island map", () => {
  it.each([
    [248, 760],
    [318, 680],
    [440, 600],
    [1100, 600],
  ])("keeps every region visible without overlapping at %ipx × %ipx", (width, height) => {
    const anchors = coordinates.map(([longitude, latitude], index) => ({
      id: String(index),
      x: 45 + ((longitude - 126.08) / 0.9) * (width - 90),
      y: height / 2 - ((latitude - 33.37) / 0.5) * 180,
    }));
    const positions = layoutWeatherPins(anchors, { width, height, pinWidth: 76, pinHeight: 88 });
    expect(positions).toHaveLength(12);
    const find = (index: number) => positions.find(({ id }) => id === String(index))!;
    expect(find(3).x).toBeLessThan(find(9).x);
    expect(find(4).y).toBeGreaterThan(find(11).y);
    expect(find(0).y).toBeLessThan(find(6).y);
    for (const position of positions) {
      expect(position.x - 38).toBeGreaterThanOrEqual(8);
      expect(position.x + 38).toBeLessThanOrEqual(width - 8);
      expect(position.y - 44).toBeGreaterThanOrEqual(116);
      expect(position.y + 44).toBeLessThanOrEqual(height - 64);
      for (const other of positions) {
        if (position.id === other.id) continue;
        expect(Math.abs(position.x - other.x) >= 84 || Math.abs(position.y - other.y) >= 96).toBe(
          true
        );
      }
    }
  });

  it("preserves all labels when their projected locations coincide", () => {
    const positions = layoutWeatherPins(
      coordinates.map((_, index) => ({ id: String(index), x: 159, y: 310 })),
      { width: 318, height: 680, pinWidth: 76, pinHeight: 88 }
    );
    expect(new Set(positions.map(({ id }) => id)).size).toBe(12);
    expect(new Set(positions.map(({ x, y }) => `${x},${y}`)).size).toBe(12);
  });
});
