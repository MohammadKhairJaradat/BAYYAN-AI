import { useEffect, useMemo, useState } from "react";
import { getCalendarEvents } from "../services/api";
import type { CalendarEvent } from "../types/api";
import { useLang } from "../contexts/hooks";
import { Icon } from "../components/brand";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function localIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function eventColor(type: CalendarEvent["type"]): { bg: string; fg: string } {
  switch (type) {
    case "deadline":
      return { bg: "var(--clay-tint)", fg: "var(--clay)" };
    case "filing":
      return { bg: "var(--green-tint)", fg: "var(--green)" };
    default:
      return { bg: "var(--gold-tint)", fg: "var(--gold)" };
  }
}

export default function Calendar() {
  const { t } = useLang();
  const C = t.calendar;
  const [currentDate, setCurrentDate] = useState(new Date());
  const [eventsByYear, setEventsByYear] = useState<Record<number, CalendarEvent[]>>({});
  const [loadingYear, setLoadingYear] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth();

  useEffect(() => {
    if (eventsByYear[currentYear]) return;
    let cancelled = false;
    (async () => {
      setLoadingYear(currentYear);
      setErrorMsg(null);
      try {
        const events = await getCalendarEvents(currentYear);
        if (!cancelled) setEventsByYear((prev) => ({ ...prev, [currentYear]: events }));
      } catch {
        if (!cancelled) setErrorMsg(t.common.error);
      } finally {
        if (!cancelled) setLoadingYear(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentYear, eventsByYear, t.common.error]);

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};
    const list = eventsByYear[currentYear] ?? [];
    for (const e of list) (map[e.date] ??= []).push(e);
    return map;
  }, [eventsByYear, currentYear]);

  const upcoming = useMemo(() => {
    const list = eventsByYear[currentYear] ?? [];
    const todayIso = localIsoDate(new Date());
    return [...list]
      .filter((e) => e.date >= todayIso)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 4);
  }, [eventsByYear, currentYear]);

  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const startDay = new Date(currentYear, currentMonth, 1).getDay();

  const cells: (Date | null)[] = [];
  for (let i = 0; i < startDay; i++) cells.push(null);
  for (let i = 1; i <= daysInMonth; i++) cells.push(new Date(currentYear, currentMonth, i));
  const remaining = (7 - (cells.length % 7)) % 7;
  for (let i = 0; i < remaining; i++) cells.push(null);

  const prevMonth = () => setCurrentDate(new Date(currentYear, currentMonth - 1, 1));
  const nextMonth = () => setCurrentDate(new Date(currentYear, currentMonth + 1, 1));

  return (
    <div className="wrap wrap-app" style={{ paddingBlock: "40px 64px" }}>
      <div className="row-between" style={{ marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {C.title}
          </h1>
          <p className="t-body">{C.sub}</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 20, alignItems: "start" }} className="max-md:!grid-cols-1">
        {/* Month grid */}
        <div className="card card-pad">
          <div className="row-between" style={{ marginBottom: 18 }}>
            <h2 className="t-h3" style={{ fontSize: 20 }}>
              {MONTH_NAMES[currentMonth]} {currentYear}
            </h2>
            <div className="row" style={{ gap: 6 }}>
              <button
                onClick={prevMonth}
                title="Previous"
                style={{ width: 36, height: 36, borderRadius: 9, border: "1px solid var(--line)", background: "var(--paper)", display: "grid", placeItems: "center" }}
              >
                <Icon name="chevron" size={16} color="var(--ink-soft)" style={{ transform: "scaleX(-1)" }} />
              </button>
              <button
                onClick={nextMonth}
                title="Next"
                style={{ width: 36, height: 36, borderRadius: 9, border: "1px solid var(--line)", background: "var(--paper)", display: "grid", placeItems: "center" }}
              >
                <Icon name="chevron" size={16} color="var(--ink-soft)" />
              </button>
            </div>
          </div>

          {loadingYear === currentYear && (
            <div className="t-small faint center" style={{ marginBottom: 8 }}>
              {t.common.loading}
            </div>
          )}
          {errorMsg && (
            <div className="t-small" style={{ color: "var(--danger)", marginBottom: 12 }}>
              {errorMsg}
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 8, marginBottom: 8 }}>
            {C.weekdays.map((day, i) => (
              <div key={i} className="t-eyebrow center" style={{ color: "var(--ink-faint)", fontSize: 11 }}>
                {day}
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 8 }}>
            {cells.map((dateObj, idx) => {
              const today = new Date();
              const isToday =
                dateObj &&
                dateObj.getDate() === today.getDate() &&
                dateObj.getMonth() === today.getMonth() &&
                dateObj.getFullYear() === today.getFullYear();
              const dayEvents = dateObj ? eventsByDate[localIsoDate(dateObj)] ?? [] : [];
              return (
                <div
                  key={idx}
                  title={dayEvents.map((e) => e.title).join("\n")}
                  style={{
                    aspectRatio: "1",
                    borderRadius: 12,
                    border: dateObj ? "1px solid var(--line)" : "1px solid transparent",
                    background: dateObj ? "var(--paper-2)" : "transparent",
                    padding: 8,
                    display: "flex",
                    flexDirection: "column",
                    boxShadow: isToday ? "0 0 0 2px var(--green)" : "none",
                  }}
                >
                  {dateObj && (
                    <>
                      <span className="num" style={{ fontSize: 13, fontWeight: 600, color: isToday ? "var(--green)" : "var(--ink-soft)" }}>
                        {dateObj.getDate()}
                      </span>
                      {dayEvents.length > 0 && (
                        <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
                          {dayEvents.slice(0, 2).map((evt, i) => {
                            const c = eventColor(evt.type);
                            return (
                              <div
                                key={i}
                                style={{ fontSize: 10, fontWeight: 600, borderRadius: 6, padding: "1px 5px", background: c.bg, color: c.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                              >
                                {evt.title}
                              </div>
                            );
                          })}
                          {dayEvents.length > 2 && (
                            <div className="t-small faint" style={{ fontSize: 10 }}>
                              +{dayEvents.length - 2}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Upcoming deadlines */}
        <div className="card card-pad">
          <h3 className="t-eyebrow" style={{ marginBottom: 16 }}>
            {C.upcomingTitle}
          </h3>
          {upcoming.length === 0 ? (
            <p className="t-small faint">—</p>
          ) : (
            <ul className="stack" style={{ ["--gap"]: "14px", listStyle: "none", margin: 0, padding: 0 } as React.CSSProperties}>
              {upcoming.map((e, ix) => {
                const d = new Date(e.date + "T00:00:00");
                const c = eventColor(e.type);
                return (
                  <li key={`${e.date}-${ix}`} className="row" style={{ gap: 12, alignItems: "flex-start" }}>
                    <div style={{ width: 46, borderRadius: 10, background: c.bg, color: c.fg, textAlign: "center", padding: "6px 0", flex: "none" }}>
                      <div className="num" style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>
                        {d.getDate()}
                      </div>
                      <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase" }}>
                        {MONTH_NAMES[d.getMonth()].slice(0, 3)}
                      </div>
                    </div>
                    <div>
                      <div className="t-body" style={{ color: "var(--ink)", fontWeight: 600, fontSize: 14.5 }}>
                        {e.title}
                      </div>
                      {e.description && <div className="t-small">{e.description}</div>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
