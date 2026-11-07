import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatePickerField } from "@/components/date-picker-field";

afterEach(cleanup);

describe("DatePickerField", () => {
  it("opens a Korean calendar with month/year selection and commits an ISO day", async () => {
    const change = vi.fn();
    render(
      <DatePickerField id="test-date" aria-label="채취 날짜" value="2026-11-07" onChange={change} />
    );
    expect(document.querySelector('input[type="date"]')).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "채취 날짜" }));
    expect(await screen.findByRole("combobox", { name: "월 선택" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "연도 선택" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "2026-11-09 선택" }));
    expect(change).toHaveBeenCalledWith("2026-11-09");
    await waitFor(() => expect(screen.queryByRole("combobox", { name: "월 선택" })).toBeNull());
  });

  it("disables days outside the allowed range", async () => {
    render(
      <DatePickerField
        aria-label="날짜"
        value="2026-11-07"
        min="2026-11-05"
        max="2026-11-10"
        onChange={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "날짜" }));
    const before = await screen.findByRole("button", { name: "2026-11-04 선택" });
    expect((before as HTMLButtonElement).disabled).toBe(true);
    expect(
      (screen.getByRole("button", { name: "2026-11-11 선택" }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "2026-11-09 선택" }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("closes with Escape without changing the value", async () => {
    const change = vi.fn();
    render(<DatePickerField aria-label="날짜" value="2026-11-07" onChange={change} />);
    const trigger = screen.getByRole("button", { name: "날짜" });
    fireEvent.click(trigger);
    const day = await screen.findByRole("button", { name: "2026-11-07 선택" });
    fireEvent.keyDown(day, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("combobox", { name: "월 선택" })).toBeNull());
    expect(change).not.toHaveBeenCalled();
  });
});

it("clears an optional selected date", async () => {
  const change = vi.fn();
  render(<DatePickerField aria-label="시작 날짜" value="2026-11-07" onChange={change} />);
  fireEvent.click(screen.getByRole("button", { name: "시작 날짜" }));
  fireEvent.click(await screen.findByRole("button", { name: "날짜 지우기" }));
  expect(change).toHaveBeenCalledWith("");
});

it("keeps a required date selected and does not offer clearing", async () => {
  const change = vi.fn();
  render(<DatePickerField required aria-label="채취 날짜" value="2026-11-07" onChange={change} />);
  fireEvent.click(screen.getByRole("button", { name: "채취 날짜" }));
  const day = await screen.findByRole("button", { name: "2026-11-07 선택" });
  expect(screen.queryByRole("button", { name: "날짜 지우기" })).toBeNull();
  fireEvent.click(day);
  expect(change).toHaveBeenCalledWith("2026-11-07");
});
