import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AccountDialog } from "@/components/account-dialog";
import { ApiError } from "@/lib/gosari.api";

const ID_LABEL = /아이디/;
const PASSWORD_LABEL = /비밀번호/;
const LENGTH_HINT = /3~32자/;
const SIGNUP_SWITCH = /처음이에요/;
const calls = vi.hoisted(() => ({ login: vi.fn(), signup: vi.fn() }));
vi.mock("@/lib/gosari.api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/gosari.api")>();
  return { ...actual, api: { ...actual.api, login: calls.login, signup: calls.signup } };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function fill(loginId: string, password: string) {
  fireEvent.change(screen.getByLabelText(ID_LABEL), { target: { value: loginId } });
  fireEvent.change(screen.getByLabelText(PASSWORD_LABEL), { target: { value: password } });
}

it("logs in with a normalized id and reports the merged session", async () => {
  const state = { login_id: "gosari", session_id: "sess-home", merged: { contacts: 1 } };
  calls.login.mockResolvedValue(state);
  const onDone = vi.fn();
  render(<AccountDialog open onOpenChange={() => {}} onDone={onDone} />);
  fill(" Gosari ", "spring-2026!");
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  await waitFor(() => expect(onDone).toHaveBeenCalledWith(state));
  expect(calls.login).toHaveBeenCalledWith({ login_id: "gosari", password: "spring-2026!" });
});

it("switches to signup and validates before calling the server", async () => {
  render(<AccountDialog open onOpenChange={() => {}} onDone={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: SIGNUP_SWITCH }));
  expect(screen.getByRole("heading", { name: "회원가입" })).toBeTruthy();
  fill("ab", "short");
  fireEvent.click(screen.getByRole("button", { name: "가입하고 이어가기" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(LENGTH_HINT);
  expect(calls.signup).not.toHaveBeenCalled();
});

it("shows the safe message for a wrong password", async () => {
  calls.login.mockRejectedValue(new ApiError(401, "LOGIN_FAILED", "x"));
  render(<AccountDialog open onOpenChange={() => {}} onDone={() => {}} />);
  fill("gosari", "wrong-pass!");
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "아이디 또는 비밀번호가 맞지 않습니다."
  );
});
