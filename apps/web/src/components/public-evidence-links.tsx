import { useAtomValue } from "jotai";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatDisplayDate } from "@/lib/date-format";
import { api } from "@/lib/gosari.api";
import { publicEvidenceLabel } from "@/lib/public-evidence-label";
import { featureResultsAtom, messagesAtom } from "@/stores/chat.atoms";

interface EvidenceChoice {
  ids: string[];
  label: string;
}

export function PublicEvidenceSelector({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const results = useAtomValue(featureResultsAtom);
  const messages = useAtomValue(messagesAtom);
  const candidates = useMemo(() => {
    const choices: EvidenceChoice[] = [];
    const seen = new Set<string>();
    for (const result of [
      ...Object.values(results),
      ...messages.flatMap((message) => [
        message.envelope,
        ...Object.values(message.ui_results ?? {}),
        ...(message.stream?.tools.map((tool) => tool.result) ?? []),
      ]),
    ]) {
      if (!result) continue;
      const ids = result.evidence_ids.filter((id) => !seen.has(id));
      if (!ids.length) continue;
      for (const id of ids) seen.add(id);
      choices.push({ ids, label: publicEvidenceLabel(result) });
    }
    return choices;
  }, [results, messages]);
  const retained = useMemo(
    () => value.filter((id) => !candidates.some((choice) => choice.ids.includes(id))),
    [value, candidates]
  );
  const [retainedLabels, setRetainedLabels] = useState<Record<string, string>>({});
  useEffect(() => {
    let active = true;
    if (retained.length)
      void Promise.all(
        retained.map(async (id) => {
          try {
            return [id, publicEvidenceLabel(await api.evidence(id))] as const;
          } catch {
            return [id, "이전에 연결한 자료"] as const;
          }
        })
      ).then((entries) => {
        if (active) setRetainedLabels(Object.fromEntries(entries));
      });
    return () => {
      active = false;
    };
  }, [retained]);
  const choices = candidates.map((choice) => ({ ...choice, ids: [...choice.ids] }));
  for (const id of retained) {
    const label = retainedLabels[id] ?? "이전에 연결한 자료";
    const existing = choices.find((choice) => choice.label === label);
    if (existing) existing.ids = [...existing.ids, id];
    else choices.push({ ids: [id], label });
  }
  if (!choices.length) return null;
  const selected = choices.filter((choice) => choice.ids.some((id) => value.includes(id)));
  return (
    <section aria-label="참고 자료" className="grid min-w-0 gap-3">
      {selected.length ? (
        <ul className="grid gap-2 text-base">
          {selected.map((choice) => (
            <li
              key={choice.ids.join(":")}
              className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg bg-muted px-3 py-2"
            >
              <span className="min-w-0 break-words">{choice.label}</span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`${choice.label} 연결 해제`}
                onClick={() => onChange(value.filter((id) => !choice.ids.includes(id)))}
              >
                연결 해제
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <details className="min-w-0">
        <summary className="flex min-h-11 cursor-pointer items-center text-base text-primary">
          날씨·가격 자료 연결
        </summary>
        <fieldset className="mt-2 grid gap-2" aria-label="연결할 자료">
          {choices.map((choice) => (
            <label
              key={choice.ids.join(":")}
              className="flex min-h-11 cursor-pointer items-center gap-3 text-base"
            >
              <input
                type="checkbox"
                className="size-5 shrink-0 accent-primary"
                checked={choice.ids.every((id) => value.includes(id))}
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...new Set([...value, ...choice.ids])]
                      : value.filter((id) => !choice.ids.includes(id))
                  )
                }
              />
              <span className="min-w-0 break-words">{choice.label}</span>
            </label>
          ))}
        </fieldset>
      </details>
    </section>
  );
}

const VALUE_LABELS: Record<string, string> = {
  station_count: "관측 지점",
  temperature_c: "기온 (℃)",
  mean_temperature: "평균 기온 (℃)",
  precipitation_probability: "강수 확률 (%)",
  precipitation_mm: "강수량 (mm)",
  rain_valid_days: "강수 기록일",
  rain_positive_days: "비 온 날",
  price: "가격 (원)",
  producer_price: "생산지 가격 (원)",
  wholesale_price: "도매 가격 (원)",
  retail_price: "소비지 가격 (원)",
};
interface EvidenceSource {
  source_id?: string;
  verified_on?: string;
  source_mode?: string;
  transport_status?: string;
  failed_scope?: Record<string, unknown>;
}

function hasFailedScope(source: EvidenceSource): boolean {
  return Object.values(source.failed_scope ?? {}).some((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "number") return value > 0;
    if (value && typeof value === "object") return Object.keys(value).length > 0;
    return Boolean(value);
  });
}

export function PublicEvidenceLinks({ ids }: { ids: string[] }) {
  const [open, setOpen] = useState(false);
  const [records, setRecords] = useState<{ id: string; value: Record<string, unknown> }[]>([]);
  const [missingCount, setMissingCount] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  if (!ids.length) return null;
  async function show() {
    setOpen(true);
    setState("loading");
    setMissingCount(0);
    const loaded = await Promise.allSettled(ids.map((id) => api.evidence(id)));
    const found = loaded.flatMap((entry, index) =>
      entry.status === "fulfilled" ? [{ id: ids[index], value: entry.value }] : []
    );
    setRecords(found);
    setMissingCount(loaded.length - found.length);
    setState(found.length ? "ready" : "error");
  }
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => void show()}>
        참고 자료 보기
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          showCloseButton={false}
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto text-base"
        >
          <DialogHeader>
            <DialogTitle>참고 자료</DialogTitle>
          </DialogHeader>
          {state === "loading" ? (
            <p role="status">조회 불러오는 중…</p>
          ) : state === "error" ? (
            <p role="status">{missingCount}건을 불러오지 못했습니다.</p>
          ) : (
            <div className="grid gap-4">
              {missingCount > 0 ? (
                <p role="status" className="text-base text-muted-foreground">
                  {missingCount}건을 불러오지 못했습니다.
                </p>
              ) : null}
              <ul className="grid gap-5">
                {records.map(({ id, value: record }) => {
                  const values = record.result_values as Record<string, unknown> | undefined;
                  const manifests = (record.source_manifests ?? []) as EvidenceSource[];
                  const quality = record.quality_summary as Record<string, unknown> | undefined;
                  const dataStatus = record.data_status ?? quality?.data_status ?? values?.status;
                  const replay =
                    record.source_mode === "replay" ||
                    manifests.some((source) => source.source_mode === "replay");
                  const partial =
                    dataStatus === "partial" ||
                    manifests.some(
                      (source) => source.transport_status === "partial" || hasFailedScope(source)
                    );
                  const sources = [
                    ...new Set(
                      (manifests ?? []).map((item) =>
                        item.source_id === "kma_aws" || item.source_id?.startsWith("kma")
                          ? "기상청"
                          : item.source_id === "open_meteo"
                            ? "Open-Meteo 날씨"
                            : item.source_id?.includes("forest")
                              ? "산림조합"
                              : "공개 자료"
                      )
                    ),
                  ];
                  return (
                    <li key={id} className="grid gap-2 border-b border-border pb-4 last:border-0">
                      <p className="font-medium">{publicEvidenceLabel(record)}</p>
                      <p className="text-base text-muted-foreground">
                        {sources.join(" · ") || "자료"}
                      </p>
                      {replay ||
                      partial ||
                      dataStatus === "needs_confirmation" ||
                      dataStatus === "unavailable" ||
                      dataStatus === "no_data" ? (
                        <div className="flex flex-wrap gap-2">
                          {replay ? <Badge variant="secondary">표본 자료</Badge> : null}
                          {partial ? <Badge variant="secondary">일부 자료</Badge> : null}
                          {dataStatus === "needs_confirmation" ? (
                            <Badge variant="secondary">확인 필요</Badge>
                          ) : null}
                          {dataStatus === "unavailable" || dataStatus === "no_data" ? (
                            <Badge variant="secondary">자료 없음</Badge>
                          ) : null}
                        </div>
                      ) : null}
                      {manifests?.[0]?.verified_on ? (
                        <p className="text-base text-muted-foreground">
                          확인 날짜 {formatDisplayDate(manifests[0].verified_on)}
                        </p>
                      ) : null}
                      {typeof values?.date === "string" ? (
                        <p>{formatDisplayDate(values.date)}</p>
                      ) : null}
                      {Array.isArray(values?.locations) ? (
                        <ul className="grid gap-2">
                          {(
                            values.locations as {
                              id: string;
                              name: string;
                              temperature_c: number | null;
                              precipitation_probability: number | null;
                            }[]
                          ).map((location) => (
                            <li key={location.id} className="flex flex-wrap justify-between gap-3">
                              <span>{location.name}</span>
                              <span className="tabular-nums">
                                {location.temperature_c ?? "—"}℃ · 비{" "}
                                {location.precipitation_probability ?? "—"}%
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <dl className="grid gap-2">
                        {Object.entries(values ?? {}).flatMap(([key, value]) =>
                          VALUE_LABELS[key] &&
                          (typeof value === "string" || typeof value === "number")
                            ? [
                                <div key={key} className="flex justify-between gap-4">
                                  <dt>{VALUE_LABELS[key]}</dt>
                                  <dd className="tabular-nums">{value}</dd>
                                </div>,
                              ]
                            : []
                        )}
                      </dl>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <Button variant="outline" className="min-h-11" onClick={() => setOpen(false)}>
            닫기
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}
