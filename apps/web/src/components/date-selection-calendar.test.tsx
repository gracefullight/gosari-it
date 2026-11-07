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
