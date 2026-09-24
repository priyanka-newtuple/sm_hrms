import type {
  Invitation,
  InvitationCreate,
  InvitationValidation,
  InvitationAccept,
  InvitationAcceptResponse,
  InvitationStatus,
} from '../../types';
import { request } from './client';

export const invitations = {
  create: (data: InvitationCreate) =>
    request<Invitation>('/invitations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: (status?: InvitationStatus) => {
    const params = status ? `?status=${status}` : '';
    return request<Invitation[]>(`/invitations${params}`);
  },

  validate: (token: string) =>
    request<InvitationValidation>(`/invitations/validate?token=${encodeURIComponent(token)}`),

  accept: (data: InvitationAccept) =>
    request<InvitationAcceptResponse>('/invitations/accept', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  resend: (invitationId: string) =>
    request<Invitation>(`/invitations/${invitationId}/resend`, {
      method: 'POST',
    }),

  revoke: (invitationId: string) =>
    request<Invitation>(`/invitations/${invitationId}/revoke`, {
      method: 'POST',
    }),
};
