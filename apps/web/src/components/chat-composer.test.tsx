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
    fireEvent.click(screen.getByRole("button", { name: "AI 대화 (홈)" }));
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();
  });
});
