import { Button, Input, Textarea } from "@gracefullight/krds-tw";
import { useState } from "react";
import { useChat } from "../hooks/useChat";
import { ApiError, api } from "../lib/api";
import type { PrepareResponse, Preview } from "../lib/types";

interface FormProps {
  onPreview: (preview: Preview) => void;
}

function FormError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="mt-2 text-sm text-red-700" role="alert">
      {error}
    </p>
  );
}

export function ConditionForm({ prepare }: { prepare: PrepareResponse }) {
  const { confirmSpec } = useChat();
  const [station, setStation] = useState("선흘");
  const [years, setYears] = useState("2023,2024");
  const questions = prepare.form?.questions;

  function submit() {
    const yearList = years
      .split(",")
      .map((y) => Number.parseInt(y.trim(), 10))
      .filter((y) => !Number.isNaN(y));
    confirmSpec(
      {
        operation: "history_compare",
        source_ids: ["jeju_579"],
        station_selections: [{ source_id: "jeju_579", station_name: station }],
        years: yearList,
        month_day_start: "04-01",
        month_day_end: "05-31",
        elements: ["daily_rainfall"],
        comparison_scope: "common_valid_month_days",
        aggregation: "count_positive_days",
        unit: "day",
        timezone: "Asia/Seoul",
      },
      `${station} ${yearList.join("·")}년 봄 강수 비교`
    );
  }

  return (
    <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-3 text-base font-semibold">분석 조건을 확인해 주세요</p>
      {questions ? (
        <ul className="mb-3 list-inside list-disc text-sm text-gray-600">
          {questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-col gap-3">
        <Input label="관측소 이름" value={station} onChange={(e) => setStation(e.target.value)} />
        <Input
          label="비교 연도 (쉼표 구분)"
          value={years}
          onChange={(e) => setYears(e.target.value)}
        />
        <Button variant="primary" onClick={submit} disabled={!station || years.length === 0}>
          이 조건으로 비교
        </Button>
      </div>
    </div>
  );
}

export function NotebookForm({ onPreview }: FormProps) {
  const [date, setDate] = useState("");
  const [text, setText] = useState("");
  const [aliases, setAliases] = useState("");
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("봉지");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.notebookPrepare({
        experience_date: date,
        activity_text: text,
        companion_aliases: aliases ? aliases.split(",").map((a) => a.trim()) : [],
        amount_value: amount ? Number(amount) : null,
        amount_unit: amount ? unit : null,
      });
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "미리보기 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-1 text-base font-semibold">내 수첩 — 새 기록</p>
      <p className="mb-3 text-sm text-gray-600">
        저장 전 미리보기에서 확인합니다. 외부로 전송되지 않습니다.
      </p>
      <div className="flex flex-col gap-3">
        <Input
          label="활동 날짜"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <Textarea
          label="경험 내용"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={2000}
        />
        <Input
          label="동행 별칭 (쉼표 구분)"
          value={aliases}
          onChange={(e) => setAliases(e.target.value)}
        />
        <div className="flex gap-2">
          <Input
            label="수량"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Input label="단위" value={unit} onChange={(e) => setUnit(e.target.value)} />
        </div>
        <Button variant="primary" onClick={submit} disabled={busy || !date || !text}>
          미리보기
        </Button>
      </div>
      <FormError error={error} />
    </div>
  );
}

export function ShareForm({ onPreview }: FormProps) {
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("1");
  const [unit, setUnit] = useState("봉지");
  const [delivery, setDelivery] = useState("");
  const [messageEnabled, setMessageEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.sharePrepare({
        items: [
          {
            recipient_alias: recipient,
            amount_value: Number(amount),
            amount_unit: unit,
            planned_delivery: delivery || null,
          },
        ],
        message_enabled: messageEnabled,
      });
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "미리보기 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-1 text-base font-semibold">나눔 준비</p>
      <p className="mb-3 text-sm text-gray-600">
        대상·분량·시점을 정리합니다. 실제 전송은 없습니다.
      </p>
      <div className="flex flex-col gap-3">
        <Input
          label="나눌 대상 별칭"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
        <div className="flex gap-2">
          <Input
            label="분량"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Input label="단위" value={unit} onChange={(e) => setUnit(e.target.value)} />
        </div>
        <Input
          label="전달 시점 (선택)"
          value={delivery}
          onChange={(e) => setDelivery(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={messageEnabled}
            onChange={(e) => setMessageEnabled(e.target.checked)}
          />
          문자 문구 준비
        </label>
        <Button variant="primary" onClick={submit} disabled={busy || !recipient || !amount}>
          미리보기
        </Button>
      </div>
      <FormError error={error} />
    </div>
  );
}

export function RegionForm({ onPreview }: FormProps) {
  const [alias, setAlias] = useState("");
  const [area, setArea] = useState("");
  const [kind, setKind] = useState<"existing" | "interest">("interest");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.regionsPrepare({
        kind,
        local_alias: alias,
        public_area_code: area,
      });
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "미리보기 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-[85%] rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-1 text-base font-semibold">지역 등록</p>
      <p className="mb-3 text-sm text-gray-600">
        대략 지역만 등록합니다. 정확 채취 좌표는 저장하지 않습니다.
      </p>
      <div className="flex flex-col gap-3">
        <Input label="지역 별칭" value={alias} onChange={(e) => setAlias(e.target.value)} />
        <Input
          label="대략 지역 (예: 제주시 조천읍)"
          value={area}
          onChange={(e) => setArea(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="kind"
            checked={kind === "existing"}
            onChange={() => setKind("existing")}
          />
          기존 이용 지역
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="kind"
            checked={kind === "interest"}
            onChange={() => setKind("interest")}
          />
          새 관심 지역
        </label>
        <Button variant="primary" onClick={submit} disabled={busy || !alias || !area}>
          미리보기
        </Button>
      </div>
      <FormError error={error} />
    </div>
  );
}
