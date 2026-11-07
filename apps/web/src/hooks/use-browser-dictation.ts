import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export type DictationStatus =
  | "idle"
  | "starting"
  | "listening"
  | "stopping"
  | "review"
  | "error"
  | "unsupported";
interface RecognitionResult {
  isFinal: boolean;
  [index: number]: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: { length: number; [index: number]: RecognitionResult };
}
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
interface RecognitionConstructor {
  new (): Recognition;
}
type VoiceWindow = Window & {
  AudioContext?: typeof AudioContext;
  SpeechRecognition?: RecognitionConstructor;
  webkitSpeechRecognition?: RecognitionConstructor;
  webkitAudioContext?: typeof AudioContext;
};
interface CaptureRun {
  originalText: string;
  segments: Map<number, string>;
  recognition: Recognition | null;
  stream: MediaStream | null;
  context: AudioContext | null;
  source: MediaStreamAudioSourceNode | null;
  analyser: AnalyserNode | null;
  frame: number | null;
  timer: ReturnType<typeof setTimeout> | null;
  finishing: boolean;
}
export interface BrowserDictationOptions {
  initialText: string;
  disabled?: boolean;
  onListeningChange?: (active: boolean) => void;
  onConfirm: (mergedText: string) => void;
  onCancel?: () => void;
  onLevels?: (levels: readonly number[]) => void;
}
const SILENCE = Array<number>(64).fill(0);
const TRAILING_SPACE = /\s$/u;
const ERROR_MESSAGES: Record<string, string> = {
  "not-allowed": "마이크 사용을 허용해 주세요.",
  NotAllowedError: "마이크 사용을 허용해 주세요.",
  SecurityError: "이 환경에서는 마이크를 사용할 수 없습니다.",
  "service-not-allowed": "이 브라우저에서는 음성 인식을 사용할 수 없습니다.",
  "audio-capture": "마이크를 찾을 수 없습니다.",
  NotFoundError: "마이크를 찾을 수 없습니다.",
  NotReadableError: "마이크를 사용할 수 없습니다. 다른 앱의 사용을 확인해 주세요.",
  "no-speech": "말소리를 듣지 못했습니다. 다시 눌러 주세요.",
  network: "브라우저 음성 인식에 연결하지 못했습니다.",
  "language-not-supported": "한국어 음성 인식을 사용할 수 없습니다.",
  aborted: "음성 입력이 중지되었습니다.",
};
function capabilities() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return null;
  const browser = window as VoiceWindow;
  const recognition = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
  const audio = browser.AudioContext ?? browser.webkitAudioContext;
  return recognition && audio && typeof navigator.mediaDevices?.getUserMedia === "function"
    ? { recognition, audio }
    : null;
}

export function mergeDictationText(draft: string, speech: string): string {
  const text = speech.trim();
  if (!text) return draft;
  return draft ? `${draft}${TRAILING_SPACE.test(draft) ? "" : " "}${text}` : text;
}
function transcriptFor(run: CaptureRun): string {
  return [...run.segments]
    .sort(([left], [right]) => left - right)
    .map(([, text]) => text.trim())
    .filter(Boolean)
    .join(" ");
}
function releaseAudio(run: CaptureRun): void {
  if (run.frame != null) cancelAnimationFrame(run.frame);
  run.frame = null;
  run.stream?.getTracks().forEach((track) => {
    track.stop();
  });
  run.stream = null;
  try {
    run.source?.disconnect();
  } catch {
    /* Already disconnected. */
  }
  try {
    run.analyser?.disconnect();
  } catch {
    /* Already disconnected. */
  }
  run.source = null;
  run.analyser = null;
  const context = run.context;
  run.context = null;
  if (context && context.state !== "closed") void context.close().catch(() => undefined);
}
function releaseRun(run: CaptureRun, abort = true): void {
  releaseAudio(run);
  if (run.timer != null) clearTimeout(run.timer);
  run.timer = null;
  const recognition = run.recognition;
  run.recognition = null;
  if (!recognition) return;
  recognition.onstart = null;
  recognition.onresult = null;
  recognition.onerror = null;
  recognition.onend = null;
  if (abort) {
    try {
      recognition.abort();
    } catch {
      /* The browser may already have ended recognition. */
    }
  }
}

