import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChatReplySuggestions } from "@/components/chat-reply-suggestions";
import type { ChatMessage } from "@/stores/chat.atoms";

const messages: ChatMessage[] = [{ id: "a", role: "assistant", kind: "text", text: "안녕하세요" }];
afterEach(cleanup);

it("sends exactly the clicked suggestion through the existing callback", () => {
  const send = vi.fn();
  render(<ChatReplySuggestions messages={messages} onSend={send} />);
  expect(screen.getAllByRole("button")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "현재 제주 날씨를 알려줘" }));
  expect(send).toHaveBeenCalledExactlyOnceWith("현재 제주 날씨를 알려줘");
});

it.each([{ pending: true }, { voiceActive: true }])(
  "hides suggestions without submitting during %o",
  (state) => {
    const send = vi.fn();
    render(<ChatReplySuggestions messages={messages} onSend={send} {...state} />);
    expect(screen.queryByRole("group", { name: "이어 물어보기" })).toBeNull();
    expect(send).not.toHaveBeenCalled();
  }
);

it("prevents a second click while the selected question is being sent", async () => {
  let finish: (() => void) | undefined;
  const send = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      })
  );
  render(<ChatReplySuggestions messages={messages} onSend={send} />);
  fireEvent.click(screen.getByRole("button", { name: "현재 제주 날씨를 알려줘" }));
  expect(screen.queryAllByRole("button")).toHaveLength(0);
  expect(send).toHaveBeenCalledOnce();
  await act(async () => {
    finish?.();
  });
  await waitFor(() => expect(screen.getAllByRole("button")).toHaveLength(3));
});
