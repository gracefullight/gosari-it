import {
  CloudIcon,
  CloudRainIcon,
  CloudSnowIcon,
  CloudSunIcon,
  MapPinIcon,
  NavigationArrowIcon,
  QuestionMarkIcon,
  SunIcon,
} from "@phosphor-icons/react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { requestJejuLocation } from "@/lib/map-location";
import { layoutWeatherPins } from "@/lib/weather-pin-layout";

const JEJU_BOUNDS: maplibregl.LngLatBoundsLike = [
  [126.08, 33.12],
  [126.98, 33.62],
];

const JEJU_FIT_PADDING = { top: 100, bottom: 90, left: 16, right: 16 };

interface JejuMapViewport {
  getContainer: () => Pick<HTMLElement, "getBoundingClientRect">;
  resize: () => unknown;
  cameraForBounds: (
    bounds: maplibregl.LngLatBoundsLike,
    options: maplibregl.CameraForBoundsOptions
  ) => { zoom?: number } | undefined;
  setMinZoom: (zoom: number) => unknown;
  fitBounds: (bounds: maplibregl.LngLatBoundsLike, options: maplibregl.FitBoundsOptions) => unknown;
}

/** Recompute the whole-island zoom floor for the actual visible viewport. */
export function resizeJejuViewport(map: JejuMapViewport, userMoved: boolean) {
  const { width, height } = map.getContainer().getBoundingClientRect();
  if (
    width <= JEJU_FIT_PADDING.left + JEJU_FIT_PADDING.right ||
    height <= JEJU_FIT_PADDING.top + JEJU_FIT_PADDING.bottom
  )
    return;
  map.resize();
  const camera = map.cameraForBounds(JEJU_BOUNDS, { padding: JEJU_FIT_PADDING, maxZoom: 16 });
  if (camera?.zoom != null && Number.isFinite(camera.zoom))
    map.setMinZoom(Math.max(0, Math.min(16, camera.zoom)));
  if (!userMoved) map.fitBounds(JEJU_BOUNDS, { padding: JEJU_FIT_PADDING, duration: 0 });
}

export interface WeatherLocation {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  temperature_c: number | null;
  temperature_min_c?: number | null;
  temperature_max_c?: number | null;
  precipitation_probability: number | null;
  condition: "clear" | "cloudy" | "partly_cloudy" | "rain" | "snow" | "unknown";
  forecast_at: string | null;
}

export const WEATHER_LABELS = {
  clear: "맑음",
  cloudy: "흐림",
  partly_cloudy: "구름 조금",
  rain: "비",
  snow: "눈",
  unknown: "자료 없음",
};
export function WeatherIcon({
  condition,
  className = "size-7",
}: {
  condition: WeatherLocation["condition"];
  className?: string;
}) {
  const Icon =
    {
      clear: SunIcon,
      cloudy: CloudIcon,
      partly_cloudy: CloudSunIcon,
      rain: CloudRainIcon,
      snow: CloudSnowIcon,
      unknown: QuestionMarkIcon,
    }[condition] ?? QuestionMarkIcon;
  return (
    <Icon
      weight="duotone"
      className={`${className} ${condition === "clear" ? "text-weather-sun" : "text-weather-rain"}`}
      aria-hidden="true"
    />
  );
}

function WeatherPin({
  location,
  onSelect,
}: {
  location: WeatherLocation;
  onSelect: (location: WeatherLocation) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(location)}
      data-weather-pin
      className="flex h-[88px] w-[76px] cursor-pointer flex-col items-center justify-center gap-0 rounded-xl border border-border bg-card px-1 py-1.5 text-foreground shadow-[0_3px_12px_rgb(26_31_27_/_10%)] hover:border-primary hover:outline-2 hover:outline-ring hover:outline-offset-2 focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      aria-label={`${location.name} ${WEATHER_LABELS[location.condition]} ${location.temperature_c ?? "미확인"}도, 강수확률 ${location.precipitation_probability == null ? "미확인" : `${location.precipitation_probability}%`}`}
    >
      <span className="text-base leading-6 font-semibold text-muted-foreground">
        {location.name}
      </span>
      <span className="flex items-center justify-center gap-1">
        <WeatherIcon condition={location.condition} className="size-6" />
        <span className="text-lg leading-6 font-bold tabular-nums">
          {location.temperature_c == null ? "—" : `${Math.round(location.temperature_c)}°`}
        </span>
      </span>
      <span className="text-base leading-6 font-medium tabular-nums text-weather-rain">
        {location.precipitation_probability == null
          ? "—"
          : `${location.precipitation_probability}%`}
      </span>
    </button>
  );
}

