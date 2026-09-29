import { apiClient } from "./client";

export interface PerformanceCycle {
  id: string; name: string; description?: string | null; start_date: string; end_date: string;
  goal_due_date: string; self_review_due_date: string; manager_review_due_date: string;
  status: string; created_by_name?: string | null; approved_by_name?: string | null;
}
export interface PerformanceGoal {
  id: string; title: string; description?: string | null; category: string; measurement: string;
  weight: number; target_date: string; progress: number; evidence?: string | null; status: string;
  manager_comment?: string | null; version: number;
}
export interface ProjectFeedback {
  id: string; review_id: string; project_id: string; project_name: string; employee_name: string;
  status: string; rating?: number | null; contribution?: string | null; collaboration?: string | null;
}
export interface PerformanceReview {
  id: string; cycle: PerformanceCycle; employee_id: string; employee_name: string;
  manager_id?: string | null; manager_name: string; status: string; goals: PerformanceGoal[];
  self_summary?: string | null; self_rating?: number | null; manager_summary?: string | null;
  manager_rating?: number | null; calibration_comment?: string | null; calibrated_rating?: number | null;
  final_rating?: number | null; calibrated_by_name?: string | null; project_feedback: ProjectFeedback[];
  published_at?: string | null; acknowledged_at?: string | null; employee_comment?: string | null;
}
export interface PerformanceDashboard {
  cycles: PerformanceCycle[]; my_reviews: PerformanceReview[]; team_reviews: PerformanceReview[];
  feedback_requests: ProjectFeedback[]; can_manage_cycles: boolean; can_approve_cycles: boolean;
}

export type CyclePayload = Omit<PerformanceCycle, "id" | "status" | "created_by_name" | "approved_by_name">;
export type GoalPayload = Omit<PerformanceGoal, "id" | "status" | "manager_comment" | "version">;

export const performanceApi = {
  dashboard: () => apiClient.get<PerformanceDashboard>("/performance/dashboard").then(r => r.data),
  review: (id: string) => apiClient.get<PerformanceReview>(`/performance/reviews/${id}`).then(r => r.data),
  createCycle: (payload: CyclePayload) => apiClient.post("/performance/cycles", payload).then(r => r.data),
  updateCycle: (id: string, payload: CyclePayload) => apiClient.put(`/performance/cycles/${id}`, payload).then(r => r.data),
  submitCycle: (id: string) => apiClient.post(`/performance/cycles/${id}/submit`).then(r => r.data),
  decideCycle: (id: string, decision: "approve" | "changes_requested", comment?: string) => apiClient.post(`/performance/cycles/${id}/decision`, {decision, comment}).then(r => r.data),
  createGoal: (reviewId: string, payload: GoalPayload) => apiClient.post(`/performance/reviews/${reviewId}/goals`, payload).then(r => r.data),
  updateGoal: (goalId: string, payload: GoalPayload) => apiClient.put(`/performance/goals/${goalId}`, payload).then(r => r.data),
  submitGoals: (reviewId: string) => apiClient.post(`/performance/reviews/${reviewId}/goals/submit`).then(r => r.data),
  decideGoals: (reviewId: string, decision: "approve" | "changes_requested", comment?: string) => apiClient.post(`/performance/reviews/${reviewId}/goals/decision`, {decision, comment}).then(r => r.data),
  selfReview: (reviewId: string, summary: string, rating: number) => apiClient.post(`/performance/reviews/${reviewId}/self-review`, {summary, rating}).then(r => r.data),
  managerReview: (reviewId: string, summary: string, rating: number) => apiClient.post(`/performance/reviews/${reviewId}/manager-review`, {summary, rating}).then(r => r.data),
  feedback: (id: string, rating: number, contribution: string, collaboration?: string) => apiClient.post(`/performance/feedback/${id}`, {rating, contribution, collaboration}).then(r => r.data),
  calibrate: (reviewId: string, rating: number, comment: string) => apiClient.post(`/performance/reviews/${reviewId}/calibrate`, {rating, comment}).then(r => r.data),
  publish: (reviewId: string) => apiClient.post(`/performance/reviews/${reviewId}/publish`).then(r => r.data),
  acknowledge: (reviewId: string, comment?: string) => apiClient.post(`/performance/reviews/${reviewId}/acknowledge`, {comment}).then(r => r.data),
};
