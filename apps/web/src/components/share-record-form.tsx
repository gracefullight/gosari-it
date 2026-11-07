import { DatePickerField } from "@/components/date-picker-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDisplayDate } from "@/lib/date-format";
import type { NotebookEntry } from "@/lib/gosari.types";

export interface ShareRecordValues {
  date: string;
  status: "planned" | "delivered";
  amount: string;
  unit: string;
  sourceRecord: string;
}

interface ShareRecordFormProps {
  recipientName: string;
  editing: boolean;
  values: ShareRecordValues;
  onChange: (values: ShareRecordValues) => void;
  notebooks: NotebookEntry[];
  busy: boolean;
  onCancel: () => void;
  onSave: () => void;
}

export function ShareRecordForm({
  recipientName,
  editing,
  values,
  onChange,
  notebooks,
  busy,
  onCancel,
  onSave,
}: ShareRecordFormProps) {
  return (
    <div className="mb-7 rounded-xl bg-muted/60 p-4">
      <h4 className="mb-4 font-semibold">
        {recipientName} 나눔 {editing ? "수정" : "기록"}
      </h4>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="share-occurred-on">날짜</Label>
          <DatePickerField
            id="share-occurred-on"
            required={values.status === "delivered"}
            aria-label="나눔 날짜"
            value={values.date}
            onChange={(date) => onChange({ ...values, date })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="share-status">상태</Label>
          <select
            id="share-status"
            value={values.status}
            onChange={(event) =>
              onChange({ ...values, status: event.target.value as "planned" | "delivered" })
            }
            className="min-h-11 rounded-lg border border-input bg-background px-3 text-base"
          >
            <option value="delivered">전달 완료</option>
            <option value="planned">전달 예정</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="share-amount">분량</Label>
          <Input
            id="share-amount"
            type="number"
            min="0"
            step="any"
            value={values.amount}
            onChange={(event) => onChange({ ...values, amount: event.target.value })}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="share-unit">단위</Label>
          <Input
            id="share-unit"
            value={values.unit}
            onChange={(event) => onChange({ ...values, unit: event.target.value })}
            placeholder="봉지, g, kg"
          />
        </div>
      </div>
      {notebooks.length ? (
        <div className="mt-4 grid gap-2">
          <Label htmlFor="share-source-record">연결할 수첩 기록</Label>
          <select
            id="share-source-record"
            value={values.sourceRecord}
            onChange={(event) => onChange({ ...values, sourceRecord: event.target.value })}
            className="min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base"
          >
            <option value="">연결 안 함</option>
            {notebooks.map((entry) => (
              <option key={entry.record_id} value={entry.record_id}>
                {formatDisplayDate(entry.experience_date)} · {entry.activity_text.slice(0, 50)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          취소
        </Button>
        <Button
          onClick={onSave}
          disabled={
            busy ||
            !values.unit.trim() ||
            !Number.isFinite(Number(values.amount)) ||
            Number(values.amount) <= 0 ||
            (values.status === "delivered" && !values.date)
          }
        >
          기록 확인
        </Button>
      </div>
    </div>
  );
}
