import { Button, Textarea } from "@gracefullight/krds-tw";
import { type KeyboardEvent, useRef, useState } from "react";

interface ComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}

export function Composer({ onSend, disabled, placeholder, autoFocus }: ComposerProps) {
  const [value, setValue] = useState("");
  const composing = useRef(false);

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
    <div className="flex w-full items-end gap-2">
      <Textarea
        label="메시지 입력"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          composing.current = true;
        }}
        onCompositionEnd={() => {
          composing.current = false;
        }}
        placeholder={
          placeholder ?? "한 문장으로 질문해 주세요. 필요한 조건은 대화 중에 확인합니다."
        }
        rows={2}
        maxLength={2000}
        disabled={disabled}
        autoFocus={autoFocus}
        className="min-h-11 flex-1"
      />
      <Button
        variant="primary"
        size="large"
        onClick={submit}
        disabled={disabled || value.trim().length === 0}
        aria-label="메시지 보내기"
        className="h-11 shrink-0"
      >
        보내기
      </Button>
    </div>
  );
}
