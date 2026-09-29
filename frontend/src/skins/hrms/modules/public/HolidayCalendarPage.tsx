import { useMemo, useState } from "react";

import heroImg from "@/skins/hrms/assets/learning_bg.png";
import { publicContentApi } from "@/skins/hrms/api/hrCockpit";
import { PublicContent, PublicHero, PublicPageLayout } from "@/skins/hrms/components/PublicPageLayout";
import { usePublicQuery as useQuery } from "./usePublicContent";

export function HolidayCalendarPage() {
  const { data = [], isLoading } = useQuery({ queryKey: ["public", "holidays"], queryFn: publicContentApi.holidays });
  const currentYear = new Date().getFullYear();
  const years = useMemo(
    () => Array.from(new Set([currentYear - 1, currentYear, currentYear + 1, ...data.map(h => Number(String(h.holiday_date).slice(0, 4)))])).sort(),
    [data, currentYear],
  );
  const [year, setYear] = useState(currentYear);
  const holidays = data.filter(h => Number(String(h.holiday_date).slice(0, 4)) === year);

  return <PublicPageLayout>
    <PublicHero image={heroImg} kicker="Company calendar" title="Public Holidays" accent={`Plan your time in ${year}.`} blurb="The official holiday list published by HR and used by timesheets." />
    <PublicContent>
      <div className="overflow-hidden rounded-card bg-white shadow-lg shadow-gray-900/5">
        <div className="flex items-center justify-between border-b p-4">
          <div><h2 className="font-semibold">Holiday calendar</h2><p className="text-sm text-gray-500">{holidays.length} published holiday{holidays.length === 1 ? "" : "s"} in {year}</p></div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">Year
            <select className="rounded-lg border border-gray-300 bg-white px-4 py-2" value={year} onChange={e => setYear(Number(e.target.value))}>
              {years.map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
        </div>
        <table className="w-full text-left"><thead className="bg-gray-50"><tr><th className="p-4">Date</th><th>Holiday</th><th>Location</th><th>Type</th></tr></thead><tbody>{holidays.map(h => <tr className="border-t" key={h.id}><td className="p-4">{new Date(h.holiday_date + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}</td><td className="font-medium">{h.name}</td><td>{h.location}</td><td>{h.is_optional ? "Optional" : "Company holiday"}</td></tr>)}</tbody></table>
        {isLoading && <p className="p-6 text-center">Loading…</p>}
        {!isLoading && !holidays.length && <p className="p-6 text-center text-gray-500">No holidays have been published for {year}.</p>}
      </div>
    </PublicContent>
  </PublicPageLayout>;
}
