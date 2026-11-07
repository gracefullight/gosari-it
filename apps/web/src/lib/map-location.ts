export interface MapLocation {
  latitude: number;
  longitude: number;
}

export function isJejuLocation(point: MapLocation): boolean {
  return (
    Number.isFinite(point.latitude) &&
    Number.isFinite(point.longitude) &&
    point.latitude >= 33.12 &&
    point.latitude <= 33.63 &&
    point.longitude >= 126.08 &&
    point.longitude <= 126.99
  );
}

export function requestJejuLocation(): Promise<MapLocation | null> {
  if (!navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const point = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        resolve(isJejuLocation(point) ? point : null);
      },
      () => resolve(null),
      { enableHighAccuracy: false, maximumAge: 5 * 60_000, timeout: 7000 }
    );
  });
}
