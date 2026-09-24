import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  Link2,
  Loader2,
  Pencil,
  Plus,
} from 'lucide-react';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/core/components/ConfirmDialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { entityRelations, entityTypes, schedules } from '@/core/services/api';
import type {
  EntitySchedule,
  ScheduleConditionOperator,
  ScheduleRunPreview,
} from '@/core/services/api/schedules';
import type { EntityType, FieldDefinition, RelationDeclaration } from '@/core/types';
import {
  isBooleanScheduleField,
  isNumericScheduleField,
  parseScheduleConditionValue,
} from './scheduleConditionValue';
import { AutomationHeader, AutomationSurface } from './AutomationSurface';
import { AutomationActions } from './AutomationActions';

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  machineName?: string;
  workflowEntityType?: string;
  workflowLabels?: Record<string, string>;
  embedded?: boolean;
}

type AnchorRecord = { entity_id: string; data: Record<string, unknown> };

const fieldClass = 'h-10 w-full rounded-lg border border-border bg-background px-3 text-sm';
const typeId = (type: EntityType) => type.entity_type_id ?? type.id;
const typeLabel = (type?: EntityType) => type?.display_name || type?.name || 'Related entity';
const humanizeField = (value: string) =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
const localToday = () => {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
};
const TIMEZONES = (() => {
  const intlWithSupportedValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: 'timeZone') => string[];
  };
  const values = intlWithSupportedValues.supportedValuesOf?.('timeZone') ?? [];
  return [...new Set(['UTC', ...values])].sort();
})();

