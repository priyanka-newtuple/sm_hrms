import type {
  EmailTemplate,
  EmailTemplateCreateRequest,
  EmailTemplateListResponse,
  EmailTemplateUpdateRequest,
} from '../../types';
import { request } from './client';

export const emailTemplates = {
  list: (): Promise<EmailTemplateListResponse> =>
    request<EmailTemplateListResponse>('/email-templates'),

  get: (templateId: string): Promise<EmailTemplate> =>
    request<EmailTemplate>(`/email-templates/${templateId}`),

  create: (data: EmailTemplateCreateRequest): Promise<EmailTemplate> =>
    request<EmailTemplate>('/email-templates', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (templateId: string, data: EmailTemplateUpdateRequest): Promise<EmailTemplate> =>
    request<EmailTemplate>(`/email-templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (templateId: string): Promise<void> =>
    request<void>(`/email-templates/${templateId}`, {
      method: 'DELETE',
    }),
};
