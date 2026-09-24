export const roleKeys = {
  all:    () => ['roles'] as const,
  list:   () => [...roleKeys.all(), 'list'] as const,
  detail: (id: string) => [...roleKeys.all(), 'detail', id] as const,
};

export const timelineKeys = {
  all: (entityId: string) => ['timeline', entityId] as const,
};

export const boardDisplayFieldsKeys = {
  all:    () => ['boardDisplayFields'] as const,
  detail: (machineName: string) => [...boardDisplayFieldsKeys.all(), machineName] as const,
};

export const workflowEntityKeys = {
  all:  () => ['workflowEntities'] as const,
  list: (machineName: string, thumbnailField?: string) =>
    [...workflowEntityKeys.all(), machineName, thumbnailField ?? null] as const,
  column: (machineName: string, stateName: string, thumbnailField?: string) =>
    [...workflowEntityKeys.all(), 'column', machineName, stateName, thumbnailField ?? null] as const,
  table: (machineName: string, thumbnailField?: string) =>
    [...workflowEntityKeys.all(), 'table', machineName, thumbnailField ?? null] as const,
};
