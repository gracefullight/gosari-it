import type { ResultEnvelope } from "@/lib/gosari.types";
import { hasDetailedResult } from "@/lib/result-display";

export interface StreetViewLink {
  url: string;
  locationName: string;
}
const VIEWPOINT = /^-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?$/;
const PARAMS = new Set(["api", "map_action", "viewpoint"]);

function googleStreetViewUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" ||
      url.hostname !== "www.google.com" ||
      url.port ||
      url.username ||
      url.password ||
      url.hash ||
      url.pathname !== "/maps/@"
    )
      return undefined;
    if (
      [...url.searchParams.keys()].some(
        (key) => !PARAMS.has(key) || url.searchParams.getAll(key).length !== 1
      ) ||
      url.searchParams.get("api") !== "1" ||
      url.searchParams.get("map_action") !== "pano"
    )
      return undefined;
    const viewpoint = url.searchParams.get("viewpoint") ?? "";
    if (!VIEWPOINT.test(viewpoint)) return undefined;
    const parts = viewpoint.split(",");
    const latitude = Number(parts[0]);
    const longitude = Number(parts[1]);
    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      Math.abs(latitude) > 90 ||
      Math.abs(longitude) > 180
    )
      return undefined;
    const canonical = new URL("https://www.google.com/maps/@");
    canonical.search = new URLSearchParams({
      api: "1",
      map_action: "pano",
      viewpoint: `${latitude},${longitude}`,
    }).toString();
    return canonical.toString();
  } catch {
    return undefined;
  }
}

export function getStreetViewLinks(
  envelopes: (ResultEnvelope | null | undefined)[]
): StreetViewLink[] {
  const found = new Map<string, StreetViewLink>();
  for (const envelope of envelopes) {
    const links = envelope?.result.street_view_links;
    if (!Array.isArray(links)) continue;
    for (const value of links) {
      if (!value || typeof value !== "object") continue;
      const row = value as Record<string, unknown>;
      const url = row.provider === "google" ? googleStreetViewUrl(row.url) : undefined;
      if (url && typeof row.location_name === "string" && row.location_name.trim())
        found.set(url, { url, locationName: row.location_name.trim() });
    }
  }
  return [...found.values()];
}

export function hasModalResult(envelope?: ResultEnvelope | null): envelope is ResultEnvelope {
  if (!envelope) return false;
  if (!("street_view_links" in envelope.result)) return hasDetailedResult(envelope);
  const {
    street_view_links: _links,
    location_id: _id,
    location_name: _name,
    latitude: _lat,
    longitude: _lon,
    ...result
  } = envelope.result;
  return hasDetailedResult({ ...envelope, result });
}
