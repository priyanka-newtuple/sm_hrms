import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { workflowEntities, stateMachines as stateMachinesApi } from '../../../core/services/api';
import type { WorkflowEntityState } from '../../../core/services/api';
import type { FormSchema, StateMachineRecord } from '../../../core/types';
import { useSourcePickers } from '../../../core/hooks/useSourcePickers';
import { useDocumentUploadEntity } from '../../../core/hooks/useDocumentUploadEntity';
import { useEntityStore, schemaForEntityType } from '../../../core/stores/entityStore';
import { usePermissions } from '../../../core/hooks/usePermissions';
import { useFeatureFlags } from '../../../core/hooks/useFeatureFlags';
import { useGlobalEntityFilter } from '../../../core/contexts/GlobalEntityFilterContext';
import AccessDenied from '../../../core/components/AccessDenied';
import {
  buildCompleteSchemaFieldsForSchemas,
  buildDefaultFormDataForSchemas,
  getFormFields,
  getEnterableFields,
  getReferenceFields,
  isMissingRequiredFieldValue,
  collectTimerFields,
  withoutTimerFields,
  getCalculatedFields,
  pickEnterableData,
  validateFieldValue,
  IDENTIFIER_FIELD_KEY,
} from '../../../shared/utils/entityForm';
import { useIdentifierConfig } from '@/shared/hooks/useIdentifierConfig';
import { useWorkflowFieldsByEntityType } from '@/shared/hooks/useWorkflowFieldsByEntityType';
import { resolveEntityFormSchemas } from '@/lib/state-machine/entitySchema';
import { applyCalculations } from '@/shared/utils/calc';
import TimerDurationField from '@/core/components/TimerDurationField';
import { STATE_MACHINES_CHANGED_EVENT } from '@/core/events';
import type { FormField } from '@/core/types';
import { useRecordTimer } from '@/shared/hooks/useRecordTimer';
import {
  dedupeMachinesByName,
  deriveEntityDisplayName,
  isEntityEditDirty,
  isSchemaForMachineEntityType,
  normalizeEntityType,
} from './helpers';
import {
  methodSchemasForWorkflowInitialState,
  methodSchemasForWorkflowState,
  useEntityTypeMethodSchemas,
} from './methodSchemas';
import DetailHeader from './components/DetailHeader';
import DetailFilters from './components/DetailFilters';
import ErrorBanner from './components/ErrorBanner';
import EmptyState from './components/EmptyState';
import EntityTable from './components/EntityTable';
import CreateEntityModal from './components/CreateEntityModal';
import EditEntityModal from './components/EditEntityModal';

