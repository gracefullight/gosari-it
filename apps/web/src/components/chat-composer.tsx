import { ArrowUpIcon, SquareIcon } from "@phosphor-icons/react";
import { useFormatForDisplay, useHotkey } from "@tanstack/react-hotkeys";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { ChatVoiceInput } from "@/components/chat-voice-input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface ChatComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  responding?: boolean;
  stopping?: boolean;
  onStop?: () => void | Promise<void>;
  onVoiceActiveChange?: (active: boolean) => void;
}
const MAX_MESSAGE_LENGTH = 2000;

export function ChatComposer({
  onSend,
  disabled,
  placeholder,
  autoFocus,
  responding = false,
  stopping = false,
  onStop,
  onVoiceActiveChange,
}: ChatComposerProps) {
  const [value, setValue] = useState("");
  const draft = useRef("");
  const voiceDraft = useRef("");
  const wasListening = useRef(false);
  const [voiceActive, setVoiceActive] = useState(false);
  const [multiline, setMultiline] = useState(false);
  const formatHotkey = useFormatForDisplay();
  const expanded = multiline || voiceActive;
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const tooLong = value.trim().length > MAX_MESSAGE_LENGTH;
  useLayoutEffect(() => {
    if (voiceActive) return;
    const input = textarea.current;
    if (!input) return;
    input.style.height = "auto";
    const style = window.getComputedStyle(input);
    const line = Number.parseFloat(style.lineHeight) || 24;
    const padding =
      (Number.parseFloat(style.paddingTop) || 4) + (Number.parseFloat(style.paddingBottom) || 4);
    const limit = Math.min(line * 6 + padding, window.innerHeight * 0.3);
    const explicitLines = Math.min(value.split("\n").length, 6);
    const contentHeight = value
      ? Math.max(input.scrollHeight, explicitLines * line + padding)
      : line + padding;
    input.style.height = `${Math.min(contentHeight, limit)}px`;
    setMultiline(contentHeight > line + padding + 1);
  }, [value, voiceActive]);
  useEffect(() => {
    if (autoFocus && !disabled && !voiceActive) textarea.current?.focus({ preventScroll: true });
  }, [autoFocus, disabled, voiceActive]);
  const focusDraft = useCallback(() => {
    window.requestAnimationFrame(() => textarea.current?.focus({ preventScroll: true }));
  }, []);
  const updateDraft = useCallback((text: string) => {
    draft.current = text;
    if (!wasListening.current) voiceDraft.current = text;
    setValue(text);
  }, []);
  const listeningChanged = useCallback(
    (active: boolean) => {
      const previous = wasListening.current;
      if (active && !previous) voiceDraft.current = draft.current;
      wasListening.current = active;
      setVoiceActive(active);
      onVoiceActiveChange?.(active);
      if (previous && !active) focusDraft();
    },
    [focusDraft, onVoiceActiveChange]
  );
  useEffect(() => () => onVoiceActiveChange?.(false), [onVoiceActiveChange]);

  function submit() {
    const trimmed = draft.current.trim();
    if (!trimmed || trimmed.length > MAX_MESSAGE_LENGTH || disabled || responding || voiceActive)
      return;
    draft.current = "";
    setValue("");
    onSend(trimmed);
  }

  useHotkey(
    "Mod+Enter",
    (event) => {
      if (
        composing.current ||
        event.isComposing ||
        event.keyCode === 229 ||
        event.repeat ||
        event.shiftKey ||
        event.altKey
      )
        return;
      submit();
    },
    {
      target: textarea,
      ignoreInputs: false,
      enabled: !disabled && !responding && !voiceActive && !tooLong,
      ignoreDefaultPrevented: true,
      requireReset: true,
    }
  );

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.repeat) return;
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !composing.current &&
      event.nativeEvent.isComposing !== true &&
      event.nativeEvent.keyCode !== 229
    ) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div
      className={`grid w-full min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] gap-2 rounded-[28px] border border-border bg-card shadow-sm ${expanded ? "p-3 sm:p-4" : "p-2"}`}
    >
      {!voiceActive ? (
        <div
          className={
            expanded
              ? "col-span-3 row-start-1 min-w-0"
              : "col-start-1 row-start-1 min-w-0 self-center"
          }
        >
          <Label htmlFor="gosari-composer" className="sr-only">
            메시지 입력
          </Label>
          <Textarea
            ref={textarea}
            id="gosari-composer"
            aria-label="메시지 입력"
            value={value}
            onChange={(e) => updateDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => {
              composing.current = true;
            }}
            onCompositionEnd={() => {
              composing.current = false;
            }}
            placeholder={placeholder ?? "메시지 입력"}
            rows={1}
            maxLength={MAX_MESSAGE_LENGTH}
            style={{ minHeight: 32 }}
            disabled={disabled || responding}
            autoFocus={autoFocus}
            aria-invalid={tooLong}
            aria-describedby={tooLong ? "gosari-composer-error" : undefined}
            className="field-sizing-fixed min-h-8 max-h-[min(30dvh,9.5rem)] resize-none overflow-y-auto rounded-none border-0 bg-transparent px-1 py-1 text-base leading-6 shadow-none focus-visible:border-transparent focus-visible:ring-0 md:text-base"
          />
        </div>
      ) : null}
      <div
        className={
          voiceActive
            ? "col-span-3 row-start-1 min-w-0"
            : expanded
              ? "col-start-2 row-start-2 justify-self-end"
              : "col-start-2 row-start-1 self-center justify-self-end"
        }
      >
        <ChatVoiceInput
          disabled={disabled || responding}
          initialText={value}
          onListeningChange={listeningChanged}
          onConfirm={(text) => {
            wasListening.current = false;
            updateDraft(text);
            setVoiceActive(false);
            onVoiceActiveChange?.(false);
            focusDraft();
          }}
          onCancel={() => {
            wasListening.current = false;
            updateDraft(voiceDraft.current);
            setVoiceActive(false);
            onVoiceActiveChange?.(false);
            focusDraft();
          }}
        />
      </div>
      {tooLong && !voiceActive ? (
        <p
          id="gosari-composer-error"
          role="alert"
          className="col-span-3 text-base text-destructive"
        >
          메시지가 너무 깁니다. 2,000자 이내로 줄여 주세요.
        </p>
      ) : null}
      {!voiceActive || responding ? (
        <Button
          type="button"
          size="lg"
          onClick={
            responding
              ? () => {
                  void onStop?.();
                }
              : submit
          }
          disabled={
            responding ? stopping || !onStop : disabled || value.trim().length === 0 || tooLong
          }
          aria-label={responding ? "응답 중지" : "메시지 보내기"}
          aria-busy={responding && stopping}
          title={responding ? "응답 중지" : `메시지 보내기 (${formatHotkey("Mod+Enter")})`}
          className={`col-start-3 size-11 shrink-0 rounded-full p-0 ${expanded ? "row-start-2" : "row-start-1 self-center"}`}
        >
          {responding ? (
            <SquareIcon className="size-5" weight="fill" aria-hidden="true" />
          ) : (
            <ArrowUpIcon className="size-6" aria-hidden="true" />
          )}
        </Button>
      ) : null}
    </div>
  );
}
