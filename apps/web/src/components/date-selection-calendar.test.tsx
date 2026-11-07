import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DateSelectionCalendar } from "@/components/date-selection-calendar";

afterEach(cleanup);

it("opens the selected month and supports keyboard-accessible date selection", () => {
  const onSelect = vi.fn();
  render(<DateSelectionCalendar value="2026-11-07" onSelect={onSelect} />);
  expect(screen.getByText("2026년 11월")).toBeTruthy();
  const day = screen.getByRole("button", { name: "2026-11-08 선택" });
  fireEvent.click(day);
  expect(onSelect).toHaveBeenCalledWith("2026-11-08");
  expect(screen.getByRole("button", { name: "2026-11-07 선택" }).getAttribute("aria-pressed")).toBe(
    "true"
  );
});

it("renders notebook records and forwards event selection", () => {
  const onEventSelect = vi.fn();
  render(
    <DateSelectionCalendar
      value="2026-11-07"
      onSelect={vi.fn()}
      onEventSelect={onEventSelect}
      events={[{ id: "record-1", title: "선흘 채취 기록", start: "2026-11-07" }]}
    />
  );
  fireEvent.click(screen.getByText("선흘 채취 기록"));
  expect(onEventSelect).toHaveBeenCalledWith("record-1");
});

it("enforces an inclusive optional date range while leaving unrestricted calendars unchanged", () => {
  const onSelect = vi.fn();
  render(
    <DateSelectionCalendar
      value="2026-11-07"
      min="2026-11-07"
      max="2026-11-08"
      onSelect={onSelect}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: "2026-11-08 선택" }));
  expect(onSelect).toHaveBeenLastCalledWith("2026-11-08");
  const before = screen.queryByRole("button", { name: "2026-11-06 선택" });
  const after = screen.queryByRole("button", { name: "2026-11-09 선택" });
  for (const unavailable of [before, after]) {
    if (unavailable) {
      expect((unavailable as HTMLButtonElement).disabled).toBe(true);
      fireEvent.click(unavailable);
    }
  }
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(document.querySelector<HTMLButtonElement>(".fc-next-button")?.disabled).toBe(true);
});
