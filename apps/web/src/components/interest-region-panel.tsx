import { useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { WEATHER_LABELS, WeatherIcon, type WeatherLocation } from "@/components/jeju-weather-map";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError, api } from "@/lib/gosari.api";
import type { Preview, PrivateRegion } from "@/lib/gosari.types";

export interface RegionPoint {
  latitude: number;
  longitude: number;
  address?: string;
}
interface InterestRegionPanelProps {
  region?: PrivateRegion | null;
  point: RegionPoint;
  weather?: WeatherLocation;
  onClose: () => void;
  onPreview: (preview: Preview) => void;
}
export function InterestRegionPanel({
  region,
  point,
  weather,
  onClose,
  onPreview,
}: InterestRegionPanelProps) {
  const [name, setName] = useState(region?.local_alias ?? "");
  const [address, setAddress] = useState(region?.public_area_code ?? point.address ?? "");
  const [visitedOn, setVisitedOn] = useState(region?.visited_on ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function prepare(action: "create" | "update" | "delete") {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.regionsPrepare(
        action === "delete"
          ? {}
          : {
              kind: region?.kind ?? "interest",
              local_alias: name.trim(),
              public_area_code: address.trim() || null,
              latitude: point.latitude,
              longitude: point.longitude,
              visited_on: visitedOn || null,
            },
        action,
        region?.region_id
      );
      onClose();
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "지역을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{region?.local_alias ?? "관심 지역 추가"}</SheetTitle>
          <SheetDescription>{region ? "저장한 위치" : "지도에서 선택한 위치"}</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-6 px-5 pb-6">
          <div className="grid gap-2">
            <Label htmlFor="interest-name">지역 이름</Label>
            <Input
              id="interest-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="예: 다음에 가볼 곳"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="interest-address">주소·위치 메모</Label>
            <Input
              id="interest-address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              placeholder="예: 선흘리 동쪽 입구"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="interest-visited">방문 날짜</Label>
            <DatePickerField
              id="interest-visited"
              aria-label="방문 날짜"
              value={visitedOn}
              onChange={setVisitedOn}
            />
          </div>
          {weather ? (
            <section className="rounded-xl bg-muted p-4">
              <h3 className="mb-3 text-base font-medium text-muted-foreground">
                주변 날씨 · {weather.name}
              </h3>
              <div className="flex items-center gap-3">
                <WeatherIcon condition={weather.condition} className="size-10" />
                <span className="text-3xl font-bold tabular-nums">
                  {weather.temperature_c == null ? "—" : `${Math.round(weather.temperature_c)}°`}
                </span>
                <span className="text-base">{WEATHER_LABELS[weather.condition]}</span>
              </div>
              <p className="mt-3 text-base text-weather-rain">
                강수확률{" "}
                {weather.precipitation_probability == null
                  ? "—"
                  : `${weather.precipitation_probability}%`}
              </p>
            </section>
          ) : null}
          {error ? (
            <p role="alert" className="text-base text-destructive">
              {error}
            </p>
          ) : null}
          <Button
            onClick={() => void prepare(region ? "update" : "create")}
            disabled={busy || !name.trim()}
          >
            {region ? "변경 내용 저장" : "관심 지역 저장"}
          </Button>
          {region ? (
            <Button variant="destructive" disabled={busy} onClick={() => void prepare("delete")}>
              관심 지역 삭제
            </Button>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
