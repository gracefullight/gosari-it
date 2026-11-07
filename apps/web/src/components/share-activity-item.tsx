import { PublicEvidenceLinks } from "@/components/public-evidence-links";
import { Button } from "@/components/ui/button";
import { formatDisplayDate } from "@/lib/date-format";
import type { NotebookEntry, ShareDraft, ShareItem } from "@/lib/gosari.types";

export interface SharingActivity {
  key: string;
  item: ShareItem;
  recordedAt: string;
  draft: ShareDraft;
  index: number;
}

interface ShareActivityItemProps {
  activity: SharingActivity;
  notebooks: NotebookEntry[];
  busy: boolean;
  onEdit: (activity: SharingActivity, delivered?: boolean) => void;
  onDelete: (activity: SharingActivity) => void;
}

export function ShareActivityItem({
  activity,
  notebooks,
  busy,
  onEdit,
  onDelete,
}: ShareActivityItemProps) {
  const { item, recordedAt, draft } = activity;
  return (
    <li className="relative ml-1 border-l border-border pb-6 pl-6 last:pb-1">
      <span
        className={`absolute top-1 -left-1.5 size-3 rounded-full border-2 border-card ${item.status === "delivered" ? "bg-primary" : "bg-muted-foreground"}`}
      />
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium tabular-nums">
          {item.recipient_alias}{" "}
          <span className="ml-2">
            {Number(item.amount_value).toLocaleString()}
            {item.amount_unit}
          </span>
        </p>
        <span className="text-base text-muted-foreground">
          {item.status === "delivered" ? "전달 완료" : "전달 예정"}
        </span>
      </div>
      <p className="mt-1 text-base tabular-nums text-muted-foreground">
        {item.occurred_on || item.planned_delivery
          ? formatDisplayDate(item.occurred_on ?? item.planned_delivery)
          : `등록 ${formatDisplayDate(recordedAt)}`}
      </p>
      {draft.source_record_ids.length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {draft.source_record_ids.map((id) => {
            const entry = notebooks.find((record) => record.record_id === id);
            return entry ? (
              <a
                key={id}
                href={`/notebook/${encodeURIComponent(id)}/edit`}
                className="inline-flex min-h-11 items-center text-base text-primary underline underline-offset-4"
              >
                수첩 · {formatDisplayDate(entry.experience_date)}
              </a>
            ) : (
              <span key={id} className="text-base text-muted-foreground">
                연결된 이전 수첩 기록
              </span>
            );
          })}
        </div>
      ) : null}
      <PublicEvidenceLinks ids={draft.public_evidence_ids} />
      <div className="mt-2 flex flex-wrap gap-2">
        {item.status !== "delivered" ? (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => onEdit(activity, true)}
          >
            전달 완료로 변경
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => onEdit(activity)}>
          기록 수정
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => onDelete(activity)}>
          기록 삭제
        </Button>
      </div>
      {item.optional_role_note ? (
        <p className="mt-2 text-base text-muted-foreground">{item.optional_role_note}</p>
      ) : null}
    </li>
  );
}
