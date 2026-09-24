/**
 * Core Platform API Client — barrel re-export.
 *
 * Each domain has its own module; this index aggregates them so consumers can
 * keep importing from `@/core/services/api`. The default export mirrors the
 * legacy `api` object for code that does `import api from '...'`.
 */

export {
  createApiError,
  getApiErrorMessage,
  request,
  type ApiErrorData,
} from './client';

export { health } from './health';
export { entityRelations, type DeclarationDirection } from './entityRelations';
export { workflowEntities, getEntityThumbnailUrl, type WorkflowEntityState } from './workflowEntities';
export { transitions } from './transitions';
export {
  tasks,
  type TaskRecord,
  type TaskListResponse,
} from './tasks';
export {
  bulk,
  type BulkTransitionResult,
  type BulkTransitionResponse,
  type BulkStatesResponse,
} from './bulk';
export { events } from './events';
export { interventions } from './interventions';
export { signals } from './signals';
export { stateMachines } from './stateMachines';
export { boardDisplayFields, type WorkflowBoardDisplayFields } from './boardDisplayFields';
export { projections } from './projections';
export { dashboards } from './dashboards';
export { analytics } from './analytics';
export { stageComments } from './stageComments';
export { comments } from './comments';
export { notifications } from './notifications';
export { picklists } from './picklists';
export { fieldLibrary } from './fieldLibrary';
export { methodLibrary, METHOD_LIBRARY_MAX_LIMIT, type MethodListParams } from './methodLibrary';
export { formSchemas } from './formSchemas';
export { resumeUpload } from './resumeUpload';
export { unifiedIntegrations } from './unifiedIntegrations';
export { llmConfig } from './llmConfig';
export { emailTemplates } from './emailTemplates';
export { actionDefinitions } from './actionDefinitions';
export { transcriptionConfig } from './transcriptionConfig';
export { aiFeatures } from './aiFeatures';
export { entityTypes } from './entityTypes';
export { documentTypes } from './documentTypes';
export { documents } from './documents';
export { users } from './users';
export { organizations } from './organizations';
export { orgLogo } from './logo';
export { agent } from './agent';
export { mcp } from './mcp';
export { agentTraces } from './agentTraces';
export { transcription } from './transcription';
export { integrations } from './integrations';
export { scheduling } from './scheduling';
export { roles } from './roles';
export { permissions } from './permissions';
export { candidateLikes } from './candidateLikes';
export { invitations } from './invitations';
export { connectors } from './connectors';
export { remoteMcp } from './remoteMcp';
export { schedules } from './schedules';
export type { EntitySchedule, ScheduleTarget, ScheduleCreatePayload } from './schedules';
export {
  bulkImports,
  BULK_IMPORT_ACTIVE_STATUSES,
  type BulkImportDraft,
  type BulkImportJob,
  type BulkImportJobSummary,
  type BulkImportRelationBinding,
  type BulkImportRelationDefinition,
  type BulkImportSpreadsheetMapping,
  type BulkImportSpreadsheetSource,
} from './bulkImports';

import { health } from './health';
import { workflowEntities } from './workflowEntities';
import { transitions } from './transitions';
import { bulk } from './bulk';
import { events } from './events';
import { interventions } from './interventions';
import { signals } from './signals';
import { stateMachines } from './stateMachines';
import { boardDisplayFields } from './boardDisplayFields';
import { projections } from './projections';
import { dashboards } from './dashboards';
import { analytics } from './analytics';
import { stageComments } from './stageComments';
import { comments } from './comments';
import { notifications } from './notifications';
import { picklists } from './picklists';
import { fieldLibrary } from './fieldLibrary';
import { methodLibrary } from './methodLibrary';
import { formSchemas } from './formSchemas';
import { resumeUpload } from './resumeUpload';
import { llmConfig } from './llmConfig';
import { emailTemplates } from './emailTemplates';
import { actionDefinitions } from './actionDefinitions';
import { transcriptionConfig } from './transcriptionConfig';
import { aiFeatures } from './aiFeatures';
import { entityTypes } from './entityTypes';
import { documentTypes } from './documentTypes';
import { documents } from './documents';
import { users } from './users';
import { agent } from './agent';
import { mcp } from './mcp';
import { transcription } from './transcription';
import { integrations } from './integrations';
import { scheduling } from './scheduling';
import { roles } from './roles';
import { candidateLikes } from './candidateLikes';
import { invitations } from './invitations';
import { entityRelations } from './entityRelations';
import { schedules } from './schedules';

export default {
  entityRelations,
  health,
  workflowEntities,
  transitions,
  bulk,
  events,
  interventions,
  signals,
  stateMachines,
  boardDisplayFields,
  projections,
  stageComments,
  comments,
  notifications,
  picklists,
  fieldLibrary,
  methodLibrary,
  formSchemas,
  resumeUpload,
  llmConfig,
  emailTemplates,
  transcriptionConfig,
  aiFeatures,
  entityTypes,
  documentTypes,
  documents,
  transcription,
  users,
  agent,
  mcp,
  integrations,
  scheduling,
  roles,
  candidateLikes,
  invitations,
  dashboards,
  analytics,
  actionDefinitions,
  schedules,
};
