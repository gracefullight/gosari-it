import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react/schema";
import { z } from "zod";
import type { PrepareResponse, ResultEnvelope } from "@/lib/gosari.types";

export const AGENT_ACTION_LABELS = {
  adjust_conditions: "조건 변경",
  save_to_notebook: "수첩에 기록",
  show_weather_map: "지도 보기",
  show_price_table: "표로 보기",
  compare_dates: "날짜 비교",
  compare_packages: "다른 규격",
} as const;

export const AGENT_ACTION_IDS = [
  "adjust_conditions",
  "save_to_notebook",
  "show_weather_map",
  "show_price_table",
  "compare_dates",
  "compare_packages",
] as const;

export interface AgentUIAction {
  id: (typeof AGENT_ACTION_IDS)[number];
  resultRef: string;
  label?: string;
  values?: Record<string, unknown>;
}

const reference = z
  .string()
  .min(1)
  .max(80)
  .regex(/^[A-Za-z0-9_-]+$/);
const resultProps = z.strictObject({ resultRef: reference });
const preparationProps = z.strictObject({ preparationRef: reference });
const followupAction = z.strictObject({
  id: z.enum(AGENT_ACTION_IDS),
  label: z.string().max(80).optional(),
  resultRef: reference,
});
const followupProps = z.strictObject({ actions: z.array(followupAction).max(8) });
const actionParams = z.object({
  resultRef: reference,
  view: z.enum(["cards", "table"]).optional(),
});

export const agentUICatalog = defineCatalog(schema, {
  components: {
    ResultLayout: {
      props: z.strictObject({}),
      slots: ["default"],
      description: "검증된 조회 결과와 후속 작업을 세로로 배치합니다.",
    },
    PriceResults: {
      props: resultProps,
      description: "검증된 가격의 상품·규격·기준일을 표시합니다.",
    },
    WeatherMap: {
      props: resultProps,
      description: "공개 지역의 실제 날씨 결과를 제주 지도에 표시합니다.",
    },
    WeatherComparison: { props: resultProps, description: "검증된 날씨 관측·예보를 비교합니다." },
    OutingResults: {
      props: resultProps,
      description: "나들이 순위·날씨와 편집 가능한 준비 목록입니다.",
    },
    StationResults: { props: resultProps, description: "공개 관측소 목록과 검색을 표시합니다." },
    FollowupActions: {
      props: followupProps,
      description: "결과 조건 변경·비교·기록 작업을 제공합니다.",
    },
    PriceConditions: {
      props: preparationProps,
      description: "가격 조회 조건을 선택하고 조회합니다.",
    },
    OutingConditions: {
      props: preparationProps,
      description: "공개 지역·날짜·시간을 선택하고 비교합니다.",
    },
    ConditionForm: { props: preparationProps, description: "추가 공개 조회 조건을 확인합니다." },
  },
  actions: {
    adjust_conditions: { params: actionParams, description: "선택 결과의 조회 조건을 변경합니다." },
    save_to_notebook: { params: actionParams, description: "근거를 연결한 수첩 초안을 엽니다." },
    show_weather_map: { params: actionParams, description: "같은 날씨 결과를 지도에서 봅니다." },
    show_price_table: { params: actionParams, description: "같은 가격 결과를 표로 봅니다." },
    compare_dates: { params: actionParams, description: "다른 날짜를 선택해 비교합니다." },
    compare_packages: { params: actionParams, description: "다른 규격을 선택해 비교합니다." },
    confirm_conditions: {
      params: z.object({ spec: z.record(z.string(), z.unknown()), label: z.string() }),
      description: "이용자가 직접 선택한 조건으로 조회합니다.",
    },
  },
});

const viewTypes = [
  "PriceResults",
  "WeatherMap",
  "WeatherComparison",
  "OutingResults",
  "StationResults",
] as const;
const resultNode = z.strictObject({
  type: z.enum(viewTypes),
  props: resultProps,
  children: z.array(z.string()).max(0).optional(),
});
const preparationNode = z.strictObject({
  type: z.enum(["PriceConditions", "OutingConditions", "ConditionForm"]),
  props: preparationProps,
  children: z.array(z.string()).max(0).optional(),
});
const actionNode = z.strictObject({
  type: z.literal("FollowupActions"),
  props: followupProps,
  children: z.array(z.string()).max(0).optional(),
});
const layoutNode = z.strictObject({
  type: z.literal("ResultLayout"),
  props: z.strictObject({}),
  children: z.array(z.string()).min(1).max(20),
});
const specSchema = z.strictObject({
  root: reference,
  elements: z.record(reference, z.union([layoutNode, resultNode, preparationNode, actionNode])),
});
export type AgentUISpec = z.infer<typeof specSchema>;

/** The renderer only accepts known components with existing data references. */
export function parseAgentUISpec(
  value: unknown,
  results: Record<string, ResultEnvelope>,
  preparations: Record<string, PrepareResponse> = {}
): AgentUISpec | null {
  const checked = specSchema.safeParse(value);
  if (!checked.success) return null;
  const spec = checked.data;
  const keys = Object.keys(spec.elements);
  if (!keys.length || keys.length > 24 || spec.elements[spec.root]?.type !== "ResultLayout")
    return null;
  const visited = new Set<string>();
  const visit = (key: string, depth: number): boolean => {
    if (depth > 3 || visited.has(key) || !Object.hasOwn(spec.elements, key)) return false;
    const node = spec.elements[key];
    if (!node) return false;
    visited.add(key);
    if (node.type === "ResultLayout")
      return node.children.every((child) => visit(child, depth + 1));
    if (node.type === "FollowupActions")
      return node.props.actions.every(
        (action) => Object.hasOwn(results, action.resultRef) && Boolean(results[action.resultRef])
      );
    if (
      node.type === "PriceConditions" ||
      node.type === "OutingConditions" ||
      node.type === "ConditionForm"
    )
      return (
        Object.hasOwn(preparations, node.props.preparationRef) &&
        Boolean(preparations[node.props.preparationRef])
      );
    return (
      "resultRef" in node.props &&
      Object.hasOwn(results, node.props.resultRef) &&
      Boolean(results[node.props.resultRef])
    );
  };
  return visit(spec.root, 0) && visited.size === keys.length ? spec : null;
}

export function isAgentUISpec(
  value: unknown,
  results: Record<string, ResultEnvelope> = {},
  preparations: Record<string, PrepareResponse> = {}
): value is AgentUISpec {
  return parseAgentUISpec(value, results, preparations) !== null;
}
