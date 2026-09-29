import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { timesheetsApi, type Holiday, type TimesheetSubmission } from "@/skins/hrms/api/timesheets";
import { useAuth } from "@/skins/hrms/auth/AuthContext";
import { usePermission } from "@/skins/hrms/auth/usePermission";
import { Badge } from "@/skins/hrms/components/Badge";
import { Button } from "@/skins/hrms/components/Button";
import { Card, CardHeader, CardTitle } from "@/skins/hrms/components/Card";
import { Field, FormError, Select, TextArea, TextInput } from "@/skins/hrms/components/Form";
import { Modal } from "@/skins/hrms/components/Modal";
import { apiErrorMessage } from "@/skins/hrms/lib/apiError";
import { FEATURES } from "@/skins/hrms/lib/features";

type Tab = "week" | "submissions" | "month" | "leave" | "approvals";
type DraftCell = { hours: string; task_details: string; status?: string };

const iso = (date: Date) => date.toLocaleDateString("en-CA");
const parseDate = (value: string) => new Date(`${value}T00:00:00`);
const monday = (date: Date) => {
  const copy = new Date(date);
  const day = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - day);
  return iso(copy);
};
const shiftDays = (value: string, days: number) => {
  const date = parseDate(value);
  date.setDate(date.getDate() + days);
  return iso(date);
};
const keyOf = (project: string, day: string) => `${project}:${day}`;
const shortDay = (value: string) => parseDate(value).toLocaleDateString(undefined, { weekday: "short", day: "numeric" });

