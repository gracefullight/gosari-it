import { HotkeysProvider } from "@tanstack/react-hotkeys";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppCommandMenu } from "@/components/app-command-menu";

const feature = vi.fn();
const newChat = vi.fn();
const write = vi.fn();
const changed = vi.fn();

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <label>
        편집 중<input aria-label="편집 중" defaultValue="보존할 메모" />
      </label>
      <AppCommandMenu
        open={open}
        onOpenChange={(value) => {
          changed(value);
          setOpen(value);
        }}
        onSelectFeature={feature}
        onNewConversation={newChat}
        onWriteNotebook={write}
      />
    </>
  );
}

function chord(
  key: string,
  code: string,
  extra: KeyboardEventInit = {},
  target: Document | HTMLElement = document
) {
  fireEvent.keyDown(target, { key, code, ctrlKey: true, ...extra });
  fireEvent.keyUp(target, { key, code, ctrlKey: false });
  fireEvent.keyUp(document, { key: "Control", code: "ControlLeft", ctrlKey: false });
  fireEvent.keyUp(document, { key: "Alt", code: "AltLeft", altKey: false });
  fireEvent.keyUp(document, { key: "Meta", code: "MetaLeft", metaKey: false });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("app command menu with the real TanStack hotkey manager", () => {
  it("opens once in StrictMode and unregisters on unmount", async () => {
    const view = render(
      <StrictMode>
        <Harness />
      </StrictMode>
    );
    chord("k", "KeyK");
    expect(await screen.findByRole("combobox", { name: "메뉴 검색" })).toBeTruthy();
    expect(changed.mock.calls.filter(([open]) => open)).toHaveLength(1);
    view.unmount();
    changed.mockClear();
    chord("k", "KeyK");
    expect(changed).not.toHaveBeenCalled();
  });

  it("keeps typed input and ignores chat-focus shortcuts in another input", () => {
    render(<Harness />);
    const input = screen.getByLabelText("편집 중") as HTMLInputElement;
    input.focus();
    chord("/", "Slash", {}, input);
    expect(feature).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe("보존할 메모");
    chord("k", "KeyK", {}, input);
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(input.value).toBe("보존할 메모");
  });

  it("focuses chat through the existing public navigation callback", () => {
    render(<Harness />);
    chord("/", "Slash");
    expect(feature).toHaveBeenCalledExactlyOnceWith(null);
    expect(newChat).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
  });

  it.each([{ isComposing: true }, { keyCode: 229 }, { repeat: true }])(
    "does not run composing/repeated hotkeys: %o",
    (state) => {
      render(<Harness />);
      chord("k", "KeyK", state);
      expect(screen.queryByRole("dialog", { name: "빠른 메뉴" })).toBeNull();
      expect(changed).not.toHaveBeenCalled();
    }
  );

  it("respects defaultPrevented and another Base UI dialog", () => {
    render(<Harness />);
    const event = new KeyboardEvent("keydown", {
      key: "k",
      code: "KeyK",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    event.preventDefault();
    fireEvent(document, event);
    fireEvent.keyUp(document, { key: "k", code: "KeyK" });
    expect(changed).not.toHaveBeenCalled();
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    document.body.append(modal);
    chord("k", "KeyK");
    expect(changed).not.toHaveBeenCalled();
    chord("n", "KeyN");
    expect(newChat).not.toHaveBeenCalled();
    modal.remove();
  });

  it("filters routes, uses arrow navigation, and runs only the selected command", async () => {
    render(<Harness />);
    chord("k", "KeyK");
    const search = screen.getByRole("combobox");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: "나들이" }).getAttribute("aria-selected")).toBe(
      "true"
    );
    fireEvent.keyDown(search, { key: "Enter" });
    expect(feature).toHaveBeenCalledExactlyOnceWith("나들이");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "빠른 메뉴" })).toBeNull());
    chord("k", "KeyK");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "수첩 쓰기" } });
    fireEvent.click(screen.getByRole("option", { name: "수첩 쓰기" }));
    expect(write).toHaveBeenCalledOnce();
    expect(newChat).not.toHaveBeenCalled();
  });

  it("leaves Korean composition Enter to the input method", () => {
    render(<Harness />);
    chord("k", "KeyK");
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "새 채팅" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(newChat).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(newChat).toHaveBeenCalledOnce();
  });

  it("offers all five menus and an empty search state", () => {
    render(<Harness />);
    chord("k", "KeyK");
    for (const name of ["나들이", "지역 탐색", "내 수첩", "나눔", "가격 조사"])
      expect(screen.getByRole("option", { name })).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "없는 메뉴" } });
    expect(screen.getByText("검색한 메뉴가 없습니다.")).toBeTruthy();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });
});

