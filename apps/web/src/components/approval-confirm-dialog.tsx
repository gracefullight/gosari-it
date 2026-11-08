import { useSetAtom } from "jotai";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatDisplayDate } from "@/lib/date-format";
import { downloadTextFile } from "@/lib/download-text-file";
import { ApiError, api, commitPathFor } from "@/lib/gosari.api";
import type { Consent, Preview } from "@/lib/gosari.types";
import { clearCommittedNotebookDraftAtom } from "@/stores/notebook-drafts.atoms";

interface ApprovalConfirmDialogProps {
  preview: Preview;
  onClose: () => void;
  onCommitted: (message: string) => void;
}

const ACTION_LABELS: Record<string, string> = {
  "contact.create": "지인 등록",
  "contact.update": "지인 수정",
  "contact.delete": "지인 삭제",
  "notebook.create": "수첩 기록 저장",
  "notebook.update": "수첩 기록 수정",
  "notebook.delete": "수첩 기록 삭제",
  "region.create": "지역 등록",
  "region.update": "지역 수정",
  "region.delete": "지역 삭제",
  "share.save": "나눔 기록 저장",
  "share.update": "나눔 기록 수정",
  "share.delete": "나눔 기록 삭제",
  "share.file": "공유 파일 생성",
};

const FIELD_LABELS: Record<string, string> = {
  name: "이름",
  relationship: "나와의 관계",
  notes: "메모",
  experience_date: "활동 날짜",
  companion_aliases: "동행 별칭",
  activity_text: "경험·메모 내용",
  location_address: "위치",
  visited_on: "방문 날짜",
  amount_value: "수량",
  amount_unit: "단위",
  kind: "지역 구분",
  local_alias: "지역 별칭",
  public_area_code: "주소·위치 메모",
  items: "나눔 대상 목록",
  unit_totals: "단위별 합계",
  filename: "파일 이름",
  content: "파일 내용",
  source_record_ids: "연결할 수첩",
  public_evidence_ids: "연결할 공개 조회",
  private_region_id: "관심 지역 연결",
};

function formatPreviewValue(key: string, value: unknown): string {
  if (key === "experience_date" || key === "visited_on") return formatDisplayDate(String(value));
  if (key === "source_record_ids" || key === "public_evidence_ids")
    return Array.isArray(value) ? `${value.length}건` : "";
  if (key === "private_region_id") return value ? "연결됨" : "";
  if (key === "kind") {
    return value === "existing"
      ? "기존 방문 지역"
      : value === "interest"
        ? "새 관심 지역"
        : String(value);
  }
  if (typeof value === "boolean") {
    return value ? "예" : "아니오";
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === "object") {
          const obj = item as Record<string, unknown>;
          if ("recipient_alias" in obj) {
            const date = obj.occurred_on ?? obj.planned_delivery;
            const delivery = date ? ` (${formatDisplayDate(String(date))})` : "";
            const status =
              obj.status === "delivered"
                ? " · 전달 완료"
                : obj.status === "planned"
                  ? " · 전달 예정"
                  : "";
            return `${String(obj.recipient_alias)}: ${String(obj.amount_value ?? "")}${String(obj.amount_unit ?? "")}${delivery}${status}`;
          }
          if ("amount_unit" in obj && "total_value" in obj) {
            return `${String(obj.amount_unit)} 총 ${String(obj.total_value)}${String(obj.amount_unit)} (${String(obj.item_count ?? 1)}건)`;
          }
          return "";
        }
        return typeof item === "string" || typeof item === "number" ? String(item) : "";
      })
      .filter(Boolean)
      .join(" / ");
  }
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

export function ApprovalConfirmDialog({
  preview,
  onClose,
  onCommitted,
}: ApprovalConfirmDialogProps) {
  const clearCommittedDraft = useSetAtom(clearCommittedNotebookDraftAtom);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const issuedConsent = useRef<{ previewId: string; previewHash: string; consent: Consent } | null>(
    null
  );
  const label = ACTION_LABELS[preview.action] ?? "변경";
  const payload = preview.display_payload;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      let consent =
        issuedConsent.current?.previewId === preview.preview_id &&
        issuedConsent.current.previewHash === preview.preview_hash
          ? issuedConsent.current.consent
          : null;
      if (!consent) {
        consent = await api.consent(preview);
        issuedConsent.current = {
          previewId: preview.preview_id,
          previewHash: preview.preview_hash,
          consent,
        };
      }
      const result = await api.commit(commitPathFor(preview.action), preview, consent);
      if (result.state === "committed") {
        if (preview.action.startsWith("notebook.")) clearCommittedDraft(preview.preview_id);
        if (preview.action === "share.file" && typeof result.content === "string")
          downloadTextFile(result.filename || "나눔기록.txt", result.content);
        onCommitted(`${label} 완료`);
      } else {
        setError(result.safe_error ?? "반영 실패");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "승인 처리 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open: boolean) => {
        if (!open && !busy) {
          issuedConsent.current = null;
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{label} 확인</DialogTitle>
          <DialogDescription>내용을 확인해 주세요.</DialogDescription>
        </DialogHeader>
        <dl className="rounded-lg bg-muted p-3 text-base">
          {Object.entries(payload).map(([key, value]) => {
            if (value == null || !FIELD_LABELS[key]) return null;
            const formattedValue = formatPreviewValue(key, value);
            if (!formattedValue) return null;
            return (
              <div key={key} className="flex gap-2 py-1">
                <dt className="min-w-28 shrink-0 font-semibold text-foreground">
                  {FIELD_LABELS[key]}
                </dt>
                <dd
                  className={`break-words text-foreground ${key === "content" ? "whitespace-pre-wrap" : ""}`}
                >
                  {formattedValue}
                </dd>
              </div>
            );
          })}
        </dl>

        {error ? (
          <p className="text-base text-destructive" role="alert">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              issuedConsent.current = null;
              onClose();
            }}
            disabled={busy}
          >
            취소
          </Button>
          <Button onClick={confirm} disabled={busy}>
            {busy ? "처리 중…" : "확정"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
