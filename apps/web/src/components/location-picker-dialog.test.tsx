import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LocationPickerDialog } from "@/components/location-picker-dialog";
import { requestJejuLocation } from "@/lib/map-location";

const maps = vi.hoisted(() => ({ create: vi.fn(), flyTo: vi.fn() }));
vi.mock("@/lib/map-location", () => ({ requestJejuLocation: vi.fn() }));
vi.mock("maplibre-gl", () => ({
  default: {
    Map: class {
      constructor(options: unknown) {
        maps.create(options);
      }
      addControl() {}
      on() {}
      remove() {}
      flyTo(options: unknown) {
        maps.flyTo(options);
      }
    },
    NavigationControl: class {},
    Marker: class {
      setLngLat() {
        return this;
      }
      addTo() {
        return this;
      }
      on() {
        return this;
      }
      remove() {}
    },
  },
}));
beforeEach(() => {
  vi.mocked(requestJejuLocation).mockResolvedValue({ latitude: 33.45, longitude: 126.55 });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("centers a new map on a Jeju location without selecting or saving a pin", async () => {
  const onSelect = vi.fn();
  render(<LocationPickerDialog onSelect={onSelect} onClose={vi.fn()} />);
  await waitFor(() =>
    expect(maps.flyTo).toHaveBeenCalledWith({ center: [126.55, 33.45], zoom: 10.5 })
  );
  expect(onSelect).not.toHaveBeenCalled();
  expect((screen.getByRole("button", { name: "이 위치 선택" }) as HTMLButtonElement).disabled).toBe(
    true
  );
  fireEvent.click(screen.getByRole("button", { name: "내 위치" }));
  await waitFor(() => expect(requestJejuLocation).toHaveBeenCalledTimes(2));
});

it("prefers a saved pin and keeps manual coordinates in a collapsed section", async () => {
  render(
    <LocationPickerDialog
      value={{ address: "선흘", latitude: 33.4, longitude: 126.7 }}
      onSelect={vi.fn()}
      onClose={vi.fn()}
    />
  );
  await waitFor(() =>
    expect(maps.create).toHaveBeenCalledWith(
      expect.objectContaining({ center: [126.7, 33.4], zoom: 13 })
    )
  );
  expect(requestJejuLocation).not.toHaveBeenCalled();
  expect(screen.getByText("좌표 직접 입력").parentElement?.hasAttribute("open")).toBe(false);
});
