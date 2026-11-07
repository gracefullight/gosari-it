import {
  ActionProvider,
  type Components,
  defineRegistry,
  Renderer,
  StateProvider,
  useActions,
  useStateStore,
  useStateValue,
  ValidationProvider,
  VisibilityProvider,
} from "@json-render/react";
import { type ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  AgentOutingResults,
  AgentPriceResults,
  AgentStationResults,
  AgentWeatherComparison,
  AgentWeatherMap,
} from "@/components/agent-result-views";
import { AnalysisConditionFields } from "@/components/analysis-condition-form";
import { InlineOutingConditionForm } from "@/components/inline-outing-condition-form";
import { InlinePriceConditionForm } from "@/components/inline-price-condition-form";
import { Button } from "@/components/ui/button";
import {
  AGENT_ACTION_LABELS,
  type AgentUIAction,
  agentUICatalog,
  parseAgentUISpec,
} from "@/lib/agent-ui.catalog";
import type { PrepareResponse, ResultEnvelope } from "@/lib/gosari.types";

export interface AgentGeneratedUIProps {
  spec: unknown;
  results: Record<string, ResultEnvelope>;
  preparations?: Record<string, PrepareResponse>;
  onAction: (action: AgentUIAction) => void | Promise<void>;
  onConfirm?: (spec: Record<string, unknown>, label: string) => void | Promise<void>;
  fallback?: ReactNode;
}

function ResultNode({ resultRef, type }: { resultRef: string; type: string }) {
  const envelope = useStateValue<ResultEnvelope>(`/results/${resultRef}`);
  const views = useStateValue<Record<string, string>>("/views");
  const { execute } = useActions();
  if (!envelope) return null;
  if (type === "PriceResults")
    return (
      <AgentPriceResults
        envelope={envelope}
        table={views?.[resultRef] === "table"}
        onList={() => {
          void execute({ action: "show_price_table", params: { resultRef, view: "cards" } });
        }}
      />
    );
  if (views?.[resultRef] === "map") return <AgentWeatherMap envelope={envelope} />;
  if (type === "OutingResults") return <AgentOutingResults envelope={envelope} />;
  if (type === "StationResults") return <AgentStationResults envelope={envelope} />;
  return type === "WeatherMap" || views?.[resultRef] === "map" ? (
    <AgentWeatherMap envelope={envelope} />
  ) : (
    <AgentWeatherComparison envelope={envelope} />
  );
}

function PreparationNode({ preparationRef, type }: { preparationRef: string; type: string }) {
  const prepare = useStateValue<PrepareResponse>(`/preparations/${preparationRef}`);
  if (!prepare) return null;
  return type === "ConditionForm" ? (
    <AnalysisConditionFields prepare={prepare} />
  ) : (
    <ConditionNode prepare={prepare} price={type === "PriceConditions"} />
  );
}

