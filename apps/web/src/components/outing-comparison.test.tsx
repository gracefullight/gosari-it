import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { OutingComparisonView, ResultCard } from "@/components/result-card";

afterEach(cleanup);
it("orders candidates by ranking and shows forecast values and reasons", () => {
  render(
    <OutingComparisonView
      candidates={[
        {
          candidate_id: "a",
          station_name: "애월",
          target_date: "2026-11-08",
          target_time_window: "09:00",
          rank: 2,
          comparison_reasons: ["바람이 강해요"],
          weather: {
            temperature_c: 18,
            precipitation_probability: 30,
            wind_speed_kmh: 22,
            condition: "cloudy",
            kind: "forecast",
            source: "Open-Meteo",
            target_at: "2026-11-08T09:00",
          },
        },
        {
          candidate_id: "b",
          station_name: "조천",
          target_date: "2026-11-08",
          target_time_window: "12:00",
          rank: 1,
          comparison_reasons: ["비가 적어요"],
          weather: {
            temperature_c: 19,
            precipitation_probability: 10,
            wind_speed_kmh: 8,
            condition: "clear",
            kind: "forecast",
            source: "Open-Meteo",
            target_at: "2026-11-08T12:00",
            recent_context: [{ days: 7, total_rain_mm: 12, average_temperature_c: 17 }],
          },
        },
      ]}
      rankedIds={["b", "a"]}
      checklist={["장갑"]}
    />
  );
  const firstCandidate = screen.getByRole("article", { name: "1 / 2 후보" });
  expect(within(firstCandidate).getByText("1순위").parentElement?.textContent).toContain("조천");
  expect(screen.getByText("19℃")).toBeTruthy();
  expect(screen.getByText("10%")).toBeTruthy();
  expect(screen.getByText("8km/h")).toBeTruthy();
  expect(screen.getByText("비가 적어요")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox", { name: "장갑" }));
  expect((screen.getByRole("checkbox", { name: "장갑" }) as HTMLInputElement).checked).toBe(true);
  fireEvent.change(screen.getByLabelText("추가할 준비물"), { target: { value: "긴 양말" } });
  fireEvent.click(screen.getByRole("button", { name: "추가" }));
  const added = screen.getByRole("checkbox", { name: "긴 양말" });
  expect(added).toBeTruthy();
  fireEvent.click(
    within(added.closest("li") as HTMLLIElement).getByRole("button", { name: "수정" })
  );
  fireEvent.change(screen.getByLabelText("준비물 이름"), { target: { value: "긴 양말 두 켤레" } });
  fireEvent.click(screen.getByRole("button", { name: "완료" }));
  expect(screen.getByRole("checkbox", { name: "긴 양말 두 켤레" })).toBeTruthy();
  fireEvent.click(
    within(added.closest("li") as HTMLLIElement).getByRole("button", {
      name: "긴 양말 두 켤레 삭제",
    })
  );
  expect(screen.queryByRole("checkbox", { name: "긴 양말" })).toBeNull();
});

it("keeps long generated explanations out of the structured outing comparison", () => {
  render(
    <ResultCard
      envelope={
        {
          data_status: "complete",
          source_mode: "fetched",
          result: {
            explanation: "내부 집계와 공통기간에 관한 장문",
            candidates: [
              {
                candidate_id: "a",
                station_name: "제주시",
                target_date: "2026-11-08",
                target_time_window: "09:00",
              },
            ],
          },
          warnings: [],
          errors: [],
        } as never
      }
    />
  );
  expect(screen.queryByText("내부 집계와 공통기간에 관한 장문")).toBeNull();
  expect(screen.getByText("제주시")).toBeTruthy();
});
