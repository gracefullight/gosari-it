import {
  ArrowClockwiseIcon,
  CalendarBlankIcon,
  CaretLeftIcon,
  CaretRightIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { DateSelectionCalendar } from "@/components/date-selection-calendar";
import { DaumAddressSearch } from "@/components/daum-address-search";
import { InterestRegionPanel, type RegionPoint } from "@/components/interest-region-panel";
import {
  JejuWeatherMap,
  WEATHER_LABELS,
  WeatherIcon,
  type WeatherLocation,
} from "@/components/jeju-weather-map";
import { OutingPlanForm } from "@/components/outing-plan-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { geocodeAddress } from "@/lib/address-geocoding";
import {
  apiV1WeatherGetWeather,
  getApiV1WeatherGetWeatherQueryKey,
} from "@/lib/api/generated/endpoints";
import type { WeatherResponse as ApiWeatherResponse } from "@/lib/api/generated/model/weatherResponse";
import { api } from "@/lib/gosari.api";
import type { Preview, PrivateRegion } from "@/lib/gosari.types";
import { appPathAtom, navigateToPathAtom, revisionCounterAtom } from "@/stores/chat.atoms";

export type WeatherResponse = Omit<ApiWeatherResponse, "locations"> & {
  locations: WeatherLocation[];
  evidence_ids?: string[];
};

export function koreaToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function shiftDate(value: string, delta: number) {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

async function loadWeather(date: string, signal: AbortSignal): Promise<WeatherResponse> {
  const response = await apiV1WeatherGetWeather({ date }, { signal });
  if (response.status !== 200) throw new Error("날씨를 불러오지 못했습니다.");
  return {
    ...response.data,
    locations: response.data.locations.map((location) => ({
      ...location,
      temperature_c: location.temperature_c ?? null,
      precipitation_probability: location.precipitation_probability ?? null,
      condition: location.condition ?? "unknown",
    })),
  };
}

interface WeatherMapPageProps {
  mode: "outing" | "regions";
  onPreview: (preview: Preview) => void;
}

export function WeatherMapPage({ mode, onPreview }: WeatherMapPageProps) {
  const path = useAtomValue(appPathAtom);
  const navigate = useSetAtom(navigateToPathAtom);
  const [date, setDate] = useState(koreaToday);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [showWeather, setShowWeather] = useState(mode === "outing");
  const [panel, setPanel] = useState<{ region?: PrivateRegion; point: RegionPoint } | null>(null);
  const revision = useAtomValue(revisionCounterAtom);
  const regions = useQuery({
    queryKey: ["my-regions", revision],
    queryFn: () => api.regionsList(),
    enabled: mode === "regions",
    staleTime: 30_000,
  });
  const savedPins = useMemo(
    () =>
      (regions.data?.regions ?? []).flatMap((region) =>
        region.latitude != null && region.longitude != null
          ? [
              {
                id: region.region_id,
                name: region.local_alias,
                latitude: region.latitude,
                longitude: region.longitude,
              },
            ]
          : []
      ),
    [regions.data]
  );
  const selectMapPoint = useCallback((point: RegionPoint) => setPanel({ point }), []);
  const openRegion = useCallback(
    (id: string) => {
      const region = regions.data?.regions.find((item) => item.region_id === id);
      if (region?.latitude != null && region.longitude != null)
        setPanel({
          region,
          point: {
            latitude: region.latitude,
            longitude: region.longitude,
            address: region.public_area_code ?? "",
          },
        });
    },
    [regions.data]
  );
  const requestedRegion = new URLSearchParams(path.split("?")[1] ?? "").get("region");
  useEffect(() => {
    if (mode === "regions" && requestedRegion && regions.data) openRegion(requestedRegion);
  }, [mode, requestedRegion, regions.data, openRegion]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [focus, setFocus] = useState<{ latitude: number; longitude: number } | null>(null);
  const [selected, setSelected] = useState<WeatherLocation | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const geocodeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => geocodeRequest.current?.abort(), []);
  const weather = useQuery({
    queryKey: getApiV1WeatherGetWeatherQueryKey({ date }),
    queryFn: ({ signal }) => loadWeather(date, signal),
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: 1,
  });
  const locations = weather.data?.locations ?? [];
  const selectedWeather = selected
    ? locations.find((location) => location.id === selected.id)
    : null;
  const selectLocation = useCallback((location: WeatherLocation) => setSelected(location), []);

  async function selectAddress(nextAddress: string) {
    geocodeRequest.current?.abort();
    const controller = new AbortController();
    geocodeRequest.current = controller;
    setAddress(nextAddress);
    setSearchOpen(false);
    setSearching(true);
    setSearchError(null);
    try {
      const point = await geocodeAddress(nextAddress, controller.signal);
      if (controller.signal.aborted || point.latitude == null || point.longitude == null) return;
      const { latitude, longitude } = point;
      setFocus({ latitude, longitude });
      if (mode === "regions") setPanel({ point: { latitude, longitude, address: nextAddress } });
      const nearest = [...locations].sort(
        (a, b) =>
          Math.hypot(a.latitude - latitude, a.longitude - longitude) -
          Math.hypot(b.latitude - latitude, b.longitude - longitude)
      )[0];
      if (nearest) setSelected(nearest);
    } catch {
      if (!controller.signal.aborted)
        setSearchError("주소 위치를 찾지 못했습니다. 지도에서 가까운 지역을 선택하세요.");
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid w-full max-w-80 grid-cols-[2.75rem_minmax(0,1fr)_2.75rem] items-center gap-1 rounded-xl border border-border bg-card p-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="이전 날짜"
            disabled={date <= (weather.data?.min_date ?? "1940-01-01")}
            onClick={() => {
              setDate(shiftDate(date, -1));
              setSelected(null);
            }}
          >
            <CaretLeftIcon />
          </Button>
          <DatePickerField
            aria-label="날씨 날짜"
            required
            value={date}
            min="1940-01-01"
            max={shiftDate(koreaToday(), 15)}
            onChange={(value) => {
              setDate(value);
              setSelected(null);
            }}
          />
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="다음 날짜"
            disabled={date >= shiftDate(koreaToday(), 15)}
            onClick={() => {
              setDate(shiftDate(date, 1));
              setSelected(null);
            }}
          >
            <CaretRightIcon />
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === "regions" ? (
            <label className="mr-2 flex items-center gap-2 text-base">
              <input
                type="checkbox"
                checked={showWeather}
                onChange={(event) => setShowWeather(event.target.checked)}
                className="size-4 accent-[var(--primary)]"
              />
              날씨 표시
            </label>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDate(koreaToday());
              setSelected(null);
            }}
          >
            오늘
          </Button>
          <Button variant="outline" onClick={() => setCalendarOpen(true)}>
            <CalendarBlankIcon />
            달력
          </Button>
          <Button variant="outline" onClick={() => setSearchOpen(true)}>
            <MagnifyingGlassIcon />
            주소 검색
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="날씨 새로고침"
            disabled={weather.isFetching}
            onClick={() => void weather.refetch()}
          >
            <ArrowClockwiseIcon
              className={weather.isFetching ? "animate-spin motion-reduce:animate-none" : ""}
            />
          </Button>
        </div>
      </div>
      {weather.isPending || searching ? (
        <p role="status" className="text-base text-muted-foreground">
          {searching ? "주소 위치 찾는 중…" : "날씨 불러오는 중…"}
        </p>
      ) : null}
      {weather.error ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 text-base"
        >
          <span>{weather.error.message}</span>
          <Button variant="outline" size="sm" onClick={() => void weather.refetch()}>
            다시 시도
          </Button>
        </div>
      ) : null}
      {weather.data?.status !== "complete" && weather.data ? (
        <div
          role="status"
          className="flex items-center justify-between gap-3 rounded-xl bg-muted px-4 py-3 text-base"
        >
          <span>
            {weather.data.status === "partial"
              ? "일부 지역의 날씨를 불러오지 못했습니다."
              : "선택한 날짜의 날씨 자료가 없습니다."}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={weather.isFetching}
            onClick={() => void weather.refetch()}
          >
            다시 시도
          </Button>
        </div>
      ) : null}
      {searchError ? (
        <p role="alert" className="text-base text-destructive">
          {searchError}
        </p>
      ) : null}
      <JejuWeatherMap
        locations={showWeather ? locations : []}
        onSelect={selectLocation}
        focus={focus}
        regionPins={savedPins}
        onRegionSelect={openRegion}
        onMapSelect={mode === "regions" ? selectMapPoint : undefined}
        selectedPoint={panel?.region ? null : panel?.point}
      />
      <div className="flex flex-wrap items-center justify-between gap-2 text-base text-muted-foreground">
        <span>
          {weather.data?.kind === "historical" ? "과거 날씨" : "낮 12시 예보"}
          {address ? ` · ${address}` : ""}
        </span>
        {weather.data ? (
          <a
            href={weather.data.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            {weather.data.source}
          </a>
        ) : null}
      </div>
      {selectedWeather && mode === "outing" ? (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-primary/30 bg-card px-5 py-4">
          <div className="flex items-center gap-3">
            <MapPinIcon className="size-5 text-primary" />
            <span className="text-lg font-semibold">{selectedWeather.name}</span>
            <WeatherIcon condition={selectedWeather.condition} />
          </div>
          <div className="flex flex-wrap items-baseline gap-5">
            <span className="text-3xl font-bold tabular-nums">
              {selectedWeather.temperature_c ?? "—"}°
            </span>
            <span className="text-base text-weather-rain">
              강수확률{" "}
              {selectedWeather.precipitation_probability == null
                ? "—"
                : `${selectedWeather.precipitation_probability}%`}
            </span>
            <span className="text-base text-muted-foreground">
              {WEATHER_LABELS[selectedWeather.condition]}
            </span>
          </div>
          <Button
            variant="outline"
            onClick={() => {
              const params = new URLSearchParams({ date });
              for (const id of weather.data?.evidence_ids ?? []) params.append("evidence", id);
              navigate(`/notebook/new?${params.toString()}`);
            }}
          >
            수첩에 기록
          </Button>
        </div>
      ) : null}
      {showWeather ? (
        <section
          className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6"
          aria-label="지역별 날씨 목록"
        >
          {locations.map((location) => (
            <button
              key={location.id}
              type="button"
              onClick={() => {
                selectLocation(location);
                setFocus({ latitude: location.latitude, longitude: location.longitude });
              }}
              className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card p-3 text-left hover:border-primary focus-visible:ring-2 focus-visible:ring-ring"
              aria-pressed={selected?.id === location.id}
            >
              <span className="flex flex-col">
                <span className="text-base font-medium">{location.name}</span>
                <span className="text-base text-weather-rain">
                  비{" "}
                  {location.precipitation_probability == null
                    ? "—"
                    : `${location.precipitation_probability}%`}
                </span>
              </span>
              <span className="flex items-center gap-1">
                <WeatherIcon condition={location.condition} className="size-5" />
                <span className="font-semibold tabular-nums">
                  {location.temperature_c == null ? "—" : `${Math.round(location.temperature_c)}°`}
                </span>
              </span>
            </button>
          ))}
        </section>
      ) : null}
      {mode === "outing" ? <OutingPlanForm key={date} initialDate={date} /> : null}
      {mode === "regions" ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold">
            관심 지역{" "}
            <span className="text-muted-foreground">{regions.data?.regions.length ?? 0}</span>
          </h2>
          {regions.isError ? (
            <p role="alert" className="text-base text-destructive">
              관심 지역을 불러오지 못했습니다.
            </p>
          ) : savedPins.length === 0 ? (
            <p className="py-6 text-center text-base text-muted-foreground">
              지도에 핀을 찍거나 주소를 검색해 추가하세요.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {savedPins.map((pin) => (
                <Button
                  key={pin.id}
                  variant="outline"
                  onClick={() => {
                    openRegion(pin.id);
                    setFocus({ latitude: pin.latitude, longitude: pin.longitude });
                  }}
                >
                  <MapPinIcon />
                  {pin.name}
                </Button>
              ))}
            </div>
          )}
        </section>
      ) : null}
      {panel ? (
        <InterestRegionPanel
          key={panel.region?.region_id ?? `${panel.point.latitude},${panel.point.longitude}`}
          region={panel.region}
          point={panel.point}
          weather={
            [...locations].sort(
              (a, b) =>
                Math.hypot(a.latitude - panel.point.latitude, a.longitude - panel.point.longitude) -
                Math.hypot(b.latitude - panel.point.latitude, b.longitude - panel.point.longitude)
            )[0]
          }
          onClose={() => setPanel(null)}
          onPreview={onPreview}
        />
      ) : null}
      {calendarOpen ? (
        <Dialog open onOpenChange={setCalendarOpen}>
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>날씨 날짜 선택</DialogTitle>
            </DialogHeader>
            <DateSelectionCalendar
              value={date}
              onSelect={(value) => {
                setDate(value);
                setSelected(null);
                setCalendarOpen(false);
              }}
            />
          </DialogContent>
        </Dialog>
      ) : null}
      {searchOpen ? (
        <Dialog open onOpenChange={setSearchOpen}>
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>주소 검색</DialogTitle>
            </DialogHeader>
            <DaumAddressSearch onSelect={(nextAddress) => void selectAddress(nextAddress)} />
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
