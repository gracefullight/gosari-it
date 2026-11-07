import { ArrowRightIcon, CheckCircleIcon } from "@phosphor-icons/react";
import { useAtom, useSetAtom } from "jotai";
import {
  type CardComponentProps,
  NextStepProvider,
  NextStepReact,
  type Tour,
  useNextStep,
} from "nextstepjs";
import { type ReactNode, useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ONBOARDING_TASKS, type OnboardingTaskId } from "@/lib/onboarding.tasks";
import { navigateToPathAtom } from "@/stores/chat.atoms";
import { onboardingCompletedAtom } from "@/stores/onboarding.atoms";

const OVERVIEW = "gosari-overview";
const tours: Tour[] = [
  {
    tour: OVERVIEW,
    steps: ONBOARDING_TASKS.map((task, index) => ({
      title: task.title,
      content: task.description,
      selector: '[data-tour="page-content"]',
      side: "bottom",
      nextRoute: ONBOARDING_TASKS[index + 1]?.path,
      prevRoute: ONBOARDING_TASKS[index - 1]?.path,
      selectorRetryAttempts: 15,
      selectorRetryDelay: 100,
      pointerPadding: 8,
      pointerRadius: 16,
    })),
  },
  ...ONBOARDING_TASKS.map((task) => ({
    tour: `gosari-${task.id}`,
    steps: [
      {
        title: task.title,
        content: task.description,
        selector: '[data-tour="page-content"]',
        side: "bottom" as const,
        selectorRetryAttempts: 15,
        selectorRetryDelay: 100,
        pointerPadding: 8,
      },
    ],
  })),
];
function useHistoryNavigation() {
  const navigate = useSetAtom(navigateToPathAtom);
  return useMemo(
    () => ({ push: navigate, getCurrentPath: () => window.location.pathname }),
    [navigate]
  );
}
function OnboardingTourCard({
  step,
  currentStep,
  totalSteps,
  nextStep,
  prevStep,
  skipTour,
}: CardComponentProps) {
  return (
    <section
      aria-label="둘러보기 안내"
      className="w-80 max-w-[calc(100vw-2rem)] rounded-2xl border border-border bg-card p-5 text-foreground shadow-xl"
    >
      <p className="mb-2 text-base tabular-nums text-muted-foreground">
        {currentStep + 1} / {totalSteps}
      </p>
      <h2 className="text-lg font-semibold">{step.title}</h2>
      <div className="mt-2 text-base leading-relaxed text-muted-foreground">{step.content}</div>
      <div className="mt-5 flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={skipTour}>
          닫기
        </Button>
        <div className="flex gap-2">
          {currentStep > 0 ? (
            <Button variant="outline" size="sm" onClick={prevStep}>
              이전
            </Button>
          ) : null}
          <Button size="sm" onClick={nextStep}>
            {currentStep + 1 === totalSteps ? "둘러보기 끝내기" : "다음"}
          </Button>
        </div>
      </div>
    </section>
  );
}
export function OnboardingProvider({ children }: { children: ReactNode }) {
  return (
    <NextStepProvider>
      <NextStepReact
        navigationAdapter={useHistoryNavigation}
        steps={tours}
        cardComponent={OnboardingTourCard}
        disableConsoleLogs
        scrollToTop={false}
        cardTransition={{ duration: 0 }}
        displayArrow={false}
      >
        {children}
      </NextStepReact>
    </NextStepProvider>
  );
}
interface OnboardingGuideProps {
  onClose: () => void;
}
export function OnboardingGuide({ onClose }: OnboardingGuideProps) {
  const [completed, setCompleted] = useAtom(onboardingCompletedAtom);
  const navigate = useSetAtom(navigateToPathAtom);
  const { startNextStep } = useNextStep();
  const count = ONBOARDING_TASKS.filter((task) => completed[task.id]).length;
  function start(id?: OnboardingTaskId) {
    const task = id ? ONBOARDING_TASKS.find((item) => item.id === id)! : ONBOARDING_TASKS[0];
    onClose();
    navigate(task.path);
    startNextStep(id ? `gosari-${id}` : OVERVIEW);
  }
  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>고사리잇 시작하기</SheetTitle>
          <SheetDescription>
            해본 항목은 직접 완료로 표시하세요. {count}/{ONBOARDING_TASKS.length}
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-5 px-5 pb-6">
          <Button onClick={() => start()}>
            {count ? "다시 둘러보기" : "둘러보기 시작"}
            <ArrowRightIcon aria-hidden="true" />
          </Button>
          <ul className="divide-y divide-border">
            {ONBOARDING_TASKS.map((task) => (
              <li key={task.id} className="flex items-start gap-3 py-4">
                <label className="flex min-h-10 flex-1 cursor-pointer items-center gap-3">
                  <input
                    type="checkbox"
                    checked={Boolean(completed[task.id])}
                    onChange={(event) =>
                      setCompleted((previous) => ({ ...previous, [task.id]: event.target.checked }))
                    }
                    className="size-5 shrink-0 accent-[var(--primary)]"
                  />
                  <span className="text-base font-medium">{task.title}</span>
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => start(task.id)}
                  aria-label={`${task.title} 안내`}
                >
                  보기
                  <ArrowRightIcon aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
          {count === ONBOARDING_TASKS.length ? (
            <p className="flex items-center gap-2 text-base text-primary">
              <CheckCircleIcon aria-hidden="true" />
              모든 항목을 확인했습니다.
            </p>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
