import type {
  RelationDeclaration,
  RelationDeclarationListResponse,
  RelationMode,
} from '../../types';
import { request } from './client';

export type DeclarationDirection = 'from' | 'to' | 'both';

export const entityRelations = {
  listDeclarations: (entityTypeId: string, direction: DeclarationDirection = 'from') =>
    request<RelationDeclarationListResponse>(
      `/entity-types/${encodeURIComponent(entityTypeId)}/relation-declarations?direction=${direction}`
    ),

  getDeclarationForPair: (fromEntityTypeId: string, toEntityTypeId: string) =>
    request<RelationDeclaration>(
      `/entity-types/${encodeURIComponent(fromEntityTypeId)}/relation-declarations/${encodeURIComponent(toEntityTypeId)}`
    ),

  createDeclaration: (
    fromEntityTypeId: string,
    body: {
      to_entity_type_id: string;
      relation_type: RelationMode;
      relation_metadata?: Record<string, unknown>;
    }
  ) =>
    request<RelationDeclaration>(
      `/entity-types/${encodeURIComponent(fromEntityTypeId)}/relation-declarations`,
      { method: 'POST', body: JSON.stringify(body) }
    ),

  // PATCH replaces relation_metadata wholesale — always pass the complete mapping.
  updateMapping: (relationDefId: string, relationMetadata: Record<string, unknown>) =>
    request<RelationDeclaration>(
      `/entity-types/relation-declarations/${encodeURIComponent(relationDefId)}`,
      { method: 'PATCH', body: JSON.stringify({ relation_metadata: relationMetadata }) }
    ),

  deleteDeclaration: (relationDefId: string) =>
    request<{ relation_def_id: string; deleted_at: string | null }>(
      `/entity-types/relation-declarations/${encodeURIComponent(relationDefId)}`,
      { method: 'DELETE' }
    ),

  // Legacy named relations were created as forward+reverse row pairs; this
  // endpoint hard-deletes both rows atomically. Use for rows with a
  // relation_name (declarations never set one).
  deleteLegacyRelation: (fromEntityTypeId: string, relationDefId: string) =>
    request<void>(
      `/entity-types/${encodeURIComponent(fromEntityTypeId)}/relations/${encodeURIComponent(relationDefId)}`,
      { method: 'DELETE' }
    ),

  // Source-record options for the create-modal link pickers. Search runs
  // server-side (substring over record data); limit caps at 100 backend-side.
  listRecordsOfType: (entityTypeName: string, search = '', limit = 20) => {
    const params = new URLSearchParams({ entity_type_name: entityTypeName });
    if (search.trim()) params.set('search', search.trim());
    params.set('limit', String(limit));
    return request<{ items: Array<{ entity_id: string; data: Record<string, unknown> }> }>(
      `/entity-records?${params.toString()}`
    );
  },
};
