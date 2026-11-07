import { ArrowSquareOutIcon } from "@phosphor-icons/react";
import { formatDisplayDate } from "@/lib/date-format";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { hasLandOwnershipData } from "@/lib/result-display";

function officialSource(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" ||
      (url.hostname !== "vworld.kr" && !url.hostname.endsWith(".vworld.kr")) ||
      url.username ||
      url.password ||
      url.port
    )
      return undefined;
    return url.toString();
  } catch {
    return undefined;
  }
}
const REFERENCE_MONTH = /^(\d{4})-?(\d{2})$/;
function referenceMonth(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const match = REFERENCE_MONTH.exec(value);
  return match && Number(match[2]) >= 1 && Number(match[2]) <= 12
    ? `${match[1]}-${match[2]}`
    : undefined;
}

export function LandOwnershipResults({ envelope }: { envelope: ResultEnvelope }) {
  if (!hasLandOwnershipData(envelope)) return null;
  const land = envelope.result.land_ownership as Record<string, unknown>;
  const officialName = typeof land.owner_type_name === "string" ? land.owner_type_name.trim() : "";
  const ownership =
    officialName ||
    (land.ownership_class === "private"
      ? "사유지"
      : land.ownership_class === "public"
        ? "국·공유지"
        : "");
  const location =
    typeof land.location_name === "string" && land.location_name.trim()
      ? land.location_name.trim()
      : "선택한 지점";
  const month = referenceMonth(land.reference_month);
  const updated =
    typeof land.last_updated === "string" && land.last_updated
      ? formatDisplayDate(land.last_updated)
      : undefined;
  const source = officialSource(land.source_url);
  return (
    <section aria-label="토지 소유 구분" className="min-w-0 space-y-4 text-base">
      <h3 className="break-words text-lg font-semibold">{location}</h3>
      <dl className="grid gap-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">{ownership ? "소유 구분" : "사유지 여부"}</dt>
          <dd className="font-semibold">
            {ownership || (land.is_private === true ? "예" : "아니오")}
          </dd>
        </div>
        {month ? (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <dt className="text-muted-foreground">기준월</dt>
            <dd className="tabular-nums">{month}</dd>
          </div>
        ) : updated ? (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <dt className="text-muted-foreground">갱신일</dt>
            <dd className="tabular-nums">{updated}</dd>
          </div>
        ) : null}
      </dl>
      <div className="flex min-h-11 items-center gap-2 text-base text-muted-foreground">
        <span>브이월드</span>
        {source ? (
          <a
            href={source}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="브이월드 공식 출처 (새 창)"
            className="inline-flex size-11 items-center justify-center rounded-lg text-primary hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          >
            <ArrowSquareOutIcon aria-hidden="true" className="size-5" />
          </a>
        ) : null}
      </div>
    </section>
  );
}
