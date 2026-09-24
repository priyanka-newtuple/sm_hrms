import { request } from './client';

export const health = {
  check: () => request<{ status: string }>('/health'),
};
