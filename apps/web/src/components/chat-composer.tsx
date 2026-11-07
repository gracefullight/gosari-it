import { PaperPlaneRightIcon } from "@phosphor-icons/react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ChatComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}

export function ChatComposer({ onSend, disabled, placeholder, autoFocus }: ChatComposerProps) {
  const [value, setValue] = useState("");
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (autoFocus && !disabled) textarea.current?.focus({ preventScroll: true });
  }, [autoFocus, disabled]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !composing.current &&
      event.nativeEvent.isComposing === false
    ) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex w-full items-center gap-3">
      <div className="flex-1">
        <Label htmlFor="gosari-composer" className="sr-only">
          메시지 입력
        </Label>
        <Textarea
          ref={textarea}
          id="gosari-composer"
          aria-label="메시지 입력"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          placeholder={placeholder ?? "예: 선흘 봄 날씨 비교, 제주 고사리 가격"}
          rows={2}
          maxLength={2000}
          disabled={disabled}
          autoFocus={autoFocus}
          className="field-sizing-fixed h-16 min-h-16 max-h-16 resize-none overflow-y-auto"
        />
      </div>
      <Button
        size="lg"
        onClick={submit}
        disabled={disabled || value.trim().length === 0}
        aria-label="메시지 보내기"
        className="h-12 shrink-0"
      >
        <PaperPlaneRightIcon data-icon="inline-start" />
        보내기
      </Button>
    </div>
  );
}
