import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("does not send whitespace-only messages", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력");
    fireEvent.change(textarea, { target: { value: "   " } });
    fireEvent.click(screen.getByLabelText("메시지 보내기"));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("sends on click and clears the draft", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "선흘 강수 비교" } });
    fireEvent.click(screen.getByLabelText("메시지 보내기"));
    expect(onSend).toHaveBeenCalledWith("선흘 강수 비교");
    expect(textarea.value).toBe("");
  });

  it("does not send while IME is composing", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
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
    render(<Composer onSend={onSend} />);
    const textarea = screen.getByLabelText("메시지 입력");
    fireEvent.change(textarea, { target: { value: "줄바꿈" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true, isComposing: false });
    expect(onSend).not.toHaveBeenCalled();
  });
});
