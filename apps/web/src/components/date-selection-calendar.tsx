import type { EventInput } from "@fullcalendar/core";
import koLocale from "@fullcalendar/core/locales/ko";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import { useEffect, useRef } from "react";

export interface DateSelectionCalendarProps {
  value: string;
  onSelect: (date: string) => void;
  events?: EventInput[];
  onEventSelect?: (id: string) => void;
  min?: string;
  max?: string;
}

function formatCalendarDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function DateSelectionCalendar({
  value,
  onSelect,
  events = [],
  onEventSelect,
  min,
  max,
}: DateSelectionCalendarProps) {
  const calendar = useRef<FullCalendar>(null);
  const isAvailable = (day: string) => (!min || day >= min) && (!max || day <= max);
  const end = max ? new Date(`${max}T12:00:00Z`) : undefined;
  end?.setUTCDate(end.getUTCDate() + 1);
  useEffect(() => {
    if (value) calendar.current?.getApi().gotoDate(value);
  }, [value]);
  return (
    <div className="min-w-0 text-base [&_.fc-button]:min-h-11 [&_.fc-button]:min-w-11 [&_.fc-button]:cursor-pointer [&_.fc-button]:text-base [--fc-border-color:var(--border)] [--fc-button-bg-color:var(--primary)] [--fc-button-border-color:var(--primary)] [--fc-button-hover-bg-color:var(--primary)] [--fc-button-hover-border-color:var(--primary)] [--fc-button-active-bg-color:var(--primary)] [--fc-button-active-border-color:var(--primary)] [--fc-event-bg-color:var(--primary)] [--fc-event-border-color:var(--primary)] [--fc-today-bg-color:var(--accent)] [&_.fc-toolbar-title]:text-base [&_.fc-toolbar-title]:font-semibold [&_.fc-daygrid-day-frame]:min-h-16 [&_.fc-daygrid-event]:cursor-pointer [&_.fc-daygrid-day-number]:p-0 [&_.fc-day-selected]:bg-accent">
      <FullCalendar
        ref={calendar}
        plugins={[dayGridPlugin, interactionPlugin]}
        initialView="dayGridMonth"
        initialDate={value || undefined}
        locale={koLocale}
        headerToolbar={{ left: "prev", center: "title", right: "next" }}
        height="auto"
        fixedWeekCount={false}
        validRange={min || max ? { start: min, end: end?.toISOString().slice(0, 10) } : undefined}
        dayMaxEventRows={2}
        events={events}
        eventInteractive
        eventClick={(info) => {
          info.jsEvent.preventDefault();
          onEventSelect?.(info.event.id);
        }}
        dateClick={(info) => {
          if (isAvailable(info.dateStr)) onSelect(info.dateStr);
        }}
        dayCellClassNames={(info) =>
          formatCalendarDate(info.date) === value ? ["fc-day-selected"] : []
        }
        dayCellContent={(info) => {
          const day = formatCalendarDate(info.date);
          return (
            <button
              type="button"
              aria-label={`${day} 선택`}
              aria-pressed={day === value}
              disabled={!isAvailable(day)}
              className="m-0 flex size-11 cursor-pointer items-center justify-center rounded-lg font-medium hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring aria-pressed:bg-primary aria-pressed:text-primary-foreground disabled:cursor-default disabled:text-muted-foreground"
              onClick={(event) => {
                event.stopPropagation();
                if (isAvailable(day)) onSelect(day);
              }}
            >
              {info.date.getDate()}
            </button>
          );
        }}
      />
    </div>
  );
}
