import { Popover } from "@base-ui/react/popover";
import { CalendarBlankIcon } from "@phosphor-icons/react";
import { ko } from "date-fns/locale";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { formatDisplayDate } from "@/lib/date-format";

export interface DatePickerFieldProps {
  id?: string;
  value: string;
  onChange: (date: string) => void;
  placeholder?: string;
  "aria-label"?: string;
  min?: string;
  max?: string;
  disabled?: boolean;
  required?: boolean;
}
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function parseDay(value?: string): Date | undefined {
  if (!value || !DATE_ONLY.test(value)) return undefined;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
    ? date
    : undefined;
}
function formatDay(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function DatePickerField({
  id,
  value,
  onChange,
  placeholder = "날짜 선택",
  "aria-label": ariaLabel,
  min,
  max,
  disabled,
  required = false,
}: DatePickerFieldProps) {
  const [open, setOpen] = useState(false);
  const requiredDescriptionId = useId();
  const selected = parseDay(value);
  const start = parseDay(min);
  const end = parseDay(max);
  const disabledDays = [...(start ? [{ before: start }] : []), ...(end ? [{ after: end }] : [])];
  const displayValue = selected ? formatDisplayDate(value) : placeholder;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      {required ? (
        <span id={requiredDescriptionId} className="sr-only">
          필수 입력
        </span>
      ) : null}
      <Popover.Trigger
        render={<Button variant="outline" />}
        id={id}
        aria-label={ariaLabel}
        aria-describedby={required ? requiredDescriptionId : undefined}
        disabled={disabled}
        className="w-full min-w-0 justify-between gap-2 px-2 font-normal"
      >
        <span className="min-w-0 truncate">{displayValue}</span>
        <CalendarBlankIcon className="size-4 text-muted-foreground" aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="start" className="z-50">
          <Popover.Popup
            aria-label="날짜 선택 달력"
            className="max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-popover text-popover-foreground shadow-lg outline-none"
          >
            <Calendar
              className="[--cell-size:2.75rem]"
              mode="single"
              required={required}
              locale={ko}
              selected={selected}
              defaultMonth={selected ?? new Date()}
              captionLayout="dropdown"
              startMonth={start ?? new Date(1940, 0)}
              endMonth={end ?? new Date(new Date().getFullYear() + 20, 11)}
              disabled={disabledDays}
              autoFocus
              onSelect={(date: Date | undefined) => {
                onChange(date ? formatDay(date) : "");
                setOpen(false);
              }}
              labels={{
                labelMonthDropdown: () => "월 선택",
                labelYearDropdown: () => "연도 선택",
                labelNext: () => "다음 달",
                labelPrevious: () => "이전 달",
                labelDayButton: (date) => `${formatDay(date)} 선택`,
              }}
            />
            {!required && selected ? (
              <div className="border-t border-border px-3 py-2">
                <Button
                  variant="ghost"
                  className="w-full"
                  onClick={() => {
                    onChange("");
                    setOpen(false);
                  }}
                >
                  날짜 지우기
                </Button>
              </div>
            ) : null}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
