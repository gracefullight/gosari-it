import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "jotai";
import { afterEach, expect, it, vi } from "vitest";
import { MainSideNavigation } from "@/components/main-side-navigation";

const QUICK_MENU = /빠른 메뉴/;
const chat = vi.hoisted(() => ({ openFeature: vi.fn(), resetConversation: vi.fn() }));
vi.mock("@/hooks/use-chat", () => ({ useChat: () => chat }));
vi.mock("@/components/onboarding-guide", () => ({ OnboardingGuide: () => null }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
});

function setup(open = true) {
  const onEndSession = vi.fn();
  const onToggle = vi.fn();
  const view = render(
    <Provider>
      <MainSideNavigation open={open} onToggle={onToggle} onEndSession={onEndSession} />
    </Provider>
  );
  return { ...view, onEndSession, onToggle };
}

it("shows the shortcut in expanded and collapsed menus without duplicate global handlers", () => {
  const { rerender, onToggle, onEndSession } = setup();
  const nav = screen.getByRole("navigation", { name: "주 메뉴" });
  expect(within(nav).getByRole("button", { name: QUICK_MENU }).textContent).toContain("Ctrl+K");
  const newConversation = within(nav).getByRole("button", { name: "새 채팅" });
  expect(newConversation.textContent).toContain("Ctrl+Alt+N");
  expect(newConversation.getAttribute("aria-keyshortcuts")).toContain("Control+Alt+N");
  rerender(
    <Provider>
      <MainSideNavigation open={false} onToggle={onToggle} onEndSession={onEndSession} />
    </Provider>
  );
  fireEvent.keyDown(document, { key: "k", code: "KeyK", ctrlKey: true });
  fireEvent.keyUp(document, { key: "k", code: "KeyK" });
  expect(screen.getAllByRole("dialog", { name: "빠른 메뉴" })).toHaveLength(1);
  expect(screen.getAllByRole("combobox", { name: "메뉴 검색" })).toHaveLength(1);
});

it("opens a notebook draft route without committing or resetting personal records", async () => {
  const { onEndSession } = setup();
  const nav = screen.getByRole("navigation", { name: "주 메뉴" });
  fireEvent.click(within(nav).getByRole("button", { name: QUICK_MENU }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "수첩 쓰기" } });
  fireEvent.click(screen.getByRole("option", { name: "수첩 쓰기" }));
  expect(chat.openFeature).toHaveBeenCalledExactlyOnceWith("내 수첩");
  expect(window.location.pathname).toBe("/notebook/new");
  expect(onEndSession).not.toHaveBeenCalled();
  expect(chat.resetConversation).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "빠른 메뉴" })).toBeNull());
});

it("runs the existing new-conversation action only after a command is selected", () => {
  setup();
  const nav = screen.getByRole("navigation", { name: "주 메뉴" });
  fireEvent.click(within(nav).getByRole("button", { name: QUICK_MENU }));
  expect(chat.resetConversation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("option", { name: "새 채팅" }));
  expect(chat.resetConversation).toHaveBeenCalledOnce();
});
