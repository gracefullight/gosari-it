import { useHotkey } from "@tanstack/react-hotkeys";

interface AppHotkeysOptions {
  menuOpen: boolean;
  onToggleMenu: () => void;
  onFocusChat: () => void;
  onNewConversation: () => void;
}

function hasAnotherDialog() {
  return Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]')).some(
    (dialog) => !dialog.hasAttribute("data-app-command-menu")
  );
}

function canHandle(event: KeyboardEvent) {
  return !event.defaultPrevented && !event.isComposing && event.keyCode !== 229 && !event.repeat;
}

/** Mounted once by MainSideNavigation, never by the repeated chat hook. */
export function useAppHotkeys({
  menuOpen,
  onToggleMenu,
  onFocusChat,
  onNewConversation,
}: AppHotkeysOptions) {
  useHotkey(
    "Mod+K",
    (event) => {
      if (!canHandle(event) || hasAnotherDialog()) return;
      event.preventDefault();
      onToggleMenu();
    },
    {
      ignoreInputs: false,
      ignoreDefaultPrevented: true,
      preventDefault: false,
      requireReset: true,
    }
  );

  useHotkey(
    "Mod+/",
    (event) => {
      if (!canHandle(event) || hasAnotherDialog()) return;
      event.preventDefault();
      onFocusChat();
    },
    {
      enabled: !menuOpen,
      ignoreInputs: true,
      ignoreDefaultPrevented: true,
      preventDefault: false,
      requireReset: true,
    }
  );
  useHotkey(
    "Mod+Alt+N",
    (event) => {
      if (!canHandle(event) || hasAnotherDialog()) return;
      event.preventDefault();
      onNewConversation();
    },
    {
      ignoreInputs: false,
      ignoreDefaultPrevented: true,
      preventDefault: false,
      requireReset: true,
    }
  );
  useHotkey(
    "Mod+N",
    (event) => {
      if (!canHandle(event) || hasAnotherDialog()) return;
      event.preventDefault();
      onNewConversation();
    },
    {
      ignoreInputs: false,
      ignoreDefaultPrevented: true,
      preventDefault: false,
      requireReset: true,
    }
  );
}
