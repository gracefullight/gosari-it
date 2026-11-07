import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChatComposer } from "@/components/chat-composer";

afterEach(cleanup);

it("focuses the conversation input when it is opened", () => {
  render(<ChatComposer onSend={vi.fn()} autoFocus />);
  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "메시지 입력" }));
});

it("restores focus after a response enables the input", () => {
  const onSend = vi.fn();
  const { rerender } = render(<ChatComposer onSend={onSend} autoFocus disabled />);
  rerender(<ChatComposer onSend={onSend} autoFocus disabled={false} />);
  expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "메시지 입력" }));
});