it("registers Mod+N once and prevents the delivered browser shortcut", () => {
  render(
    <StrictMode>
      <Harness />
    </StrictMode>
  );
  const event = new KeyboardEvent("keydown", {
    key: "n",
    code: "KeyN",
    ctrlKey: true,
    bubbles: true,
    cancelable: true,
  });
  fireEvent(document, event);
  fireEvent.keyUp(document, { key: "n", code: "KeyN" });
  fireEvent.keyUp(document, { key: "Alt", code: "AltLeft" });
  fireEvent.keyUp(document, { key: "Control", code: "ControlLeft" });
  fireEvent.keyUp(document, { key: "Meta", code: "MetaLeft" });
  expect(event.defaultPrevented).toBe(true);
  expect(newChat).toHaveBeenCalledOnce();
});

it.each([{ isComposing: true }, { keyCode: 229 }, { repeat: true }])(
  "leaves Mod+N inactive for composition/repeat %o",
  (state) => {
    render(<Harness />);
    chord("n", "KeyN", state);
    expect(newChat).not.toHaveBeenCalled();
  }
);

it.each(["mac", "windows", "linux"] as const)("shows only the SDK modifier for %s", (platform) => {
  render(
    <HotkeysProvider defaultOptions={{ platform }}>
      <Harness />
    </HotkeysProvider>
  );
  chord("k", "KeyK", { ctrlKey: platform !== "mac", metaKey: platform === "mac" });
  const command = screen.getByRole("option", { name: "새 채팅" });
  if (platform === "mac") {
    expect(command.textContent).toContain("⌘");
    expect(command.textContent).toContain("⌥");
    expect(command.textContent).toContain("N");
  } else expect(command.textContent).toContain("Ctrl+Alt+N");
  expect(command.textContent).not.toContain(platform === "mac" ? "Ctrl" : "⌘");
  expect(command.getAttribute("aria-keyshortcuts")).toContain("Meta+Alt+N");
});

it.each(["mac", "windows", "linux"] as const)("runs Mod+Alt+N exactly once on %s", (platform) => {
  render(
    <StrictMode>
      <HotkeysProvider defaultOptions={{ platform }}>
        <Harness />
      </HotkeysProvider>
    </StrictMode>
  );
  const event = new KeyboardEvent("keydown", {
    key: "n",
    code: "KeyN",
    altKey: true,
    ctrlKey: platform !== "mac",
    metaKey: platform === "mac",
    bubbles: true,
    cancelable: true,
  });
  // Happy DOM conflates Ctrl+Alt with AltGraph; this case represents left Alt, not AltGr.
  const modifierState = event.getModifierState.bind(event);
  event.getModifierState = (key) => (key === "AltGraph" ? false : modifierState(key));
  fireEvent(document, event);
  fireEvent.keyUp(document, { key: "n", code: "KeyN" });
  fireEvent.keyUp(document, { key: "Alt", code: "AltLeft" });
  fireEvent.keyUp(document, { key: "Control", code: "ControlLeft" });
  fireEvent.keyUp(document, { key: "Meta", code: "MetaLeft" });
  expect(event.defaultPrevented).toBe(true);
  expect(newChat).toHaveBeenCalledOnce();
});

it.each([{ isComposing: true }, { keyCode: 229 }, { repeat: true }])(
  "ignores composing/repeated Mod+Alt+N: %o",
  (state) => {
    render(<Harness />);
    chord("n", "KeyN", { altKey: true, ...state });
    expect(newChat).not.toHaveBeenCalled();
  }
);

it("keeps Mod+Alt+N inactive under another modal", () => {
  render(<Harness />);
  const modal = document.createElement("div");
  modal.setAttribute("role", "dialog");
  document.body.append(modal);
  chord("n", "KeyN", { altKey: true });
  expect(newChat).not.toHaveBeenCalled();
  modal.remove();
});

it("does not replace Linux AltGr typing with a new conversation", () => {
  render(
    <HotkeysProvider defaultOptions={{ platform: "linux" }}>
      <Harness />
    </HotkeysProvider>
  );
  const event = new KeyboardEvent("keydown", {
    key: "n",
    code: "KeyN",
    ctrlKey: true,
    altKey: true,
    bubbles: true,
  });
  event.getModifierState = (key) => key === "AltGraph";
  fireEvent(document, event);
  fireEvent.keyUp(document, { key: "n", code: "KeyN" });
  expect(newChat).not.toHaveBeenCalled();
});
