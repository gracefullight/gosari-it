import { Button, Dialog } from "@gracefullight/krds-tw";
import { useState } from "react";
import { ApiError, api, commitPathFor } from "../lib/api";
import type { Preview } from "../lib/types";

interface ConfirmDialogProps {
  preview: Preview;
  onClose: () => void;
  onCommitted: (message: string) => void;
}

const ACTION_LABELS: Record<string, string> = {
  "notebook.create": "수첩 기록 저장",
  "notebook.update": "수첩 기록 수정",
  "notebook.delete": "수첩 기록 삭제",
  "region.create": "지역 등록",
  "region.update": "지역 수정",
  "region.delete": "지역 삭제",
  "share.save": "나눔 목록 저장",
};

export function ConfirmDialog({ preview, onClose, onCommitted }: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = ACTION_LABELS[preview.action] ?? preview.action;
  const payload = preview.display_payload;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const consent = await api.consent(preview);
      const result = await api.commit(commitPathFor(preview.action), preview, consent);
      if (result.state === "committed") {
        onCommitted(`${label}이(가) 반영되었습니다. (현재 세션 한정)`);
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
    <Dialog open onClose={onClose} title={`${label} 확인`}>
      <div className="flex flex-col gap-3 p-2">
        <p className="text-sm text-gray-600">
          아래 내용이 정확히 반영됩니다. 취소하면 아무 변경도 없습니다.
        </p>
        <dl className="rounded-lg bg-gray-50 p-3 text-sm">
          {Object.entries(payload).map(([key, value]) => {
            if (value == null || key.endsWith("_ids")) return null;
            return (
              <div key={key} className="flex gap-2 py-1">
                <dt className="shrink-0 font-semibold text-gray-700">{key}</dt>
                <dd className="break-words text-gray-900">
                  {Array.isArray(value) ? value.join(", ") : String(value)}
                </dd>
              </div>
            );
          })}
        </dl>
        {preview.action === "share.save" && typeof payload.editable_message === "string" && (
          <div className="rounded-lg border border-gray-200 p-3">
            <p className="mb-1 text-xs font-semibold text-gray-500">준비된 문구 (전송 없음)</p>
            <p className="whitespace-pre-wrap text-sm">{String(payload.editable_message)}</p>
          </div>
        )}
        {Boolean(error) && (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button variant="primary" onClick={confirm} disabled={busy}>
            {busy ? "처리 중…" : "확정"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
