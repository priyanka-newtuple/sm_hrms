import { request } from './client';

export interface AnalyticsSeriesPoint {
  label: string;
  value: number;
}

export interface LoginActivityResponse {
  date_from: string;
  date_to: string;
  active_users: number;
  total_logins: number;
  daily: AnalyticsSeriesPoint[];
  weekly: AnalyticsSeriesPoint[];
}

export interface ActionBreakdownResponse {
  date_from: string;
  date_to: string;
  total_actions: number;
  items: Array<{ action: string; category: string; count: number }>;
}

export interface UserActivityResponse {
  date_from: string;
  date_to: string;
  total: number;
  limit: number;
  offset: number;
  items: Array<{
    user_id: string;
    name: string;
    email: string | null;
    actor_type?: string;
    last_login_at: string | null;
    login_count: number;
    total_actions: number;
    actions: Array<{ action: string; category: string; count: number }>;
  }>;
}

export interface AnalyticsOverviewResponse {
  logins: LoginActivityResponse;
  actions: ActionBreakdownResponse;
  users: UserActivityResponse;
}

export type AnalyticsGroupBy = 'day' | 'week' | 'user' | 'action' | 'category';

export interface FlexibleAnalyticsResponse {
  date_from: string;
  date_to: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
  total: number;
  limit: number;
  offset: number;
}

export interface AnalyticsDateParams {
  date_from?: string;
  date_to?: string;
}

function overviewQuery(
  params: AnalyticsDateParams & { user_limit: number; user_offset: number },
): string {
  const query = new URLSearchParams();
  if (params.date_from) query.set('date_from', params.date_from);
  if (params.date_to) query.set('date_to', params.date_to);
  query.set('user_limit', String(params.user_limit));
  query.set('user_offset', String(params.user_offset));
  return `?${query.toString()}`;
}

export const analytics = {
  /** Fetch the fixed login/action/per-user reports for a date range in one call. */
  overview: (params: AnalyticsDateParams & { user_limit: number; user_offset: number }) =>
    request<AnalyticsOverviewResponse>(`/analytics/overview${overviewQuery(params)}`),
  /** Run a custom grouped report over the approved dimensions (day/week/user/action/category). */
  flexible: (payload: {
    date_from?: string;
    date_to?: string;
    group_by: AnalyticsGroupBy[];
    include_auth?: boolean;
    limit: number;
    offset: number;
  }) =>
    request<FlexibleAnalyticsResponse>('/analytics/flexible', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
