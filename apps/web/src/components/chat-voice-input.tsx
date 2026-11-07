import { CheckIcon, MicrophoneIcon, XIcon } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { type BrowserDictationOptions, useBrowserDictation } from "@/hooks/use-browser-dictation";

export type ChatVoiceInputProps = Omit<BrowserDictationOptions, "onLevels">;
const WAVEFORM_BARS = Array.from({ length: 64 }, (_, index) => ({
  id: `audio-bar-${index}`,
  index,
}));

export function ChatVoiceInput(props: ChatVoiceInputProps) {
  const waveform = useRef<SVGSVGElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const paintWaveform = useCallback((levels: readonly number[]) => {
    waveform.current?.querySelectorAll("rect").forEach((bar, index) => {
      const height = Math.max(2, (levels[index] ?? 0) * 36);
      bar.setAttribute("height", String(height));
      bar.setAttribute("y", String((40 - height) / 2));
    });
  }, []);
  const dictation = useBrowserDictation({ ...props, onLevels: paintWaveform });
  useEffect(() => {
    if (!dictation.active) return;
    cancelButton.current?.focus({ preventScroll: true });
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      dictation.cancel();
    };
    document.addEventListener("keydown", dismissOnEscape);
    return () => document.removeEventListener("keydown", dismissOnEscape);
  }, [dictation.active, dictation.cancel]);
  const [showError, setShowError] = useState(false);
  if (!dictation.active)
    return (
      <div className="relative w-11 shrink-0">
        <Button
          type="button"
          variant="ghost"
          className="size-11 shrink-0 rounded-full p-0"
          disabled={props.disabled || !dictation.supported}
          aria-label={dictation.supported ? "음성으로 입력" : "음성 입력 미지원"}
          title={dictation.supported ? "음성으로 입력" : "음성 입력 미지원"}
          onClick={() => {
            setShowError(true);
            void dictation.start();
          }}
        >
          <MicrophoneIcon aria-hidden="true" className="size-6" />
        </Button>
        {showError && dictation.supported && dictation.error ? (
          <p
            role="alert"
            className="absolute right-0 bottom-full z-20 mb-2 w-max max-w-[min(20rem,calc(100vw-3rem))] rounded-lg border border-border bg-card p-3 text-base text-destructive shadow-sm"
          >
            {dictation.error}
          </p>
        ) : null}
      </div>
    );
  const status = {
    starting: "마이크 연결 중…",
    listening: "듣고 있습니다…",
    stopping: "받아쓴 내용 확인 중…",
    review: "받아쓴 내용을 확인해 주세요.",
  }[dictation.status as "starting" | "listening" | "stopping" | "review"];
  return (
    <section className="flex w-full min-w-0 flex-1 flex-col gap-2 px-1 py-1" aria-label="음성 입력">
      {dictation.status !== "starting" ? (
        <svg
          ref={waveform}
          viewBox="0 0 640 40"
          preserveAspectRatio="none"
          className="h-10 w-full text-primary"
          aria-hidden="true"
        >
          {WAVEFORM_BARS.map((bar) => (
            <rect
              key={bar.id}
              x={bar.index * 10 + 2}
              y={19}
              width={6}
              height={2}
              rx={3}
              fill="currentColor"
            />
          ))}
        </svg>
      ) : null}
      <div className="flex min-w-0 items-center gap-2">
        <div className="min-w-0 flex-1">
          <p role="status" className="text-base leading-6 text-muted-foreground">
            {status}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            ref={cancelButton}
            type="button"
            variant="outline"
            className="size-11 rounded-full p-0"
            aria-label="음성 입력 취소"
            title="음성 입력 취소"
            onClick={dictation.cancel}
          >
            <XIcon aria-hidden="true" />
          </Button>
          {dictation.status !== "starting" ? (
            <Button
              type="button"
              className="size-11 rounded-full p-0"
              aria-label="입력란에 넣기"
              title="받아쓴 내용을 입력란에 넣기"
              disabled={dictation.status === "stopping" || !dictation.transcript.trim()}
              onClick={dictation.finish}
            >
              <CheckIcon aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      </div>
      {dictation.transcript ? (
        <Textarea
          readOnly
          value={dictation.transcript}
          rows={1}
          className="field-sizing-fixed h-6 min-h-6 max-h-6 resize-none overflow-y-auto rounded-none border-0 bg-transparent p-0 text-base leading-6 shadow-none md:text-base"
          aria-label="받아쓴 내용"
        />
      ) : null}
    </section>
  );
}
