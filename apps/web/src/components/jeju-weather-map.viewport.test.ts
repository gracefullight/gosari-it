import { describe, expect, it, vi } from "vitest";
import { resizeJejuViewport } from "@/components/jeju-weather-map";

function viewport(width = 1000, height = 600, zoom = 9.8) {
  const element = { getBoundingClientRect: vi.fn(() => ({ width, height }) as DOMRect) };
  const map = {
    getContainer: () => element,
    resize: vi.fn(),
    cameraForBounds: vi.fn(() => ({ zoom })),
    setMinZoom: vi.fn(),
    fitBounds: vi.fn(),
  };
  return { map, element };
}

describe("Jeju whole-island zoom floor", () => {
  it("uses the padded home fit zoom as the zoom-out limit, without adding a zoom-in restriction", () => {
    const { map } = viewport();
    resizeJejuViewport(map, false);
    expect(map.resize).toHaveBeenCalledOnce();
    expect(map.cameraForBounds).toHaveBeenCalledWith(
      [
        [126.08, 33.12],
        [126.98, 33.62],
      ],
      { padding: { top: 100, bottom: 90, left: 16, right: 16 }, maxZoom: 16 }
    );
    expect(map.setMinZoom).toHaveBeenCalledExactlyOnceWith(9.8);
    expect(map.fitBounds).toHaveBeenCalledWith(
      [
        [126.08, 33.12],
        [126.98, 33.62],
      ],
      { padding: { top: 100, bottom: 90, left: 16, right: 16 }, duration: 0 }
    );
    expect(Object.keys(map)).not.toContain("setMaxZoom");
  });

  it("recomputes the lower bound for a narrow viewport while preserving a user's camera", () => {
    const { map, element } = viewport();
    resizeJejuViewport(map, true);
    element.getBoundingClientRect.mockReturnValue({ width: 320, height: 760 } as DOMRect);
    map.cameraForBounds.mockReturnValue({ zoom: 8.3 });
    resizeJejuViewport(map, true);
    expect(map.setMinZoom.mock.calls.map(([zoom]) => zoom)).toEqual([9.8, 8.3]);
    expect(map.fitBounds).not.toHaveBeenCalled();
  });

  it("does not measure or refit a collapsed map at zero size, and resumes when reopened", () => {
    const { map, element } = viewport(0, 0);
    resizeJejuViewport(map, false);
    expect(map.resize).not.toHaveBeenCalled();
    expect(map.cameraForBounds).not.toHaveBeenCalled();
    expect(map.setMinZoom).not.toHaveBeenCalled();
    element.getBoundingClientRect.mockReturnValue({ width: 768, height: 600 } as DOMRect);
    resizeJejuViewport(map, false);
    expect(map.resize).toHaveBeenCalledOnce();
    expect(map.setMinZoom).toHaveBeenCalledExactlyOnceWith(9.8);
  });

  it("does not install a non-finite zoom constraint", () => {
    const { map } = viewport(1000, 600, Number.NaN);
    resizeJejuViewport(map, true);
    expect(map.setMinZoom).not.toHaveBeenCalled();
    expect(map.fitBounds).not.toHaveBeenCalled();
  });
});