export default function TimesheetsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canApprove = usePermission(FEATURES.TIMESHEETS, "approve");
  const canManageHolidays = ["HR - Basic", "HR - Full", "Super Admin"].includes(user?.role_name ?? "");
  const [tab, setTab] = useState<Tab>("week");
  const [weekStart, setWeekStart] = useState(() => monday(new Date()));
  const [month, setMonth] = useState(() => iso(new Date()).slice(0, 7));
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [holidayOpen, setHolidayOpen] = useState(false);

  const week = useQuery({ queryKey: ["timesheet-week", weekStart], queryFn: () => timesheetsApi.week(weekStart) });
  const monthView = useQuery({ queryKey: ["timesheet-month", month], queryFn: () => timesheetsApi.month(month), enabled: tab === "month" });
  const submissions = useQuery({ queryKey: ["timesheet-submissions"], queryFn: timesheetsApi.submissions });
  const holidays = useQuery({ queryKey: ["holidays", Number(month.slice(0, 4))], queryFn: () => timesheetsApi.holidays(Number(month.slice(0, 4))) });
  const leaves = useQuery({ queryKey: ["leave-requests"], queryFn: () => timesheetsApi.leaves() });
  const approvals = useQuery({ queryKey: ["timesheet-approvals"], queryFn: timesheetsApi.approvals, enabled: canApprove && tab === "approvals" });
  const leaveApprovals = useQuery({ queryKey: ["leave-approvals"], queryFn: () => timesheetsApi.leaves(true), enabled: canApprove && tab === "approvals" });
  const [drafts, setDrafts] = useState<Record<string, DraftCell>>({});

  useEffect(() => {
    if (!week.data) return;
    const next: Record<string, DraftCell> = {};
    for (const entry of week.data.entries) next[keyOf(entry.project_id, entry.work_date)] = {
      hours: String(entry.hours), task_details: entry.task_details ?? "", status: entry.status,
    };
    setDrafts(next);
  }, [week.data]);

  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["timesheet-week"] }),
    queryClient.invalidateQueries({ queryKey: ["timesheet-month"] }),
    queryClient.invalidateQueries({ queryKey: ["timesheet-submissions"] }),
    queryClient.invalidateQueries({ queryKey: ["timesheet-approvals"] }),
    queryClient.invalidateQueries({ queryKey: ["leave-requests"] }),
    queryClient.invalidateQueries({ queryKey: ["leave-approvals"] }),
    queryClient.invalidateQueries({ queryKey: ["holidays"] }),
  ]);

  const weekEntries = () => (week.data?.projects ?? []).flatMap(project => (week.data?.days ?? []).flatMap(day => {
    const value = drafts[keyOf(project.id, day)];
    if (!value || (!Number(value.hours) && !week.data?.entries.some(e => e.project_id === project.id && e.work_date === day))) return [];
    return [{ project_id: project.id, work_date: day, hours: Number(value.hours || 0), task_details: value.task_details.trim() || null }];
  }));
  const save = useMutation({ mutationFn: () => timesheetsApi.saveWeek(weekStart, weekEntries()), onSuccess: refresh });
  const submit = useMutation({ mutationFn: async () => { await timesheetsApi.saveWeek(weekStart, weekEntries()); return timesheetsApi.submitWeek(weekStart); }, onSuccess: refresh });

  const holidayByDate = new Map(week.data?.holidays.map(h => [h.holiday_date, h]) ?? []);
  const leaveOn = (day: string) => week.data?.leaves.find(l => l.start_date <= day && l.end_date >= day);
  const projectedTotal = Object.values(drafts).reduce((sum, cell) => sum + Number(cell.hours || 0), 0);
  const weekLocked = ["submitted", "approved"].includes(week.data?.submission?.status ?? "");

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-2xl font-light tracking-tight text-gray-900">Timesheets</h1><p className="mt-1 text-sm text-gray-600">Log time, submit your week, request leave, and check company holidays.</p></div>
      <div className="flex gap-2"><Button variant="secondary" onClick={() => setLeaveOpen(true)}>Apply for leave</Button>{canManageHolidays && <Button onClick={() => setHolidayOpen(true)}><Plus size={16} /> Add holiday</Button>}</div>
    </div>
    <div className="flex flex-wrap gap-2" role="tablist">
      <Button variant={tab === "week" ? "primary" : "secondary"} onClick={() => setTab("week")}>Week view</Button>
      <Button variant={tab === "submissions" ? "primary" : "secondary"} onClick={() => setTab("submissions")}>My submissions</Button>
      <Button variant={tab === "month" ? "primary" : "secondary"} onClick={() => { setMonth(weekStart.slice(0, 7)); setTab("month"); }}>Month view</Button>
      <Button variant={tab === "leave" ? "primary" : "secondary"} onClick={() => setTab("leave")}>Leave & holidays</Button>
      {canApprove && <Button variant={tab === "approvals" ? "primary" : "secondary"} onClick={() => setTab("approvals")}>Manager approvals</Button>}
    </div>

    {tab === "week" && <Card>
      <CardHeader><div><CardTitle>Week of {weekStart}</CardTitle><p className="text-sm text-gray-600">{projectedTotal} hours entered</p></div><div className="flex gap-2"><Button variant="ghost" aria-label="Previous week" onClick={() => setWeekStart(shiftDays(weekStart, -7))}><ChevronLeft size={16} /></Button><Button variant="secondary" onClick={() => setWeekStart(monday(new Date()))}>This week</Button><Button variant="ghost" aria-label="Next week" onClick={() => setWeekStart(shiftDays(weekStart, 7))}><ChevronRight size={16} /></Button></div></CardHeader>
      {week.data?.submission && <SubmissionStatus item={week.data.submission} compact />}
      {week.isLoading ? <p>Loading week…</p> : week.error ? <FormError message={apiErrorMessage(week.error)} /> : week.data?.projects.length === 0 ? <p className="text-sm text-gray-600">No active project allocations cover this week.</p> : <div className="overflow-x-auto"><table className="min-w-[1050px] w-full text-sm"><thead><tr><th className="p-2 text-left">Project</th>{week.data?.days.map(day => <th key={day} className="p-2 text-left">{shortDay(day)}{holidayByDate.get(day) && <span className="block text-xs text-danger">{holidayByDate.get(day)?.name}</span>}{leaveOn(day) && <span className="block text-xs text-cobalt">{leaveOn(day)?.status} leave</span>}</th>)}</tr></thead><tbody>{week.data?.projects.map(project => <tr key={project.id} className="border-t border-gray-100"><th className="p-2 text-left align-top font-medium">{project.name}</th>{week.data?.days.map(day => {
        const cellKey = keyOf(project.id, day); const cell = drafts[cellKey] ?? { hours: "", task_details: "" }; const blocked = !!holidayByDate.get(day) || leaveOn(day)?.status === "approved"; const locked = weekLocked || ["submitted", "approved"].includes(cell.status ?? "");
        return <td key={day} className={`p-2 align-top ${blocked ? "bg-gray-50" : ""}`}><TextInput aria-label={`${project.name} hours ${day}`} type="number" min={0} max={24} step="0.25" placeholder={blocked ? "Blocked" : "Hours"} disabled={blocked || locked} value={cell.hours} onChange={e => setDrafts(prev => ({...prev, [cellKey]: {...cell, hours: e.target.value}}))} /><TextArea aria-label={`${project.name} task details ${day}`} rows={2} className="mt-1 min-w-28" placeholder={blocked ? "Holiday / leave" : "Task details"} disabled={blocked || locked || !Number(cell.hours)} value={cell.task_details} onChange={e => setDrafts(prev => ({...prev, [cellKey]: {...cell, task_details: e.target.value}}))} />{cell.status && <span className="mt-1 block"><Badge>{cell.status}</Badge></span>}</td>;
      })}</tr>)}</tbody></table></div>}
      <FormError message={save.error ? apiErrorMessage(save.error) : submit.error ? apiErrorMessage(submit.error) : null} />
      <div className="mt-4 flex justify-end gap-2"><Button variant="secondary" disabled={weekLocked || save.isPending || submit.isPending} onClick={() => save.mutate()}>Save draft</Button><Button disabled={weekLocked || save.isPending || submit.isPending || projectedTotal <= 0} onClick={() => submit.mutate()}>Submit week to manager</Button></div>
    </Card>}

    {tab === "submissions" && <SubmissionHistory items={submissions.data ?? []} loading={submissions.isLoading} error={submissions.error} onOpen={value => { setWeekStart(value); setMonth(value.slice(0, 7)); setTab("week"); }} />}
    {tab === "month" && <MonthlyCalendar month={month} setMonth={setMonth} data={monthView.data} loading={monthView.isLoading} error={monthView.error} latestMonth={submissions.data?.[0]?.week_start_date.slice(0, 7)} />}
    {tab === "leave" && <LeaveAndHolidays leaves={leaves.data ?? []} holidays={holidays.data ?? []} canManage={canManageHolidays} refresh={refresh} />}
    {tab === "approvals" && canApprove && <Approvals timesheets={approvals.data ?? []} leaves={leaveApprovals.data ?? []} refresh={refresh} />}
    {leaveOpen && <LeaveModal onClose={() => setLeaveOpen(false)} refresh={refresh} />}
    {holidayOpen && <HolidayModal onClose={() => setHolidayOpen(false)} refresh={refresh} />}
  </div>;
}

