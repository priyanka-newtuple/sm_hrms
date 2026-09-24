export interface FrontendApiEndpoint {
  serviceGroup: string;
  serviceLabel: string;
  methodName: string;
  method: string;
  path: string;
  sourceFile: string;
}

export const frontendApiInventory: FrontendApiEndpoint[] = [
  {
    "serviceGroup": "stateMachines",
    "serviceLabel": "State Machines",
    "methodName": "list",
    "method": "GET",
    "path": "/state-machines",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "stateMachines",
    "serviceLabel": "State Machines",
    "methodName": "get",
    "method": "GET",
    "path": "/state-machines/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "picklists",
    "serviceLabel": "Picklists",
    "methodName": "list",
    "method": "GET",
    "path": "/config/picklists",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "picklists",
    "serviceLabel": "Picklists",
    "methodName": "get",
    "method": "GET",
    "path": "/config/picklists/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "picklists",
    "serviceLabel": "Picklists",
    "methodName": "create",
    "method": "POST",
    "path": "/config/picklists",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "picklists",
    "serviceLabel": "Picklists",
    "methodName": "update",
    "method": "PUT",
    "path": "/config/picklists/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "picklists",
    "serviceLabel": "Picklists",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/config/picklists/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "list",
    "method": "GET",
    "path": "/config/forms",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "get",
    "method": "GET",
    "path": "/config/forms/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "create",
    "method": "POST",
    "path": "/config/forms",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "update",
    "method": "PUT",
    "path": "/config/forms/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "reset",
    "method": "POST",
    "path": "/config/forms//reset",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "formSchemas",
    "serviceLabel": "Form Schemas",
    "methodName": "seed",
    "method": "POST",
    "path": "/config/seed",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "listProviders",
    "method": "GET",
    "path": "/config/transcription/providers",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "list",
    "method": "GET",
    "path": "/config/transcription",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "save",
    "method": "POST",
    "path": "/config/transcription",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/config/transcription/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "validate",
    "method": "POST",
    "path": "/config/transcription/validate",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "transcriptionConfig",
    "serviceLabel": "Transcription Config",
    "methodName": "listModels",
    "method": "POST",
    "path": "/config/transcription/models",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "jobs",
    "serviceLabel": "Processing Jobs",
    "methodName": "list",
    "method": "GET",
    "path": "/jobs",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "jobs",
    "serviceLabel": "Processing Jobs",
    "methodName": "get",
    "method": "GET",
    "path": "/jobs/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "jobs",
    "serviceLabel": "Processing Jobs",
    "methodName": "getActive",
    "method": "GET",
    "path": "/jobs/active/current",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "jobs",
    "serviceLabel": "Processing Jobs",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/jobs/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "aiFeatures",
    "serviceLabel": "AI Features",
    "methodName": "list",
    "method": "GET",
    "path": "/config/ai-features",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "aiFeatures",
    "serviceLabel": "AI Features",
    "methodName": "getModels",
    "method": "GET",
    "path": "/config/ai-features/models",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "aiFeatures",
    "serviceLabel": "AI Features",
    "methodName": "get",
    "method": "GET",
    "path": "/config/ai-features/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "aiFeatures",
    "serviceLabel": "AI Features",
    "methodName": "update",
    "method": "PUT",
    "path": "/config/ai-features/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "aiFeatures",
    "serviceLabel": "AI Features",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/config/ai-features/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "list",
    "method": "GET",
    "path": "/config/document-types",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "get",
    "method": "GET",
    "path": "/config/document-types/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "create",
    "method": "POST",
    "path": "/config/document-types",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "update",
    "method": "PUT",
    "path": "/config/document-types/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/config/document-types/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "getTools",
    "method": "GET",
    "path": "/config/document-types/tools",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "documentTypes",
    "serviceLabel": "Document Types",
    "methodName": "getToolPresets",
    "method": "GET",
    "path": "/config/document-types/tools/presets",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "list",
    "method": "GET",
    "path": "/users",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "listPending",
    "method": "GET",
    "path": "/users/pending",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "get",
    "method": "GET",
    "path": "/users/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "approve",
    "method": "POST",
    "path": "/users//approve",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "reject",
    "method": "POST",
    "path": "/users//reject",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "suspend",
    "method": "POST",
    "path": "/users//suspend",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "reactivate",
    "method": "POST",
    "path": "/users//reactivate",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "updateRole",
    "method": "PUT",
    "path": "/users//role",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "users",
    "serviceLabel": "Users",
    "methodName": "getStats",
    "method": "GET",
    "path": "/users/stats/summary",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "list",
    "method": "GET",
    "path": "/organizations",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "listPending",
    "method": "GET",
    "path": "/organizations/pending",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "get",
    "method": "GET",
    "path": "/organizations/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "getCurrent",
    "method": "GET",
    "path": "/organizations/current",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "approve",
    "method": "POST",
    "path": "/organizations//approve",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "reject",
    "method": "POST",
    "path": "/organizations//reject",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/organizations/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "listUsers",
    "method": "GET",
    "path": "/organizations/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "createUser",
    "method": "POST",
    "path": "/organizations//users",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "organizations",
    "serviceLabel": "Organizations",
    "methodName": "deleteUser",
    "method": "DELETE",
    "path": "/organizations/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "listDefinitions",
    "method": "GET",
    "path": "/agent/definitions?active_only=",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "getDefinition",
    "method": "GET",
    "path": "/agent/definitions/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "createDefinition",
    "method": "POST",
    "path": "/agent/definitions",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "updateDefinition",
    "method": "PATCH",
    "path": "/agent/definitions/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "deleteDefinition",
    "method": "DELETE",
    "path": "/agent/definitions/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "listSessions",
    "method": "GET",
    "path": "/agent/sessions?limit=",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "getSession",
    "method": "GET",
    "path": "/agent/sessions/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "deleteSession",
    "method": "DELETE",
    "path": "/agent/sessions/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "createRun",
    "method": "POST",
    "path": "/agent/runs",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "listRuns",
    "method": "GET",
    "path": "/agent/runs",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agent",
    "serviceLabel": "Agent Definitions",
    "methodName": "getRun",
    "method": "GET",
    "path": "/agent/runs/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agentTraces",
    "serviceLabel": "Agent Traces",
    "methodName": "listRuns",
    "method": "GET",
    "path": "/agent-traces/runs",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agentTraces",
    "serviceLabel": "Agent Traces",
    "methodName": "listSessions",
    "method": "GET",
    "path": "/agent-traces/sessions",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "agentTraces",
    "serviceLabel": "Agent Traces",
    "methodName": "getRun",
    "method": "GET",
    "path": "/agent-traces/runs/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "integrations",
    "serviceLabel": "Integrations",
    "methodName": "getGoogleCalendarAuthUrl",
    "method": "GET",
    "path": "/integrations/google-calendar/auth-url",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "integrations",
    "serviceLabel": "Integrations",
    "methodName": "googleCalendarCallback",
    "method": "POST",
    "path": "/integrations/google-calendar/callback",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "list",
    "method": "GET",
    "path": "/roles",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "get",
    "method": "GET",
    "path": "/roles/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "create",
    "method": "POST",
    "path": "/roles",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "update",
    "method": "PUT",
    "path": "/roles/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "delete",
    "method": "DELETE",
    "path": "/roles/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "duplicate",
    "method": "POST",
    "path": "/roles//duplicate",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "getUserRoles",
    "method": "GET",
    "path": "/roles/users//roles",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "setUserRole",
    "method": "PUT",
    "path": "/roles/users//role",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "removeUserRole",
    "method": "DELETE",
    "path": "/roles/users/",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "roles",
    "serviceLabel": "Roles",
    "methodName": "getMyPermissions",
    "method": "GET",
    "path": "/roles/my-permissions",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "create",
    "method": "POST",
    "path": "/invitations",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "list",
    "method": "GET",
    "path": "/invitations",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "validate",
    "method": "GET",
    "path": "/invitations/validate?token=",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "accept",
    "method": "POST",
    "path": "/invitations/accept",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "resend",
    "method": "POST",
    "path": "/invitations//resend",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "invitations",
    "serviceLabel": "Invitations",
    "methodName": "revoke",
    "method": "POST",
    "path": "/invitations//revoke",
    "sourceFile": "core/services/api/index.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "list",
    "method": "GET",
    "path": "/config/funnels",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "get",
    "method": "GET",
    "path": "/config/funnels/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "getVersions",
    "method": "GET",
    "path": "/config/funnels//versions",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "create",
    "method": "POST",
    "path": "/config/funnels",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "update",
    "method": "PUT",
    "path": "/config/funnels/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "validate",
    "method": "POST",
    "path": "/config/funnels/validate",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "funnels",
    "serviceLabel": "Funnels",
    "methodName": "publish",
    "method": "POST",
    "path": "/config/funnels//publish",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "list",
    "method": "GET",
    "path": "/playbooks?",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "get",
    "method": "GET",
    "path": "/playbooks/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "create",
    "method": "POST",
    "path": "/playbooks",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "update",
    "method": "PATCH",
    "path": "/playbooks/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "startRun",
    "method": "POST",
    "path": "/playbooks/runs",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "listRuns",
    "method": "GET",
    "path": "/playbooks/runs",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "getRun",
    "method": "GET",
    "path": "/playbooks/runs/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "pauseRun",
    "method": "POST",
    "path": "/playbooks/runs//pause",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "resumeRun",
    "method": "POST",
    "path": "/playbooks/runs//resume",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "cancelRun",
    "method": "POST",
    "path": "/playbooks/runs//cancel",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "listSteps",
    "method": "GET",
    "path": "/playbooks/runs//steps",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "getStep",
    "method": "GET",
    "path": "/playbooks/steps/",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "completeStep",
    "method": "POST",
    "path": "/playbooks/steps//complete",
    "sourceFile": "domains/ats/services/api.ts"
  },
  {
    "serviceGroup": "playbooks",
    "serviceLabel": "Playbooks",
    "methodName": "executeStep",
    "method": "POST",
    "path": "/playbooks/steps//execute",
    "sourceFile": "domains/ats/services/api.ts"
  }
];
