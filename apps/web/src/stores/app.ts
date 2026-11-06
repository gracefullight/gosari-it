import { atom } from "jotai";
import type { Capabilities, PrepareResponse, Preview, ResultEnvelope } from "../lib/types";

export type Feature = "나들이" | "지역 탐색" | "내 수첩" | "나눔" | "가격 조사";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  envelope?: ResultEnvelope;
  prepare?: PrepareResponse;
  preview?: Preview;
  error?: string;
  kind?: "result" | "clarify" | "personal-form" | "preview" | "error" | "text";
}

export const sessionReadyAtom = atom(false);
export const sessionEndedAtom = atom(false);
export const capabilitiesAtom = atom<Capabilities | null>(null);
export const onboardingDoneAtom = atom(false);
export const activeFeatureAtom = atom<Feature | null>(null);
export const messagesAtom = atom<ChatMessage[]>([]);
export const busyAtom = atom(false);
export const lnbOpenAtom = atom(true);

export const chatStateAtom = atom((get) => {
  if (get(sessionEndedAtom)) return "session.ended";
  if (!get(onboardingDoneAtom)) return "onboarding.welcome";
  const messages = get(messagesAtom);
  if (messages.length === 0) return "chat.empty";
  if (get(busyAtom)) return "chat.running";
  return "chat.result";
});
