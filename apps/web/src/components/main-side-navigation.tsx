import { Menu } from "@base-ui/react/menu";
import {
  CaretLeftIcon,
  CaretRightIcon,
  ChatCircleDotsIcon,
  GearIcon,
  ListIcon,
  MagnifyingGlassIcon,
  MapTrifoldIcon,
  NotebookIcon,
  PlusIcon,
  SunHorizonIcon,
  TagIcon,
  UsersThreeIcon,
} from "@phosphor-icons/react";
import { useFormatForDisplay } from "@tanstack/react-hotkeys";
import { useAtomValue, useSetAtom } from "jotai";
import { type ComponentType, useState } from "react";
import { AppCommandMenu } from "@/components/app-command-menu";
import { OnboardingGuide } from "@/components/onboarding-guide";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useChat } from "@/hooks/use-chat";
import { activeFeatureAtom, FEATURES, type Feature, navigateToPathAtom } from "@/stores/chat.atoms";

const FEATURE_ICONS: Record<Feature, ComponentType<{ className?: string }>> = {
  나들이: SunHorizonIcon,
  "지역 탐색": MapTrifoldIcon,
  "내 수첩": NotebookIcon,
  나눔: UsersThreeIcon,
  "가격 조사": TagIcon,
};

const FEATURE_SUBTITLES: Record<Feature, string> = {
  나들이: "날짜별 제주 날씨",
  "지역 탐색": "지도·관심 지역",
  "내 수첩": "개인 채취 경험·회고",
  나눔: "가족·지인 나눔 준비",
  "가격 조사": "도매·지역조사·소매가",
};

interface MainSideNavigationProps {
  open: boolean;
  onToggle: () => void;
  onEndSession: () => void;
  loginId?: string | null;
  onOpenAccount?: () => void;
  onLogout?: () => void;
}

