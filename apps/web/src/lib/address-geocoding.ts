import type { SelectedLocation } from "@/components/location-picker-dialog";

export async function geocodeAddress(
  address: string,
  signal?: AbortSignal
): Promise<SelectedLocation> {
  const params = new URLSearchParams({
    q: address,
    format: "json",
    limit: "1",
    countrycodes: "kr",
  });
  const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, { signal });
  if (!response.ok) throw new Error("주소 위치를 찾지 못했습니다.");
  const rows = (await response.json()) as { lat: string; lon: string }[];
  const latitude = Number(rows[0]?.lat);
  const longitude = Number(rows[0]?.lon);
  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    Math.abs(latitude) > 90 ||
    Math.abs(longitude) > 180
  )
    throw new Error("주소 위치를 찾지 못했습니다.");
  return { address, latitude, longitude };
}
