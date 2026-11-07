import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider, useAtomValue } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MainSideNavigation } from "@/components/main-side-navigation";
import { OnboardingProvider } from "@/components/onboarding-guide";
import { ONBOARDING_STORAGE_KEY } from "@/lib/onboarding.tasks";
import { appPathAtom } from "@/stores/chat.atoms";

const ONE_OF_FIVE = /1\/5/;

function PageTarget() {
  const path = useAtomValue(appPathAtom);
  return (
    <main key={path} data-tour="page-content">
      현재 페이지 {path}
    </main>
  );
}
function mount(onEndSession = vi.fn()) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Provider>
        <OnboardingProvider>
          <MainSideNavigation open onToggle={vi.fn()} onEndSession={onEndSession} />
          <PageTarget />
        </OnboardingProvider>
      </Provider>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  // Happy DOM rejects canceled WAAPI promises; these tests exercise tour routing rather than animation.
  vi.spyOn(Animation.prototype, "cancel").mockImplementation(() => {});
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("onboarding guide", () => {
  it("opens a checklist only on request and persists manual completion", async () => {
    mount();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("region", { name: "둘러보기 안내" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "사용 안내" }));
    const guide = await screen.findByRole("dialog");
    expect(within(guide).getAllByRole("checkbox")).toHaveLength(5);
    fireEvent.click(within(guide).getByRole("checkbox", { name: "제주 날씨 보기" }));
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(ONBOARDING_STORAGE_KEY) ?? "{}")).toEqual({
        weather: true,
      })
    );
    expect(within(guide).getByText(ONE_OF_FIVE)).toBeTruthy();
  });

  it("routes an individual guide through NextStep without claiming task completion", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "사용 안내" }));
    fireEvent.click(await screen.findByRole("button", { name: "가격 조회 안내" }));
    await waitFor(() => expect(window.location.pathname).toBe("/prices"));
    const tour = await screen.findByRole("region", { name: "둘러보기 안내" });
    expect(within(tour).getByRole("heading", { name: "가격 조회" })).toBeTruthy();
    fireEvent.click(within(tour).getByRole("button", { name: "둘러보기 끝내기" }));
    expect(JSON.parse(window.localStorage.getItem(ONBOARDING_STORAGE_KEY) ?? "{}")).toEqual({});
  });

  it("moves the overview between feature URLs", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "사용 안내" }));
    fireEvent.click(await screen.findByRole("button", { name: "둘러보기 시작" }));
    const tour = await screen.findByRole("region", { name: "둘러보기 안내" });
    expect(window.location.pathname).toBe("/outing");
    fireEvent.click(within(tour).getByRole("button", { name: "다음" }));
    await waitFor(() => expect(window.location.pathname).toBe("/regions"));
    await screen.findByRole("heading", { name: "관심 지역 저장" });
  });

  it("keeps reset inside a settings dropdown and calls the existing reset action only when clicked", async () => {
    const end = vi.fn();
    mount(end);
    expect(screen.queryByRole("button", { name: "개인 기록 초기화" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "설정" }));
    const settings = await screen.findByRole("menu");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(end).not.toHaveBeenCalled();
    fireEvent.click(within(settings).getByRole("menuitem", { name: "개인 기록 초기화" }));
    expect(end).toHaveBeenCalledTimes(1);
  });
});
