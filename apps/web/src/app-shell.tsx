import { useQueryClient } from "@tanstack/react-query";
import { useAtom, useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";
import { AccountDialog } from "@/components/account-dialog";
import { ChatShell } from "@/components/chat-shell";
import { MainSideNavigation } from "@/components/main-side-navigation";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/gosari.api";
import {
  accountLoginIdAtom,
  capabilitiesAtom,
  lnbOpenAtom,
  sessionEndedAtom,
  sessionReadyAtom,
} from "@/stores/chat.atoms";

export function AppShell() {
  const queryClient = useQueryClient();
  const [sessionReady, setSessionReady] = useAtom(sessionReadyAtom);
  const [sessionEnded, setSessionEnded] = useAtom(sessionEndedAtom);
  const setCapabilities = useSetAtom(capabilitiesAtom);
  const [lnbOpen, setLnbOpen] = useAtom(lnbOpenAtom);
  const [loginId, setLoginId] = useAtom(accountLoginIdAtom);
  const [accountOpen, setAccountOpen] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const cancelReset = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        await api.createSession();
        const caps = await api.capabilities();
        const account = await api.accountMe().catch(() => null);
        if (!cancelled) {
          setCapabilities(caps);
          setLoginId(account?.login_id ?? null);
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
  }, [setCapabilities, setLoginId, setSessionReady]);

  async function endSession() {
    if (resetBusy) return;
    setResetBusy(true);
    setResetError(null);
    try {
      await api.endSession();
      queryClient.clear();
      setResetOpen(false);
      setSessionEnded(true);
    } catch {
      setResetError("개인 기록을 초기화하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setResetBusy(false);
    }
  }

  async function logout() {
    try {
      await api.logout();
    } finally {
      queryClient.clear();
      window.location.reload();
    }
  }

  if (sessionEnded) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md rounded-2xl border border-border bg-card p-6 text-center shadow-sm">
          <h1 className="mb-3 text-2xl font-bold text-foreground">개인 기록이 초기화되었습니다</h1>
          <p className="mb-6 text-base text-muted-foreground">
            수첩·관심 지역·나눔 목록이 삭제되었습니다.
          </p>
          <Button size="lg" onClick={() => window.location.reload()}>
            새로 시작하기
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden md:flex-row">
      <MainSideNavigation
        open={lnbOpen}
        onToggle={() => setLnbOpen((v) => !v)}
        onEndSession={() => {
          setResetError(null);
          setResetOpen(true);
        }}
        loginId={loginId}
        onOpenAccount={() => setAccountOpen(true)}
        onLogout={() => void logout()}
      />
      <main
        className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
        aria-label="대화 작업 공간"
      >
        {resetError && !resetOpen ? (
          <p role="alert" className="bg-destructive/10 px-4 py-3 text-base text-destructive">
            {resetError}
          </p>
        ) : null}
        {!sessionReady ? (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            불러오는 중…
          </div>
        ) : (
          <ChatShell />
        )}
      </main>
      <AccountDialog
        open={accountOpen}
        onOpenChange={setAccountOpen}
        onDone={() => {
          queryClient.clear();
          window.location.reload();
        }}
      />
      <Dialog
        open={resetOpen}
        onOpenChange={(open) => {
          if (!resetBusy) setResetOpen(open);
        }}
      >
        <DialogContent initialFocus={cancelReset} showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>개인 기록을 초기화할까요?</DialogTitle>
            <DialogDescription>수첩·관심 지역·지인·나눔 기록을 모두 삭제합니다.</DialogDescription>
          </DialogHeader>
          {resetError ? (
            <p role="alert" className="text-base text-destructive">
              {resetError}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              ref={cancelReset}
              variant="outline"
              disabled={resetBusy}
              onClick={() => setResetOpen(false)}
            >
              취소
            </Button>
            <Button variant="destructive" disabled={resetBusy} onClick={() => void endSession()}>
              {resetBusy ? "삭제 중…" : "모두 삭제"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
