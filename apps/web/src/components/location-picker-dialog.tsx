import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { DaumAddressSearch } from "@/components/daum-address-search";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { geocodeAddress } from "@/lib/address-geocoding";
import { requestJejuLocation } from "@/lib/map-location";

export interface SelectedLocation {
  address: string;
  latitude: number | null;
  longitude: number | null;
}
interface LocationPickerDialogProps {
  value?: SelectedLocation | null;
  onSelect: (location: SelectedLocation) => void;
  onClose: () => void;
}

export function LocationPickerDialog({ value, onSelect, onClose }: LocationPickerDialogProps) {
  const [location, setLocation] = useState<SelectedLocation>(
    () => value ?? { address: "", latitude: null, longitude: null }
  );
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const [search, setSearch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [locating, setLocating] = useState(false);
  const locationRequest = useRef(0);
  const mapTouched = useRef(false);
  const map = useRef<maplibregl.Map | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  const geocodeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => geocodeRequest.current?.abort(), []);
  useEffect(() => {
    if (!container) return;
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({
        container,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: "© OpenStreetMap contributors",
            },
          },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        },
        center: [value?.longitude ?? 126.55, value?.latitude ?? 33.38],
        zoom: value?.latitude != null ? 13 : 9.35,
      });
    } catch {
      setError("지도를 불러오지 못했습니다. 주소를 검색해 저장할 수 있습니다.");
      return;
    }
    map.current = instance;
    mapTouched.current = false;
    if (value?.latitude == null || value?.longitude == null) {
      const request = ++locationRequest.current;
      void requestJejuLocation()
        .then((point) => {
          if (
            point &&
            request === locationRequest.current &&
            map.current === instance &&
            !mapTouched.current
          ) {
            instance.flyTo({ center: [point.longitude, point.latitude], zoom: 10.5 });
          }
        })
        .catch(() => undefined);
    }
    instance.on("dragstart", () => {
      mapTouched.current = true;
    });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    instance.on("click", (event) => {
      mapTouched.current = true;
      locationRequest.current += 1;
      geocodeRequest.current?.abort();
      setSearching(false);
      setLocation((prev) => ({ ...prev, latitude: event.lngLat.lat, longitude: event.lngLat.lng }));
    });
    return () => {
      locationRequest.current += 1;
      marker.current?.remove();
      marker.current = null;
      instance.remove();
      map.current = null;
    };
  }, [container, value?.latitude, value?.longitude]);
  useEffect(() => {
    if (!container || !map.current || location.latitude == null || location.longitude == null)
      return;
    marker.current?.remove();
    marker.current = new maplibregl.Marker({ draggable: true })
      .setLngLat([location.longitude, location.latitude])
      .addTo(map.current);
    marker.current.on("dragend", () => {
      const point = marker.current?.getLngLat();
      if (point) setLocation((prev) => ({ ...prev, latitude: point.lat, longitude: point.lng }));
    });
  }, [location.latitude, location.longitude, container]);

  async function locateMe() {
    const instance = map.current;
    if (!instance) return;
    const request = ++locationRequest.current;
    setLocating(true);
    try {
      const point = await requestJejuLocation();
      if (point && request === locationRequest.current && map.current === instance) {
        instance.flyTo({ center: [point.longitude, point.latitude], zoom: 10.5 });
      }
    } catch {
      /* Keep the existing map view when location is unavailable. */
    } finally {
      if (map.current === instance) setLocating(false);
    }
  }

  async function selectAddress(address: string) {
    mapTouched.current = true;
    locationRequest.current += 1;
    geocodeRequest.current?.abort();
    const controller = new AbortController();
    geocodeRequest.current = controller;
    setLocation({ address, latitude: null, longitude: null });
    marker.current?.remove();
    setSearch(false);
    setSearching(true);
    setError(null);
    try {
      const { latitude, longitude } = await geocodeAddress(address, controller.signal);
      if (controller.signal.aborted) return;
      setLocation({ address, latitude, longitude });
      if (latitude != null && longitude != null)
        map.current?.flyTo({ center: [longitude, latitude], zoom: 14 });
    } catch {
      if (!controller.signal.aborted) setError("주소를 선택했습니다. 지도에서 위치를 찍어 주세요.");
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>위치 선택</DialogTitle>
          <DialogDescription>주소를 검색하거나 지도에 핀을 찍으세요.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
          <Input
            value={location.address}
            readOnly
            placeholder="선택한 주소"
            aria-label="선택한 주소"
          />
          <Button variant="outline" disabled={locating} onClick={() => void locateMe()}>
            {locating ? "위치 확인 중…" : "내 위치"}
          </Button>
          <Button variant="outline" onClick={() => setSearch((prev) => !prev)}>
            주소 검색
          </Button>
        </div>
        {search ? <DaumAddressSearch onSelect={(address) => void selectAddress(address)} /> : null}
        <section
          ref={setContainer}
          className="h-80 w-full overflow-hidden rounded-xl border border-border sm:h-96"
          aria-label="위치 선택 지도"
        />
        <details className="rounded-lg border border-border px-3 py-2">
          <summary className="cursor-pointer text-base text-muted-foreground">
            좌표 직접 입력
          </summary>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="location-latitude">위도</Label>
              <Input
                id="location-latitude"
                type="number"
                step="any"
                value={location.latitude ?? ""}
                onChange={(e) =>
                  setLocation((prev) => ({
                    ...prev,
                    latitude: e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
              />
            </div>
            <div>
              <Label htmlFor="location-longitude">경도</Label>
              <Input
                id="location-longitude"
                type="number"
                step="any"
                value={location.longitude ?? ""}
                onChange={(e) =>
                  setLocation((prev) => ({
                    ...prev,
                    longitude: e.target.value === "" ? null : Number(e.target.value),
                  }))
                }
              />
            </div>
          </div>
        </details>
        {searching ? (
          <p role="status" className="text-base text-muted-foreground">
            주소 위치 찾는 중…
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-base text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button
            disabled={
              searching ||
              (!location.address && (location.latitude == null || location.longitude == null)) ||
              (location.latitude == null) !== (location.longitude == null) ||
              (location.latitude != null &&
                (Math.abs(location.latitude) > 90 || !Number.isFinite(location.latitude))) ||
              (location.longitude != null &&
                (Math.abs(location.longitude) > 180 || !Number.isFinite(location.longitude)))
            }
            onClick={() => onSelect(location)}
          >
            이 위치 선택
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
