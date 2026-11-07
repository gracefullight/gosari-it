import { Menu } from "@base-ui/react/menu";
import {
  CaretLeftIcon,
  CaretRightIcon,
  ChatCircleDotsIcon,
  GearIcon,
  ListIcon,
  MapTrifoldIcon,
  NotebookIcon,
  PlusIcon,
  SunHorizonIcon,
  TagIcon,
  UsersThreeIcon,
} from "@phosphor-icons/react";
import { useAtomValue, useSetAtom } from "jotai";
import { type ComponentType, useState } from "react";
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
import { activeFeatureAtom, FEATURES, type Feature, messagesAtom } from "@/stores/chat.atoms";

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
}

export function MainSideNavigation({ open, onToggle, onEndSession }: MainSideNavigationProps) {
  const activeFeature = useAtomValue(activeFeatureAtom);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const setMessages = useSetAtom(messagesAtom);
  const { openFeature } = useChat();

  function selectFeature(feature: Feature | null) {
    openFeature(feature);
    setMobileOpen(false);
  }

  function newConversation() {
    setMessages([]);
    openFeature(null);
    setMobileOpen(false);
  }

  function showHelp() {
    setGuideOpen(true);
    setMobileOpen(false);
  }

  const navItems = (compact: boolean) => {
    const isChatHome = activeFeature === null;
    return (
      <>
        <Button
          variant={isChatHome ? "default" : "ghost"}
          size={compact ? "icon" : "default"}
          title="AI 대화 (홈)"
          aria-label="AI 대화 (홈)"
          aria-current={isChatHome ? "page" : undefined}
          className={compact ? "" : "w-full justify-start"}
          onClick={() => selectFeature(null)}
        >
          <ChatCircleDotsIcon className="size-4 shrink-0" />
          {compact ? null : <span className="truncate">AI 대화 (홈)</span>}
        </Button>

        {!compact ? (
          <div className="mt-2 mb-1 px-2 text-base font-bold tracking-wider text-muted-foreground uppercase">
            둘러보기
          </div>
        ) : null}

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
    <div className="mt-auto flex h-[var(--app-footer-height)] shrink-0 items-center justify-between gap-2 border-t border-border p-3">
      <Button variant="ghost" className="justify-start text-muted-foreground" onClick={showHelp}>
        사용 안내
      </Button>
      <Menu.Root>
        <Menu.Trigger render={<Button variant="ghost" size="icon" />} aria-label="설정">
          <GearIcon />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner side="top" align="end" sideOffset={8} className="z-50">
            <Menu.Popup className="min-w-48 rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none">
              <Menu.Item
                onClick={() => {
                  setMobileOpen(false);
                  onEndSession();
                }}
                className="cursor-pointer rounded-lg px-3 py-2.5 text-base text-destructive outline-none data-[highlighted]:bg-destructive/10"
              >
                개인 기록 초기화
              </Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </div>
  );

  return (
    <>
      {guideOpen ? <OnboardingGuide onClose={() => setGuideOpen(false)} /> : null}

      <header className="flex items-center justify-between border-b border-border bg-background px-4 py-3 md:hidden">
        <button
          type="button"
          onClick={() => selectFeature(null)}
          className="min-h-11 text-lg font-bold text-primary focus-visible:outline-2 focus-visible:outline-ring"
        >
          고사리잇 {activeFeature ? `· ${activeFeature}` : ""}
        </button>
        <Button
          variant="outline"
          size="icon"
          aria-label="메뉴 열기"
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen(true)}
        >
          <ListIcon />
        </Button>
      </header>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 max-w-[85%] p-0">
          <SheetHeader className="border-b border-border">
            <SheetTitle className="text-primary">고사리잇</SheetTitle>
            <SheetDescription>전용 페이지 이동 및 기록 관리</SheetDescription>
          </SheetHeader>
          <div className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
            <Button variant="outline" className="mb-2 w-full" onClick={newConversation}>
              <PlusIcon data-icon="inline-start" />새 대화 초기화
            </Button>
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
            <div className="p-3 pb-1">
              <Button variant="outline" className="w-full" onClick={newConversation}>
                <PlusIcon data-icon="inline-start" />새 대화 초기화
              </Button>
            </div>
            <div className="flex flex-col gap-1 px-3 py-2">{navItems(false)}</div>
            {footer}
          </>
        ) : (
          <div className="flex flex-col items-center gap-2 p-2">{navItems(true)}</div>
        )}
      </nav>
    </>
  );
}
