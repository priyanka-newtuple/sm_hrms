import { useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Search } from "lucide-react";

import heroImg from "@/skins/hrms/assets/learning_bg.png";
import { publicContentApi } from "@/skins/hrms/api/hrCockpit";
import { PublicContent, PublicHero, PublicPageLayout } from "@/skins/hrms/components/PublicPageLayout";
import { usePublicQuery as useQuery } from "./usePublicContent";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const isoMonth = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
const isoDay = (date: Date) => `${isoMonth(date)}-${String(date.getDate()).padStart(2, "0")}`;

function calendarDays(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const first = new Date(year, monthNumber - 1, 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const start = new Date(year, monthNumber - 1, 1 - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return { date, key: isoDay(date), inMonth: date.getMonth() === monthNumber - 1 };
  });
}

function shiftMonth(value: string, delta: number) {
  const [year, month] = value.split("-").map(Number);
  return isoMonth(new Date(year, month - 1 + delta, 1));
}

const EVENT_TONES = [
  "border-blue-500 bg-blue-50 text-blue-950",
  "border-violet-500 bg-violet-50 text-violet-950",
  "border-emerald-500 bg-emerald-50 text-emerald-950",
  "border-orange-500 bg-orange-50 text-orange-950",
  "border-rose-500 bg-rose-50 text-rose-950",
];

function eventTone(category: string) {
  const score = [...category].reduce((total, character) => total + character.charCodeAt(0), 0);
  return EVENT_TONES[score % EVENT_TONES.length];
}

export function LdCalendarPage() {
  const { data = [], isLoading } = useQuery({ queryKey: ["public", "learning-events"], queryFn: publicContentApi.events });
  const [month, setMonth] = useState(() => isoMonth(new Date()));
  const [search, setSearch] = useState("");
  const cells = useMemo(() => calendarDays(month), [month]);
  const query = search.trim().toLowerCase();
  const events = data.filter(event => {
    const eventMonth = String(event.starts_at).slice(0, 7);
    const searchable = `${event.title} ${event.description ?? ""} ${event.category} ${event.location} ${event.audience}`.toLowerCase();
    return eventMonth === month && (!query || searchable.includes(query));
  });
  const byDate = new Map<string, typeof events>();
  for (const event of events) {
    const key = String(event.starts_at).slice(0, 10);
    byDate.set(key, [...(byDate.get(key) ?? []), event]);
  }
  const monthTitle = new Date(`${month}-01T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const today = isoDay(new Date());

  return <PublicPageLayout>
    <PublicHero image={heroImg} kicker="Learning & Development" title="Learning Calendar" accent="Stay curious. Learn together." blurb="Find upcoming sessions published by the People team." />
    <PublicContent className="space-y-5">
      <section className="overflow-hidden rounded-card border border-white/80 bg-white shadow-xl shadow-gray-900/10">
        <div className="flex flex-col gap-4 bg-gradient-to-r from-cobalt/[0.08] via-white to-orange-50 px-5 py-5 lg:flex-row lg:items-center lg:justify-between sm:px-7">
          <div className="flex items-center gap-2">
            <button type="button" aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))} className="rounded-full border border-white bg-white p-2 text-gray-600 shadow-sm transition hover:-translate-x-0.5 hover:text-cobalt"><ChevronLeft size={18} /></button>
            <div className="min-w-48 text-center"><h2 className="text-xl font-semibold text-gray-900">{monthTitle}</h2><p className="mt-0.5 text-xs text-gray-500">{events.length} learning session{events.length === 1 ? "" : "s"}</p></div>
            <button type="button" aria-label="Next month" onClick={() => setMonth(shiftMonth(month, 1))} className="rounded-full border border-white bg-white p-2 text-gray-600 shadow-sm transition hover:translate-x-0.5 hover:text-cobalt"><ChevronRight size={18} /></button>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search sessions, topics or location" aria-label="Search learning sessions" className="w-full rounded-full border border-white bg-white py-2.5 pl-9 pr-4 text-sm shadow-sm focus:border-cobalt focus:outline-none sm:w-72" />
            </label>
            <label className="flex items-center gap-2 rounded-full border border-white bg-white px-3 text-sm text-gray-600 shadow-sm">
              <CalendarDays size={16} />
              <input type="month" value={month} onChange={event => setMonth(event.target.value)} aria-label="Filter by month" className="bg-transparent py-2.5 outline-none" />
            </label>
          </div>
        </div>

        <div className="overflow-x-auto">
          <div className="min-w-[760px]"><div className="grid grid-cols-7 bg-cobalt">{WEEKDAYS.map(day => <div key={day} className="border-r border-white/15 px-3 py-3 text-center text-[11px] font-semibold uppercase tracking-[0.14em] text-white last:border-r-0">{day}</div>)}</div>
          <div className="grid grid-cols-7">{cells.map((cell, index) => <div key={cell.key} className={`min-h-32 border-r border-t border-gray-100 p-2.5 transition-colors hover:bg-blue-50/30 ${(index + 1) % 7 === 0 ? "border-r-0" : ""} ${cell.inMonth ? ((index % 7) > 4 ? "bg-amber-50/30" : "bg-white") : "bg-gray-50/80 text-gray-400"}`}>
            <div className={`mb-2 flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${cell.key === today ? "bg-cobalt text-white shadow-md shadow-cobalt/30" : cell.inMonth ? "text-gray-700" : "text-gray-400"}`}>{cell.date.getDate()}</div>
            <div className="space-y-1.5">{(byDate.get(cell.key) ?? []).map(event => <article key={event.id} title={`${event.title} — ${event.location}`} className={`rounded-lg border-l-[3px] px-2 py-2 shadow-sm ${eventTone(event.category)}`}>
              <p className="line-clamp-2 text-xs font-semibold">{event.title}</p>
              <p className="mt-1 text-[10px] opacity-70">{new Date(event.starts_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {event.location}</p>
            </article>)}</div>
          </div>)}</div></div>
        </div>

        {isLoading && <p className="border-t border-gray-100 py-8 text-center text-gray-500">Loading calendar…</p>}
        {!isLoading && !events.length && <div className="border-t border-gray-100 px-6 py-9 text-center"><span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-cobalt/10 text-cobalt"><CalendarDays size={20} /></span><p className="mt-3 font-medium text-gray-800">No sessions found</p><p className="mt-1 text-sm text-gray-500">Try another month or adjust your search.</p></div>}
      </section>
    </PublicContent>
  </PublicPageLayout>;
}
