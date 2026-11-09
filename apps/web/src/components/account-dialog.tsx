import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/gosari.api";
import type { AccountState } from "@/lib/gosari.types";

type Mode = "login" | "signup";

interface AccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: (state: AccountState) => void;
}

const LOGIN_ID_PATTERN = /^[a-z0-9_]{3,32}$/;

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "LOGIN_FAILED") return "아이디 또는 비밀번호가 맞지 않습니다.";
    if (error.code === "LOGIN_ID_TAKEN") return "이미 사용 중인 아이디입니다.";
    if (error.code === "LOCAL_BUSY") return "시도가 많습니다. 잠시 후 다시 해 주세요.";
    if (error.code === "INVALID_INPUT")
      return "아이디는 영문 소문자·숫자·밑줄 3~32자, 비밀번호는 8자 이상이어야 합니다.";
    return error.message;
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

export function AccountDialog({ open, onOpenChange, onDone }: AccountDialogProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idField = useId();
  const passwordField = useId();

  function reset() {
    setLoginId("");
    setPassword("");
    setError(null);
    setBusy(false);
  }

  async function submit() {
    if (busy) return;
    const normalized = loginId.trim().toLowerCase();
    if (!LOGIN_ID_PATTERN.test(normalized)) {
      setError("아이디는 영문 소문자·숫자·밑줄 3~32자입니다.");
      return;
    }
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = { login_id: normalized, password };
      const state = mode === "signup" ? await api.signup(body) : await api.login(body);
      reset();
      onOpenChange(false);
      onDone(state);
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  }

  const signup = mode === "signup";

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
          className="flex flex-col gap-4"
        >
          <DialogHeader>
            <DialogTitle>{signup ? "회원가입" : "로그인"}</DialogTitle>
            <DialogDescription>
              {signup
                ? "가입하면 지금까지 이 브라우저에 쌓인 수첩·관심 장소·지인·나눔 기록이 회원 기록으로 이어집니다."
                : "로그인하면 이 브라우저의 기록이 회원 기록에 합쳐지고, 다른 기기에서도 같은 기록을 봅니다."}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor={idField} required>
              아이디
            </Label>
            <Input
              id={idField}
              name="login_id"
              autoComplete="username"
              autoCapitalize="none"
              value={loginId}
              onChange={(event) => setLoginId(event.target.value)}
              disabled={busy}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={passwordField} required>
              비밀번호
            </Label>
            <Input
              id={passwordField}
              name="password"
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={busy}
              required
            />
          </div>
          {error ? (
            <p role="alert" className="text-base text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter className="items-center justify-between gap-2 sm:justify-between">
            <Button
              type="button"
              variant="link"
              disabled={busy}
              onClick={() => {
                setMode(signup ? "login" : "signup");
                setError(null);
              }}
            >
              {signup ? "이미 계정이 있어요" : "처음이에요, 가입할게요"}
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "처리 중…" : signup ? "가입하고 이어가기" : "로그인"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
