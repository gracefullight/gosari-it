import { atomWithStorage } from "jotai/utils";
import { ONBOARDING_STORAGE_KEY, type OnboardingTaskId } from "@/lib/onboarding.tasks";
export const onboardingCompletedAtom = atomWithStorage<Partial<Record<OnboardingTaskId, boolean>>>(
  ONBOARDING_STORAGE_KEY,
  {},
  undefined,
  { getOnInit: true }
);
