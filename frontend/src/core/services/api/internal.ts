/**
 * Internal helpers shared across domain modules: file conversion, document mapping,
 * org-id resolution, query builders.
 */

import type { DocumentType, DocumentMetadata } from '../../types';
import { BYPASS_AUTH, BYPASS_ORG_ID } from './client';

export async function fileToBase64Content(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      resolve(base64);
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

export function mapFileType(raw: Record<string, unknown>): DocumentType {
  const typeId = String(raw.type_id || '');
  const now = new Date().toISOString();
  const metadata = (raw.metadata as Record<string, unknown> | null) ?? null;
  const agentEnabled = Boolean(metadata?.agent_processing_enabled ?? false);
  return {
    id: String(raw.type_id || raw.id || typeId),
    type_id: typeId,
    display_name: String(raw.display_name || typeId),
    description: (raw.description as string | null) ?? null,
    folder: String(raw.folder || ''),
    allowed_extensions: Array.isArray(raw.allowed_extensions) ? raw.allowed_extensions.map(String) : [],
    max_size_mb: Number(raw.max_size_mb || 10),
    extract_enabled: false,
    system_prompt: null,
    extraction_prompt: null,
    extraction_schema: null,
    agent_enabled: agentEnabled,
    agent_system_prompt: null,
    agent_prompt: null,
    agent_tools: null,
    agent_model: null,
    is_entity: false,
    entity_type_name: null,
    state_machine_name: null,
    upload_contexts: Array.isArray(raw.upload_contexts) ? raw.upload_contexts as import('../../types').UploadContextConfig[] : null,
    agent_config: (raw.agent_config && typeof raw.agent_config === 'object') ? raw.agent_config as import('../../types').DocumentAgentConfig : null,
    is_active: Boolean(raw.is_active ?? true),
    is_system: Boolean(raw.is_system ?? false),
    is_preview_thumbnail: Boolean(raw.is_preview_thumbnail ?? false),
    metadata,
    created_at: now,
    updated_at: now,
  };
}

export function mapFileRecordToDocument(record: Record<string, unknown>): DocumentMetadata {
  return {
    id: String(record.file_id || ''),
    type: String(record.type_id || ''),
    filename: String(record.filename || ''),
    storage_key: String(record.storage_key || ''),
    content_type: String(record.content_type || ''),
    size_bytes: Number(record.size_bytes || 0),
    uploaded_at: String(record.created_at || new Date().toISOString()),
    uploaded_by: String(record.uploaded_by || 'unknown'),
    status: record.status ? String(record.status) : undefined,
    failure_reason: record.failure_reason ? String(record.failure_reason) : null,
    metadata: (record.metadata && typeof record.metadata === 'object')
      ? record.metadata as Record<string, unknown>
      : {},
  };
}

export const buildOrgQuery = (orgId?: string) => orgId ? `?org_id=${orgId}` : '';

export function resolveOrganizationId(orgId?: string): string | undefined {
  if (orgId && orgId.trim()) {
    return orgId;
  }
  if (BYPASS_AUTH) {
    return BYPASS_ORG_ID;
  }
  return undefined;
}

export function requireOrganizationId(orgId?: string, surface = 'integration configuration'): string {
  const resolved = resolveOrganizationId(orgId);
  if (!resolved) {
    throw new Error(`${surface} requires an organization context.`);
  }
  return resolved;
}
