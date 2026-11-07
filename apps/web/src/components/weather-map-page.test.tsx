import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { koreaToday, shiftDate, WeatherMapPage } from "@/components/weather-map-page";
import * as endpoints from "@/lib/api/generated/endpoints";
import { api } from "@/lib/gosari.api";
import type { Preview, PrivateRegion } from "@/lib/gosari.types";
import { appPathAtom } from "@/stores/chat.atoms";

vi.mock("@/components/jeju-weather-map", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/components/jeju-weather-map")>();
  return {
    ...original,
    JejuWeatherMap: ({
      onMapSelect,
      onRegionSelect,
      regionPins,
      locations,
    }: ComponentProps<typeof original.JejuWeatherMap>) => (
      <section aria-label="제주 지도">
        {onMapSelect ? (
          <button
            type="button"
            onClick={() => onMapSelect({ latitude: 33.4567, longitude: 126.6789 })}
          >
            새 위치 선택
          </button>
        ) : null}
        {regionPins?.map((pin) => (
          <button type="button" key={pin.id} onClick={() => onRegionSelect?.(pin.id)}>
            {pin.name} 지도 핀
          </button>
        ))}
        <span>날씨 핀 {locations.length}개</span>
      </section>
    ),
  };
});

let queryClient: QueryClient;
const savedRegion: PrivateRegion = {
  region_id: "region-one",
  revision: 1,
  kind: "interest",
  local_alias: "선흘 숲길",
  public_area_code: "제주시 조천읍 선흘리",
  coarse_grid: null,
  latitude: 33.46,
  longitude: 126.68,
  selected_station_mapping_ids: [],
  created_at: "2026-11-07",
  updated_at: "2026-11-07",
};
const preview: Preview = {
  preview_id: "preview-one",
  action: "region.create",
  target_id: "region-new",
  target_revision: 0,
  schema_version: "region-v1",
  display_payload: {},
  preview_hash: "hash",
  expires_at: "later",
};

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(api, "regionsList").mockResolvedValue({ regions: [savedRegion] });
  vi.spyOn(api, "regionsPrepare").mockResolvedValue(preview);
  vi.spyOn(endpoints, "apiV1WeatherGetWeather").mockImplementation(async (params) => ({
    status: 200,
    headers: new Headers(),
    data: {
      date: params?.date ?? koreaToday(),
      evidence_ids: ["ev-public-weather"],
      updated_at: "2026-11-07T00:00:00Z",
      kind: "forecast",
      status: "complete",
      source: "날씨 출처",
      source_url: "https://example.com/weather",
      min_date: "1940-01-01",
      max_date: shiftDate(koreaToday(), 15),
      locations: [
        {
          id: "west",
          name: "서쪽 지역",
          latitude: 33.3,
          longitude: 126.1,
          temperature_c: 13,
          precipitation_probability: 80,
          condition: "rain",
          forecast_at: "2026-11-07T12:00:00+09:00",
        },
        {
          id: "east",
          name: "선흘",
          latitude: 33.45,
          longitude: 126.67,
          temperature_c: 18.4,
          precipitation_probability: 30,
          condition: "clear",
          forecast_at: "2026-11-07T12:00:00+09:00",
        },
      ],
    },
  }));
});
afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.restoreAllMocks();
});

function mountRegions(onPreview = vi.fn()) {
  render(
    <QueryClientProvider client={queryClient}>
      <Provider>
        <WeatherMapPage mode="regions" onPreview={onPreview} />
      </Provider>
    </QueryClientProvider>
  );
  return onPreview;
}

