import { HotkeysProvider } from "@tanstack/react-hotkeys";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatComposer } from "@/components/chat-composer";
import { ChatShell } from "@/components/chat-shell";
import { MainSideNavigation } from "@/components/main-side-navigation";

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ entries: [], count: 0, drafts: [], regions: [], stations: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Composer", () => {
  it("grows from one line up to six lines and keeps longer drafts scrollable", () => {
    render(<ChatComposer onSend={vi.fn()} />);
    const input = screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement;
    const initial = Number.parseFloat(input.style.height);
    fireEvent.change(input, { target: { value: "첫째 줄\n둘째 줄\n셋째 줄" } });
    const three = Number.parseFloat(input.style.height);
    expect(three).toBeGreaterThan(initial);
    fireEvent.change(input, { target: { value: Array(6).fill("기록").join("\n") } });
    const six = Number.parseFloat(input.style.height);
    fireEvent.change(input, { target: { value: Array(9).fill("기록").join("\n") } });
    expect(Number.parseFloat(input.style.height)).toBe(six);
    expect(input.value.split("\n")).toHaveLength(9);
  });

  it.each(["mac", "windows"] as const)(
    "sends Mod+Enter once on %s and keeps the shortcut scoped to its textarea",
    (platform) => {
      const send = vi.fn();
      render(
        <HotkeysProvider defaultOptions={{ platform }}>
          <ChatComposer onSend={send} />
          <input aria-label="다른 입력" />
        </HotkeysProvider>
      );
      const input = screen.getByRole("textbox", { name: "메시지 입력" });
      const modifiers = platform === "mac" ? { metaKey: true } : { ctrlKey: true };
      fireEvent.change(input, { target: { value: "한 번만 보내기" } });
      fireEvent.keyDown(screen.getByRole("textbox", { name: "다른 입력" }), {
        key: "Enter",
        code: "Enter",
        ...modifiers,
      });
      expect(send).not.toHaveBeenCalled();
      input.focus();
      fireEvent.keyDown(input, { key: "Enter", code: "Enter", ...modifiers });
      fireEvent.keyDown(input, { key: "Enter", code: "Enter", repeat: true, ...modifiers });
      fireEvent.keyUp(input, { key: "Enter", code: "Enter", ...modifiers });
      expect(send).toHaveBeenCalledExactlyOnceWith("한 번만 보내기");
      expect((input as HTMLTextAreaElement).value).toBe("");
      expect(screen.getByRole("button", { name: "메시지 보내기" }).textContent).toBe("");
    }
  );

  it("ignores Mod+Enter while Korean composition is active and while a response runs", () => {
    const send = vi.fn();
    const stop = vi.fn();
    const view = render(
      <HotkeysProvider defaultOptions={{ platform: "mac" }}>
        <ChatComposer onSend={send} />
      </HotkeysProvider>
    );
    const input = screen.getByRole("textbox", { name: "메시지 입력" });
    fireEvent.change(input, { target: { value: "입력 중" } });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", metaKey: true });
    fireEvent.keyUp(input, { key: "Enter", code: "Enter", metaKey: true });
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", metaKey: true, keyCode: 229 });
    fireEvent.keyUp(input, { key: "Enter", code: "Enter", metaKey: true });
    expect(send).not.toHaveBeenCalled();
    view.rerender(
      <HotkeysProvider defaultOptions={{ platform: "mac" }}>
        <ChatComposer onSend={send} responding onStop={stop} />
      </HotkeysProvider>
    );
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", metaKey: true });
    fireEvent.keyUp(input, { key: "Enter", code: "Enter", metaKey: true });
    expect(send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "응답 중지" }));
    expect(stop).toHaveBeenCalledOnce();
    view.rerender(
      <HotkeysProvider defaultOptions={{ platform: "mac" }}>
        <ChatComposer onSend={send} responding stopping onStop={stop} />
      </HotkeysProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "응답 중지" }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it("does not send whitespace-only messages", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력");
    fireEvent.change(textarea, { target: { value: "   " } });
    fireEvent.click(screen.getByLabelText("메시지 보내기"));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends on click and clears the draft", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "선흘 강수 비교" } });
    fireEvent.click(screen.getByLabelText("메시지 보내기"));
    expect(onSend).toHaveBeenCalledWith("선흘 강수 비교");
    expect(textarea.value).toBe("");
  });

  it("does not send while IME is composing", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력");
    fireEvent.change(textarea, { target: { value: "가나다" } });
    fireEvent.compositionStart(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.compositionEnd(textarea);
    fireEvent.keyDown(textarea, { key: "Enter", isComposing: false });
    expect(onSend).toHaveBeenCalledWith("가나다");
  });

  it("shift+enter does not send", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력");
    fireEvent.change(textarea, { target: { value: "줄바꿈" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true, isComposing: false });
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("LNB Page Navigation", () => {
  it("switches dedicated pages when LNB menu items are clicked instead of stacking cards", async () => {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Provider>
          <div>
            <MainSideNavigation open={true} onToggle={vi.fn()} onEndSession={vi.fn()} />
            <ChatShell />
          </div>
        </Provider>
      </QueryClientProvider>
    );

    // Initially on AI 대화 (홈)
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();

    // Click 내 수첩 menu -> switches to 내 수첩 page
    fireEvent.click(screen.getByRole("button", { name: "내 수첩" }));
    expect(screen.getByRole("heading", { name: "내 수첩" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "고사리잇" })).toBeNull();

    // Click 나눔 menu -> replaces view with 나눔 page (no 내 수첩 card remaining!)
    fireEvent.click(screen.getByRole("button", { name: "나눔" }));
    expect(await screen.findByRole("heading", { name: "지인" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "내 수첩" })).toBeNull();

    // Click AI 대화 (홈) -> returns to AI 대화 view with 0 stacked cards
    fireEvent.click(screen.getByRole("button", { name: "채팅" }));
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();
  });
});