export default function EntityDetailPage() {
  const params = useParams<{ entityType?: string }>();
  const navigate = useNavigate();
  const { bulkImportEnabled } = useFeatureFlags();
  const routeEntityType = params.entityType ? decodeURIComponent(params.entityType) : '';
  const normalizedRouteEntityType = normalizeEntityType(routeEntityType);
  const {
    templateMode,
    label: identifierLabel,
    requiredMessage: identifierRequiredMessage,
  } = useIdentifierConfig(routeEntityType);

  const {
    entities: entityList,
    entityTypes: entityTypeDefinitions,
    schemas,
    loading,
    error,
    schemasError,
    fetchAll,
    patchEntity,
    deleteEntity,
    clearError,
  } = useEntityStore();
  const { activeAnchorEntityId } = useGlobalEntityFilter();

  const { can, filterVisibleFields, shouldMaskField, canEditField, filterEditablePayload } = usePermissions();
  const canView   = !normalizedRouteEntityType || can('view',   normalizedRouteEntityType);
  const canCreate = can('create', normalizedRouteEntityType);
  const canEdit   = can('edit',   normalizedRouteEntityType);
  const canDelete = can('delete', normalizedRouteEntityType);

  const [machines, setMachines] = useState<StateMachineRecord[]>([]);
  const [machinesLoading, setMachinesLoading] = useState(true);
  const [machinesError, setMachinesError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [selectedSchema, setSelectedSchema] = useState<FormSchema | null>(null);
  const [selectedMachineName, setSelectedMachineName] = useState<string | null>(null);
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [creating, setCreating] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Source-record link pickers for relation declarations targeting this entity type.
  const sourceLinks = useSourcePickers();

  const [editingEntity, setEditingEntity] = useState<WorkflowEntityState | null>(null);
  const [editingEntityLoading, setEditingEntityLoading] = useState(false);
  const [editingSchema, setEditingSchema] = useState<FormSchema | null>(null);
  const [editFormData, setEditFormData] = useState<Record<string, unknown>>({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [deletingEntityId, setDeletingEntityId] = useState<string | null>(null);

  const loadMachines = useCallback(async () => {
    setMachinesLoading(true);
    setMachinesError(null);
    try {
      const machineResp = await stateMachinesApi.listPublished();
      setMachines(dedupeMachinesByName(machineResp));
    } catch (err) {
      // Any throw here is a genuine failure — empty results are a valid response, not an exception.
      const isApiError = err instanceof Error && err.name === 'ApiError';
      if (isApiError) {
        console.error('Failed to load published workflows:', err);
      } else {
        console.warn('Failed to load published workflows (network):', err);
      }
      setMachinesError('Could not load workflows. You can still create without one.');
    } finally {
      setMachinesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll(activeAnchorEntityId);
    loadMachines();
    // Live-refresh the published-workflow list when a workflow is created/published
    // elsewhere, so a newly configured workflow appears without a page refresh (STAT-424).
    const onChange = () => void loadMachines();
    window.addEventListener(STATE_MACHINES_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(STATE_MACHINES_CHANGED_EVENT, onChange);
  }, [activeAnchorEntityId, fetchAll, loadMachines]);

  // An entity type whose fields come from a workflow's pinned Method Blocks has
  // no Form of its own, so filtering the Forms list alone left this page with
  // nothing but the identifier. Same resolution the pipeline surfaces use: a
  // Form wins when there is one, the workflow's entity_schema stands in when
  // there isn't.
  const workflowFieldsByEntityType = useWorkflowFieldsByEntityType();
  const pageSchemas = useMemo(() => {
    const forms = (normalizedRouteEntityType
      ? schemas.filter(
          (schema) => normalizeEntityType(schema.entity_type) === normalizedRouteEntityType,
        )
      : schemas
    )
      .slice()
      .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
    if (forms.length > 0 || !routeEntityType) return forms;
    return resolveEntityFormSchemas(routeEntityType, {
      scope: 'union',
      formSchemas: schemas,
      workflowFields: workflowFieldsByEntityType[routeEntityType] ?? null,
    });
  }, [schemas, normalizedRouteEntityType, routeEntityType, workflowFieldsByEntityType]);

  const pageMachines = useMemo(
    () =>
      normalizedRouteEntityType
        ? machines.filter(
            (machine) =>
              normalizeEntityType(machine.entity_type) === normalizedRouteEntityType ||
              pageSchemas.some((schema) => isSchemaForMachineEntityType(schema, machine)),
          )
        : machines,
    [machines, normalizedRouteEntityType, pageSchemas],
  );

  // Only published (version >= 1) workflows are eligible for enrollment when creating records.
  // Sorted alphabetically by display name for consistent UX.
  const publishedPageMachines = useMemo(
    () =>
      pageMachines
        .filter((m) => m.version >= 1)
        .sort((a, b) => (a.name || a.machine_name).localeCompare(b.name || b.machine_name)),
    [pageMachines],
  );
  const {
    schemas: entityTypeMethodSchemas,
    loading: entityTypeMethodsLoading,
    error: entityTypeMethodsError,
  } = useEntityTypeMethodSchemas(routeEntityType);

  const createSchemas = useMemo(
    () => selectedMachineName
      ? methodSchemasForWorkflowInitialState(
          publishedPageMachines,
          routeEntityType,
          selectedMachineName,
        )
      : entityTypeMethodSchemas,
    [publishedPageMachines, routeEntityType, selectedMachineName, entityTypeMethodSchemas],
  );

  // If the workflow list refreshes while the modal is open and the previously-selected
  // machine is no longer available, reset the selection rather than submitting a stale value.
  useEffect(() => {
    if (
      showModal &&
      selectedMachineName !== null &&
      !publishedPageMachines.some((m) => m.machine_name === selectedMachineName)
    ) {
      setSelectedMachineName(null);
    }
  }, [publishedPageMachines, selectedMachineName, showModal]);

  const entityTypes = useMemo(
    () => [...new Set(entityList.map((e) => e.entity_type))].sort(),
    [entityList],
  );
  const routeEntityTypeDefinition = useMemo(
    () =>
      entityTypeDefinitions.find(
        (entityType) => normalizeEntityType(entityType.name) === normalizedRouteEntityType,
      ),
    [entityTypeDefinitions, normalizedRouteEntityType],
  );

  const filtered = useMemo(
    () =>
      entityList.filter((e) => {
        if (
          normalizedRouteEntityType &&
          normalizeEntityType(e.entity_type) !== normalizedRouteEntityType
        ) {
          return false;
        }
        if (filterType && e.entity_type !== filterType) return false;
        if (search) {
          const q = search.toLowerCase();
          return (
            e.entity_type.toLowerCase().includes(q) ||
            e.entity_id.toLowerCase().includes(q) ||
            Object.values(e.data).some((v) => String(v).toLowerCase().includes(q))
          );
        }
        return true;
      }),
    [entityList, normalizedRouteEntityType, filterType, search],
  );

  const schemaForEntity = useCallback(
    (entity: WorkflowEntityState) => schemaForEntityType(schemas, entity.entity_type),
    [schemas],
  );

  // Fields of the active tab (selectedSchema) for rendering; the union across
  // every attached form for validation and submission. Calc fields are appended
  // so they render (read-only, live) even though getEnterableFields excludes
  // them from what's actually submitted — see pickEnterableData.
  const formFields = useMemo(
    // Timers render once at record level (above the tabs), never inside a form.
    () => withoutTimerFields([
      ...getEnterableFields(selectedSchema),
      ...getCalculatedFields(selectedSchema),
    ]),
    [selectedSchema],
  );
  // Edit shows inherited (reference) fields read-only after the enterable ones,
  // plus calc fields (also read-only) for the same reason as `formFields` above.
  const editFormFields = useMemo(
    () => withoutTimerFields([
      ...getEnterableFields(editingSchema),
      ...getReferenceFields(editingSchema),
      ...getCalculatedFields(editingSchema),
    ]),
    [editingSchema],
  );
  // Calc fields/columns update live from the raw entered values; kept separate
  // from `formData`/`editFormData` so the raw, editable state is untouched
  // (backend recomputes authoritatively on write regardless).
  const computedFormData = useMemo(
    () => applyCalculations(formFields, formData),
    [formFields, formData],
  );

  /** The record-level timer strip shown above a modal's form tabs. */
  const renderTimerStrip = (
    fields: FormField[],
    values: Record<string, unknown>,
    timer: ReturnType<typeof useRecordTimer>,
    opts: {
      entityId?: string;
      canStop: boolean;
      stopHint: string;
      onChange?: (seconds: unknown) => void;
      onStopped?: (fieldId: string, seconds: number) => void | Promise<void>;
    },
  ) => {
    const primary = fields[0];
    if (!primary) return null;
    return (
      <div className="border-b border-border px-4 py-2.5">
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {primary.label}
          {fields.length > 1 && (
            <span className="ml-1 font-normal normal-case tracking-normal">
              · recorded on {fields.length} forms
            </span>
          )}
        </p>
        <TimerDurationField
          fieldKey={primary.id}
          value={values[primary.id]}
          onChange={opts.onChange ?? (() => {})}
          entityId={opts.entityId}
          canStop={opts.canStop}
          stopBlockedHint={opts.stopHint}
          onStopped={opts.onStopped ? (secs) => opts.onStopped!(primary.id, secs) : undefined}
          localStartedAt={timer.startedAt}
          onLocalStart={timer.start}
          onLocalStop={timer.reset}
          pausedAt={timer.pausedAt}
          pausedMs={timer.pausedMs}
          onPause={timer.pause}
          onResume={timer.resume}
          compact
        />
      </div>
    );
  };

  const computedEditFormData = useMemo(
    () => applyCalculations(editFormFields, editFormData),
    [editFormFields, editFormData],
  );
  const workflowForEntity = useCallback(
    (record: Pick<WorkflowEntityState, 'workflow_id' | 'machine_name'>) =>
      publishedPageMachines.find(
        (candidate) => candidate.id === record.workflow_id
          || (record.machine_name != null && candidate.machine_name === record.machine_name),
      ),
    [publishedPageMachines],
  );

  const editSchemas = useMemo(() => {
    if (!editingEntity) return [];
    const workflow = workflowForEntity(editingEntity);
    const stateSchemas = methodSchemasForWorkflowState(
      workflow,
      editingEntity.entity_type,
      editingEntity.current_state,
    );
    return stateSchemas.length > 0 ? stateSchemas : entityTypeMethodSchemas;
  }, [editingEntity, entityTypeMethodSchemas, workflowForEntity]);

  // Record-level timers are held by the page so they survive switching form tabs.
  // Only the final whole-second value is persisted with the ordinary entity write.
  const createTimer = useRecordTimer();
  const editTimer = useRecordTimer();

  const createTimerFields = useMemo(
    () => collectTimerFields(createSchemas.flatMap((schema) => getFormFields(schema))),
    [createSchemas],
  );
  const editTimerFields = useMemo(
    () => collectTimerFields(editSchemas.flatMap((schema) => getFormFields(schema))),
    [editSchemas],
  );
  const createTimerRequiresStart = createTimerFields.some((field) => field.required);
  const editTimerRequiresStart = editTimerFields.some((field) => field.required);

  /** One elapsed value across every form that declares a timer, so they agree. */
  const applyTimerValue = (
    fields: FormField[],
    setter: React.Dispatch<React.SetStateAction<Record<string, unknown>>>,
    seconds: unknown,
  ) => {
    if (typeof seconds !== 'number') return;
    setter((prev) => {
      const next = { ...prev };
      for (const field of fields) next[field.id] = seconds;
      return next;
    });
  };

  /** Persist one frontend-recorded value across every form timer field. */
  const handleEditTimerStopped = async (_fieldId: string, elapsedSeconds: number) => {
    if (!editingEntity) return;
    const timerData = Object.fromEntries(
      editTimerFields.map((field) => [field.id, elapsedSeconds]),
    );
    try {
      await workflowEntities.update(editingEntity.entity_id, {
        data: timerData,
      });
      applyTimerValue(editTimerFields, setEditFormData, elapsedSeconds);
      patchEntity(editingEntity.entity_id, timerData);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Timer could not be saved';
      setEditError(message);
      throw new Error(message);
    }
  };

  // Viewable fields across every attached form — hidden fields must not block submit.
  const visibleCreateFormFields = useMemo(
    () => createSchemas.flatMap((s) => filterVisibleFields(s.entity_type, getEnterableFields(s))),
    [createSchemas, filterVisibleFields],
  );

  // A timer measures filling the record in, so it cannot stop until every
  // required field across every attached form has a value.
  const createTimerCanStop = useMemo(
    () =>
      visibleCreateFormFields.every(
        (f) => f.type === 'timer_duration' || !isMissingRequiredFieldValue(f, formData[f.id]),
      ),
    [visibleCreateFormFields, formData],
  );
  const editTimerCanStop = useMemo(
    () =>
      editSchemas
        .flatMap((schema) => getEnterableFields(schema))
        .every(
          (f) => f.type === 'timer_duration' || !isMissingRequiredFieldValue(f, editFormData[f.id]),
        ),
    [editSchemas, editFormData],
  );


  const isCreateFormInvalid = useMemo(() => {
    if (visibleCreateFormFields.some((f) => isMissingRequiredFieldValue(f, formData[f.id]))) return true;
    if (visibleCreateFormFields.some((f) => validateFieldValue(f, formData[f.id]))) return true;
    return false;
  }, [visibleCreateFormFields, formData]);

  // The create_entity tool has no notion of workflows, so an agent-created entity
  // comes back unenrolled — enroll it into the selected workflow ourselves, matching
  // what a manual Create does. Unlike a manual Create, an untouched dropdown here
  // defaults to this entity type's first published workflow rather than "no workflow"
  // — a doc-upload create has no explicit "create without workflow" intent behind it,
  // so leaving it unenrolled would make the entity permanently invisible on any
  // Pipeline board.
  const {
    entityId: uploadedEntityId,
    handleEntityCreated: handleEntityUploaded,
    reset: resetUploadedEntityId,
  } = useDocumentUploadEntity({
    resolveMachineName: () => {
      const machineName = selectedMachineName ?? publishedPageMachines[0]?.machine_name;
      // Reflect an auto-picked fallback into the dropdown too, so it doesn't keep
      // showing "Create without workflow" while the entity is actually enrolled.
      if (machineName && !selectedMachineName) setSelectedMachineName(machineName);
      return machineName;
    },
    setFormData,
    setError: setModalError,
    describeEnrollError: (message) =>
      `Entity created, but could not be added to the selected workflow: ${message}`,
  });

  const openModal = () => {
    setSelectedMachineName(null);
    setSelectedSchema(entityTypeMethodSchemas[0] ?? null);
    setFormData(buildDefaultFormDataForSchemas(entityTypeMethodSchemas));
    setModalError(null);
    createTimer.reset();
    resetUploadedEntityId();
    void sourceLinks.load(routeEntityType);
    setShowModal(true);
  };

  useEffect(() => {
    if (!showModal) return;
    setSelectedSchema((current) =>
      createSchemas.find((schema) => schema.schema_key === current?.schema_key)
      ?? createSchemas[0]
      ?? null,
    );
    setFormData((current) => ({
      ...buildDefaultFormDataForSchemas(createSchemas),
      ...pickEnterableData(createSchemas, current),
    }));
  }, [createSchemas, showModal]);

  const resetCreateModal = () => {
    setShowModal(false);
    setSelectedMachineName(null);
    setModalError(null);
    createTimer.reset();
    resetUploadedEntityId();
    sourceLinks.reset();
  };

  const handleCloseCreateModal = () => {
    // Only upload-created records exist before Create is pressed. Save the
    // frontend-owned run on that entity before the modal closes.
    if (!uploadedEntityId || createTimerFields.length === 0) {
      resetCreateModal();
      return;
    }
    void (async () => {
      const primaryTimerField = createTimerFields[0];
      const storedSeconds = formData[primaryTimerField.id];
      const baseSeconds =
        typeof storedSeconds === 'number'
          ? Math.max(0, Math.floor(storedSeconds))
          : 0;
      if (createTimer.startedAt === null && typeof storedSeconds !== 'number') {
        resetCreateModal();
        return;
      }
      const elapsedSeconds =
        createTimer.startedAt === null
          ? baseSeconds
          : createTimer.recordedSeconds(baseSeconds);
      const completedTimerData = Object.fromEntries(
        createTimerFields.map((field) => [field.id, elapsedSeconds]),
      );
      try {
        setCreating(true);
        setModalError(null);
        await workflowEntities.update(uploadedEntityId, { data: completedTimerData });
        patchEntity(uploadedEntityId, completedTimerData);
        resetCreateModal();
      } catch (e) {
        setModalError(e instanceof Error ? e.message : 'Failed to save timer before closing');
      } finally {
        setCreating(false);
      }
    })();
  };

  const closeEditModal = () => {
    setEditingEntity(null);
    setEditingSchema(null);
    setEditFormData({});
    setEditError(null);
  };

  /** Finalize a frontend-owned timer through the ordinary entity update path. */
  const completeActiveEditTimer = async (): Promise<Record<string, number>> => {
    const primaryTimerField = editTimerFields[0];
    if (!editingEntity || !primaryTimerField || editTimer.startedAt === null) return {};

    const baseSeconds =
      typeof editFormData[primaryTimerField.id] === 'number'
        ? Number(editFormData[primaryTimerField.id])
        : 0;
    const recorded = editTimer.recordedSeconds(baseSeconds);
    const completedTimerData = Object.fromEntries(
      editTimerFields.map((field) => [field.id, recorded]),
    );
    await workflowEntities.update(editingEntity.entity_id, { data: completedTimerData });
    applyTimerValue(editTimerFields, setEditFormData, recorded);
    editTimer.reset();
    return completedTimerData;
  };

  const handleCloseEditModal = () => {
    if (!editingEntity || !editTimerFields[0]) {
      closeEditModal();
      return;
    }
    void (async () => {
      try {
        setSavingEdit(true);
        setEditError(null);
        const completedTimerData = await completeActiveEditTimer();
        patchEntity(editingEntity.entity_id, completedTimerData);
        closeEditModal();
      } catch (e) {
        setEditError(e instanceof Error ? e.message : 'Failed to stop timer before closing');
      } finally {
        setSavingEdit(false);
      }
    })();
  };

  const editingEntityIndex = editingEntity
    ? filtered.findIndex((entity) => entity.entity_id === editingEntity.entity_id)
    : -1;
  const editIsDirty = Boolean(
    editingEntity &&
      isEntityEditDirty(editFormData, editingEntity.data),
  );

  const navigateEditModal = (offset: -1 | 1) => {
    const target = filtered[editingEntityIndex + offset];
    if (!target || editingEntityLoading || savingEdit) return;
    if (
      editIsDirty &&
      !confirm('Discard your unsaved changes and open another entity?')
    ) {
      return;
    }
    void (async () => {
      const currentEntity = editingEntity;
      try {
        setSavingEdit(true);
        setEditError(null);
        // Iterator navigation ends the current form session just like the
        // modal X does. Stop its timer before replacing the record.
        const completedTimerData = await completeActiveEditTimer();
        if (currentEntity && Object.keys(completedTimerData).length > 0) {
          patchEntity(currentEntity.entity_id, completedTimerData);
        }
        await openEditModal(target);
      } catch (e) {
        setEditError(e instanceof Error ? e.message : 'Failed to stop timer before changing record');
      } finally {
        setSavingEdit(false);
      }
    })();
  };

  const validateCreateForm = (): {
    error: string;
    ownerSchema: FormSchema | null;
    clearSelectedWorkflow?: boolean;
  } | null => {
    if (!selectedMachineName && entityTypeMethodsLoading) {
      return { error: 'Methods are still loading. Please wait a moment and try again.', ownerSchema: null };
    }
    if (
      selectedMachineName !== null &&
      !publishedPageMachines.some((m) => m.machine_name === selectedMachineName)
    ) {
      return {
        error: 'The selected workflow is no longer available. Please select again.',
        ownerSchema: null,
        clearSelectedWorkflow: true,
      };
    }
    if (sourceLinks.missingRequired) {
      return {
        error: `Link a ${sourceLinks.missingRequired.providerName} record before creating`,
        ownerSchema: null,
      };
    }
    if (!templateMode && !String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim()) {
      return { error: identifierRequiredMessage, ownerSchema: createSchemas[0] ?? null };
    }
    const missingField = visibleCreateFormFields.find((f) =>
      isMissingRequiredFieldValue(f, formData[f.id]),
    );
    if (missingField) {
      const owner = createSchemas.find((s) => getFormFields(s).some((f) => f.id === missingField.id));
      return { error: `"${missingField.label}" is required`, ownerSchema: owner ?? null };
    }
    const invalidField = visibleCreateFormFields.find((f) => validateFieldValue(f, formData[f.id]));
    if (invalidField) {
      const owner = createSchemas.find((s) => getFormFields(s).some((f) => f.id === invalidField.id));
      return {
        error: validateFieldValue(invalidField, formData[invalidField.id]) ?? 'Invalid field value',
        ownerSchema: owner ?? null,
      };
    }
    return null;
  };

  const handleCreate = async () => {
    const validation = validateCreateForm();
    if (validation) {
      if (validation.clearSelectedWorkflow) setSelectedMachineName(null);
      if (validation.ownerSchema) setSelectedSchema(validation.ownerSchema);
      setModalError(validation.error);
      return;
    }

    try {
      setCreating(true);
      setModalError(null);
      const editableData = filterEditablePayload(
        routeEntityType,
        pickEnterableData(createSchemas, computedFormData),
      );
      if (templateMode) delete editableData[IDENTIFIER_FIELD_KEY];
      // Before an entity exists its timer only lives in this modal. Saving the
      // form records its final cumulative value with the new entity.
      const primaryTimerField = createTimerFields[0];
      const baseSeconds =
        primaryTimerField && typeof formData[primaryTimerField.id] === 'number'
          ? Number(formData[primaryTimerField.id])
          : 0;
      const recordedTimerSeconds =
        createTimer.startedAt !== null
          ? createTimer.recordedSeconds(baseSeconds)
          : primaryTimerField && typeof formData[primaryTimerField.id] === 'number'
            ? baseSeconds
            : null;
      const timerData =
        recordedTimerSeconds === null
          ? {}
          : Object.fromEntries(createTimerFields.map((field) => [field.id, recordedTimerSeconds]));

      // Merge identifier explicitly so the permission filter can't strip it — skipped
      // entirely in templateMode, where this entity type has no identifier field.
      const payloadData = {
        ...editableData,
        ...timerData,
        ...(!templateMode
          ? { [IDENTIFIER_FIELD_KEY]: String(formData[IDENTIFIER_FIELD_KEY] ?? '').trim() }
          : {}),
      };
      const created = uploadedEntityId
        ? // The agent already created this entity from an uploaded document —
          // update it instead of creating a second one. Same schema_fields/
          // source_entity_ids as the create branch below, so a schema-shape edit or a
          // source link picked along the way isn't lost.
          await workflowEntities.update(uploadedEntityId, {
            data: payloadData,
            schema_fields: buildCompleteSchemaFieldsForSchemas(createSchemas),
            ...(sourceLinks.sourceEntityIds.length
              ? { source_entity_ids: sourceLinks.sourceEntityIds }
              : {}),
          })
        : await workflowEntities.create({
            entity_type: routeEntityType,
            ...(selectedMachineName ? { machine_name: selectedMachineName } : {}),
            data: payloadData,
            schema_fields: buildCompleteSchemaFieldsForSchemas(createSchemas),
          ...(sourceLinks.sourceEntityIds.length
            ? { source_entity_ids: sourceLinks.sourceEntityIds }
            : {}),
          });
      useEntityStore.getState().addEntity(created);
      resetCreateModal();
    } catch (e) {
      setModalError(e instanceof Error ? e.message : 'Failed to create entity');
    } finally {
      setCreating(false);
    }
  };

  const openEditModal = async (entity: WorkflowEntityState) => {
    setEditingEntityLoading(true);
    setEditError(null);
    try {
      const fullEntity = await workflowEntities.get(entity.entity_id);
      const record = { ...fullEntity, ...entity, data: fullEntity.data };
      setEditingEntity(record);
      setEditFormData({ ...fullEntity.data });
      const workflow = workflowForEntity(record);
      const stateSchemas = methodSchemasForWorkflowState(
        workflow,
        record.entity_type,
        record.current_state,
      );
      setEditingSchema(stateSchemas[0] ?? entityTypeMethodSchemas[0] ?? null);
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Failed to load entity');
      return;
    } finally {
      setEditingEntityLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingEntity) return;
    if (!templateMode && !String(editFormData[IDENTIFIER_FIELD_KEY] ?? '').trim()) {
      setEditingSchema(editSchemas[0] ?? null);
      setEditError(identifierRequiredMessage);
      return;
    }
    // Validate editable, non-masked fields across every attached form; switch to
    // the tab that owns an offending field so the error shows in context.
    const editableFields = editSchemas
      .flatMap((s) => getEnterableFields(s))
      .filter(
        (f) =>
          canEditField(editingEntity.entity_type, f.id) &&
          !shouldMaskField(editingEntity.entity_type, f.id),
      );
    const missingField = editableFields.find((f) => f.required && !editFormData[f.id]);
    if (missingField) {
      const owner = editSchemas.find((s) => getFormFields(s).some((f) => f.id === missingField.id));
      if (owner) setEditingSchema(owner);
      setEditError(`"${missingField.label}" is required`);
      return;
    }
    const invalidField = editableFields.find((f) => validateFieldValue(f, editFormData[f.id]));
    if (invalidField) {
      const owner = editSchemas.find((s) => getFormFields(s).some((f) => f.id === invalidField.id));
      if (owner) setEditingSchema(owner);
      setEditError(validateFieldValue(invalidField, editFormData[invalidField.id]));
      return;
    }
    try {
      setSavingEdit(true);
      setEditError(null);
      // editFormData is seeded from entity.data, which carries backend-overlaid
      // inherited values — send only enterable field values (plus identifier).
      const enterableData = pickEnterableData(editSchemas, computedEditFormData);
      if (templateMode) delete enterableData[IDENTIFIER_FIELD_KEY];
      const primaryTimerField = editTimerFields[0];
      const baseSeconds =
        primaryTimerField && typeof editFormData[primaryTimerField.id] === 'number'
          ? Number(editFormData[primaryTimerField.id])
          : 0;
      const completedTimerData =
        primaryTimerField && editTimer.isActive
          ? Object.fromEntries(
              editTimerFields.map((field) => [field.id, editTimer.recordedSeconds(baseSeconds)]),
            )
          : {};
      await workflowEntities.update(editingEntity.entity_id, {
        data: {
          ...filterEditablePayload(editingEntity.entity_type, enterableData),
          ...completedTimerData,
        },
        schema_fields: buildCompleteSchemaFieldsForSchemas(editSchemas),
      });
      if (editTimer.isActive) editTimer.reset();
      patchEntity(editingEntity.entity_id, { ...computedEditFormData, ...completedTimerData });
      closeEditModal();
    } catch (e) {
      setEditError(e instanceof Error ? e.message : 'Failed to update entity');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeleteEntity = async (entity: WorkflowEntityState) => {
    if (!confirm(`Delete entity "${deriveEntityDisplayName(entity, schemaForEntity(entity))}"?`))
      return;
    try {
      setDeletingEntityId(entity.entity_id);
      await deleteEntity(entity.entity_id);
    } catch (e) {
      useEntityStore.setState({
        error: e instanceof Error ? e.message : 'Failed to delete entity',
      });
    } finally {
      setDeletingEntityId(null);
    }
  };

  if (loading || (editingEntityLoading && !editingEntity)) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  if (!loading && !canView) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <AccessDenied entityType={routeEntityType} />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <DetailHeader
        routeEntityType={routeEntityType}
        entityTypeLabel={routeEntityTypeDefinition?.display_name || routeEntityTypeDefinition?.name}
        recordCount={filtered.length}
        canCreate={!schemasError && canCreate}
        onCreate={openModal}
        onBulkImport={
          bulkImportEnabled && routeEntityTypeDefinition
            ? () => navigate(`/bulk-import?entityType=${encodeURIComponent(routeEntityTypeDefinition.name)}`)
            : undefined
        }
      />

      {error && <ErrorBanner message={error} onDismiss={clearError} />}
      {schemasError && (
        <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive-subtle p-4 text-sm text-destructive">
          Form configuration could not be loaded. Creating and editing are disabled until the page
          is refreshed.
        </div>
      )}
      {editError && !editingEntity && (
        <ErrorBanner message={editError} onDismiss={() => setEditError(null)} />
      )}

      <DetailFilters
        search={search}
        onSearchChange={setSearch}
        routeEntityType={routeEntityType}
        filterType={filterType}
        onFilterTypeChange={setFilterType}
        entityTypes={entityTypes}
      />

      {filtered.length === 0 ? (
        <EmptyState
          routeEntityType={routeEntityType}
          hasMachines={pageMachines.length > 0}
          hasSchemas={createSchemas.length > 0}
          onCreate={openModal}
        />
      ) : (
        <EntityTable
          entities={filtered}
          columnScope={routeEntityType || filterType || 'all'}
          schemaForEntity={schemaForEntity}
          deletingEntityId={deletingEntityId}
          onEdit={openEditModal}
          onDelete={handleDeleteEntity}
          canEdit={!schemasError && canEdit}
          canDelete={canDelete}
          canView={canView}
        />
      )}

      {showModal && (
        <CreateEntityModal
          timerSlot={renderTimerStrip(createTimerFields, formData, createTimer, {
            canStop: createTimerCanStop,
            stopHint: 'Fill in every required field, across all forms, before stopping the timer.',
            onChange: (seconds) => applyTimerValue(createTimerFields, setFormData, seconds),
          })}
          fieldsLocked={createTimerRequiresStart && (!createTimer.isActive || createTimer.isPaused)}
          fieldsLockedHint={createTimer.isPaused
            ? `${createTimerFields[0]?.label ?? 'The timer'} is paused. Resume it to carry on filling this form in.`
            : `Start ${createTimerFields[0]?.label ?? 'the timer'} to fill this form.`}
          routeEntityType={routeEntityType}
          publishedWorkflows={publishedPageMachines}
          workflowsLoading={machinesLoading}
          machinesError={machinesError}
          selectedMachineName={selectedMachineName}
          onWorkflowChange={setSelectedMachineName}
          schema={selectedSchema}
          schemas={createSchemas}
          noWorkflowForms={Boolean(selectedMachineName) && !entityTypeMethodsLoading && createSchemas.length === 0}
          onSelectTab={(s) => {
            setSelectedSchema(s);
            setModalError(null);
          }}
          formFields={formFields}
          formData={computedFormData}
          onFieldChange={(id, value) => setFormData((prev) => ({ ...prev, [id]: value }))}
          sourcePickers={sourceLinks.pickers}
          sourceSelections={sourceLinks.selections}
          onSourceChange={sourceLinks.setSelection}
          error={modalError ?? (!selectedMachineName ? entityTypeMethodsError : null)}
          creating={creating}
          isFormInvalid={isCreateFormInvalid}
          onClose={handleCloseCreateModal}
          onSubmit={handleCreate}
          uploadedEntityId={uploadedEntityId}
          onEntityUploaded={handleEntityUploaded}
        />
      )}

      {editingEntity && (
        <EditEntityModal
          timerSlot={renderTimerStrip(editTimerFields, computedEditFormData, editTimer, {
            entityId: editingEntity.entity_id,
            canStop: editTimerCanStop,
            stopHint: 'Fill in every required field, across all forms, before stopping the timer.',
            onStopped: handleEditTimerStopped,
          })}
          fieldsLocked={editTimerRequiresStart && (!editTimer.isActive || editTimer.isPaused)}
          fieldsLockedHint={editTimer.isPaused
            ? `${editTimerFields[0]?.label ?? 'The timer'} is paused. Resume it to carry on editing.`
            : `Start ${editTimerFields[0]?.label ?? 'the timer'} to edit this record.`}
          entity={editingEntity}
          schema={editingSchema}
          schemas={editSchemas}
          onSelectTab={(s) => {
            setEditingSchema(s);
            setEditError(null);
          }}
          fields={editFormFields}
          values={computedEditFormData}
          onFieldChange={(id, value) => setEditFormData((prev) => ({ ...prev, [id]: value }))}
          error={editError}
          saving={savingEdit}
          onClose={handleCloseEditModal}
          onSubmit={handleSaveEdit}
          readOnly={!canEdit || Boolean(schemasError)}
          identifierLabel={identifierLabel}
          identifierReadOnly={templateMode}
          loading={editingEntityLoading}
          iterator={
            editingEntityIndex >= 0
              ? {
                  current: editingEntityIndex + 1,
                  total: filtered.length,
                  onPrevious: () => navigateEditModal(-1),
                  onNext: () => navigateEditModal(1),
                }
              : undefined
          }
        />
      )}
    </div>
  );
}
