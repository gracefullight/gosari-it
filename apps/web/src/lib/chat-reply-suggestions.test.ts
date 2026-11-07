import { describe, expect, it } from "vitest";
import { getChatReplySuggestions } from "@/lib/chat-reply-suggestions";
import type { ResultEnvelope } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

const DATE_QUERY = /날짜|내일/;
const DIGIT = /\d/;
const PRIVATE_HINT = /엄마|010|33\.1234|홍길동|999999|우리집/;

function envelope(operation: string, scope: Record<string, unknown> = {}): ResultEnvelope {
  return {
    schema_version: "result-v1",
    request_id: "r",
    data_status: "complete",
    source_mode: "replay",
    action_status: null,
    link_status: "not_requested",
    cache_resolution: "bypass",
    requested_scope: { operation, ...scope },
    effective_scope: {},
    observed_period: {},
    fetched_at: null,
    verified_on: null,
    result: {},
    evidence_ids: [],
    warnings: [],
    errors: [],
  };
}
function answer(values: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "a",
    role: "assistant",
    kind: "agent",
    text: "확인했어요.",
    stream: { status: "completed", seen_event_ids: [], tools: [] },
    ...values,
  };
}

describe("deterministic chat reply suggestions", () => {
  it("offers three service starters only after a completed assistant response", () => {
    expect(getChatReplySuggestions([])).toEqual([]);
    expect(getChatReplySuggestions([{ id: "u", role: "user", text: "안녕" }])).toEqual([]);
    expect(getChatReplySuggestions([answer()])).toEqual([
      "현재 제주 날씨를 알려줘",
      "제주 고사리 가격을 알려줘",
      "나들이 준비물을 알려줘",
    ]);
  });

  it("continues a selected retail package with public package/channel/comparison queries", () => {
    const result = envelope("retail_lookup", {
      source_ids: ["retail_sample", "tamnao"],
      fresh_or_dried: "건고사리",
      package_weight_unit: "100 g",
    });
    expect(getChatReplySuggestions([answer({ envelope: result })])).toEqual([
      "탐나오 건고사리 판매가를 규격별로 보여줘",
      "제주 건고사리 조사가를 알려줘",
      "탐나오와 오아시스 건고사리 판매가를 비교해줘",
    ]);
  });

  it("changes provider rather than repeating a package-free broad query", () => {
    const result = envelope("retail_lookup", {
      source_ids: ["retail_sample", "tamnao"],
      fresh_or_dried: "건고사리",
    });
    expect(getChatReplySuggestions([answer({ envelope: result })])[0]).toBe(
      "오아시스 건고사리 판매가를 알려줘"
    );
  });

  it("uses a trusted provider URL on cached UI-bound results", () => {
    const result = envelope("retail_lookup", { package_weight_unit: "100 g" });
    result.result.price_cards = [
      { source_url: "https://www.tamnao.com/product", product: "비공개 별칭은 무시" },
    ];
    const suggestions = getChatReplySuggestions([answer({ ui_results: { result_1: result } })]);
    expect(suggestions[0]).toContain("탐나오");
    expect(suggestions.join()).not.toContain("비공개");
  });

  it("does not repeat the selected survey stage", () => {
    const result = envelope("survey_link", { survey_stage: "생산지", fresh_or_dried: "생고사리" });
    const suggestions = getChatReplySuggestions([answer({ envelope: result })]);
    expect(suggestions).toEqual([
      "그럼 도매지는?",
      "그럼 소비지는?",
      "제주 생고사리 판매가를 알려줘",
    ]);
  });

  it("offers other channels and date conditions after wholesale results", () => {
    expect(
      getChatReplySuggestions([
        answer({ envelope: envelope("market_query", { fresh_or_dried: "생고사리" }) }),
      ])
    ).toEqual([
      "제주 생고사리 판매가를 알려줘",
      "제주 생고사리 조사가를 알려줘",
      "다른 날짜의 생고사리 도매가격을 알아보고 싶어",
    ]);
  });

  it.each(["current_observation", "history_compare", "outing_compare"])(
    "uses date/region/preparation followups after %s",
    (operation) => {
      const suggestions = getChatReplySuggestions([answer({ envelope: envelope(operation) })]);
      expect(suggestions).toHaveLength(3);
      expect(suggestions[0]).toMatch(DATE_QUERY);
      expect(suggestions[1]).toBe("서귀포 나들이 날씨를 알려줘");
      expect(suggestions[2]).toBe("나들이 준비물을 알려줘");
      expect(suggestions.join()).not.toMatch(DIGIT);
    }
  );

  it.each(["streaming", "disconnected", "failed", "cancelled"] as const)(
    "hides suggestions for %s responses",
    (status) => {
      expect(
        getChatReplySuggestions([answer({ stream: { status, seen_event_ids: [], tools: [] } })])
      ).toEqual([]);
    }
  );

  it("hides private forms, previews, failed messages and empty responses", () => {
    for (const values of [
      { kind: "personal-form" as const },
      { kind: "preview" as const },
      { error: "오류" },
      { text: "", kind: "text" as const, stream: undefined },
      { kind: "agent" as const, stream: undefined },
    ])
      expect(getChatReplySuggestions([answer(values)])).toEqual([]);
    const personal = envelope("retail_lookup");
    personal.action_status = "committed";
    expect(getChatReplySuggestions([answer({ envelope: personal })])).toEqual([]);
  });

  it("never copies arbitrary measurements, names, coordinates or private fields", () => {
    const result = envelope("retail_lookup", {
      fresh_or_dried: "우리 엄마 010-1234-5678",
      source_ids: ["우리집"],
      latitude: 33.1234,
    });
    result.result.price_cards = [
      {
        source_url: "https://tamnao.com.evil.example",
        product: "지인 홍길동",
        price_value: 999999,
      },
    ];
    const text = getChatReplySuggestions([answer({ envelope: result })]).join();
    expect(text).not.toMatch(PRIVATE_HINT);
  });

  it("filters a question already asked, ignoring spacing and punctuation", () => {
    const user: ChatMessage = { id: "u", role: "user", text: "현재제주날씨를알려줘?" };
    expect(getChatReplySuggestions([user, answer()])).not.toContain("현재 제주 날씨를 알려줘");
    expect(getChatReplySuggestions([answer(), user])).toEqual([]);
  });
});
