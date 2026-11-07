import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { PublicEvidenceSelector } from "@/components/public-evidence-links";
import { api } from "@/lib/gosari.api";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { publicEvidenceLabel } from "@/lib/public-evidence-label";
import { messagesAtom } from "@/stores/chat.atoms";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function result(
  operation: string,
  ids: string[],
  scope: Record<string, unknown>,
  values: Record<string, unknown>
): ResultEnvelope {
  return {
    schema_version: "result-v1",
    request_id: "public-query",
    data_status: "complete",
    source_mode: "fetched",
    action_status: null,
    link_status: "not_requested",
    cache_resolution: "miss",
    requested_scope: { operation, ...scope },
    effective_scope: {},
    result: values,
    evidence_ids: ids,
    observed_period: {},
    fetched_at: null,
    verified_on: null,
    warnings: [],
    errors: [],
  };
}
function Harness({
  initial = [],
  onChange,
}: {
  initial?: string[];
  onChange: (ids: string[]) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <PublicEvidenceSelector
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

it("groups a weather query into one readable, collapsed choice and keeps every source reference", () => {
  const store = createStore();
  store.set(messagesAtom, [
    {
      id: "message",
      role: "assistant",
      ui_results: {
        result_1: result(
          "outing_compare",
          ["hidden-source-a", "hidden-source-b"],
          {},
          {
            candidates: [
              { station_name: "애월", target_date: "2026-11-08", target_time_window: "09:00" },
            ],
          }
        ),
      },
    },
  ]);
  const changed = vi.fn();
  render(
    <Provider store={store}>
      <Harness onChange={changed} />
    </Provider>
  );
  expect(screen.getByText("날씨·가격 자료 연결").closest("details")?.open).toBe(false);
  expect(document.body.textContent).not.toContain("공개 조회");
  expect(document.body.textContent).not.toContain("(1)");
  expect(document.body.textContent).not.toContain("hidden-source");
  fireEvent.click(screen.getByText("날씨·가격 자료 연결"));
  const checkbox = screen.getByRole("checkbox", { name: "애월 나들이 날씨 · 2026-11-08 09:00" });
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  fireEvent.click(checkbox);
  expect(changed).toHaveBeenLastCalledWith(["hidden-source-a", "hidden-source-b"]);
  fireEvent.click(
    screen.getByRole("button", { name: "애월 나들이 날씨 · 2026-11-08 09:00 연결 해제" })
  );
  expect(changed).toHaveBeenLastCalledWith([]);
});

it("names a retained map reference from its public date and place without clearing it", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue({
    public_query_spec: {
      operation: "outing_compare",
      candidates: [{ location_id: "seongsan", date: "2026-11-09", time_slot: "12:00" }],
    },
    result_values: {},
  });
  const changed = vi.fn();
  render(
    <Provider>
      <Harness initial={["retained-id"]} onChange={changed} />
    </Provider>
  );
  await screen.findByRole("button", { name: "성산 나들이 날씨 · 2026-11-09 12:00 연결 해제" });
  expect(changed).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain("retained-id");
});

it("keeps an unavailable old reference until the user explicitly unlinks it", async () => {
  vi.spyOn(api, "evidence").mockRejectedValue(new Error("missing"));
  const changed = vi.fn();
  render(
    <Provider>
      <Harness initial={["old-id"]} onChange={changed} />
    </Provider>
  );
  await screen.findByRole("button", { name: "이전에 연결한 자료 연결 해제" });
  expect(changed).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "이전에 연결한 자료 연결 해제" }));
  expect(changed).toHaveBeenLastCalledWith([]);
});

it("labels actual price-card and history results using conditions instead of generic query numbers", () => {
  expect(
    publicEvidenceLabel(
      result(
        "market_query",
        ["id"],
        { market_ids: ["110001"], fresh_or_dried: "생고사리", settlement_date: "2026-11-04" },
        { sample_cards: [{ price_value: 22000 }] }
      )
    )
  ).toBe("서울가락 생고사리 도매 가격 · 2026-11-04");
  expect(
    publicEvidenceLabel(
      result(
        "history_compare",
        ["id"],
        { station_selections: [{ station_name: "선흘" }] },
        { daily_rainfall: {} }
      )
    )
  ).toBe("선흘 과거 날씨 비교");
});
