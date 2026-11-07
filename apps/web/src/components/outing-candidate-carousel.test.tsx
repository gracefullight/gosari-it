import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OutingCandidateCarousel } from "@/components/outing-candidate-carousel";
import { OutingComparisonView } from "@/components/result-card";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function setup(reduced = false) {
  vi.spyOn(window, "matchMedia").mockReturnValue({ matches: reduced } as MediaQueryList);
  render(
    <OutingCandidateCarousel
      items={[
        {
          id: "a",
          rank: 1,
          content: (
            <div>
              애월 후보<button type="button">비교 근거</button>
            </div>
          ),
        },
        { id: "b", rank: 2, content: <div>한림 후보</div> },
        { id: "c", rank: 3, content: <div>성산 후보</div> },
      ]}
    />
  );
  const viewport = screen.getByRole("region", { name: "후보 넘겨 보기" });
  Object.defineProperty(viewport, "clientWidth", { configurable: true, value: 360 });
  const scrollTo = vi.fn();
  viewport.scrollTo = scrollTo;
  return { viewport, scrollTo };
}

describe("outing candidate carousel", () => {
  it("exposes one candidate at a time and stops at either end", () => {
    const { scrollTo } = setup();
    const previous = screen.getByRole("button", { name: "이전 후보" });
    const next = screen.getByRole("button", { name: "다음 후보" });
    expect(previous.hasAttribute("disabled")).toBe(true);
    expect(screen.getAllByRole("article")).toHaveLength(1);
    fireEvent.click(next);
    expect(scrollTo).toHaveBeenLastCalledWith({ left: 360, behavior: "smooth" });
    expect(screen.getByRole("article", { name: "2 / 3 후보" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("2순위");
    fireEvent.click(next);
    expect(next.hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("3 / 3 후보");
    fireEvent.click(previous);
    expect(screen.getByRole("article", { name: "2 / 3 후보" })).toBeTruthy();
  });

  it("supports Left/Right on the viewport without hijacking child controls", () => {
    const { viewport } = setup();
    fireEvent.keyDown(screen.getByRole("button", { name: "비교 근거" }), { key: "ArrowRight" });
    expect(screen.getByRole("status").textContent).toContain("1순위");
    fireEvent.keyDown(viewport, { key: "ArrowRight" });
    expect(screen.getByRole("status").textContent).toContain("2순위");
    fireEvent.keyDown(viewport, { key: "ArrowLeft" });
    expect(screen.getByRole("status").textContent).toContain("1순위");
  });

  it("updates the current candidate after native touch scrolling", () => {
    const { viewport } = setup();
    fireEvent.pointerDown(viewport, { pointerType: "touch" });
    viewport.scrollLeft = 720;
    fireEvent.scroll(viewport);
    expect(screen.getByRole("status").textContent).toContain("3순위");
    expect(screen.getByRole("article", { name: "3 / 3 후보" })).toBeTruthy();
    expect(viewport.className).toContain("snap-mandatory");
  });

  it("removes smooth movement when reduced motion is enabled", () => {
    const { scrollTo } = setup(true);
    fireEvent.click(screen.getByRole("button", { name: "다음 후보" }));
    expect(scrollTo).toHaveBeenCalledWith({ left: 360, behavior: "instant" });
  });

  it("omits an empty carousel and keeps a single candidate usable", () => {
    const { rerender } = render(<OutingCandidateCarousel items={[]} />);
    expect(screen.queryByRole("region", { name: "나들이 후보" })).toBeNull();
    rerender(<OutingCandidateCarousel items={[{ id: "one", rank: 1, content: <p>애월</p> }]} />);
    expect(screen.getByRole("status").textContent).toContain("1 / 1 후보");
    expect(screen.getByRole("button", { name: "다음 후보" }).hasAttribute("disabled")).toBe(true);
  });

  it("preserves ranked weather, details, date and editable checklist across candidates", () => {
    render(
      <OutingComparisonView
        candidates={[
          {
            candidate_id: "second",
            station_name: "한림",
            rank: 2,
            target_date: "2026-11-08",
            target_time_window: "12:00",
          },
          {
            candidate_id: "first",
            station_name: "애월",
            rank: 1,
            target_date: "2026-11-07",
            target_time_window: "09:00",
            comparison_reasons: ["비가 적습니다"],
            weather: {
              temperature_c: 18,
              precipitation_probability: 10,
              wind_speed_kmh: 8,
              condition: "clear",
              kind: "forecast",
              source: "open_meteo",
              target_at: "2026-11-07T09:00:00+09:00",
            },
          },
        ]}
        rankedIds={["first", "second"]}
        checklist={["우산"]}
      />
    );
    const viewport = screen.getByRole("region", { name: "후보 넘겨 보기" });
    viewport.scrollTo = vi.fn();
    expect(screen.getByRole("article", { name: "1 / 2 후보" }).textContent).toContain("애월");
    expect(screen.getByText("18℃")).toBeTruthy();
    expect(screen.getByText("2026-11-07 · 09:00")).toBeTruthy();
    fireEvent.click(screen.getByText("비교 근거"));
    expect(screen.getByText("비가 적습니다").closest("details")?.open).toBe(true);
    const umbrella = screen.getByRole("checkbox", { name: "우산" }) as HTMLInputElement;
    fireEvent.click(umbrella);
    fireEvent.click(screen.getByRole("button", { name: "다음 후보" }));
    expect(umbrella.checked).toBe(true);
    expect(screen.getByRole("article", { name: "2 / 2 후보" }).textContent).toContain("한림");
    fireEvent.click(screen.getByRole("button", { name: "수정" }));
    fireEvent.change(screen.getByRole("textbox", { name: "준비물 이름" }), {
      target: { value: "장갑" },
    });
    fireEvent.click(screen.getByRole("button", { name: "완료" }));
    expect(screen.getByRole("checkbox", { name: "장갑" })).toBeTruthy();
  });
});