export function useBrowserDictation(options: BrowserDictationOptions) {
  const supported = Boolean(capabilities());
  const [status, setStatus] = useState<DictationStatus>(supported ? "idle" : "unsupported");
  const [error, setError] = useState<string | null>(
    supported ? null : "이 브라우저에서는 음성 입력을 사용할 수 없습니다."
  );
  const [transcript, setTranscript] = useState("");
  const levels = useRef<readonly number[]>(SILENCE);
  const current = useRef<CaptureRun | null>(null);
  const mounted = useRef(true);
  const callbacks = useRef(options);
  useLayoutEffect(() => {
    callbacks.current = options;
  });
  const updateLevels = useCallback((next: readonly number[]) => {
    levels.current = next;
    callbacks.current.onLevels?.(next);
  }, []);
  const active =
    status === "starting" || status === "listening" || status === "stopping" || status === "review";

  const cancel = useCallback(() => {
    const run = current.current;
    current.current = null;
    if (run) releaseRun(run);
    updateLevels(SILENCE);
    setTranscript("");
    setError(null);
    setStatus(capabilities() ? "idle" : "unsupported");
    if (run) callbacks.current.onCancel?.();
  }, [updateLevels]);
  const fail = useCallback(
    (run: CaptureRun, code: string) => {
      if (!mounted.current || current.current !== run) return;
      const text = transcriptFor(run);
      if (text) {
        releaseRun(run);
        run.finishing = false;
        updateLevels(SILENCE);
        setTranscript(text);
        setError(null);
        setStatus("review");
        return;
      }
      current.current = null;
      releaseRun(run);
      updateLevels(SILENCE);
      setError(ERROR_MESSAGES[code] ?? "음성 입력을 시작하지 못했습니다. 다시 눌러 주세요.");
      setStatus("error");
    },
    [updateLevels]
  );
  const commit = useCallback(
    (run: CaptureRun) => {
      if (!mounted.current || current.current !== run) return;
      const text = transcriptFor(run);
      current.current = null;
      releaseRun(run);
      updateLevels(SILENCE);
      if (!text) {
        setError(ERROR_MESSAGES["no-speech"]);
        setStatus("error");
        return;
      }
      setTranscript("");
      setError(null);
      setStatus("idle");
      callbacks.current.onConfirm(mergeDictationText(run.originalText, text));
    },
    [updateLevels]
  );
  const finish = useCallback(() => {
    const run = current.current;
    if (!run || run.finishing) return;
    run.finishing = true;
    releaseAudio(run);
    updateLevels(SILENCE);
    setStatus("stopping");
    if (!run.recognition) {
      commit(run);
      return;
    }
    if (run.timer != null) clearTimeout(run.timer);
    run.timer = setTimeout(() => commit(run), 1500);
    try {
      run.recognition.stop();
    } catch {
      commit(run);
    }
  }, [commit, updateLevels]);

  const start = useCallback(async () => {
    if (callbacks.current.disabled || current.current) return;
    const available = capabilities();
    if (!available) {
      setStatus("unsupported");
      setError("이 브라우저에서는 음성 입력을 사용할 수 없습니다.");
      return;
    }
    const run: CaptureRun = {
      originalText: callbacks.current.initialText,
      segments: new Map(),
      recognition: null,
      stream: null,
      context: null,
      source: null,
      analyser: null,
      frame: null,
      timer: null,
      finishing: false,
    };
    current.current = run;
    setStatus("starting");
    setError(null);
    setTranscript("");
    updateLevels(SILENCE);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      if (!mounted.current || current.current !== run) {
        stream.getTracks().forEach((track) => {
          track.stop();
        });
        return;
      }
      run.stream = stream;
      const context = new available.audio();
      run.context = context;
      if (context.state === "suspended") await context.resume();
      if (!mounted.current || current.current !== run) {
        releaseAudio(run);
        return;
      }
      const analyser = context.createAnalyser();
      analyser.fftSize = 1024;
      run.analyser = analyser;
      const source = context.createMediaStreamSource(stream);
      run.source = source;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const reducedMotion =
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
      let lastSample = -Infinity;
      const sample = (timestamp: number) => {
        if (!mounted.current || current.current !== run || !run.analyser) return;
        if (timestamp - lastSample >= (reducedMotion ? 200 : 50)) {
          lastSample = timestamp;
          try {
            analyser.getByteTimeDomainData(samples);
          } catch {
            fail(run, "audio-capture");
            return;
          }
          const bars = SILENCE.map((_, index) => {
            const first = Math.floor((index * samples.length) / SILENCE.length);
            const last = Math.floor(((index + 1) * samples.length) / SILENCE.length);
            let energy = 0;
            for (let position = first; position < last; position++)
              energy += ((samples[position] - 128) / 128) ** 2;
            return Math.min(1, Math.sqrt(energy / Math.max(1, last - first)) * 3);
          });
          updateLevels(bars);
        }
        run.frame = requestAnimationFrame(sample);
      };
      run.frame = requestAnimationFrame(sample);
      const recognition = new available.recognition();
      run.recognition = recognition;
      recognition.lang = "ko-KR";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.onstart = () => {
        if (current.current !== run || !mounted.current || run.recognition !== recognition) return;
        setStatus("listening");
      };
      recognition.onresult = (event) => {
        if (current.current !== run || !mounted.current || run.recognition !== recognition) return;
        for (const index of run.segments.keys())
          if (index >= event.results.length) run.segments.delete(index);
        for (let index = event.resultIndex; index < event.results.length; index++)
          run.segments.set(index, event.results[index][0]?.transcript ?? "");
        setTranscript(transcriptFor(run));
      };
      recognition.onerror = (event) => {
        if (run.recognition === recognition) fail(run, event.error);
      };
      recognition.onend = () => {
        if (current.current !== run || !mounted.current || run.recognition !== recognition) return;
        if (run.finishing) {
          commit(run);
          return;
        }
        releaseRun(run, false);
        updateLevels(SILENCE);
        if (transcriptFor(run)) setStatus("review");
        else fail(run, "no-speech");
      };
      recognition.start();
    } catch (cause) {
      fail(run, cause instanceof Error ? cause.name : "unknown");
    }
  }, [commit, fail, updateLevels]);

  useEffect(() => {
    callbacks.current.onListeningChange?.(active);
  }, [active]);
  useEffect(() => {
    if (options.disabled && current.current) cancel();
  }, [options.disabled, cancel]);
  useEffect(() => {
    mounted.current = true;
    const hide = () => {
      if (document.visibilityState === "hidden" && current.current) cancel();
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      mounted.current = false;
      document.removeEventListener("visibilitychange", hide);
      const run = current.current;
      current.current = null;
      if (run) releaseRun(run);
    };
  }, [cancel]);
  return {
    status,
    supported,
    active,
    transcript,
    error,
    levelsRef: levels,
    start,
    finish,
    cancel,
  };
}
