import { atom } from "jotai";
import { FEATURE_PATHS, type Feature, resolveAppRoute } from "@/lib/app-routes";
import type {
  AgentChatState,
  Capabilities,
  PrepareResponse,
  Preview,
  ResultEnvelope,
} from "@/lib/gosari.types";

export type { Feature } from "@/lib/app-routes";

export const FEATURES: Feature[] = ["나들이", "지역 탐색", "내 수첩", "나눔", "가격 조사"];

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  envelope?: ResultEnvelope;
  prepare?: PrepareResponse;
  preview?: Preview;
  error?: string;
  stream?: AgentChatState;
  kind?: "agent" | "result" | "clarify" | "personal-form" | "preview" | "error" | "text";
}

export const sessionReadyAtom = atom(false);
export const sessionEndedAtom = atom(false);
export const capabilitiesAtom = atom<Capabilities | null>(null);
export const onboardingDoneAtom = atom(true);
export const appPathAtom = atom(
  typeof window === "undefined" ? "/" : window.location.pathname + window.location.search
);
appPathAtom.onMount = (setPath) => {
  const sync = () => setPath(window.location.pathname + window.location.search);
  sync();
  window.addEventListener("popstate", sync);
  return () => window.removeEventListener("popstate", sync);
};
export const navigateToPathAtom = atom(null, (_get, set, path: string) => {
  if (window.location.pathname + window.location.search !== path)
    window.history.pushState(null, "", path);
  set(appPathAtom, path);
});
export const activeFeatureAtom = atom(
  (get) => resolveAppRoute(get(appPathAtom)).feature,
  (_get, set, feature: Feature | null) =>
    set(navigateToPathAtom, feature ? FEATURE_PATHS[feature] : "/")
);
export const messagesAtom = atom<ChatMessage[]>([]);
export const conversationIdAtom = atom<string | null>(null);
export const featureResultsAtom = atom<Partial<Record<Feature, ResultEnvelope>>>({});
export const featureErrorsAtom = atom<Partial<Record<Feature, string | null>>>({});
export const revisionCounterAtom = atom(0);
export const lastCommitNoticeAtom = atom<string | null>(null);
export const pendingRequestsAtom = atom<Partial<Record<Feature | "chat", number>>>({});
export const analysisJobsAtom = atom<Record<string, { feature: Feature | null; message: string }>>(
  {}
);
export const busyAtom = atom((get) => {
  const key = get(activeFeatureAtom) ?? "chat";
  return (get(pendingRequestsAtom)[key] ?? 0) > 0;
});
export const lnbOpenAtom = atom(true);
export const mobileNavOpenAtom = atom(false);

export const chatStateAtom = atom((get) => {
  if (get(sessionEndedAtom)) return "session.ended";
  const activeFeature = get(activeFeatureAtom);
  if (activeFeature) return `page.${activeFeature}`;
  const messages = get(messagesAtom);
  if (messages.length === 0) return "chat.empty";
  if (get(busyAtom)) return "chat.running";
  return "chat.result";
});
