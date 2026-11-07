import { expect, it } from "vitest";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { getStreetViewLinks, hasModalResult } from "@/lib/street-view";

const url = "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=33.3524%2C126.533";
const link = { provider: "google", label: "Google 스트리트뷰", url, location_name: "한라산남벽" };
const envelope = (result: Record<string, unknown>) => ({ result }) as ResultEnvelope;

it("deduplicates the official coordinate action and keeps link-only results outside the detail modal", () => {
  const result = envelope({
    street_view_links: [link],
    latitude: 33.3524,
    longitude: 126.533,
    location_name: "한라산남벽",
  });
  expect(getStreetViewLinks([result, result])).toEqual([{ url, locationName: "한라산남벽" }]);
  expect(hasModalResult(result)).toBe(false);
  expect(hasModalResult(envelope({ ...result.result, stations: [{ rain_mm: 0 }] }))).toBe(true);
});

it.each([
  "javascript:alert(1)",
  "data:text/html,alert(1)",
  url.replace("www.google.com", "www.google.com.evil.invalid"),
  url.replace("https:", "http:"),
  url.replace("www.google.com", "user@www.google.com"),
  `${url}&redirect=https://evil.invalid`,
  `${url}&api=2`,
  url.replace("33.3524%2C126.533", "NaN%2C126.533"),
  url.replace("33.3524%2C126.533", "91%2C126.533"),
  url.replace("map_action=pano", "map_action=map"),
])("rejects unsafe or non-canonical street-view URLs: %s", (unsafe) => {
  expect(getStreetViewLinks([envelope({ street_view_links: [{ ...link, url: unsafe }] })])).toEqual(
    []
  );
});
