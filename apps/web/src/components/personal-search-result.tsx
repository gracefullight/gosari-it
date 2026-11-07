import { ArrowRightIcon } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useSetAtom } from "jotai";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/gosari.api";
import type { PersonalSearchResponse } from "@/lib/gosari.types";
import { navigateToPathAtom } from "@/stores/chat.atoms";

const LABELS = { notebook: "수첩", region: "관심 지역", contact: "지인", share: "나눔" };
function itemPath(item: PersonalSearchResponse["items"][number]) {
  if (item.kind === "notebook") return `/notebook/${encodeURIComponent(item.id)}/edit`;
  if (item.kind === "region") return `/regions?region=${encodeURIComponent(item.id)}`;
  if (item.kind === "contact") return `/share?contact=${encodeURIComponent(item.id)}`;
  return "/share";
}
export function PersonalSearchResult({ query }: { query: string }) {
  const navigate = useSetAtom(navigateToPathAtom);
  const result = useQuery({
    queryKey: ["personal-search", query],
    queryFn: () => api.personalSearch(query),
    staleTime: 0,
    gcTime: 5 * 60_000,
    retry: 1,
  });
  if (result.isPending)
    return (
      <p role="status" className="text-base text-muted-foreground">
        내 기록을 찾고 있습니다…
      </p>
    );
  if (result.isError)
    return (
      <div role="alert" className="rounded-xl border border-border p-4">
        <p>{result.error.message}</p>
        <Button variant="outline" className="mt-3" onClick={() => void result.refetch()}>
          다시 찾기
        </Button>
      </div>
    );
  return (
    <section className="rounded-2xl border border-border bg-card p-5">
      <h2 className="mb-4 text-lg font-semibold">내 기록 검색</h2>
      <p className="mb-3 text-base">{result.data.answer}</p>
      <ul className="divide-y divide-border">
        {result.data.items.map((item) => (
          <li key={`${item.kind}:${item.id}`} className="py-4">
            <div className="mb-2 flex flex-wrap items-center gap-3 text-base text-muted-foreground">
              <span>{LABELS[item.kind]}</span>
              {item.date ? <time>{item.date}</time> : null}
            </div>
            <button
              type="button"
              className="flex min-h-11 w-full items-center justify-between gap-3 text-left font-semibold text-primary hover:underline focus-visible:outline-2 focus-visible:outline-ring"
              onClick={() => navigate(itemPath(item))}
            >
              {item.title}
              <ArrowRightIcon className="size-5 shrink-0" aria-hidden="true" />
            </button>
            <p className="mt-1 whitespace-pre-wrap text-base text-muted-foreground">
              {item.snippet}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
