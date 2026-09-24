import { useEffect, useMemo, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import Input from '../../../../core/components/Input';
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from '@/components/ui/combobox';
import { renderIdentifierPreview } from '@/shared/utils/entityForm';
import { entityTypes as entityTypesApi } from '../../../../core/services/api';
import type { EntityType, FormSchema } from '../../../../core/types';
import {
  allowedIdentifierFields,
  appendToken,
  buildPreviewValueMap,
  buildTokenOptions,
  fieldsForEntityType,
  hasStrayBraces,
} from './entityTypeFields';

interface IdentifierConfigSectionProps {
  /** The entity type being edited, or null when creating a new one. */
  entityType: EntityType | null;
  label: string;
  template: string;
  errorMessage: string;
  onLabelChange: (value: string) => void;
  onTemplateChange: (value: string) => void;
  onErrorMessageChange: (value: string) => void;
  types: EntityType[];
  schemas: FormSchema[];
  saving: boolean;
}

/**
 * `{{<related_type>_identifier}}` tokens available to the edited type, derived
 * from relation declarations that inherit fields from another entity type.
 */
function useRelatedIdentifierTokens(entityType: EntityType | null, types: EntityType[]): string[] {
  const [tokens, setTokens] = useState<string[]>([]);

  useEffect(() => {
    const typeId = entityType?.entity_type_id ?? entityType?.id;
    if (!typeId) return;

    let cancelled = false;
    entityTypesApi
      .relations(typeId)
      .then((response) => {
        if (cancelled) return;
        const nameById = new Map(types.map((t) => [t.entity_type_id ?? t.id, t.name] as const));
        setTokens([
          ...new Set(
            (response.inherited_fields ?? [])
              .map((item) => nameById.get(item.source_entity_type_id))
              .filter((name): name is string => Boolean(name))
              .map((name) => `${name}_identifier`),
          ),
        ]);
      })
      .catch(() => {
        if (!cancelled) setTokens([]);
      });

    return () => {
      cancelled = true;
    };
  }, [entityType, types]);

  return tokens;
}

export default function IdentifierConfigSection({
  entityType,
  label,
  template,
  errorMessage,
  onLabelChange,
  onTemplateChange,
  onErrorMessageChange,
  types,
  schemas,
  saving,
}: IdentifierConfigSectionProps) {
  // Remount the combobox after each pick so its input clears for the next insert.
  const [tokenPickerKey, setTokenPickerKey] = useState(0);
  const relatedIdentifierTokens = useRelatedIdentifierTokens(entityType, types);

  const allowedFields = useMemo(
    () => (entityType ? allowedIdentifierFields(fieldsForEntityType(schemas, entityType.name)) : []),
    [entityType, schemas],
  );

  const tokenOptions = useMemo(
    () => buildTokenOptions(allowedFields, relatedIdentifierTokens),
    [allowedFields, relatedIdentifierTokens],
  );
  const tokenIds = useMemo(() => tokenOptions.map((option) => option.id), [tokenOptions]);
  const tokenLabelById = useMemo(
    () => new Map(tokenOptions.map((option) => [option.id, option.label])),
    [tokenOptions],
  );

  const templateHasStrayBraces = hasStrayBraces(template);

  return (
    <Accordion
      type="single"
      collapsible
      defaultValue={label || template || errorMessage ? 'identifier-config' : undefined}
    >
      <AccordionItem value="identifier-config" className="border-b-0">
        <AccordionTrigger className="py-2 hover:no-underline">
          <span className="flex items-center gap-2">
            Custom identifier
            <span className="text-xs font-normal text-muted-foreground">· optional</span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="space-y-4 pb-1">
          <Input
            id="entity-type-identifier-label"
            label="Identifier label"
            value={label}
            onChange={(event) => onLabelChange(event.target.value)}
            placeholder='e.g. "Candidate ID" — leave blank for default'
            maxLength={64}
            disabled={saving}
          />

          <Input
            id="entity-type-identifier-error-message"
            label="Required error message"
            value={errorMessage}
            onChange={(event) => onErrorMessageChange(event.target.value)}
            placeholder={`e.g. "Enter a candidate ID" — leave blank for "${label.trim() || 'Unique Name'} is required"`}
            maxLength={200}
            disabled={saving}
            helperText="Shown under the field when it is left blank."
          />

          <Input
            id="entity-type-identifier-template"
            label="Identifier template"
            value={template}
            onChange={(event) => onTemplateChange(event.target.value)}
            placeholder="e.g. {{first_name}}-{{last_name}} or INV-{{seq}}"
            maxLength={256}
            disabled={saving}
          />

          <Combobox
            key={tokenPickerKey}
            items={tokenIds}
            onValueChange={(id) => {
              if (typeof id === 'string' && id) {
                onTemplateChange(appendToken(template, id));
                setTokenPickerKey((k) => k + 1);
              }
            }}
            disabled={saving}
          >
            <ComboboxInput placeholder="Insert field token…" className="w-full" />
            <ComboboxContent>
              <ComboboxEmpty>No fields found.</ComboboxEmpty>
              <ComboboxList>
                {(id: string) => (
                  <ComboboxItem key={id} value={id}>
                    <span className="font-mono text-xs">{`{{${id}}}`}</span>
                    <span className="text-muted-foreground">{tokenLabelById.get(id)}</span>
                  </ComboboxItem>
                )}
              </ComboboxList>
            </ComboboxContent>
          </Combobox>

          {templateHasStrayBraces && (
            <p className="text-sm text-warning">
              <AlertCircle className="mr-1 inline h-3.5 w-3.5 align-[-2px]" aria-hidden="true" />
              Malformed braces — every token must look like {'{{field_name}}'}. Use the field picker
              above to insert tokens.
            </p>
          )}
          {template.trim() && (
            <p className="text-sm text-muted-foreground">
              Preview:{' '}
              <code className="rounded bg-muted px-2 py-0.5 font-mono text-xs">
                {renderIdentifierPreview(
                  template,
                  buildPreviewValueMap(allowedFields, relatedIdentifierTokens),
                ) || '—'}
              </code>
            </p>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
