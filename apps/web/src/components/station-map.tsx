import { useAtomValue } from "jotai";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { capabilitiesAtom } from "@/stores/chat.atoms";

export interface MapStation {
  station_name: string;
  station_code?: string | null;
  location?: string;
}

export function StationMap({ stations }: { stations: MapStation[] }) {
  const caps = useAtomValue(capabilitiesAtom);
  const mapRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const tilesEnabled = caps?.map.tiles ?? false;

  useEffect(() => {
    if (!tilesEnabled || !mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors (ODbL)",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [126.55, 33.38],
      zoom: 9,
    });
    return () => map.remove();
  }, [tilesEnabled]);

  const filtered = stations.filter((s) => {
    const q = query.trim();
    if (!q) return true;
    return (
      s.station_name.includes(q) ||
      s.location?.includes(q) ||
      (s.station_code && String(s.station_code).includes(q))
    );
  });

  if (!tilesEnabled) {
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted/40 p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-base font-bold text-foreground">
              제주 관측소 목록 ({filtered.length}/{stations.length}개 지점)
            </p>
            <p className="text-base text-muted-foreground">
              관측소 이름이나 읍면동으로 검색하세요.
            </p>
          </div>
          <div className="w-full sm:w-56">
            <Input
              placeholder="지점명·읍면동 검색 (예: 선흘, 조천)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="관측소 지점 검색"
            />
          </div>
        </div>
        <div className="grid max-h-64 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
          {filtered.map((s) => (
            <div
              key={`${s.station_code}-${s.station_name}`}
              className="flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2 text-base shadow-xs"
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-bold text-foreground">{s.station_name}</span>
                {s.location ? <span className="text-muted-foreground">{s.location}</span> : null}
              </div>
              {s.station_code ? (
                <Badge variant="secondary" className="tabular-nums">
                  #{s.station_code}
                </Badge>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div
      ref={mapRef}
      className="h-80 w-full overflow-hidden rounded-lg [&_.maplibregl-ctrl-group_button]:min-h-11 [&_.maplibregl-ctrl-group_button]:min-w-11 [&_.maplibregl-ctrl-group_button]:cursor-pointer [&_.maplibregl-ctrl-attrib]:text-base! [&_.maplibregl-ctrl-scale]:text-base!"
      role="img"
      aria-label="관측소 지도"
    />
  );
}
