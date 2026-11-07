import type { ResultEnvelope } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

const PRICE_OPERATIONS = new Set(["market_query", "survey_link", "retail_lookup"]);
const WEATHER_OPERATIONS = new Set([
  "current_observation",
  "forecast_compare",
  "history_compare",
  "region_compare",
  "outing_compare",
]);
const STARTERS = ["현재 제주 날씨를 알려줘", "제주 고사리 가격을 알려줘", "나들이 준비물을 알려줘"];

function normalize(text: string) {
  return text.replace(/[\s\p{P}]/gu, "").toLocaleLowerCase();
}

function publicProvider(scope: Record<string, unknown>, result: Record<string, unknown>) {
  const sources = Array.isArray(scope.source_ids) ? scope.source_ids : [];
  if (sources.includes("tamnao") && !sources.includes("oasis")) return "탐나오";
  if (sources.includes("oasis") && !sources.includes("tamnao")) return "오아시스";
  const cards = Array.isArray(result.price_cards)
    ? result.price_cards
    : Array.isArray(result.sample_cards)
      ? result.sample_cards
      : [];
  for (const card of cards) {
    if (!card || typeof card !== "object") continue;
    const source = card as Record<string, unknown>;
    try {
      const host = new URL(String(source.source_url ?? "")).hostname;
      if (host === "tamnao.com" || host.endsWith(".tamnao.com")) return "탐나오";
      if (host === "oasis.co.kr" || host.endsWith(".oasis.co.kr")) return "오아시스";
    } catch {
      /* A public provider is optional; arbitrary source text is never copied. */
    }
  }
  return "";
}

function priceSuggestions(envelope: ResultEnvelope): string[] {
  const scope = envelope.requested_scope;
  const operation = String(scope.operation ?? "");
  const form =
    scope.fresh_or_dried === "생고사리" || scope.fresh_or_dried === "건고사리"
      ? scope.fresh_or_dried
      : "고사리";
  if (operation === "survey_link") {
    return [
      ...["생산지", "도매지", "소비지"]
        .filter((stage) => stage !== scope.survey_stage)
        .map((stage) => `그럼 ${stage}는?`),
      `제주 ${form} 판매가를 알려줘`,
    ];
  }
  if (operation === "market_query" || envelope.result.channel === "wholesale") {
    return [
      `제주 ${form} 판매가를 알려줘`,
      `제주 ${form} 조사가를 알려줘`,
      `다른 날짜의 ${form} 도매가격을 알아보고 싶어`,
    ];
  }
  const provider = publicProvider(scope, envelope.result);
  const subject = `${provider ? `${provider} ` : "제주 "}${form}`;
  const sources = Array.isArray(scope.source_ids) ? scope.source_ids : [];
  const narrowedProvider = sources.includes("tamnao") !== sources.includes("oasis");
  const packageSelected = Boolean(
    scope.package_weight_unit || scope.product_option || scope.product_id
  );
  const nextProvider = provider === "탐나오" && narrowedProvider ? "오아시스" : "탐나오";
  return [
    packageSelected
      ? `${subject} 판매가를 규격별로 보여줘`
      : `${nextProvider} ${form} 판매가를 알려줘`,
    `제주 ${form} 조사가를 알려줘`,
    ...(narrowedProvider ? [`탐나오와 오아시스 ${form} 판매가를 비교해줘`] : []),
    `제주 ${form} 도매가격을 알려줘`,
  ];
}

function weatherSuggestions(envelope: ResultEnvelope): string[] {
  const operation = envelope.requested_scope.operation;
  if (operation === "outing_compare" || operation === "forecast_compare") {
    return [
      "다른 날짜의 제주 나들이 날씨를 비교해줘",
      "서귀포 나들이 날씨를 알려줘",
      "나들이 준비물을 알려줘",
    ];
  }
  return ["내일 제주 날씨를 알려줘", "서귀포 나들이 날씨를 알려줘", "나들이 준비물을 알려줘"];
}

/** Suggestions are public query text, never generated measurements, personal names or coordinates. */
export function getChatReplySuggestions(messages: readonly ChatMessage[]): string[] {
  const latest = messages.at(-1);
  if (
    latest?.role !== "assistant" ||
    latest.error ||
    latest.preview ||
    latest.prepare ||
    ["error", "preview", "personal-form", "clarify"].includes(latest.kind ?? "")
  )
    return [];
  if (latest.stream && latest.stream.status !== "completed") return [];
  if (latest.kind === "agent" && !latest.stream) return [];
  const envelope = latest.envelope ?? Object.values(latest.ui_results ?? {}).at(0);
  if (!latest.text?.trim() && !envelope) return [];
  if (envelope?.action_status || (envelope?.errors?.length ?? 0) > 0) return [];
  let candidates = STARTERS;
  if (envelope) {
    const operation = String(envelope.requested_scope.operation ?? "");
    if (
      PRICE_OPERATIONS.has(operation) ||
      envelope.result.channel ||
      Array.isArray(envelope.result.price_cards) ||
      Array.isArray(envelope.result.sample_cards)
    )
      candidates = priceSuggestions(envelope);
    else if (WEATHER_OPERATIONS.has(operation) || Array.isArray(envelope.result.stations))
      candidates = weatherSuggestions(envelope);
  }
  const asked = new Set(
    messages
      .filter((message) => message.role === "user")
      .map((message) => normalize(message.text ?? ""))
  );
  return [...new Set(candidates)]
    .filter((candidate) => !asked.has(normalize(candidate)))
    .slice(0, 3);
}
