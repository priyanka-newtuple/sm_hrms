import { useCallback, useState, type Dispatch, type SetStateAction } from 'react';
import { workflowEntities } from '../services/api';
import type { WorkflowEntityState } from '../services/api';

interface UseDocumentUploadEntityOptions {
  /**
   * Resolve which workflow to enroll the newly created entity into, for this call.
   * Return null/undefined to skip enrollment (e.g. no workflow available). May have a
   * side effect (e.g. syncing a controlled workflow-select dropdown to the resolved value).
   */
  resolveMachineName: () => string | null | undefined;
  setFormData: Dispatch<SetStateAction<Record<string, unknown>>>;
  setError: Dispatch<SetStateAction<string | null>>;
  /** Builds the user-facing message shown when enrollment fails, given the underlying error text. */
  describeEnrollError: (message: string) => string;
}

/**
 * Shared "the agent already created this entity via document upload" handling for both
 * create-entity surfaces (Pipeline's AddEntityDialog, records/detail's Create modal).
 * create_entity has no notion of workflows, so this always attempts to enroll the
 * resulting entity into one afterward — without it the entity would exist but never
 * show up on any Pipeline board.
 */
export function useDocumentUploadEntity({
  resolveMachineName,
  setFormData,
  setError,
  describeEnrollError,
}: UseDocumentUploadEntityOptions) {
  const [entityId, setEntityId] = useState<string | null>(null);

  const handleEntityCreated = useCallback(
    async (entity: WorkflowEntityState) => {
      setEntityId(entity.entity_id);
      setFormData((prev) => ({ ...prev, ...entity.data }));
      setError(null);
      const machineName = resolveMachineName();
      if (!machineName) return;
      try {
        const enrolled = await workflowEntities.enroll(machineName, entity.entity_id);
        setFormData((prev) => ({ ...prev, ...enrolled.data }));
      } catch (e) {
        setError(describeEnrollError(e instanceof Error ? e.message : 'unknown error'));
      }
    },
    [resolveMachineName, setFormData, setError, describeEnrollError]
  );

  const reset = useCallback(() => setEntityId(null), []);

  return { entityId, handleEntityCreated, reset };
}
