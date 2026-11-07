import { MagnifyingGlassIcon, XIcon } from "@phosphor-icons/react";
import { useFormatForDisplay } from "@tanstack/react-hotkeys";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAppHotkeys } from "@/hooks/use-app-hotkeys";
import type { Feature } from "@/lib/app-routes";
import { FEATURES } from "@/stores/chat.atoms";

interface AppCommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectFeature: (feature: Feature | null) => void;
  onNewConversation: () => void;
  onWriteNotebook: () => void;
}

export function AppCommandMenu({
  open,
  onOpenChange,
  onSelectFeature,
  onNewConversation,
  onWriteNotebook,
}: AppCommandMenuProps) {
  const formatHotkey = useFormatForDisplay();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const commands = [
    {
      id: "chat",
      label: "채팅",
      keywords: "홈 채팅 질문",
      shortcut: formatHotkey("Mod+/"),
      run: () => onSelectFeature(null),
    },
    ...FEATURES.map((feature) => ({
      id: feature,
      label: feature,
      keywords: "메뉴 이동",
      shortcut: "",
      run: () => onSelectFeature(feature),
    })),
    {
      id: "new-chat",
      label: "새 채팅",
      keywords: "새 대화 초기화",
      shortcut: formatHotkey("Mod+Alt+N"),
      run: onNewConversation,
    },
    {
      id: "write-notebook",
      label: "수첩 쓰기",
      keywords: "기록 작성 새 메모",
      shortcut: "",
      run: onWriteNotebook,
    },
  ];
  const normalized = query.replace(/\s/g, "").toLocaleLowerCase();
  const filtered = commands.filter((command) =>
    `${command.label}${command.keywords}`
      .replace(/\s/g, "")
      .toLocaleLowerCase()
      .includes(normalized)
  );
  const selected = filtered[Math.min(activeIndex, Math.max(0, filtered.length - 1))];

  const selectedId = selected?.id;
  useEffect(() => {
    if (open && selectedId)
      document.getElementById(`${listId}-${selectedId}`)?.scrollIntoView?.({ block: "nearest" });
  }, [open, listId, selectedId]);

  function changeOpen(next: boolean) {
    setQuery("");
    setActiveIndex(0);
    onOpenChange(next);
  }

  function execute(command: (typeof commands)[number]) {
    changeOpen(false);
    command.run();
  }

  useAppHotkeys({
    menuOpen: open,
    onToggleMenu: () => changeOpen(!open),
    onNewConversation: () => {
      changeOpen(false);
      onNewConversation();
    },
    onFocusChat: () => {
      changeOpen(false);
      onSelectFeature(null);
    },
  });

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent
        data-app-command-menu
        initialFocus={input}
        showCloseButton={false}
        className="flex max-h-[calc(100dvh-2rem)] flex-col gap-4 p-5 text-base sm:max-w-lg"
      >
        <DialogHeader>
          <DialogTitle className="pr-12 text-2xl font-bold">빠른 메뉴</DialogTitle>
          <DialogDescription className="sr-only">메뉴와 대화 명령을 검색합니다.</DialogDescription>
        </DialogHeader>
        <DialogClose
          render={<Button variant="ghost" size="icon-lg" className="absolute top-3 right-3" />}
          aria-label="빠른 메뉴 닫기"
        >
          <XIcon />
        </DialogClose>
        <div className="relative">
          <MagnifyingGlassIcon
            aria-hidden="true"
            className="pointer-events-none absolute top-3.5 left-3 size-5 text-muted-foreground"
          />
          <Input
            ref={input}
            aria-label="메뉴 검색"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={selected ? `${listId}-${selected.id}` : undefined}
            value={query}
            placeholder="메뉴 검색"
            className="min-h-11 pl-10 text-base md:text-base"
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={(event) => {
              if (event.defaultPrevented || event.nativeEvent.isComposing || event.keyCode === 229)
                return;
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                if (filtered.length)
                  setActiveIndex(
                    (index) =>
                      (index + (event.key === "ArrowDown" ? 1 : -1) + filtered.length) %
                      filtered.length
                  );
              } else if (event.key === "Home" || event.key === "End") {
                event.preventDefault();
                setActiveIndex(event.key === "Home" ? 0 : Math.max(0, filtered.length - 1));
              } else if (event.key === "Enter" && selected) {
                event.preventDefault();
                execute(selected);
              }
            }}
          />
        </div>
        <div
          id={listId}
          role="listbox"
          aria-label="이동할 메뉴"
          className="min-h-0 max-h-[min(55dvh,28rem)] flex-1 space-y-1 overflow-y-auto"
        >
          {filtered.length ? (
            filtered.map((command) => (
              <Button
                id={`${listId}-${command.id}`}
                key={command.id}
                role="option"
                aria-label={command.label}
                aria-keyshortcuts={
                  command.id === "new-chat"
                    ? "Control+Alt+N Meta+Alt+N Control+N Meta+N"
                    : command.id === "chat"
                      ? "Control+/ Meta+/"
                      : undefined
                }
                aria-selected={selected?.id === command.id}
                tabIndex={-1}
                variant={selected?.id === command.id ? "secondary" : "ghost"}
                size="lg"
                className="w-full justify-between text-left text-base"
                onMouseEnter={() => setActiveIndex(filtered.indexOf(command))}
                onClick={() => execute(command)}
              >
                <span>{command.label}</span>
                {command.shortcut ? (
                  <kbd className="rounded border border-border px-2 py-0.5 font-sans text-base text-muted-foreground">
                    {command.shortcut}
                  </kbd>
                ) : null}
              </Button>
            ))
          ) : (
            <p className="px-3 py-4 text-base text-muted-foreground">검색한 메뉴가 없습니다.</p>
          )}
        </div>
        <p className="border-t border-border pt-3 text-base text-muted-foreground">
          ↑↓ 선택 · Enter 이동 · Esc 닫기
        </p>
      </DialogContent>
    </Dialog>
  );
}