export function MainSideNavigation({
  open,
  onToggle,
  onEndSession,
  loginId = null,
  onOpenAccount,
  onLogout,
}: MainSideNavigationProps) {
  const formatHotkey = useFormatForDisplay();
  const activeFeature = useAtomValue(activeFeatureAtom);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const navigate = useSetAtom(navigateToPathAtom);
  const { openFeature, resetConversation } = useChat();

  function selectFeature(feature: Feature | null) {
    openFeature(feature);
    setMobileOpen(false);
  }

  function newConversation() {
    resetConversation();
    setMobileOpen(false);
  }

  function showHelp() {
    setGuideOpen(true);
    setMobileOpen(false);
  }

  function commandButton(compact = false) {
    return (
      <Button
        variant="outline"
        size={compact ? "icon-lg" : "lg"}
        title={`빠른 메뉴 (${formatHotkey("Mod+K")})`}
        aria-keyshortcuts="Control+K Meta+K"
        aria-label={`빠른 메뉴 (${formatHotkey("Mod+K")})`}
        aria-haspopup="dialog"
        className={compact ? "" : "w-full justify-between text-base"}
        onClick={() => {
          setMobileOpen(false);
          setCommandOpen(true);
        }}
      >
        <MagnifyingGlassIcon aria-hidden="true" />
        {compact ? null : (
          <>
            <span>빠른 메뉴</span>
            <kbd className="ml-auto font-sans text-base text-muted-foreground">
              {formatHotkey("Mod+K")}
            </kbd>
          </>
        )}
      </Button>
    );
  }

  const navItems = (compact: boolean) => {
    const isChatHome = activeFeature === null;
    return (
      <>
        <Button
          variant={isChatHome ? "default" : "ghost"}
          size={compact ? "icon" : "default"}
          title={`채팅 · ${formatHotkey("Mod+/")}`}
          aria-keyshortcuts="Control+/ Meta+/"
          aria-label="채팅"
          aria-current={isChatHome ? "page" : undefined}
          className={compact ? "" : "w-full justify-start"}
          onClick={() => selectFeature(null)}
        >
          <ChatCircleDotsIcon className="size-4 shrink-0" />
          {compact ? null : <span className="truncate">채팅</span>}
        </Button>

        {FEATURES.map((feature) => {
          const Icon = FEATURE_ICONS[feature];
          const active = activeFeature === feature;
          return (
            <Button
              key={feature}
              data-tour={`nav-${feature}`}
              variant={active ? "default" : "ghost"}
              size={compact ? "icon" : "default"}
              title={`${feature} · ${FEATURE_SUBTITLES[feature]}`}
              aria-label={feature}
              aria-current={active ? "page" : undefined}
              className={compact ? "" : "w-full justify-between"}
              onClick={() => selectFeature(feature)}
            >
              <span className="flex items-center gap-2 truncate">
                <Icon className="size-4 shrink-0" />
                {compact ? null : <span>{feature}</span>}
              </span>
            </Button>
          );
        })}
      </>
    );
  };

  const footer = (
    <div className="mt-auto flex min-h-16 shrink-0 items-center justify-between gap-2 border-t border-border p-2">
      <Button
        variant="ghost"
        size="lg"
        className="justify-start text-base text-muted-foreground"
        onClick={showHelp}
      >
        사용 안내
      </Button>
      <Menu.Root>
        <Menu.Trigger render={<Button variant="ghost" size="icon-lg" />} aria-label="설정">
          <GearIcon />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner side="top" align="end" sideOffset={8} className="z-50">
            <Menu.Popup className="min-w-48 rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none">
              {loginId ? (
                <>
                  <p className="px-3 py-2 text-sm text-muted-foreground">{loginId} 님</p>
                  <Menu.Item
                    onClick={() => {
                      setMobileOpen(false);
                      onLogout?.();
                    }}
                    className="cursor-pointer rounded-lg px-3 py-2.5 text-base outline-none data-[highlighted]:bg-accent"
                  >
                    로그아웃
                  </Menu.Item>
                </>
              ) : (
                <>
                  <Menu.Item
                    onClick={() => {
                      setMobileOpen(false);
                      onOpenAccount?.();
                    }}
                    className="cursor-pointer rounded-lg px-3 py-2.5 text-base outline-none data-[highlighted]:bg-accent"
                  >
                    로그인·회원가입
                  </Menu.Item>
                  <Menu.Item
                    onClick={() => {
                      setMobileOpen(false);
                      onEndSession();
                    }}
                    className="cursor-pointer rounded-lg px-3 py-2.5 text-base text-destructive outline-none data-[highlighted]:bg-destructive/10"
                  >
                    개인 기록 초기화
                  </Menu.Item>
                </>
              )}
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </div>
  );

  return (
    <>
      <AppCommandMenu
        open={commandOpen}
        onOpenChange={setCommandOpen}
        onSelectFeature={selectFeature}
        onNewConversation={newConversation}
        onWriteNotebook={() => {
          selectFeature("내 수첩");
          navigate("/notebook/new");
        }}
      />
      {guideOpen ? <OnboardingGuide onClose={() => setGuideOpen(false)} /> : null}

      <header className="flex items-center justify-between border-b border-border bg-background px-4 py-3 md:hidden">
        <button
          type="button"
          onClick={() => selectFeature(null)}
          className="min-h-11 text-lg font-bold text-primary focus-visible:outline-2 focus-visible:outline-ring"
        >
          고사리잇 {activeFeature ? `· ${activeFeature}` : ""}
        </button>
        <div className="flex items-center gap-2">
          {commandButton(true)}
          <Button
            variant="outline"
            size="icon"
            aria-label="메뉴 열기"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)}
          >
            <ListIcon />
          </Button>
        </div>
      </header>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 max-w-[85%] p-0">
          <SheetHeader className="border-b border-border">
            <SheetTitle className="text-primary">고사리잇</SheetTitle>
            <SheetDescription>전용 페이지 이동 및 기록 관리</SheetDescription>
          </SheetHeader>
          <div className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
            <Button
              variant="outline"
              size="lg"
              className="mb-2 w-full justify-between"
              title={`새 채팅 (${formatHotkey("Mod+Alt+N")})`}
              aria-label="새 채팅"
              aria-keyshortcuts="Control+Alt+N Meta+Alt+N Control+N Meta+N"
              onClick={newConversation}
            >
              <PlusIcon data-icon="inline-start" />
              <span>새 채팅</span>
              <kbd className="ml-auto font-sans text-base text-muted-foreground">
                {formatHotkey("Mod+Alt+N")}
              </kbd>
            </Button>
            {commandButton()}
            {navItems(false)}
          </div>
          {footer}
        </SheetContent>
      </Sheet>

      <nav
        aria-label="주 메뉴"
        className={`hidden shrink-0 flex-col border-r border-border bg-background md:flex ${
          open ? "w-64" : "w-16"
        }`}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          {open ? (
            <button
              type="button"
              onClick={() => selectFeature(null)}
              className="min-h-11 text-left text-lg font-bold text-primary hover:opacity-90 focus-visible:outline-2 focus-visible:outline-ring"
            >
              고사리잇
            </button>
          ) : null}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onToggle}
            aria-label={open ? "메뉴 접기" : "메뉴 펼치기"}
          >
            {open ? <CaretLeftIcon /> : <CaretRightIcon />}
          </Button>
        </div>
        {open ? (
          <>
            <div className="space-y-2 p-3 pb-1">
              <Button
                variant="outline"
                size="lg"
                className="w-full justify-between"
                title={`새 채팅 (${formatHotkey("Mod+Alt+N")})`}
                aria-label="새 채팅"
                aria-keyshortcuts="Control+Alt+N Meta+Alt+N Control+N Meta+N"
                onClick={newConversation}
              >
                <PlusIcon data-icon="inline-start" />
                <span>새 채팅</span>
                <kbd className="ml-auto font-sans text-base text-muted-foreground">
                  {formatHotkey("Mod+Alt+N")}
                </kbd>
              </Button>
              {commandButton()}
            </div>
            <div className="flex flex-col gap-1 px-3 py-2">{navItems(false)}</div>
            {footer}
          </>
        ) : (
          <div className="flex flex-col items-center gap-2 p-2">
            {commandButton(true)}
            {navItems(true)}
          </div>
        )}
      </nav>
    </>
  );
}
