import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChatComposer } from "@/components/chat-composer";

const voiceScenario = vi.hoisted(() => ({ text: "받아쓴 문장" }));

vi.mock("@/hooks/use-browser-dictation", async () => {
  const { useRef, useState } = await import("react");
  const { mergeDictationText } = await vi.importActual<
    typeof import("@/hooks/use-browser-dictation")
  >("@/hooks/use-browser-dictation");
  return {
    useBrowserDictation: (
      options: import("@/hooks/use-browser-dictation").BrowserDictationOptions
    ) => {
      const [active, setActive] = useState(false);
      const original = useRef("");
      return {
        status: active ? "listening" : "idle",
        supported: true,
        active,
        transcript: active ? voiceScenario.text : "",
        error: null,
        levelsRef: useRef(Array(24).fill(0.5)),
        start: async () => {
          original.current = options.initialText;
          setActive(true);
          options.onListeningChange?.(true);
        },
        finish: () => {
          options.onConfirm(mergeDictationText(original.current, voiceScenario.text));
          setActive(false);
          options.onListeningChange?.(false);
        },
        cancel: () => {
          options.onCancel?.();
          setActive(false);
          options.onListeningChange?.(false);
        },
      };
    },
  };
});
afterEach(() => {
  cleanup();
  voiceScenario.text = "받아쓴 문장";
});

it("confirms dictation into an editable draft without sending and restores focus", async () => {
  const send = vi.fn();
  const active = vi.fn();
  render(<ChatComposer onSend={send} onVoiceActiveChange={active} />);
  fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
    target: { value: "기존 초안\n" },
  });
  fireEvent.click(screen.getByRole("button", { name: "음성으로 입력" }));
  expect(await screen.findByRole("region", { name: "음성 입력" })).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "메시지 입력" })).toBeNull();
  fireEvent.keyDown(document, { key: "Enter", metaKey: true });
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "입력란에 넣기" }));
  const input = (await screen.findByRole("textbox", {
    name: "메시지 입력",
  })) as HTMLTextAreaElement;
  expect(input.value).toBe("기존 초안\n받아쓴 문장");
  expect(send).not.toHaveBeenCalled();
  await waitFor(() => expect(document.activeElement).toBe(input));
  fireEvent.change(input, { target: { value: "직접 고친 질문" } });
  fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
  expect(send).toHaveBeenCalledExactlyOnceWith("직접 고친 질문");
  expect(active).toHaveBeenCalledWith(true);
  expect(active).toHaveBeenLastCalledWith(false);
});

it("cancels voice input back to the exact original draft", async () => {
  const send = vi.fn();
  render(<ChatComposer onSend={send} />);
  const original = "  원래 질문\n둘째 줄  ";
  fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
    target: { value: original },
  });
  fireEvent.click(screen.getByRole("button", { name: "음성으로 입력" }));
  fireEvent.click(await screen.findByRole("button", { name: "음성 입력 취소" }));
  expect(
    ((await screen.findByRole("textbox", { name: "메시지 입력" })) as HTMLTextAreaElement).value
  ).toBe(original);
  expect(send).not.toHaveBeenCalled();
});

it("preserves oversized dictated text and blocks sending until the user shortens it", async () => {
  const send = vi.fn();
  voiceScenario.text = "가".repeat(2001);
  render(<ChatComposer onSend={send} />);
  fireEvent.click(screen.getByRole("button", { name: "음성으로 입력" }));
  fireEvent.click(await screen.findByRole("button", { name: "입력란에 넣기" }));
  const input = (await screen.findByRole("textbox", {
    name: "메시지 입력",
  })) as HTMLTextAreaElement;
  expect(input.value).toBe(voiceScenario.text);
  expect(screen.getByRole("alert").textContent).toContain("2,000자");
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
  expect(send).not.toHaveBeenCalled();
  expect(input.value).toHaveLength(2001);
  fireEvent.change(input, { target: { value: "짧게 고친 질문" } });
  fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
  expect(send).toHaveBeenCalledExactlyOnceWith("짧게 고친 질문");
});
