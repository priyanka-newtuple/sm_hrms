import { request } from './client';

export interface PermissionDefinitionRead {
  id: string;
  key: string;
  resource: string;
  action: string;
  description: string | null;
  is_system: boolean;
}

export const permissions = {
  list: () => request<PermissionDefinitionRead[]>('/permissions'),
};
