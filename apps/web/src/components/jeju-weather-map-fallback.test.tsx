import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { JejuWeatherMap } from "@/components/jeju-weather-map";

const state = vi.hoisted(() => ({
  handlers: new Map<string, ((event: unknown) => void)[]>(),
  options: null as { style: { sources: { osm: { tiles: string[] } } } } | null,
}));
vi.mock("@/lib/map-location", () => ({ requestJejuLocation: async () => null }));
vi.mock("maplibre-gl", () => ({
  default: {
    Map: class {
      container: HTMLElement;
      constructor(options: {
        container: HTMLElement;
        style: { sources: { osm: { tiles: string[] } } };
      }) {
        state.options = options;
        this.container = options.container;
      }
      on(name: string, callback: (event: unknown) => void) {
        state.handlers.set(name, [...(state.handlers.get(name) ?? []), callback]);
      }
      off(name: string, callback: (event: unknown) => void) {
        state.handlers.set(
          name,
          (state.handlers.get(name) ?? []).filter((item) => item !== callback)
        );
      }
      getContainer() {
        return this.container;
      }
      addControl() {}
      resize() {}
      fitBounds() {}
      remove() {}
    },
    NavigationControl: class {},
    ScaleControl: class {},
  },
}));
beforeEach(() => {
  state.handlers.clear();
  state.options = null;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    }
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the existing text fallback when an OSM tile fails asynchronously", async () => {
  render(<JejuWeatherMap locations={[]} onSelect={vi.fn()} />);
  expect(screen.queryByRole("alert")).toBeNull();
  act(() => {
    for (const callback of state.handlers.get("error") ?? [])
      callback({ sourceId: "osm", error: new Error("tile blocked") });
  });
  expect((await screen.findByRole("alert")).textContent).toContain(
    "아래에서 지역별 날씨를 확인하세요."
  );
  expect(state.options?.style.sources.osm.tiles).toEqual([
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  ]);
});
it("removes its asynchronous error handler when the map is unmounted", () => {
  const view = render(<JejuWeatherMap locations={[]} onSelect={vi.fn()} />);
  expect(state.handlers.get("error")?.length).toBe(1);
  view.unmount();
  expect(state.handlers.get("error")?.length).toBe(0);
});
