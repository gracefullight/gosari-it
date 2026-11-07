import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { isJejuLocation, requestJejuLocation } from "@/lib/map-location";

beforeEach(() => vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: vi.fn() } }));
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("accepts Jeju and keeps mainland or overseas positions out of the initial map view", () => {
  expect(isJejuLocation({ latitude: 33.4996, longitude: 126.5312 })).toBe(true);
  expect(isJejuLocation({ latitude: 37.5665, longitude: 126.978 })).toBe(false);
  expect(isJejuLocation({ latitude: -33.8688, longitude: 151.2093 })).toBe(false);
  expect(isJejuLocation({ latitude: Number.NaN, longitude: 126.5 })).toBe(false);
});
it("uses an accepted current position without generating a point outside Jeju", async () => {
  vi.spyOn(navigator.geolocation, "getCurrentPosition").mockImplementation((success) =>
    success({ coords: { latitude: 33.45, longitude: 126.6 } } as GeolocationPosition)
  );
  await expect(requestJejuLocation()).resolves.toEqual({ latitude: 33.45, longitude: 126.6 });
});
it("leaves the default view when current position is outside Jeju or permission is denied", async () => {
  const spy = vi
    .spyOn(navigator.geolocation, "getCurrentPosition")
    .mockImplementation((success) =>
      success({ coords: { latitude: 37.5, longitude: 127 } } as GeolocationPosition)
    );
  await expect(requestJejuLocation()).resolves.toBeNull();
  spy.mockImplementation((_success, failure) => failure?.({ code: 1 } as GeolocationPositionError));
  await expect(requestJejuLocation()).resolves.toBeNull();
});
