import { apiClient } from "./client";
import type { Asset, AssetAssignment, Page } from "./types";

export const assetsApi = {
  list: (page = 1, pageSize = 50) =>
    apiClient.get<Page<Asset>>("/assets", { params: { page, page_size: pageSize } }).then((r) => r.data),
  create: (payload: Partial<Asset>) => apiClient.post<Asset>("/assets", payload).then((r) => r.data),
  assign: (assetId: string, payload: { employee_id: string; assigned_date: string; condition_notes?: string }) =>
    apiClient.post<AssetAssignment>(`/assets/${assetId}/assign`, payload).then((r) => r.data),
  returnAsset: (assignmentId: string, payload: { returned_date: string; condition_notes?: string }) =>
    apiClient
      .post<AssetAssignment>(`/asset-assignments/${assignmentId}/return`, payload)
      .then((r) => r.data),
  employeeHistory: (employeeId: string) =>
    apiClient.get<AssetAssignment[]>(`/employees/${employeeId}/assets`).then((r) => r.data),
};
