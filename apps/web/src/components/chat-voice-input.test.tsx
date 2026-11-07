import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatVoiceInput } from "@/components/chat-voice-input";

const voice = vi.hoisted(() => ({
  state: {
    status: "idle",
    supported: true,
    active: false,
    transcript: "",
    error: null as string | null,
    start: vi.fn(),
    finish: vi.fn(),
    cancel: vi.fn(),
  },
  paint: undefined as ((levels: readonly number[]) => void) | undefined,
}));
vi.mock("@/hooks/use-browser-dictation", () => ({
  useBrowserDictation: (options: { onLevels?: (levels: readonly number[]) => void }) => {
    voice.paint = options.onLevels;
    return voice.state;
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(voice.state, {
    status: "idle",
    supported: true,
    active: false,
    transcript: "",
    error: null,
  });
  voice.paint = undefined;
});
afterEach(cleanup);

describe("chat voice control", () => {
  it("shows microphone startup with cancellation and no language preparation controls", () => {
    Object.assign(voice.state, { status: "starting", active: true });
    render(<ChatVoiceInput initialText="초안" onConfirm={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toBe("마이크 연결 중…");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "상태 확인" })).toBeNull();
    expect(screen.queryByRole("button", { name: "음성 입력 시작" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "음성 입력 취소" }));
    expect(voice.state.cancel).toHaveBeenCalledOnce();
  });
  it("starts only on the microphone control and does not insert text before any result", () => {
    const confirm = vi.fn();
    render(<ChatVoiceInput initialText="내 초안" onConfirm={confirm} />);
    expect(voice.state.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "음성으로 입력" }));
    expect(voice.state.start).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("paints real supplied samples directly into SVG and allows stopping or cancelling", () => {
    Object.assign(voice.state, { status: "listening", active: true, transcript: "제주 날씨" });
    const { container } = render(<ChatVoiceInput initialText="내 초안" onConfirm={vi.fn()} />);
    const bar = container.querySelector("rect");
    expect(container.querySelectorAll("rect")).toHaveLength(64);
    const wave = container.querySelector("svg");
    expect(wave?.getAttribute("preserveAspectRatio")).toBe("none");
    expect(wave?.classList.contains("w-full")).toBe(true);
    expect(wave?.parentElement?.firstElementChild).toBe(wave);
    expect(bar?.getAttribute("height")).toBe("2");
    act(() => voice.paint?.(Array<number>(64).fill(0.5)));
    expect(bar?.getAttribute("height")).toBe("18");
    act(() => voice.paint?.(Array<number>(64).fill(0)));
    expect(bar?.getAttribute("height")).toBe("2");
    expect(screen.getByRole("status").textContent).toBe("듣고 있습니다…");
    fireEvent.click(screen.getByRole("button", { name: "음성 입력 마치기" }));
    expect(voice.state.finish).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "음성 입력 취소" }));
    expect(voice.state.cancel).toHaveBeenCalledOnce();
  });

  it("marks unsupported recognition in the button without an unsolicited warning", () => {
    Object.assign(voice.state, {
      status: "unsupported",
      supported: false,
      error: "이 브라우저에서는 음성 입력을 사용할 수 없습니다.",
    });
    render(<ChatVoiceInput initialText="" onConfirm={vi.fn()} />);
    expect(
      (screen.getByRole("button", { name: "음성 입력 미지원" }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(voice.state.start).not.toHaveBeenCalled();
  });

  it("moves keyboard focus to cancellation and lets Escape stop dictation", () => {
    Object.assign(voice.state, { status: "listening", active: true, transcript: "제주 날씨" });
    render(<ChatVoiceInput initialText="원문" onConfirm={vi.fn()} />);
    const cancel = screen.getByRole("button", { name: "음성 입력 취소" });
    expect(document.activeElement).toBe(cancel);
    fireEvent.keyDown(cancel, { key: "Escape" });
    expect(voice.state.cancel).toHaveBeenCalledOnce();
  });

  it("reports an actual microphone error after a user attempt without widening the button", () => {
    const { rerender } = render(<ChatVoiceInput initialText="원문" onConfirm={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "음성으로 입력" }));
    Object.assign(voice.state, { status: "error", error: "마이크 사용을 허용해 주세요." });
    rerender(<ChatVoiceInput initialText="원문" onConfirm={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).toBe("마이크 사용을 허용해 주세요.");
    expect(
      screen.getByRole("button", { name: "음성으로 입력" }).parentElement?.className
    ).toContain("w-11");
  });
});