function DataBindings({
  results,
  preparations,
}: Pick<AgentGeneratedUIProps, "results" | "preparations">) {
  const state = useStateStore();
  useEffect(() => {
    state.update({ "/results": results, "/preparations": preparations ?? {} });
  }, [state.update, results, preparations]);
  return null;
}
function FollowupButtons({ actions }: { actions: AgentUIAction[] }) {
  const { execute, loadingActions } = useActions();
  const [error, setError] = useState("");
  return (
    <div className="border-t border-border pt-4">
      <fieldset className="flex flex-wrap gap-2" aria-label="결과 이어서 보기">
        {actions.map((action) => (
          <Button
            key={`${action.id}-${action.resultRef}`}
            type="button"
            variant="outline"
            className="min-h-11 max-w-full whitespace-normal text-base"
            disabled={loadingActions.has(action.id)}
            onClick={async () => {
              setError("");
              try {
                await execute({ action: action.id, params: { resultRef: action.resultRef } });
              } catch {
                setError("작업을 이어가지 못했습니다. 다시 눌러 주세요.");
              }
            }}
          >
            {AGENT_ACTION_LABELS[action.id]}
          </Button>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className="mt-3 text-base text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
function ConditionNode({ prepare, price }: { prepare: PrepareResponse; price: boolean }) {
  const { execute } = useActions();
  const [error, setError] = useState("");
  const onConfirm = (spec: Record<string, unknown>, label: string) => {
    setError("");
    void execute({ action: "confirm_conditions", params: { spec, label } }).catch(() =>
      setError("조건을 확인하고 다시 조회해 주세요.")
    );
  };
  return (
    <section
      aria-label={price ? "가격 조회 조건" : "나들이 조회 조건"}
      className="min-w-0 rounded-xl border border-border bg-card p-4"
    >
      <h3 className="mb-4 text-lg font-semibold">{price ? "가격 조건" : "나들이 조건"}</h3>
      {price ? (
        <InlinePriceConditionForm prepare={prepare} onConfirm={onConfirm} />
      ) : (
        <InlineOutingConditionForm prepare={prepare} onConfirm={onConfirm} />
      )}
      {error ? (
        <p role="alert" className="mt-3 text-base text-destructive">
          {error}
        </p>
      ) : null}
    </section>
  );
}

type RegistryResult = ReturnType<typeof defineRegistry<typeof agentUICatalog>>;
const AGENT_COMPONENTS: Components<typeof agentUICatalog> = {
  ResultLayout: ({ children }) => (
    <div className="min-w-0 space-y-5 text-base" data-agent-ui="true">
      {children}
    </div>
  ),
  PriceResults: ({ props: { resultRef } }) => (
    <ResultNode resultRef={resultRef} type="PriceResults" />
  ),
  WeatherMap: ({ props: { resultRef } }) => <ResultNode resultRef={resultRef} type="WeatherMap" />,
  WeatherComparison: ({ props: { resultRef } }) => (
    <ResultNode resultRef={resultRef} type="WeatherComparison" />
  ),
  OutingResults: ({ props: { resultRef } }) => (
    <ResultNode resultRef={resultRef} type="OutingResults" />
  ),
  StationResults: ({ props: { resultRef } }) => (
    <ResultNode resultRef={resultRef} type="StationResults" />
  ),
  FollowupActions: ({ props }) => <FollowupButtons actions={props.actions} />,
  PriceConditions: ({ props: { preparationRef } }) => (
    <PreparationNode preparationRef={preparationRef} type="PriceConditions" />
  ),
  OutingConditions: ({ props: { preparationRef } }) => (
    <PreparationNode preparationRef={preparationRef} type="OutingConditions" />
  ),
  ConditionForm: ({ props: { preparationRef } }) => (
    <PreparationNode preparationRef={preparationRef} type="ConditionForm" />
  ),
};
function ActionScope({
  registration,
  children,
}: {
  registration: RegistryResult;
  children: ReactNode;
}) {
  const state = useStateStore();
  const handlers = registration.handlers(
    () => (updater) => {
      const next = updater(state.getSnapshot());
      state.set("/views", next.views ?? {});
    },
    () => state.getSnapshot()
  );
  return <ActionProvider handlers={handlers}>{children}</ActionProvider>;
}

export function AgentGeneratedUI(props: AgentGeneratedUIProps) {
  const latest = useRef(props);
  useLayoutEffect(() => {
    latest.current = props;
  });
  const registration = useMemo(() => {
    const forward = async (id: AgentUIAction["id"], params: { resultRef: string } | undefined) => {
      if (!params || !latest.current.results[params.resultRef]) return;
      await latest.current.onAction({
        id,
        resultRef: params.resultRef,
        label: AGENT_ACTION_LABELS[id],
      });
    };
    return defineRegistry(agentUICatalog, {
      components: AGENT_COMPONENTS,
      actions: {
        adjust_conditions: async (params) => forward("adjust_conditions", params),
        save_to_notebook: async (params) => forward("save_to_notebook", params),
        compare_dates: async (params) => forward("compare_dates", params),
        compare_packages: async (params) => forward("compare_packages", params),
        show_price_table: async (params, setState) => {
          if (!params || !latest.current.results[params.resultRef]) return;
          setState((state) => ({
            ...state,
            views: {
              ...(state.views as Record<string, unknown>),
              [params.resultRef]: params.view ?? "table",
            },
          }));
        },
        show_weather_map: async (params, setState) => {
          if (!params || !latest.current.results[params.resultRef]) return;
          setState((state) => ({
            ...state,
            views: { ...(state.views as Record<string, unknown>), [params.resultRef]: "map" },
          }));
        },
        confirm_conditions: async (params) => {
          if (params) await latest.current.onConfirm?.(params.spec, params.label);
        },
      },
    });
  }, []);
  const spec = parseAgentUISpec(props.spec, props.results, props.preparations);
  if (!spec) return <>{props.fallback ?? null}</>;
  return (
    <StateProvider
      initialState={{ views: {}, results: props.results, preparations: props.preparations ?? {} }}
    >
      <DataBindings results={props.results} preparations={props.preparations} />
      <VisibilityProvider>
        <ValidationProvider>
          <ActionScope registration={registration}>
            <Renderer spec={spec} registry={registration.registry} />
          </ActionScope>
        </ValidationProvider>
      </VisibilityProvider>
    </StateProvider>
  );
}
