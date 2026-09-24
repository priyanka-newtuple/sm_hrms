import { request } from './client';

export interface WorkflowBoardDisplayFields {
  machine_name: string;
  fields: string[];
  updated_at: string | null;
  updated_by: string | null;
}

/** Up to 3 extra entity fields shown on one workflow's Kanban cards.
 *  Scoped to the workflow itself (not the entity type), applies immediately
 *  on save, and is shared by everyone viewing that workflow's board. */
export const boardDisplayFields = {
  get: (machineName: string) =>
    request<WorkflowBoardDisplayFields>(
      `/workflow-board-display-fields?machine_name=${encodeURIComponent(machineName)}`,
    ),

  update: (machineName: string, fields: string[]) =>
    request<WorkflowBoardDisplayFields>('/workflow-board-display-fields', {
      method: 'PUT',
      body: JSON.stringify({ machine_name: machineName, fields }),
    }),
};