function statusLabel(status: TimesheetSubmission["status"]) {
  return status === "submitted" ? "Pending approval" : status.replace(/_/g, " ");
}

function SubmissionStatus({ item, compact = false }: { item: TimesheetSubmission; compact?: boolean }) {
  return <div className={`mb-4 rounded-xl border p-3 ${item.status === "rejected" ? "border-danger/30 bg-danger/5" : "border-cobalt/20 bg-cobalt/5"}`}>
    <div className="flex flex-wrap items-center justify-between gap-2"><div><strong className="capitalize">{statusLabel(item.status)}</strong>{item.status === "submitted" && <p className="text-sm text-gray-700">Pending with {item.pending_with_name ?? "Super Admin"}</p>}{item.decided_by_name && item.status !== "submitted" && <p className="text-sm text-gray-700">Reviewed by {item.decided_by_name}</p>}</div><Badge>{item.status}</Badge></div>
    {!compact && <p className="mt-1 text-sm text-gray-600">{item.total_hours} hours · Submitted {item.submitted_at ? new Date(item.submitted_at).toLocaleString() : "—"}</p>}
    {item.decision_comment && <p className="mt-2 text-sm">Comment: {item.decision_comment}</p>}
  </div>;
}

function SubmissionHistory({ items, loading, error, onOpen }: { items: TimesheetSubmission[]; loading: boolean; error: unknown; onOpen: (week: string) => void }) {
  return <Card><CardHeader><div><CardTitle>My submitted timesheets</CardTitle><p className="text-sm text-gray-600">Track approval status and see who currently has each week.</p></div></CardHeader>
    {loading ? <p className="text-sm text-gray-600">Loading submissions…</p> : error ? <FormError message={apiErrorMessage(error)} /> : items.length === 0 ? <p className="text-sm text-gray-600">You have not submitted any timesheets yet.</p> : <div className="space-y-3">{items.map(item => <button type="button" key={item.week_start_date} onClick={() => onOpen(item.week_start_date)} className="block w-full rounded-xl border border-gray-200 p-4 text-left hover:border-cobalt/40 hover:bg-gray-50"><div className="mb-2"><strong>Week of {item.week_start_date}</strong><p className="text-sm text-gray-600">{item.total_hours} hours</p></div><SubmissionStatus item={item} compact /></button>)}</div>}
  </Card>;
}

