import { useAtom, useSetAtom } from "jotai";
import { useEffect } from "react";
import { ChatShell } from "./components/ChatShell";
import { Lnb } from "./components/Lnb";
import { api } from "./lib/api";
import { capabilitiesAtom, lnbOpenAtom, sessionEndedAtom, sessionReadyAtom } from "./stores/app";

export function App() {
  const [sessionReady, setSessionReady] = useAtom(sessionReadyAtom);
  const [sessionEnded, setSessionEnded] = useAtom(sessionEndedAtom);
  const setCapabilities = useSetAtom(capabilitiesAtom);
  const [lnbOpen, setLnbOpen] = useAtom(lnbOpenAtom);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        await api.createSession();
        const caps = await api.capabilities();
        if (!cancelled) {
          setCapabilities(caps);
          setSessionReady(true);
        }
      } catch {
        if (!cancelled) setSessionReady(true);
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [setCapabilities, setSessionReady]);

  async function endSession() {
    try {
      await api.endSession();
    } finally {
      setSessionEnded(true);
    }
  }

  if (sessionEnded) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md text-center">
          <h1 className="mb-4 text-2xl font-bold">세션이 종료되었습니다</h1>
          <p className="mb-6 text-base text-gray-600">
            개인 기록·초안·승인이 정리되었습니다. 이전 세션은 복구되지 않습니다.
          </p>
          <button
            type="button"
            className="rounded-lg bg-green-700 px-6 py-3 text-base font-semibold text-white hover:bg-green-800"
            onClick={() => window.location.reload()}
          >
            새로 시작
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <Lnb open={lnbOpen} onToggle={() => setLnbOpen((v) => !v)} onEndSession={endSession} />
      <main className="flex min-w-0 flex-1 flex-col" aria-label="대화 작업 공간">
        {!sessionReady ? (
          <div className="flex flex-1 items-center justify-center text-gray-500">세션 준비 중…</div>
        ) : (
          <ChatShell />
        )}
      </main>
    </div>
  );
}
