import { useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { useEntityStore, schemaForEntityType } from "@/core/stores/entityStore";
import type { EntityField, StateMachineDocument } from "@/lib/state-machine/types";
import { buildEntityFieldsFromFormSchema } from "@/lib/state-machine/entitySchema";

interface Props {
  doc: StateMachineDocument;
}

function renderDefaultValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "None";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function EntitySchemaEditor({ doc }: Props) {
  const schemas = useEntityStore((s) => s.schemas);
  const fetchSchemas = useEntityStore((s) => s.fetchSchemas);
  const entityType = doc.definition.entity_type.trim();
  const selectedSchema = entityType ? schemaForEntityType(schemas, entityType) : null;

  useEffect(() => {
    if (schemas.length === 0) {
      void fetchSchemas();
    }
  }, [fetchSchemas, schemas.length]);

  const fields: EntityField[] = selectedSchema
    ? buildEntityFieldsFromFormSchema(selectedSchema)
    : doc.definition.entity_schema.fields;

  return (
    <Card className="p-5">
      <div className="mb-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Entity schema</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Read-only fields for the selected entity type. These drive guard configuration and required-field checks.
          </p>
        </div>
      </div>

      {!entityType ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
          Select an entity type in workflow settings to view its schema.
        </div>
      ) : (
        <>
          <div className="mb-4 flex items-center gap-2">
            <Badge variant="secondary">{entityType}</Badge>
            {selectedSchema ? (
              <span className="text-xs text-muted-foreground">Showing active schema fields for this entity type.</span>
            ) : (
              <span className="text-xs text-muted-foreground">Showing fields already attached to this workflow.</span>
            )}
          </div>

          {fields.length === 0 ? (
            <div className="rounded-md border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
              No schema fields are available for this entity type.
            </div>
          ) : (
            <div className="space-y-3">
              {fields.map((field) => (
                <div key={field.field} className="rounded-md border border-border bg-muted/30 p-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Field name</Label>
                      <div className="font-mono text-sm text-foreground">{field.field}</div>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Type</Label>
                      <div className="text-sm text-foreground">{field.type}</div>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Required</Label>
                      <div className="text-sm text-foreground">{field.required ? "Yes" : "No"}</div>
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Default</Label>
                      <div className="text-sm text-foreground">{renderDefaultValue(field.default)}</div>
                    </div>
                    {field.enum_values.length > 0 && (
                      <div className="space-y-1 sm:col-span-2">
                        <Label className="text-xs text-muted-foreground">Allowed values</Label>
                        <div className="flex flex-wrap gap-2">
                          {field.enum_values.map((value) => (
                            <Badge key={value} variant="outline" className="font-mono text-[11px]">
                              {value}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="space-y-1 sm:col-span-2">
                      <Label className="text-xs text-muted-foreground">Description</Label>
                      <div className="text-sm text-foreground">{field.description || "No description provided."}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