function MonthlyCalendar({ month, setMonth, data, loading, error, latestMonth }: { month: string; setMonth: (value: string) => void; data?: Awaited<ReturnType<typeof timesheetsApi.month>>; loading: boolean; error: unknown; latestMonth?: string }) {
  const [year, monthNumber] = month.split("-").map(Number); const count = new Date(year, monthNumber, 0).getDate(); const offset = (new Date(year, monthNumber - 1, 1).getDay() + 6) % 7;
  const cells = [...Array(offset).fill(null), ...Array.from({length: count}, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`)];
  const hours = (day: string) => data?.entries.filter(e => e.work_date === day).reduce((sum, e) => sum + Number(e.hours), 0) ?? 0;
  const shift = (delta: number) => { const date = new Date(year, monthNumber - 1 + delta, 1); setMonth(iso(date).slice(0, 7)); };
  const title = new Date(year, monthNumber - 1).toLocaleDateString(undefined, {month: "long", year: "numeric"});
  const latestTitle = latestMonth ? new Date(`${latestMonth}-01T00:00:00`).toLocaleDateString(undefined, {month: "long", year: "numeric"}) : null;
  return <Card><CardHeader><div><CardTitle>{title}</CardTitle><p className="text-sm text-gray-600">{data?.total_hours ?? 0} hours</p></div><div className="flex flex-wrap items-center gap-2"><TextInput aria-label="Select month" type="month" value={month} onChange={event => setMonth(event.target.value)} /><Button variant="ghost" aria-label="Previous month" onClick={() => shift(-1)}><ChevronLeft size={16}/></Button><Button variant="secondary" onClick={() => setMonth(iso(new Date()).slice(0, 7))}>This month</Button><Button variant="ghost" aria-label="Next month" onClick={() => shift(1)}><ChevronRight size={16}/></Button></div></CardHeader>
    {loading ? <p className="mb-4 text-sm text-gray-600">Loading monthly timesheets…</p> : error ? <FormError message={apiErrorMessage(error)} /> : data?.entries.length === 0 && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3"><p className="text-sm text-gray-700">No timesheets were recorded in {title}.</p>{latestMonth && latestMonth !== month && <Button variant="secondary" onClick={() => setMonth(latestMonth)}>View latest submission · {latestTitle}</Button>}</div>}
    <div className="grid grid-cols-7 border-l border-t border-gray-200">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d => <div key={d} className="border-b border-r border-gray-200 p-2 text-xs font-semibold text-gray-600">{d}</div>)}{cells.map((day, index) => day ? <div key={day} className="min-h-24 border-b border-r border-gray-200 p-2"><span className="text-sm">{Number(day.slice(-2))}</span>{data?.holidays.filter(h => h.holiday_date === day).map(h => <p key={h.id} className="mt-1 rounded bg-danger/10 px-1 text-xs text-danger">{h.name}</p>)}{data?.leaves.filter(l => l.start_date <= day && l.end_date >= day && l.status !== "cancelled").map(l => <p key={l.id} className="mt-1 rounded bg-cobalt/10 px-1 text-xs text-cobalt">{l.leave_type} · {l.status}</p>)}{hours(day) > 0 && <p className="mt-1 text-sm font-semibold text-gray-900">{hours(day)}h</p>}{data?.entries.filter(e => e.work_date === day).map(e => <p key={e.id} className="truncate text-xs text-gray-600">{e.project_name}: {e.task_details || "No details"}</p>)}</div> : <div key={`blank-${index}`} className="border-b border-r border-gray-200 bg-gray-50" />)}</div></Card>;
}

function LeaveAndHolidays({ leaves, holidays, canManage, refresh }: { leaves: Awaited<ReturnType<typeof timesheetsApi.leaves>>; holidays: Holiday[]; canManage: boolean; refresh: () => Promise<unknown> }) {
  return <div className="grid gap-5 lg:grid-cols-2"><Card><CardHeader><CardTitle>My leave requests</CardTitle></CardHeader><div className="space-y-3">{leaves.length === 0 && <p className="text-sm text-gray-600">No leave requests.</p>}{leaves.map(item => <div key={item.id} className="rounded-xl border border-gray-200 p-3"><div className="flex justify-between"><strong>{item.leave_type.replace(/_/g," ")}</strong><Badge>{item.status}</Badge></div><p className="text-sm text-gray-600">{item.start_date} to {item.end_date}</p>{item.reason && <p className="mt-1 text-sm">{item.reason}</p>}{item.decision_comment && <p className="mt-1 text-sm text-danger">{item.decision_comment}</p>}{item.status === "pending" && <Button className="mt-2" variant="ghost" onClick={async () => {await timesheetsApi.cancelLeave(item.id); await refresh();}}>Cancel request</Button>}</div>)}</div></Card><Card><CardHeader><CardTitle><span className="flex items-center gap-2"><CalendarDays size={18}/> Holiday calendar</span></CardTitle></CardHeader><div className="space-y-3">{holidays.map(h => <div key={h.id} className="flex justify-between gap-3 rounded-xl border border-gray-200 p-3"><div><strong>{h.name}</strong><p className="text-sm text-gray-600">{h.holiday_date}{h.is_optional ? " · Optional" : ""}</p>{h.description && <p className="text-sm">{h.description}</p>}</div>{canManage && <Button variant="ghost" onClick={async () => {await timesheetsApi.removeHoliday(h.id); await refresh();}}>Remove</Button>}</div>)}</div></Card></div>;
}

function LeaveModal({ onClose, refresh }: { onClose: () => void; refresh: () => Promise<unknown> }) {
  const [form, setForm] = useState({start_date: iso(new Date()), end_date: iso(new Date()), leave_type: "annual", reason: ""}); const mutation = useMutation({mutationFn: () => timesheetsApi.applyLeave({...form, reason: form.reason || null}), onSuccess: async () => {await refresh(); onClose();}});
  return <Modal open onClose={onClose} title="Apply for leave"><form className="space-y-3" onSubmit={e => {e.preventDefault(); mutation.mutate();}}><div className="grid grid-cols-2 gap-3"><Field label="From"><TextInput required type="date" value={form.start_date} onChange={e => setForm({...form,start_date:e.target.value})}/></Field><Field label="To"><TextInput required type="date" min={form.start_date} value={form.end_date} onChange={e => setForm({...form,end_date:e.target.value})}/></Field></div><Field label="Leave type"><Select value={form.leave_type} onChange={e => setForm({...form,leave_type:e.target.value})}><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></Select></Field><Field label="Reason"><TextArea maxLength={2000} value={form.reason} onChange={e => setForm({...form,reason:e.target.value})}/></Field><FormError message={mutation.error ? apiErrorMessage(mutation.error) : null}/><div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>Submit to manager</Button></div></form></Modal>;
}

function HolidayModal({ onClose, refresh }: { onClose: () => void; refresh: () => Promise<unknown> }) {
  const [form, setForm] = useState({holiday_date: iso(new Date()), name: "", description: "", is_optional: false}); const mutation = useMutation({mutationFn: () => timesheetsApi.createHoliday({...form, description: form.description || null}), onSuccess: async () => {await refresh(); onClose();}});
  return <Modal open onClose={onClose} title="Add company holiday"><form className="space-y-3" onSubmit={e => {e.preventDefault(); mutation.mutate();}}><Field label="Date"><TextInput required type="date" value={form.holiday_date} onChange={e => setForm({...form,holiday_date:e.target.value})}/></Field><Field label="Holiday name"><TextInput required maxLength={150} value={form.name} onChange={e => setForm({...form,name:e.target.value})}/></Field><Field label="Description"><TextArea maxLength={2000} value={form.description} onChange={e => setForm({...form,description:e.target.value})}/></Field><label className="flex gap-2 text-sm"><input type="checkbox" checked={form.is_optional} onChange={e => setForm({...form,is_optional:e.target.checked})}/>Optional holiday</label><FormError message={mutation.error ? apiErrorMessage(mutation.error) : null}/><div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={mutation.isPending}>Add holiday</Button></div></form></Modal>;
}

function Approvals({ timesheets, leaves, refresh }: { timesheets: Awaited<ReturnType<typeof timesheetsApi.approvals>>; leaves: Awaited<ReturnType<typeof timesheetsApi.leaves>>; refresh: () => Promise<unknown> }) {
  const [comment, setComment] = useState(""); const decide = async (employee: string, week: string, action: "approve"|"reject") => {await timesheetsApi.decideWeek(employee, week, action, comment); setComment(""); await refresh();};
  return <div className="grid gap-5 lg:grid-cols-2"><Card><CardHeader><CardTitle>Timesheets awaiting approval</CardTitle></CardHeader><div className="space-y-4">{timesheets.length === 0 && <p className="text-sm text-gray-600">No submitted weeks.</p>}{timesheets.map(group => <div key={`${group.employee_id}-${group.week_start_date}`} className="rounded-xl border border-gray-200 p-3"><strong>{group.employee_name}</strong><p className="text-sm text-gray-600">Week of {group.week_start_date} · {group.total_hours}h</p><ul className="my-2 text-sm">{group.entries.map(entry => <li key={entry.id}>{entry.work_date} · {entry.project_name} · {entry.hours}h · {entry.task_details || "No details"}</li>)}</ul><TextArea placeholder="Comment (required for rejection)" value={comment} onChange={e => setComment(e.target.value)}/><div className="mt-2 flex gap-2"><Button onClick={() => decide(group.employee_id,group.week_start_date,"approve")}>Approve</Button><Button variant="danger" disabled={!comment.trim()} onClick={() => decide(group.employee_id,group.week_start_date,"reject")}>Reject</Button></div></div>)}</div></Card><Card><CardHeader><CardTitle>Leave awaiting approval</CardTitle></CardHeader><div className="space-y-3">{leaves.length === 0 && <p className="text-sm text-gray-600">No pending leave requests.</p>}{leaves.map(item => <div key={item.id} className="rounded-xl border border-gray-200 p-3"><strong>{item.employee_name} · {item.leave_type}</strong><p className="text-sm text-gray-600">{item.start_date} to {item.end_date}</p>{item.reason && <p className="text-sm">{item.reason}</p>}<div className="mt-2 flex gap-2"><Button onClick={async()=>{await timesheetsApi.decideLeave(item.id,"approve");await refresh();}}>Approve</Button><Button variant="danger" disabled={!comment.trim()} onClick={async()=>{await timesheetsApi.decideLeave(item.id,"reject",comment);setComment("");await refresh();}}>Reject</Button></div></div>)}</div></Card></div>;
}