interface JejuWeatherMapProps {
  locations: WeatherLocation[];
  onSelect: (location: WeatherLocation) => void;
  focus?: { latitude: number; longitude: number } | null;
  regionPins?: { id: string; name: string; latitude: number; longitude: number }[];
  onRegionSelect?: (id: string) => void;
  onMapSelect?: (point: { latitude: number; longitude: number }) => void;
  selectedPoint?: { latitude: number; longitude: number } | null;
}

export function JejuWeatherMap({
  locations,
  onSelect,
  focus,
  regionPins,
  onRegionSelect,
  onMapSelect,
  selectedPoint,
}: JejuWeatherMapProps) {
  const container = useRef<HTMLElement>(null);
  const instance = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  const userMoved = useRef(false);

  useEffect(() => {
    if (!ready || !instance.current || !onMapSelect) return;
    const map = instance.current;
    const select = (event: maplibregl.MapMouseEvent) => {
      const target = event.originalEvent.target;
      if (target instanceof Element && target.closest("[data-weather-pin], [data-interest-pin]"))
        return;
      userMoved.current = true;
      onMapSelect({ latitude: event.lngLat.lat, longitude: event.lngLat.lng });
    };
    map.on("click", select);
    map.getCanvas().style.cursor = "crosshair";
    return () => {
      map.off("click", select);
    };
  }, [ready, onMapSelect]);

  useEffect(() => {
    if (!ready || !instance.current) return;
    const markers = (regionPins ?? []).map((point) => {
      const element = document.createElement("div");
      element.setAttribute("role", "group");
      element.tabIndex = -1;
      const root = createRoot(element);
      root.render(
        <button
          type="button"
          data-interest-pin
          className="flex cursor-pointer flex-col items-center gap-1"
          aria-label={`${point.name} 관심 지역 보기`}
          onClick={(event) => {
            event.stopPropagation();
            onRegionSelect?.(point.id);
          }}
        >
          <span className="rounded-lg bg-card px-2.5 py-1.5 text-base font-semibold text-primary shadow-sm">
            {point.name}
          </span>
          <MapPinIcon
            weight="fill"
            className="size-10 text-primary drop-shadow-md"
            aria-hidden="true"
          />
        </button>
      );
      const marker = new maplibregl.Marker({ element, anchor: "bottom" })
        .setLngLat([point.longitude, point.latitude])
        .addTo(instance.current!);
      return { root, marker };
    });
    return () => {
      for (const { root, marker } of markers) {
        marker.remove();
        queueMicrotask(() => root.unmount());
      }
    };
  }, [ready, regionPins, onRegionSelect]);

  useEffect(() => {
    if (!ready || !instance.current || !selectedPoint) return;
    const marker = new maplibregl.Marker()
      .setLngLat([selectedPoint.longitude, selectedPoint.latitude])
      .addTo(instance.current);
    return () => {
      marker.remove();
    };
  }, [ready, selectedPoint]);

  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>',
            },
          },
          layers: [
            {
              id: "basemap",
              type: "raster",
              source: "osm",
              paint: { "raster-saturation": -0.25, "raster-opacity": 1 },
            },
          ],
        },
        bounds: JEJU_BOUNDS,
        fitBoundsOptions: { padding: JEJU_FIT_PADDING },
        minZoom: 0,
        maxZoom: 16,
        attributionControl: { compact: true },
      });
    } catch {
      setError(true);
      return;
    }
    instance.current = map;
    const onError = () => setError(true);
    map.on("error", onError);
    map.on("dragstart", () => {
      userMoved.current = true;
    });
    map.on("zoomstart", (event) => {
      if (event.originalEvent) userMoved.current = true;
    });
    void requestJejuLocation().then((point) => {
      if (point && instance.current === map && !userMoved.current) {
        userMoved.current = true;
        map.flyTo({ center: [point.longitude, point.latitude], zoom: 10.5, essential: false });
      }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");
    setReady(true);
    resizeJejuViewport(map, userMoved.current);
    const resize = new ResizeObserver(() => resizeJejuViewport(map, userMoved.current));
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      instance.current = null;
      map.off("error", onError);
      map.remove();
    };
  }, []);

  useEffect(() => {
    if (!ready || !instance.current) return;
    const map = instance.current;
    const connections = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    connections.setAttribute("class", "pointer-events-none absolute inset-0 z-[1] h-full w-full");
    connections.setAttribute("aria-hidden", "true");
    map.getContainer().append(connections);
    const pins = locations.map((location) => {
      const element = document.createElement("div");
      element.className = "z-[2]";
      element.setAttribute("role", "group");
      element.setAttribute("aria-label", location.name);
      element.tabIndex = -1;
      const root = createRoot(element);
      root.render(<WeatherPin location={location} onSelect={onSelect} />);
      const marker = new maplibregl.Marker({ element, anchor: "center" })
        .setLngLat([location.longitude, location.latitude])
        .addTo(map);
      return { root, marker, location, element };
    });
    let frame = 0;
    const positionPins = () => {
      const { width, height } = map.getContainer().getBoundingClientRect();
      const anchors = pins.flatMap(({ location, element }) => {
        const point = map.project([location.longitude, location.latitude]);
        const visible = point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height;
        element.hidden = !visible;
        return visible ? [{ id: location.id, x: point.x, y: point.y }] : [];
      });
      const positions = layoutWeatherPins(anchors, { width, height, pinWidth: 76, pinHeight: 88 });
      connections.replaceChildren();
      for (const { location, marker, element } of pins) {
        const anchor = anchors.find((point) => point.id === location.id);
        const position = positions.find((point) => point.id === location.id);
        if (!anchor || !position) {
          element.hidden = true;
          continue;
        }
        marker.setOffset([position.x - anchor.x, position.y - anchor.y]);
        const line = document.createElementNS(connections.namespaceURI, "line");
        line.setAttribute("class", "stroke-muted-foreground stroke-[1.5] opacity-65");
        line.setAttribute("x1", String(anchor.x));
        line.setAttribute("y1", String(anchor.y));
        line.setAttribute("x2", String(position.x));
        line.setAttribute("y2", String(position.y));
        const dot = document.createElementNS(connections.namespaceURI, "circle");
        dot.setAttribute("class", "fill-primary");
        dot.setAttribute("cx", String(anchor.x));
        dot.setAttribute("cy", String(anchor.y));
        dot.setAttribute("r", "3");
        connections.append(line, dot);
      }
    };
    const schedulePosition = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(positionPins);
    };
    map.on("move", schedulePosition);
    map.on("resize", schedulePosition);
    schedulePosition();
    return () => {
      cancelAnimationFrame(frame);
      map.off("move", schedulePosition);
      map.off("resize", schedulePosition);
      connections.remove();
      for (const { root, marker } of pins) {
        marker.remove();
        queueMicrotask(() => root.unmount());
      }
    };
  }, [locations, onSelect, ready]);

  useEffect(() => {
    if (focus) userMoved.current = true;
    if (focus && instance.current)
      instance.current.flyTo({
        center: [focus.longitude, focus.latitude],
        zoom: 11,
        essential: false,
      });
  }, [focus]);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-weather-sea [&_.maplibregl-ctrl-group_button]:min-h-11 [&_.maplibregl-ctrl-group_button]:min-w-11 [&_.maplibregl-ctrl-group_button]:cursor-pointer [&_.maplibregl-ctrl-attrib]:text-base! [&_.maplibregl-ctrl-scale]:text-base!">
      <section
        ref={container}
        className="h-[760px] w-full min-[360px]:h-[680px] min-[768px]:h-[600px]"
        aria-label="제주도 지역별 날씨 지도"
      />
      <div className="pointer-events-none absolute top-3 left-3 max-w-[calc(100%-9.5rem)] rounded-lg bg-card/95 px-3 py-2 text-base shadow-sm">
        <span className="font-semibold">제주도</span>
        <span className="ml-2 text-muted-foreground">
          {onMapSelect ? "지도를 눌러 핀 추가" : "기온 · 강수확률"}
        </span>
      </div>
      {error ? (
        <div
          role="alert"
          className="absolute inset-0 flex items-center justify-center bg-muted p-6 text-center text-base"
        >
          지도를 불러오지 못했습니다. 아래에서 지역별 날씨를 확인하세요.
        </div>
      ) : null}
      <button
        type="button"
        aria-label="내 위치로 이동"
        title="내 위치"
        onClick={() =>
          void requestJejuLocation().then((point) => {
            if (point && instance.current) userMoved.current = true;
            if (point && instance.current)
              instance.current.flyTo({
                center: [point.longitude, point.latitude],
                zoom: 10.5,
                essential: false,
              });
          })
        }
        className="absolute top-3 right-[4.25rem] flex size-11 cursor-pointer items-center justify-center rounded-xl border border-border bg-card text-primary shadow-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
      >
        <NavigationArrowIcon weight="fill" className="size-5" aria-hidden="true" />
      </button>
    </div>
  );
}
