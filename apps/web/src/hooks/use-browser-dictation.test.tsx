import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mergeDictationText, useBrowserDictation } from "@/hooks/use-browser-dictation";

type ResultEvent = {
  resultIndex: number;
  results: { isFinal: boolean; 0: { transcript: string } }[];
};
class FakeRecognition {
  static available: ReturnType<typeof vi.fn> | undefined;
  static install: ReturnType<typeof vi.fn> | undefined;
  static autoStart = true;
  static instances: FakeRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 0;
  processLocally = false;
  onstart: (() => void) | null = null;
  onresult: ((event: ResultEvent) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn(() => {
    if (FakeRecognition.autoStart) this.onstart?.();
  });
  stop = vi.fn();
  abort = vi.fn();
  constructor() {
    FakeRecognition.instances.push(this);
  }
  result(text: string[], resultIndex = 0, final = true) {
    this.onresult?.({
      resultIndex,
      results: text.map((transcript) => ({ isFinal: final, 0: { transcript } })),
    });
  }
}
const readAudio = vi.fn((buffer: Uint8Array) => {
  buffer.fill(128);
});
const source = { connect: vi.fn(), disconnect: vi.fn() };
const analyser = { fftSize: 1024, getByteTimeDomainData: readAudio, disconnect: vi.fn() };
class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state = "running";
  resume = vi.fn(async () => undefined);
  close = vi.fn(async () => {
    this.state = "closed";
  });
  createAnalyser = vi.fn(() => analyser);
  createMediaStreamSource = vi.fn(() => source);
  constructor() {
    FakeAudioContext.instances.push(this);
  }
}
const track = { stop: vi.fn() };
const stream = { getTracks: () => [track] };
const getUserMedia = vi.fn(async () => stream);
let frames = new Map<number, FrameRequestCallback>();
let nextFrame = 0;

beforeEach(() => {
  vi.clearAllMocks();
  FakeRecognition.instances = [];
  FakeRecognition.available = undefined;
  FakeRecognition.install = undefined;
  FakeRecognition.autoStart = true;
  FakeAudioContext.instances = [];
  frames = new Map();
  nextFrame = 0;
  getUserMedia.mockImplementation(async () => stream);
  readAudio.mockImplementation((buffer) => {
    buffer.fill(128);
  });
  vi.stubGlobal("SpeechRecognition", FakeRecognition);
  vi.stubGlobal("webkitSpeechRecognition", undefined);
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia }, userAgent: "hermetic-voice-test" });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    const id = ++nextFrame;
    frames.set(id, callback);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    frames.delete(id);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
function sample(timestamp: number) {
  const pending = [...frames];
  frames.clear();
  for (const [, callback] of pending) callback(timestamp);
}

