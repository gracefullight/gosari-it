import { queryOptions } from "@tanstack/react-query";
import { waitForAnalysisJob } from "@/lib/analysis-jobs";
import { apiV1AnalysisJobsCreateJob } from "@/lib/api/generated/endpoints";
import type { ResultEnvelope } from "@/lib/api/generated/model/resultEnvelope";

export type PriceChannel = "retail" | "survey" | "wholesale";
export interface PriceFilters {
  settlement_date: string;
  settlement_date_end: string;
  market_ids: string[];
  fresh_or_dried: string;
  grade: string;
  package_code: string;
  package_weight_unit: string;
  origin_filter: string;
}
const PRICE_REQUESTS: Record<PriceChannel, Record<string, unknown>> = {
  retail: { operation: "retail_lookup", source_ids: ["retail_sample"], price_channel: "retail" },
  survey: { operation: "survey_link", source_ids: ["forestinfo"], price_channel: "survey" },
  wholesale: {
    operation: "market_query",
    source_ids: ["at_settlement"],
    price_channel: "wholesale",
  },
};

export function priceQueryOptions(channel: PriceChannel, filters?: PriceFilters) {
  const conditions =
    channel === "wholesale" && filters
      ? { ...filters, market_ids: [...filters.market_ids].sort() }
      : {};
  return queryOptions({
    queryKey: ["prices", "query-v2", channel, conditions] as const,
    queryFn: async (): Promise<ResultEnvelope> => {
      // Keep this read-only request alive so a quick menu return reuses it.
      const response = await apiV1AnalysisJobsCreateJob({
        spec: { ...PRICE_REQUESTS[channel], ...conditions },
      });
      const initial = response.data;
      if (!("job_id" in initial)) throw new Error("가격을 불러오지 못했습니다.");
      const job = await waitForAnalysisJob(initial);
      if (!("result" in job) || !job.result) {
        throw new Error(
          "error" in job && typeof job.error === "string"
            ? job.error
            : "가격을 불러오지 못했습니다."
        );
      }
      if (job.result.errors?.length && !Object.keys(job.result.result ?? {}).length) {
        throw new Error(job.result.errors[0].message);
      }
      return job.result;
    },
    staleTime: 10 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}
