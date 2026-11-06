import { useAtom, useSetAtom } from "jotai";
import { useCallback } from "react";
import { ApiError, api } from "../lib/api";
import type { ChatMessage, Feature } from "../stores/app";
import { busyAtom, messagesAtom, onboardingDoneAtom } from "../stores/app";

let counter = 0;
function nextId(): string {
  counter += 1;
  return `msg-${Date.now()}-${counter}`;
}

export function useChat() {
  const [messages, setMessages] = useAtom(messagesAtom);
  const setBusy = useSetAtom(busyAtom);
  const setOnboardingDone = useSetAtom(onboardingDoneAtom);

  const push = useCallback(
    (message: Omit<ChatMessage, "id">) => {
      setMessages((prev) => [...prev, { ...message, id: nextId() }]);
    },
    [setMessages]
  );

  const runSpec = useCallback(
    async (spec: Record<string, unknown>, safeText: string) => {
      setBusy(true);
      try {
        const job = await api.runAnalysis(spec, safeText);
        if (job.result) {
          push({ role: "assistant", kind: "result", envelope: job.result });
        } else {
          push({ role: "assistant", kind: "error", error: job.error ?? "작업 실패" });
        }
      } catch (err) {
        push({
          role: "assistant",
          kind: "error",
          error: err instanceof ApiError ? err.message : "분석 요청에 실패했습니다.",
        });
      } finally {
        setBusy(false);
      }
    },
    [push, setBusy]
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setOnboardingDone(true);
      push({ role: "user", kind: "text", text: trimmed });
      setBusy(true);
      try {
        const prepared = await api.prepare({ text: trimmed });
        if (prepared.classification === "personal") {
          push({ role: "assistant", kind: "personal-form", prepare: prepared });
        } else if (prepared.spec && !prepared.needs_confirmation) {
          await runSpec(prepared.spec, trimmed);
          return;
        } else if (prepared.spec) {
          push({ role: "assistant", kind: "clarify", prepare: prepared });
        } else {
          push({ role: "assistant", kind: "clarify", prepare: prepared });
        }
      } catch (err) {
        push({
          role: "assistant",
          kind: "error",
          error: err instanceof ApiError ? err.message : "요청을 처리할 수 없습니다.",
        });
      } finally {
        setBusy(false);
      }
    },
    [push, runSpec, setBusy, setOnboardingDone]
  );

  const confirmSpec = useCallback(
    (spec: Record<string, unknown>, label: string) => {
      push({ role: "user", kind: "text", text: label });
      void runSpec(spec, label);
    },
    [push, runSpec]
  );

  const openFeature = useCallback(
    (feature: Feature) => {
      setOnboardingDone(true);
      const featureMap: Record<Feature, string> = {
        나들이: "outing",
        "지역 탐색": "region_compare",
        "내 수첩": "notebook",
        나눔: "share",
        "가격 조사": "market_query",
      };
      push({
        role: "assistant",
        kind: "personal-form",
        prepare: {
          classification: feature === "내 수첩" || feature === "나눔" ? "personal" : "public",
          feature: featureMap[feature],
          needs_confirmation: true,
          form: { feature_hint: featureMap[feature] },
        },
      });
    },
    [push, setOnboardingDone]
  );

  return { messages, send, confirmSpec, runSpec, openFeature, push };
}
