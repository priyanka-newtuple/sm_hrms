import { X, Plus, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { FormField, FormSchema, RelationDeclaration } from '../../../../../core/types';
import { FIELD_TYPE_LABELS, toFieldId } from '../constants';
import { resolveEntityFormSchemas } from '@/lib/state-machine/entitySchema';
import type { EntityField } from '@/lib/state-machine/types';
import { IDENTIFIER_FIELD_KEY } from '@/shared/utils/entityForm';

// The provider's unique identifier is synthetic (not a form field), so offer it
// explicitly — it lives in entity data and resolves like any mapped field.
const IDENTIFIER_SOURCE_FIELD: FormField = {
  id: IDENTIFIER_FIELD_KEY,
  label: 'Unique identifier',
  type: 'text',
  required: false,
  system: false,
};

type Props = {
  schemas: FormSchema[];
  currentFields: FormField[];
  /** Active declarations targeting the current form's entity type (direction=to). */
  declarations: RelationDeclaration[];
  typeNameById: Map<string, string>;
  /**
   * Workflow `entity_schema` fields per entity type name, for types whose
   * fields come from pinned Method Blocks and so have no Form config. Without
   * this the picker offers nothing for them and they can never be mapped.
   */
  workflowFieldsByEntityType?: Record<string, EntityField[]>;
  /** relation_def_id of the currently selected provider, or ''. */
  selectedDefId: string;
  onSelectDeclaration: (defId: string) => void;
  onAddField: (
    declaration: RelationDeclaration,
    providerName: string,
    sourceField: FormField
  ) => void;
  onClose: () => void;
};

export default function ReferencePickerModal({
  schemas,
  currentFields,
  declarations,
  typeNameById,
  workflowFieldsByEntityType = {},
  selectedDefId,
  onSelectDeclaration,
  onAddField,
  onClose,
}: Props) {
  const selected = declarations.find((d) => d.relation_def_id === selectedDefId) ?? null;
  const providerName = selected ? (typeNameById.get(selected.from_entity_type_id) ?? '') : '';
  // `union`, not `state`: this maps an entity *type* at config time, and the
  // runtime value copy reads `data[field]` with no regard for the record's
  // state (entities/db_models.py `_resolve_reference_fields`), so scoping the
  // picker to one state would hide fields that are perfectly mappable.
  const providerSchemaFields = resolveEntityFormSchemas(providerName || undefined, {
    scope: 'union',
    formSchemas: schemas,
    workflowFields: workflowFieldsByEntityType[providerName],
  })
    .flatMap((schema) => schema.schema?.fields ?? [])
    .filter((field) => field.type !== 'section' && field.type !== 'reference');
  const providerFields = providerName
    ? [
        ...(providerSchemaFields.some((field) => field.id === IDENTIFIER_FIELD_KEY)
          ? []
          : [IDENTIFIER_SOURCE_FIELD]),
        ...providerSchemaFields,
      ]
    : [];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-card rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground">Add Field from Related Entity</h3>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {declarations.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <Link2 className="w-8 h-8 mx-auto mb-2 text-muted-foreground/60" />
              <p className="font-medium text-muted-foreground">
                No relations defined for this entity type.
              </p>
              <p className="mt-1">
                Define one in Settings → Entity Types (Relations), then add its fields here.
              </p>
            </div>
          ) : (
            <>
              {/* Provider selector — one button per declared relation */}
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Select Related Entity
                </label>
                <div className="flex flex-wrap gap-2">
                  {declarations.map((d) => {
                    const name = typeNameById.get(d.from_entity_type_id) ?? d.from_entity_type_id;
                    const isActive = d.relation_def_id === selectedDefId;
                    return (
                      <Button
                        key={d.relation_def_id}
                        variant={isActive ? 'secondary' : 'ghost'}
                        onClick={() => onSelectDeclaration(d.relation_def_id)}
                        className={`text-sm font-medium ${
                          isActive
                            ? 'border-primary/20 bg-primary/10 text-primary'
                            : 'text-muted-foreground'
                        }`}
                      >
                        {name}
                        <span className="ml-1.5 text-xs opacity-70">
                          {d.relation_type === 'REFERENCE' ? 'live' : 'copy'}
                        </span>
                      </Button>
                    );
                  })}
                </div>
              </div>

              {/* Field selector */}
              {selected && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Select Field to Include
                  </label>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {providerFields.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-4 text-center">
                        No fields available from {providerName}. Create an active form for it
                        first.
                      </p>
                    ) : (
                      providerFields.map((field) => {
                        const targetId = toFieldId(`${providerName}_${field.id}`);
                        const alreadyAdded =
                          currentFields.some((f) => f.id === targetId) ||
                          Object.prototype.hasOwnProperty.call(
                            selected.relation_metadata ?? {},
                            `${providerName}.${field.id}`
                          );
                        return (
                          <Button
                            key={field.id}
                            variant="ghost"
                            onClick={() => onAddField(selected, providerName, field)}
                            disabled={alreadyAdded}
                            className={`h-auto w-full justify-start p-3 text-left border transition-colors ${
                              alreadyAdded
                                ? 'border-border bg-muted/40 opacity-50 cursor-not-allowed'
                                : 'border-border bg-background hover:border-primary/30 hover:bg-accent/40'
                            }`}
                          >
                            <div className="flex items-center justify-between w-full">
                              <div>
                                <div className="font-medium text-foreground">{field.label}</div>
                                <div className="text-xs text-muted-foreground mt-0.5">
                                  <code className="bg-muted px-1 rounded">{field.id}</code>
                                  <span className="ml-2">{FIELD_TYPE_LABELS[field.type]}</span>
                                </div>
                              </div>
                              {alreadyAdded ? (
                                <span className="text-xs text-muted-foreground">Already added</span>
                              ) : (
                                <Plus className="w-4 h-4 text-primary" />
                              )}
                            </div>
                          </Button>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-4 border-t border-border bg-muted/50">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
