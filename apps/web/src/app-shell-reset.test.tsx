import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppShell } from "@/app-shell";
import { api } from "@/lib/gosari.api";
import { sessionReadyAtom } from "@/stores/chat.atoms";

vi.mock("@/components/chat-shell", () => ({ ChatShell: () => <p>기존 개인 기록 화면</p> }));
let queryClient: QueryClient;
beforeEach(() => {
  window.history.replaceState({}, "", "/");
  queryClient = new QueryClient();
  queryClient.setQueryData(["personal-records"], ["retained-record"]);
  vi.spyOn(api, "createSession").mockResolvedValue({
    session_id: "test-session",
    expires_at: "later",
  });
  vi.spyOn(api, "capabilities").mockResolvedValue({} as never);
});
afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.restoreAllMocks();
});
function mount() {
  const store = createStore();
  store.set(sessionReadyAtom, true);
  render(
    <QueryClientProvider client={queryClient}>
      <Provider store={store}>
        <AppShell />
      </Provider>
    </QueryClientProvider>
  );
}
async function openReset() {
  fireEvent.click(screen.getByRole("button", { name: "설정" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "개인 기록 초기화" }));
  return screen.findByRole("dialog", { name: "개인 기록을 초기화할까요?" });
}
it("requires a separate confirmation, focuses cancel and makes cancel leave records intact", async () => {
  const end = vi.spyOn(api, "endSession").mockResolvedValue({ ended: true });
  mount();
  const dialog = await openReset();
  expect(end).not.toHaveBeenCalled();
  const cancel = within(dialog).getByRole("button", { name: "취소" });
  await waitFor(() => expect(document.activeElement).toBe(cancel));
  fireEvent.click(cancel);
  expect(end).not.toHaveBeenCalled();
  expect(queryClient.getQueryData(["personal-records"])).toEqual(["retained-record"]);
  expect(screen.getByText("기존 개인 기록 화면")).toBeTruthy();
});
it("deletes and clears the cache only after explicit confirmation", async () => {
  const end = vi.spyOn(api, "endSession").mockResolvedValue({ ended: true });
  const clear = vi.spyOn(queryClient, "clear");
  mount();
  const dialog = await openReset();
  fireEvent.click(within(dialog).getByRole("button", { name: "모두 삭제" }));
  await screen.findByRole("heading", { name: "개인 기록이 초기화되었습니다" });
  expect(end).toHaveBeenCalledTimes(1);
  expect(clear).toHaveBeenCalledTimes(1);
});
it("keeps the current records and cache visible when reset fails", async () => {
  vi.spyOn(api, "endSession").mockRejectedValue(new Error("unavailable"));
  const clear = vi.spyOn(queryClient, "clear");
  mount();
  const dialog = await openReset();
  fireEvent.click(within(dialog).getByRole("button", { name: "모두 삭제" }));
  await within(dialog).findByRole("alert");
  expect(clear).not.toHaveBeenCalled();
  expect(queryClient.getQueryData(["personal-records"])).toEqual(["retained-record"]);
  expect(screen.getByText("기존 개인 기록 화면")).toBeTruthy();
  expect(
    (within(dialog).getByRole("button", { name: "모두 삭제" }) as HTMLButtonElement).disabled
  ).toBe(false);
});
