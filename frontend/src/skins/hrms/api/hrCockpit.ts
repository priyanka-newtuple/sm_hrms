import { apiClient } from "./client";

export type ContentItem = Record<string, any> & { id: string; status: string };
export type HrDashboard = { role: string; policies: ContentItem[]; events: ContentItem[]; job_descriptions: ContentItem[]; openings: ContentItem[]; referrals: ContentItem[]; holidays: ContentItem[]; hiring_managers: {id:string;name:string}[] };

export const hrCockpitApi = {
  dashboard: () => apiClient.get<HrDashboard>("/hr-cockpit/dashboard").then(r => r.data),
  createPolicy: (p: unknown) => apiClient.post("/hr-cockpit/policies", p).then(r => r.data),
  createEvent: (p: unknown) => apiClient.post("/hr-cockpit/learning-events", p).then(r => r.data),
  createJd: (p: unknown) => apiClient.post("/hr-cockpit/job-descriptions", p).then(r => r.data),
  createOpening: (p: unknown) => apiClient.post("/hr-cockpit/openings", p).then(r => r.data),
  createHoliday: (p: unknown) => apiClient.post("/hr-cockpit/holidays", p).then(r => r.data),
  transition: (kind: string, id: string, action: string) => apiClient.post(`/hr-cockpit/${kind}/${id}/${action}`).then(r => r.data),
};

export const publicContentApi = {
  policies: () => apiClient.get<ContentItem[]>("/public/content/policies").then(r => r.data),
  events: () => apiClient.get<ContentItem[]>("/public/content/learning-events").then(r => r.data),
  openings: () => apiClient.get<ContentItem[]>("/public/content/openings").then(r => r.data),
  holidays: () => apiClient.get<ContentItem[]>("/public/content/holidays").then(r => r.data),
  refer: (id: string, p: unknown) => apiClient.post(`/public/content/openings/${id}/referrals`, p).then(r => r.data),
};