function recordLabel(record: AnchorRecord): string {
  for (const key of ['identifier', 'name', 'client_name', 'customer_name', 'supplier_name', 'title']) {
    const value = record.data[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  const firstText = Object.values(record.data).find(
    (value) => typeof value === 'string' && value.trim(),
  );
  return typeof firstText === 'string' ? firstText : record.entity_id.slice(0, 8);
}

const operatorLabels: Record<ScheduleConditionOperator, string> = {
  equals: 'is',
  not_equals: 'is not',
  in: 'is one of',
  not_in: 'is not one of',
  exists: 'has a value',
  not_exists: 'is empty',
};

export default function SchedulesPanel({
  open = false,
  onOpenChange = () => undefined,
  machineName,
  workflowEntityType,
  workflowLabels = {},
  embedded = false,
}: Props) {
  const [items, setItems] = useState<EntitySchedule[]>([]);
  const [types, setTypes] = useState<EntityType[]>([]);
  const [relations, setRelations] = useState<RelationDeclaration[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<EntitySchedule | null>(null);
  const [creating, setCreating] = useState(false);
  const [runPreviewLoadingId, setRunPreviewLoadingId] = useState<string | null>(null);
  const [runConfirmation, setRunConfirmation] = useState<{
    schedule: EntitySchedule;
    preview: ScheduleRunPreview;
  } | null>(null);
  const [runningNow, setRunningNow] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState<EntitySchedule | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [name, setName] = useState('');
  const [frequency, setFrequency] = useState<'once' | 'monthly' | 'quarterly' | 'annual'>('monthly');
  const [occursOn, setOccursOn] = useState(localToday);
  const [day, setDay] = useState(1);
  const [months, setMonths] = useState('3,6,9,12');
  const [leadDays, setLeadDays] = useState(30);
  const [occurrencesPerBatch, setOccurrencesPerBatch] = useState(1);
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  );
  const [relationDefId, setRelationDefId] = useState('');
  const [anchorRecords, setAnchorRecords] = useState<AnchorRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordSearch, setRecordSearch] = useState('');
  const [selectedAnchors, setSelectedAnchors] = useState<string[]>([]);
  const [conditionEnabled, setConditionEnabled] = useState(false);
  const [conditionField, setConditionField] = useState('');
  const [conditionOperator, setConditionOperator] =
    useState<ScheduleConditionOperator>('equals');
  const [conditionValue, setConditionValue] = useState('');

  const targetType = useMemo(
    () =>
      workflowEntityType
        ? types.find((type) => type.name.toLowerCase() === workflowEntityType.toLowerCase())
        : undefined,
    [types, workflowEntityType],
  );
  const selectedRelation = useMemo(
    () => relations.find((relation) => relation.relation_def_id === relationDefId),
    [relationDefId, relations],
  );
  const anchorType = useMemo(
    () => types.find((type) => typeId(type) === selectedRelation?.from_entity_type_id),
    [selectedRelation, types],
  );
  const anchorFields = useMemo<FieldDefinition[]>(() => {
    const byName = new Map(
      (anchorType?.schema?.fields ?? []).map((field) => [field.name, field]),
    );
    for (const record of anchorRecords) {
      for (const [fieldName, value] of Object.entries(record.data)) {
        if (!byName.has(fieldName)) {
          byName.set(fieldName, {
            name: fieldName,
            type: typeof value,
            description: humanizeField(fieldName),
          });
        }
      }
    }
    const fields = [...byName.values()];
    if (!fields.some((field) => field.name === 'identifier')) {
      fields.unshift({ name: 'identifier', type: 'string', description: 'Record name' });
    }
    return fields;
  }, [anchorRecords, anchorType]);
  const conditionValueSuggestions = useMemo(
    () =>
      [...new Set(anchorRecords.map((record) => record.data[conditionField]))]
        .filter((value): value is string | number | boolean =>
          ['string', 'number', 'boolean'].includes(typeof value),
        )
        .map(String)
        .filter(Boolean)
        .sort(),
    [anchorRecords, conditionField],
  );
  const conditionFieldDefinition = useMemo(
    () => anchorFields.find((field) => field.name === conditionField),
    [anchorFields, conditionField],
  );
  const filteredRecords = useMemo(() => {
    const search = recordSearch.trim().toLowerCase();
    if (!search) return anchorRecords;
    return anchorRecords.filter((record) => recordLabel(record).toLowerCase().includes(search));
  }, [anchorRecords, recordSearch]);

  const load = useCallback(async () => {
    if (!open && !embedded) return;
    setLoading(true);
    try {
      const scheduleResponse = await schedules.list(machineName);
      setItems(scheduleResponse.items);
    } catch (error) {
      setItems([]);
      toast.error(error instanceof Error ? error.message : 'Could not load schedules');
    }

    if (machineName && workflowEntityType) {
      try {
        const [typeResponse, workflowType] = await Promise.all([
          entityTypes.list({ limit: 100 }),
          entityTypes.get(workflowEntityType),
        ]);
        setTypes(
          typeResponse.items.some((type) => typeId(type) === typeId(workflowType))
            ? typeResponse.items
            : [...typeResponse.items, workflowType],
        );
        const relationResponse = await entityRelations.listDeclarations(typeId(workflowType), 'to');
        setRelations(relationResponse.items ?? []);
      } catch (error) {
        setRelations([]);
        toast.error(error instanceof Error ? error.message : 'Could not load related entity types');
      }
    } else {
      setTypes([]);
      setRelations([]);
      setShowCreate(false);
    }
    setLoading(false);
  }, [embedded, machineName, open, workflowEntityType]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!anchorType) {
      setAnchorRecords([]);
      setSelectedAnchors([]);
      return;
    }
    setRecordsLoading(true);
    setRecordSearch('');
    entityRelations
      .listRecordsOfType(anchorType.name, '', 100)
      .then((response) => {
        setAnchorRecords(response.items ?? []);
        setSelectedAnchors([]);
      })
      .catch((error) => {
        setAnchorRecords([]);
        toast.error(error instanceof Error ? error.message : 'Could not load related records');
      })
      .finally(() => setRecordsLoading(false));
  }, [anchorType]);

  useEffect(() => {
    if (!anchorFields.some((field) => field.name === conditionField)) {
      setConditionField(anchorFields[0]?.name ?? '');
    }
  }, [anchorFields, conditionField]);

  const resetForm = () => {
    setShowCreate(false);
    setEditingSchedule(null);
    setName('');
    setFrequency('monthly');
    setOccursOn(localToday());
    setDay(1);
    setOccurrencesPerBatch(1);
    setMonths('3,6,9,12');
    setRelationDefId('');
    setSelectedAnchors([]);
    setConditionEnabled(false);
    setConditionField('');
    setConditionOperator('equals');
    setConditionValue('');
  };

  const editSchedule = (schedule: EntitySchedule) => {
    setEditingSchedule(schedule);
    setShowCreate(true);
    setName(schedule.name);
    setFrequency(schedule.recurrence.frequency);
    setOccursOn(schedule.recurrence.occurs_on ?? localToday());
    setDay(schedule.recurrence.day_of_month ?? 1);
    setMonths(schedule.recurrence.months.join(','));
    setLeadDays(schedule.lead_days);
    setOccurrencesPerBatch(schedule.occurrences_per_batch);
    setTimezone(schedule.timezone);
  };

  const changeFrequency = (value: 'once' | 'monthly' | 'quarterly' | 'annual') => {
    setFrequency(value);
    if (value === 'once') setOccurrencesPerBatch(1);
    if (value === 'quarterly') setMonths('3,6,9,12');
    if (value === 'annual') setMonths('12');
  };

  const createSchedule = async () => {
    if (!name.trim()) {
      toast.error('Give this automation a name');
      return;
    }
    if (!Number.isInteger(occurrencesPerBatch) || occurrencesPerBatch < 1 || occurrencesPerBatch > 24) {
      toast.error('Occurrences per batch must be between 1 and 24');
      return;
    }
    if (frequency === 'once' && !occursOn) {
      toast.error('Choose the date for this one-time automation');
      return;
    }
    if (
      !editingSchedule &&
      conditionEnabled &&
      !['exists', 'not_exists'].includes(conditionOperator) &&
      !conditionValue.trim()
    ) {
      toast.error('Enter the value the condition should compare against');
      return;
    }

    const parsedMonths =
      frequency === 'monthly'
        ? []
        : [...new Set(months.split(',').map((value) => Number(value.trim())))].filter(
            (value) => Number.isInteger(value) && value >= 1 && value <= 12,
          );
    if (frequency === 'quarterly' && parsedMonths.length !== 4) {
      toast.error('Quarterly schedules need exactly four month numbers, for example 3, 6, 9, 12');
      return;
    }
    if (frequency === 'annual' && parsedMonths.length !== 1) {
      toast.error('Annual schedules need exactly one month number, for example 12');
      return;
    }

    const recurrence =
      frequency === 'once'
        ? { frequency, months: [], occurs_on: occursOn }
        : { frequency, day_of_month: day, months: parsedMonths };

    if (editingSchedule) {
      setCreating(true);
      try {
        await schedules.update(editingSchedule.schedule_id, {
          name: name.trim(),
          recurrence,
          occurrences_per_batch: frequency === 'once' ? 1 : occurrencesPerBatch,
          lead_days: leadDays,
          timezone,
        });
        toast.success('Automation updated');
        resetForm();
        await load();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Could not update automation');
      } finally {
        setCreating(false);
      }
      return;
    }

    if (!machineName || !workflowEntityType) {
      toast.error('Select a workflow before creating an automation');
      return;
    }
    if (!selectedRelation || !anchorType) {
      toast.error('Choose which related entity type this schedule applies to');
      return;
    }
    if (conditionEnabled && !conditionField) {
      toast.error('Choose a field for the condition');
      return;
    }

    const needsConditionValue = !['exists', 'not_exists'].includes(conditionOperator);
    let typedConditionValue: string | number | boolean | undefined;
    if (conditionEnabled && needsConditionValue) {
      try {
        typedConditionValue = parseScheduleConditionValue(
          conditionFieldDefinition?.type,
          conditionValue,
        );
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Enter a valid condition value');
        return;
      }
    }

    setCreating(true);
    try {
      await schedules.create({
        machine_name: machineName,
        name: name.trim(),
        anchor_entity_type_id: typeId(anchorType),
        relation_def_id: selectedRelation.relation_def_id,
        target_scope: selectedAnchors.length > 0 ? 'selected' : 'all',
        recurrence,
        occurrences_per_batch: frequency === 'once' ? 1 : occurrencesPerBatch,
        lead_days: leadDays,
        timezone,
        conditions: conditionEnabled
          ? [
              {
                field: conditionField,
                operator: conditionOperator,
                ...(needsConditionValue ? { value: typedConditionValue } : {}),
              },
            ]
          : [],
        anchor_entity_ids: selectedAnchors,
      });
      toast.success('Automation created');
      resetForm();
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not create schedule');
    } finally {
      setCreating(false);
    }
  };

  const conditionFieldLabel =
    anchorFields.find((field) => field.name === conditionField)?.description || conditionField;
  const conditionSummary = conditionEnabled
    ? `${conditionFieldLabel} ${operatorLabels[conditionOperator]}${
        ['exists', 'not_exists'].includes(conditionOperator) ? '' : ` “${conditionValue || '…'}”`
      }`
    : `Every subscribed ${typeLabel(anchorType)} record`;

  const requestRunNow = async (schedule: EntitySchedule) => {
    setRunPreviewLoadingId(schedule.schedule_id);
    try {
      const preview = await schedules.previewRunNow(schedule.schedule_id);
      if (preview.eligible === 0) {
        toast.info(
          preview.skipped > 0
            ? `Nothing will be created. ${preview.skipped} related record(s) were skipped.`
            : 'This schedule has no related records to run.',
        );
        return;
      }
      setRunConfirmation({ schedule, preview });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not preview this run');
    } finally {
      setRunPreviewLoadingId(null);
    }
  };

  const confirmRunNow = async () => {
    if (!runConfirmation) return;
    setRunningNow(true);
    try {
      const result = await schedules.runNow(
        runConfirmation.schedule.schedule_id,
        runConfirmation.preview.invocation_id,
      );
      toast.success(
        `${result.queued} creation job${result.queued === 1 ? '' : 's'} queued${
          result.skipped ? `; ${result.skipped} skipped` : ''
        }`,
      );
      setRunConfirmation(null);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not run this schedule');
    } finally {
      setRunningNow(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteConfirmation) return;
    setDeleting(true);
    try {
      await schedules.delete(deleteConfirmation.schedule_id);
      toast.success('Schedule deleted');
      setDeleteConfirmation(null);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete schedule');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AutomationSurface embedded={embedded} open={open} onOpenChange={onOpenChange}>
        <AutomationHeader
          embedded={embedded}
          description={
            workflowEntityType
              ? `Create one-time or recurring ${targetType?.display_name || workflowEntityType} records and place them in this workflow automatically.`
              : 'View one-time and recurring entity-creation automations across all workflows.'
          }
        />

        <div className="space-y-5 px-5 pb-8">
          {loading ? (
            <Loader2 className="mx-auto mt-8 h-5 w-5 animate-spin" />
          ) : showCreate ? (
            <div className="space-y-6">
              <Button variant="ghost" size="md" onClick={resetForm} className="-ml-2 gap-2">
                <ArrowLeft className="h-4 w-4" /> Back to automations
              </Button>

              <section className="space-y-4 rounded-xl border border-border p-4">
                <div>
                  <p className="font-medium">
                    {editingSchedule ? 'Edit name and timing' : '1. Name and timing'}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Choose when records are due and how early they should appear.
                  </p>
                </div>
                <div>
                  <Label>Automation name</Label>
                  <Input
                    className="mt-1"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Annual supplier validation"
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label>Timing</Label>
                    <select
                      className={`${fieldClass} mt-1`}
                      value={frequency}
                      onChange={(event) =>
                        changeFrequency(event.target.value as typeof frequency)
                      }
                    >
                      <option value="monthly">Every month</option>
                      <option value="quarterly">Every quarter</option>
                      <option value="annual">Every year</option>
                      <option value="once">Once</option>
                    </select>
                  </div>
                  {frequency === 'once' ? (
                    <div>
                      <Label>Due date</Label>
                      <Input
                        className="mt-1"
                        type="date"
                        min={localToday()}
                        value={occursOn}
                        onChange={(event) => setOccursOn(event.target.value)}
                      />
                    </div>
                  ) : (
                    <div>
                      <Label>Due on day</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        min={1}
                        max={31}
                        value={day}
                        onChange={(event) => setDay(Number(event.target.value))}
                      />
                    </div>
                  )}
                  {frequency !== 'monthly' && frequency !== 'once' && (
                    <div className="sm:col-span-2">
                      <Label>{frequency === 'quarterly' ? 'Due months' : 'Due month'}</Label>
                      <Input
                        className="mt-1"
                        value={months}
                        onChange={(event) => setMonths(event.target.value)}
                        placeholder={frequency === 'quarterly' ? '3, 6, 9, 12' : '12'}
                      />
                      <p className="mt-1 text-xs text-muted-foreground">
                        Use month numbers: January is 1 and December is 12.
                      </p>
                    </div>
                  )}
                  <div>
                    <Label>Show work this many days early</Label>
                    <Input
                      className="mt-1"
                      type="number"
                      min={0}
                      value={leadDays}
                      onChange={(event) => setLeadDays(Number(event.target.value))}
                    />
                  </div>
                  {frequency !== 'once' && (
                    <div>
                      <Label>Occurrences per batch</Label>
                      <Input
                        className="mt-1"
                        type="number"
                        min={1}
                        max={24}
                        value={occurrencesPerBatch}
                        onChange={(event) => setOccurrencesPerBatch(Number(event.target.value))}
                      />
                      <p className="mt-1 text-xs text-muted-foreground">
                        For example, choose 3 to create three quarters at once.
                      </p>
                    </div>
                  )}
                  <div>
                    <Label>Timezone</Label>
                    <Input
                      className="mt-1"
                      value={timezone}
                      onChange={(event) => setTimezone(event.target.value)}
                      list="schedule-timezones"
                      placeholder="Search timezones"
                    />
                    <datalist id="schedule-timezones">
                      {TIMEZONES.map((item) => (
                        <option key={item} value={item} />
                      ))}
                    </datalist>
                  </div>
                </div>
              </section>

              {editingSchedule && (
                <div className="rounded-lg border border-info/30 bg-info-subtle p-3 text-sm text-info">
                  Workflow, related-record scope, and conditions remain unchanged.
                </div>
              )}

              {!editingSchedule && <section className="space-y-4 rounded-xl border border-border p-4">
                <div>
                  <p className="font-medium">2. Choose related records</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    By default this runs for every active related record. Select specific records
                    below only when you want to restrict the schedule.
                  </p>
                </div>

                {relations.length === 0 ? (
                  <div className="rounded-lg border border-warning/30 bg-warning-subtle p-4 text-sm text-warning">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p className="font-medium">No related entity types are configured</p>
                        <p className="mt-1 leading-5">
                          In Settings → Entity Types, add a relationship from the customer, supplier,
                          or contract type to <strong>{targetType?.display_name || workflowEntityType}</strong>.
                          Return here and those records will be available for selection.
                        </p>
                        <Link
                          to="/settings?tab=entities"
                          onClick={() => onOpenChange(false)}
                          className="mt-3 inline-flex items-center gap-1 font-medium text-amber-950 underline underline-offset-2"
                        >
                          Open Entity Type settings
                        </Link>
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <Label>Related entity type</Label>
                      <select
                        className={`${fieldClass} mt-1`}
                        value={relationDefId}
                        onChange={(event) => setRelationDefId(event.target.value)}
                      >
                        <option value="">Select a configured relationship</option>
                        {relations.map((relation) => {
                          const sourceType = types.find(
                            (type) => typeId(type) === relation.from_entity_type_id,
                          );
                          return (
                            <option key={relation.relation_def_id} value={relation.relation_def_id}>
                              {typeLabel(sourceType)} → {typeLabel(targetType)}
                            </option>
                          );
                        })}
                      </select>
                    </div>

                    {anchorType && (
                      <div>
                        <div className="flex items-end justify-between gap-3">
                          <div>
                            <Label>Restrict to specific {typeLabel(anchorType)} records (optional)</Label>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {selectedAnchors.length} of {anchorRecords.length} selected
                            </p>
                          </div>
                          {anchorRecords.length > 0 && (
                            <Button
                              variant="link"
                              size="sm"
                              onClick={() =>
                                setSelectedAnchors(
                                  selectedAnchors.length === anchorRecords.length
                                    ? []
                                    : anchorRecords.map((record) => record.entity_id),
                                )
                              }
                            >
                              {selectedAnchors.length === anchorRecords.length
                                ? 'Clear all'
                                : 'Select all'}
                            </Button>
                          )}
                        </div>
                        {recordsLoading ? (
                          <Loader2 className="mx-auto my-6 h-4 w-4 animate-spin" />
                        ) : anchorRecords.length === 0 ? (
                          <p className="mt-2 rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
                            No {typeLabel(anchorType)} records exist yet. You can still create this
                            schedule; new records will be included automatically.
                          </p>
                        ) : (
                          <>
                            <Input
                              className="mt-2"
                              value={recordSearch}
                              onChange={(event) => setRecordSearch(event.target.value)}
                              placeholder={`Search ${typeLabel(anchorType)} records`}
                            />
                            <div className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border bg-background p-2">
                              {filteredRecords.map((record) => (
                                <label
                                  key={record.entity_id}
                                  className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-muted/60"
                                >
                                  <input
                                    type="checkbox"
                                    checked={selectedAnchors.includes(record.entity_id)}
                                    onChange={(event) =>
                                      setSelectedAnchors((current) =>
                                        event.target.checked
                                          ? [...current, record.entity_id]
                                          : current.filter((id) => id !== record.entity_id),
                                      )
                                    }
                                  />
                                  <span>{recordLabel(record)}</span>
                                </label>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </>
                )}
              </section>}

              {!editingSchedule && anchorType && (
                <section className="space-y-4 rounded-xl border border-border p-4">
                  <div>
                    <p className="font-medium">3. Add a condition (optional)</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      By default the automation runs for every record in its scope.
                    </p>
                  </div>
                  <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={conditionEnabled}
                      onChange={(event) => setConditionEnabled(event.target.checked)}
                    />
                    <span>
                      <span className="block text-sm font-medium">Only create when a rule matches</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        Example: only create monthly filings when Customer name is ABC.
                      </span>
                    </span>
                  </label>

                  {conditionEnabled && (
                    <div className="grid gap-3 rounded-lg bg-muted/30 p-3 sm:grid-cols-3">
                      <div>
                        <Label>Related record field</Label>
                        <select
                          className={`${fieldClass} mt-1`}
                          value={conditionField}
                          onChange={(event) => {
                            setConditionField(event.target.value);
                            setConditionValue('');
                          }}
                        >
                          {anchorFields.map((field) => (
                            <option key={field.name} value={field.name}>
                              {field.description || field.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <Label>Comparison</Label>
                        <select
                          className={`${fieldClass} mt-1`}
                          value={conditionOperator}
                          onChange={(event) =>
                            setConditionOperator(event.target.value as ScheduleConditionOperator)
                          }
                        >
                          <option value="equals">is</option>
                          <option value="not_equals">is not</option>
                          <option value="exists">has a value</option>
                          <option value="not_exists">is empty</option>
                        </select>
                      </div>
                      {!['exists', 'not_exists'].includes(conditionOperator) && (
                        <div>
                          <Label>Value</Label>
                          {isBooleanScheduleField(conditionFieldDefinition?.type) ? (
                            <select
                              className={`${fieldClass} mt-1`}
                              value={conditionValue}
                              onChange={(event) => setConditionValue(event.target.value)}
                            >
                              <option value="">Select true or false</option>
                              <option value="true">True</option>
                              <option value="false">False</option>
                            </select>
                          ) : (
                            <>
                              <Input
                                className="mt-1"
                                type={
                                  isNumericScheduleField(conditionFieldDefinition?.type)
                                    ? 'number'
                                    : 'text'
                                }
                                step={conditionFieldDefinition?.type === 'integer' ? 1 : undefined}
                                value={conditionValue}
                                onChange={(event) => setConditionValue(event.target.value)}
                                placeholder={
                                  isNumericScheduleField(conditionFieldDefinition?.type)
                                    ? '10'
                                    : 'ABC'
                                }
                                list="schedule-condition-values"
                              />
                              <datalist id="schedule-condition-values">
                                {conditionValueSuggestions.map((value) => (
                                  <option key={value} value={value} />
                                ))}
                              </datalist>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-start gap-2 rounded-lg border border-info/30 bg-info-subtle p-3 text-sm text-info">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      <strong>Rule preview:</strong> {conditionSummary}.
                    </span>
                  </div>
                </section>
              )}

              <div className="flex justify-end gap-2">
                <Button variant="outline" size="md" onClick={resetForm}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="md"
                  disabled={creating || (!editingSchedule && relations.length === 0)}
                  onClick={() => void createSchedule()}
                >
                  {creating ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : editingSchedule ? (
                    <Pencil className="mr-2 h-4 w-4" />
                  ) : (
                    <Plus className="mr-2 h-4 w-4" />
                  )}
                  {editingSchedule ? 'Save changes' : 'Create automation'}
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-medium">Automations</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {items.length} configured {machineName ? 'for this workflow' : 'across all workflows'}
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="md"
                  disabled={!machineName}
                  title={!machineName ? 'Select a workflow to create an automation' : undefined}
                  onClick={() => setShowCreate(true)}
                >
                  <Plus className="mr-2 h-4 w-4" /> New automation
                </Button>
              </div>

              {items.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border px-6 py-10 text-center">
                  <CalendarClock className="mx-auto h-8 w-8 text-muted-foreground" />
                  <p className="mt-3 font-medium">No automations yet</p>
                  <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
                    Add an automation to create one-time or recurring workflow records for customers,
                    suppliers, contracts, or other related entities.
                  </p>
                </div>
              ) : (
                items.map((schedule) => (
                  <div key={schedule.schedule_id} className="rounded-xl border border-border p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="font-medium">{schedule.name}</p>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                          <span className="rounded-full bg-muted px-2 py-0.5 font-medium">
                            Scheduled entity creation
                          </span>
                          <span className="rounded-full bg-muted px-2 py-0.5 font-medium">
                            Invoked by schedule
                          </span>
                        </div>
                        <p className="mt-1 text-xs font-medium text-primary">
                          {workflowLabels[schedule.machine_name] || schedule.machine_name}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {schedule.recurrence.frequency === 'once'
                            ? `Once · due ${schedule.recurrence.occurs_on}`
                            : `${schedule.recurrence.frequency} · due day ${schedule.recurrence.day_of_month} · ${schedule.occurrences_per_batch} occurrence${schedule.occurrences_per_batch === 1 ? '' : 's'} per batch`}{' '}
                          · appears {schedule.lead_days} days early
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {schedule.target_scope === 'all'
                            ? 'All active related records'
                            : 'Selected related records only'}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {schedule.conditions.length === 0
                            ? 'Runs for every record in this schedule scope'
                            : schedule.conditions
                                .map(
                                  (condition) =>
                                    `${condition.field} ${operatorLabels[condition.operator]} ${String(
                                      condition.value ?? '',
                                    )}`,
                                )
                                .join(` ${schedule.condition_mode} `)}
                        </p>
                      </div>
                      <AutomationActions
                        schedule={schedule}
                        busy={creating}
                        runPreviewLoadingId={runPreviewLoadingId}
                        onEdit={editSchedule}
                        onRunNow={requestRunNow}
                        onToggle={async (item) => {
                          await schedules.update(item.schedule_id, {
                            is_enabled: !item.is_enabled,
                          });
                          await load();
                        }}
                        onDelete={setDeleteConfirmation}
                      />
                    </div>
                  </div>
                ))
              )}

              <div className="flex items-start gap-2 rounded-lg bg-muted/30 p-3 text-xs text-muted-foreground">
                <Link2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Scheduled records are linked to the related record you select, so the global entity
                filter can find them later.
              </div>
            </>
          )}
        </div>
        <ConfirmDialog
          open={runConfirmation !== null}
          title={`Run “${runConfirmation?.schedule.name || 'automation'}” now?`}
          message={
            runConfirmation
              ? `${runConfirmation.preview.items
                  .filter((item) => item.status === 'eligible')
                  .reduce((total, item) => total + item.due_dates.length, 0)} occurrence(s) will be created across ${runConfirmation.preview.eligible} related record(s); ${runConfirmation.preview.skipped} record(s) will be skipped. Each new record keeps its scheduled due date.`
              : ''
          }
          confirmLabel="Queue creation jobs"
          loading={runningNow}
          onConfirm={() => void confirmRunNow()}
          onClose={() => !runningNow && setRunConfirmation(null)}
        />
        <ConfirmDialog
          open={deleteConfirmation !== null}
          title={`Delete “${deleteConfirmation?.name || 'automation'}”?`}
          message="This stops future scheduled creation and removes all subscriptions. Existing generated records and audit history are preserved."
          confirmLabel="Delete automation"
          variant="danger"
          loading={deleting}
          onConfirm={() => void confirmDelete()}
          onClose={() => !deleting && setDeleteConfirmation(null)}
        />
    </AutomationSurface>
  );
}