describe("browser dictation", () => {
  it("starts the browser default Korean recognition without checking or installing language packs", async () => {
    FakeRecognition.available = vi.fn(() => {
      throw new Error("availability must not be queried");
    });
    FakeRecognition.install = vi.fn(() => {
      throw new Error("language packs must not be installed");
    });
    const active = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "초안", onConfirm: vi.fn(), onListeningChange: active })
    );
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    expect(recognition.start).toHaveBeenCalledExactlyOnceWith();
    expect(recognition.lang).toBe("ko-KR");
    expect(recognition.continuous).toBe(true);
    expect(recognition.interimResults).toBe(true);
    expect(recognition.processLocally).toBe(false);
    expect(FakeRecognition.available).not.toHaveBeenCalled();
    expect(FakeRecognition.install).not.toHaveBeenCalled();
    expect(getUserMedia).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("listening");
    expect(active).toHaveBeenLastCalledWith(true);
    await act(() => result.current.start());
    expect(recognition.start).toHaveBeenCalledOnce();
    act(() => result.current.cancel());
    await act(() => result.current.start());
    expect(FakeRecognition.instances[1].processLocally).toBe(false);
    expect(FakeRecognition.instances[1].start).toHaveBeenCalledExactlyOnceWith();
    expect(FakeRecognition.available).not.toHaveBeenCalled();
    expect(FakeRecognition.install).not.toHaveBeenCalled();
  });

  it("uses the prefixed browser recognition API when the standard constructor is absent", async () => {
    vi.stubGlobal("SpeechRecognition", undefined);
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "", onConfirm: vi.fn() })
    );
    await act(() => result.current.start());
    expect(result.current.status).toBe("listening");
    expect(FakeRecognition.instances[0].lang).toBe("ko-KR");
    expect(FakeRecognition.instances[0].start).toHaveBeenCalledExactlyOnceWith();
  });

  it("cancels pending microphone access and stops a late stream without starting recognition", async () => {
    let deliver!: (value: typeof stream) => void;
    getUserMedia.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          deliver = resolve;
        })
    );
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "초안", onConfirm: vi.fn() })
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.start();
    });
    act(() => result.current.cancel());
    await act(async () => {
      deliver(stream);
      await pending;
    });
    expect(result.current.status).toBe("idle");
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances).toHaveLength(0);
  });

  it("keeps partial speech reviewable after an error and ignores late results", async () => {
    const confirm = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "초안", onConfirm: confirm })
    );
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    const lateResult = recognition.onresult;
    act(() => recognition.result(["제주 날씨"]));
    act(() => recognition.onerror?.({ error: "network" }));
    expect(result.current.status).toBe("review");
    expect(result.current.transcript).toBe("제주 날씨");
    expect(track.stop).toHaveBeenCalledOnce();
    act(() =>
      lateResult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "늦은 변경" } }] })
    );
    expect(result.current.transcript).toBe("제주 날씨");
    act(() => result.current.finish());
    expect(confirm).toHaveBeenCalledExactlyOnceWith("초안 제주 날씨");
  });

  it("uses Korean continuous/interim recognition and measured microphone samples", async () => {
    const confirm = vi.fn();
    const renders = vi.fn();
    const { result } = renderHook(() => {
      renders();
      return useBrowserDictation({ initialText: "기존 초안", onConfirm: confirm });
    });
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    expect(recognition.lang).toBe("ko-KR");
    expect(recognition.continuous).toBe(true);
    expect(recognition.interimResults).toBe(true);
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: { echoCancellation: true, noiseSuppression: true },
      video: false,
    });
    expect(result.current.status).toBe("listening");
    const renderCount = renders.mock.calls.length;
    act(() => sample(0));
    expect(result.current.levelsRef.current.every((level) => level === 0)).toBe(true);
    readAudio.mockImplementation((buffer) => {
      buffer.fill(192);
    });
    act(() => sample(100));
    expect(result.current.levelsRef.current.every((level) => level > 0)).toBe(true);
    expect(renders).toHaveBeenCalledTimes(renderCount);
    expect(readAudio).toHaveBeenCalledTimes(2);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("waits for final results after stop and merges once without duplicating interim text", async () => {
    const confirm = vi.fn();
    const active = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({
        initialText: "내 초안\n",
        onConfirm: confirm,
        onListeningChange: active,
      })
    );
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    act(() => recognition.result(["제주 날"], 0, false));
    act(() => recognition.result(["제주 날씨", "알려"], 0, false));
    act(() => result.current.finish());
    expect(recognition.stop).toHaveBeenCalledOnce();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
    act(() => recognition.result(["제주 날씨", "알려줘"], 1));
    act(() => recognition.onend?.());
    expect(confirm).toHaveBeenCalledExactlyOnceWith("내 초안\n제주 날씨 알려줘");
    expect(result.current.status).toBe("idle");
    expect(frames.size).toBe(0);
    expect(active).toHaveBeenLastCalledWith(false);
  });

  it("cancels without changing the draft and ignores late recognition events", async () => {
    const confirm = vi.fn();
    const cancel = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "한글 초안", onConfirm: confirm, onCancel: cancel })
    );
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    const lateResult = recognition.onresult;
    const lateEnd = recognition.onend;
    act(() => recognition.result(["덧붙일 문장"]));
    act(() => result.current.cancel());
    act(() => {
      lateResult?.({
        resultIndex: 0,
        results: [{ isFinal: true, 0: { transcript: "늦은 결과" } }],
      });
      lateEnd?.();
    });
    expect(confirm).not.toHaveBeenCalled();
    expect(cancel).toHaveBeenCalledOnce();
    expect(recognition.abort).toHaveBeenCalledOnce();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledOnce();
    expect(result.current.transcript).toBe("");
    expect(frames.size).toBe(0);
  });

  it("releases capture when recognition ends and waits for explicit confirmation", async () => {
    const confirm = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "기존", onConfirm: confirm })
    );
    await act(() => result.current.start());
    const recognition = FakeRecognition.instances[0];
    act(() => {
      recognition.result(["문장"]);
      recognition.onend?.();
    });
    expect(result.current.status).toBe("review");
    expect(track.stop).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
    act(() => result.current.finish());
    expect(confirm).toHaveBeenCalledExactlyOnceWith("기존 문장");
  });

  it.each([
    ["not-allowed", "마이크 사용을 허용해 주세요."],
    ["no-speech", "말소리를 듣지 못했습니다. 다시 눌러 주세요."],
    ["network", "브라우저 음성 인식에 연결하지 못했습니다."],
  ])("cleans up and reports %s accurately", async (code, message) => {
    const confirm = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "원문", onConfirm: confirm })
    );
    await act(() => result.current.start());
    act(() => FakeRecognition.instances[0].onerror?.({ error: code }));
    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe(message);
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("handles denied microphone access before constructing recognition", async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException("denied", "NotAllowedError"));
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "원문", onConfirm: vi.fn() })
    );
    await act(() => result.current.start());
    expect(result.current.error).toBe("마이크 사용을 허용해 주세요.");
    expect(FakeRecognition.instances).toHaveLength(0);
    expect(FakeAudioContext.instances).toHaveLength(0);
  });

  it("closes a stream that arrives after cancellation or unmount", async () => {
    let deliver: ((value: typeof stream) => void) | undefined;
    getUserMedia.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          deliver = resolve;
        })
    );
    const { result, unmount } = renderHook(() =>
      useBrowserDictation({ initialText: "원문", onConfirm: vi.fn() })
    );
    let starting: Promise<void> | undefined;
    act(() => {
      starting = result.current.start();
    });
    unmount();
    await act(async () => {
      deliver?.(stream);
      await starting;
    });
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeAudioContext.instances).toHaveLength(0);
    expect(FakeRecognition.instances).toHaveLength(0);
  });

  it("cancels and releases every resource when the page becomes hidden", async () => {
    const confirm = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "원문", onConfirm: confirm })
    );
    await act(() => result.current.start());
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances[0].abort).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
    expect(result.current.active).toBe(false);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("preserves the draft and cancels capture when the composer becomes disabled", async () => {
    const confirm = vi.fn();
    const cancel = vi.fn();
    const { result, rerender } = renderHook(
      ({ disabled }) =>
        useBrowserDictation({
          initialText: "원래 초안",
          disabled,
          onConfirm: confirm,
          onCancel: cancel,
        }),
      { initialProps: { disabled: false } }
    );
    await act(() => result.current.start());
    act(() => FakeRecognition.instances[0].result(["작성 중"]));
    rerender({ disabled: true });
    expect(result.current.active).toBe(false);
    expect(cancel).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances[0].abort).toHaveBeenCalledOnce();
  });

  it("releases active microphone, recognition, context and animation on unmount", async () => {
    const { result, unmount } = renderHook(() =>
      useBrowserDictation({ initialText: "", onConfirm: vi.fn() })
    );
    await act(() => result.current.start());
    unmount();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances[0].abort).toHaveBeenCalledOnce();
    expect(FakeAudioContext.instances[0].close).toHaveBeenCalledOnce();
    expect(source.disconnect).toHaveBeenCalledOnce();
    expect(analyser.disconnect).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
  });

  it("closes capture on an analyser failure instead of leaving a frozen live microphone", async () => {
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "", onConfirm: vi.fn() })
    );
    await act(() => result.current.start());
    readAudio.mockImplementationOnce(() => {
      throw new Error("unavailable");
    });
    act(() => sample(0));
    expect(result.current.status).toBe("error");
    expect(track.stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances[0].abort).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
  });

  it("finishes once even if the recognition vendor never sends its final end event", async () => {
    vi.useFakeTimers();
    const confirm = vi.fn();
    const { result } = renderHook(() =>
      useBrowserDictation({ initialText: "기존", onConfirm: confirm })
    );
    await act(() => result.current.start());
    act(() => FakeRecognition.instances[0].result(["받아쓴 문장"]));
    act(() => {
      result.current.finish();
      result.current.finish();
    });
    act(() => vi.advanceTimersByTime(1500));
    expect(confirm).toHaveBeenCalledExactlyOnceWith("기존 받아쓴 문장");
    expect(FakeRecognition.instances[0].stop).toHaveBeenCalledOnce();
    expect(FakeRecognition.instances[0].abort).toHaveBeenCalledOnce();
    expect(track.stop).toHaveBeenCalledOnce();
    expect(frames.size).toBe(0);
  });

  it("supports webkit recognition and refuses unsupported environments without recording", async () => {
    vi.stubGlobal("SpeechRecognition", undefined);
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    const webkit = renderHook(() => useBrowserDictation({ initialText: "", onConfirm: vi.fn() }));
    expect(webkit.result.current.supported).toBe(true);
    webkit.unmount();
    vi.stubGlobal("webkitSpeechRecognition", undefined);
    const unsupported = renderHook(() =>
      useBrowserDictation({ initialText: "", onConfirm: vi.fn() })
    );
    await act(() => unsupported.result.current.start());
    expect(unsupported.result.current.status).toBe("unsupported");
    expect(unsupported.result.current.error).toContain("음성 입력을 사용할 수 없습니다");
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it("preserves draft whitespace and does not invent text for an empty result", () => {
    expect(mergeDictationText("기존\n", " 음성 ")).toBe("기존\n음성");
    expect(mergeDictationText("기존", "음성")).toBe("기존 음성");
    expect(mergeDictationText("한글 작성중", " ")).toBe("한글 작성중");
  });
});