describe("Interest regions on weather map", () => {
  it("opens a saved map pin in the side panel with the nearest weather and saves edits", async () => {
    const onPreview = mountRegions();
    fireEvent.click(await screen.findByRole("button", { name: "선흘 숲길 지도 핀" }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByRole("heading", { name: "선흘 숲길" })).toBeTruthy();
    expect((within(panel).getByLabelText("지역 이름") as HTMLInputElement).value).toBe("선흘 숲길");
    expect((within(panel).getByLabelText("주소·위치 메모") as HTMLInputElement).value).toBe(
      "제주시 조천읍 선흘리"
    );
    expect(await within(panel).findByText("주변 날씨 · 선흘")).toBeTruthy();
    expect(within(panel).getByText("18°")).toBeTruthy();
    expect(within(panel).getByText("강수확률 30%")).toBeTruthy();
    fireEvent.change(within(panel).getByLabelText("지역 이름"), {
      target: { value: "선흘 북쪽 숲길" },
    });
    fireEvent.click(within(panel).getByRole("button", { name: "변경 내용 저장" }));
    await waitFor(() =>
      expect(api.regionsPrepare).toHaveBeenCalledWith(
        {
          kind: "interest",
          local_alias: "선흘 북쪽 숲길",
          public_area_code: "제주시 조천읍 선흘리",
          latitude: 33.46,
          longitude: 126.68,
          visited_on: null,
        },
        "update",
        "region-one"
      )
    );
    expect(onPreview).toHaveBeenCalledWith(preview);
  });

  it("creates an interest region from the actual selected map coordinates", async () => {
    const onPreview = mountRegions();
    fireEvent.click(screen.getByRole("button", { name: "새 위치 선택" }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByRole("heading", { name: "관심 지역 추가" })).toBeTruthy();
    const save = within(panel).getByRole("button", { name: "관심 지역 저장" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(panel).getByLabelText("지역 이름"), {
      target: { value: "다음에 가볼 곳" },
    });
    fireEvent.change(within(panel).getByLabelText("주소·위치 메모"), {
      target: { value: "동쪽 입구" },
    });
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.regionsPrepare).toHaveBeenCalledWith(
        {
          kind: "interest",
          local_alias: "다음에 가볼 곳",
          public_area_code: "동쪽 입구",
          latitude: 33.4567,
          longitude: 126.6789,
          visited_on: null,
        },
        "create",
        undefined
      )
    );
    expect(onPreview).toHaveBeenCalledWith(preview);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("prepares deletion for the selected saved region without sending new content", async () => {
    const onPreview = mountRegions();
    fireEvent.click(await screen.findByRole("button", { name: "선흘 숲길 지도 핀" }));
    const panel = await screen.findByRole("dialog");
    fireEvent.click(within(panel).getByRole("button", { name: "관심 지역 삭제" }));
    await waitFor(() =>
      expect(api.regionsPrepare).toHaveBeenCalledWith({}, "delete", "region-one")
    );
    expect(onPreview).toHaveBeenCalledWith(preview);
  });

  it("selects a date in the FullCalendar dialog and requests that date", async () => {
    mountRegions();
    await screen.findByRole("button", { name: "선흘 숲길 지도 핀" });
    const nextDate = shiftDate(koreaToday(), 1);
    fireEvent.click(screen.getByRole("button", { name: "달력" }));
    const calendar = await screen.findByRole("dialog");
    expect(within(calendar).getByRole("heading", { name: "날씨 날짜 선택" })).toBeTruthy();
    fireEvent.click(await within(calendar).findByRole("button", { name: `${nextDate} 선택` }));
    await waitFor(() => expect(screen.getByLabelText("날씨 날짜").textContent).toContain(nextDate));
    await waitFor(() =>
      expect(endpoints.apiV1WeatherGetWeather).toHaveBeenCalledWith(
        { date: nextDate },
        expect.objectContaining({ signal: expect.any(AbortSignal) })
      )
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

it("opens a dated notebook from the selected public weather without putting an address in the URL", async () => {
  const store = createStore();
  render(
    <QueryClientProvider client={queryClient}>
      <Provider store={store}>
        <WeatherMapPage mode="outing" onPreview={vi.fn()} />
      </Provider>
    </QueryClientProvider>
  );
  const list = await screen.findByRole("region", { name: "지역별 날씨 목록" });
  fireEvent.click((await within(list).findAllByRole("button"))[0]);
  fireEvent.click(await screen.findByRole("button", { name: "수첩에 기록" }));
  const route = store.get(appPathAtom);
  expect(route.startsWith("/notebook/new?")).toBe(true);
  const query = new URLSearchParams(route.split("?")[1]);
  expect(query.get("date")).toBe(koreaToday());
  expect(query.getAll("evidence")).toEqual(["ev-public-weather"]);
  expect(query.has("address")).toBe(false);
});
