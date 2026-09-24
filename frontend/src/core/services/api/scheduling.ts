import type {
  ScheduleInterviewRequest,
  ScheduleInterviewResponse,
} from '../../types';
import { request } from './client';

export const scheduling = {
  scheduleInterview: (applicationId: string, data: ScheduleInterviewRequest) =>
    request<ScheduleInterviewResponse>(
      `/scheduling/applications/${applicationId}/interviews`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),
};
