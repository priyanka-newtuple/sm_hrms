import { apiClient } from "./client";
import type { HelpdeskCategory, Page, Ticket } from "./types";

export const helpdeskApi = {
  categories: () => apiClient.get<HelpdeskCategory[]>("/helpdesk/categories").then((r) => r.data),
  list: (page = 1, pageSize = 50) =>
    apiClient
      .get<Page<Ticket>>("/helpdesk/tickets", { params: { page, page_size: pageSize } })
      .then((r) => r.data),
  create: (payload: { category_id: string; subject: string; description: string; priority?: string }) =>
    apiClient.post<Ticket>("/helpdesk/tickets", payload).then((r) => r.data),
  update: (id: string, payload: Partial<Ticket>) =>
    apiClient.patch<Ticket>(`/helpdesk/tickets/${id}`, payload).then((r) => r.data),
};
