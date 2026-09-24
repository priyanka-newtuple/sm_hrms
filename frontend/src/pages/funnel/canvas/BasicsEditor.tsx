import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DDSelect } from "./DDSelect";
import ServiceSelect from "../components/ServiceSelect";
import type { StateMachineDocument } from "@/lib/state-machine/types";
import {
  buildEntityFieldsFromFormSchema,
  pruneTransitionsForEntityFields,
} from "@/lib/state-machine/entitySchema";
import { schemaForEntityType, useEntityStore } from "@/core/stores/entityStore";
import { useEffect } from "react";

interface Props {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
}

export function BasicsEditor({ doc, onChange }: Props) {
  const def = doc.definition;
  const schemas = useEntityStore((s) => s.schemas);
  const fetchSchemas = useEntityStore((s) => s.fetchSchemas);
  const entityTypes = [...new Set(schemas.map((s) => s.entity_type))];

  useEffect(() => {
    if (schemas.length === 0) fetchSchemas();
  }, []);

  const handleEntityTypeChange = (value: string) => {
    const matched = schemaForEntityType(schemas, value);
    const fields = matched ? buildEntityFieldsFromFormSchema(matched) : [];

    onChange({
      ...doc,
      definition: {
        ...def,
        entity_type: value,
        entity_schema: { entity_type: value, fields },
        transitions: pruneTransitionsForEntityFields(def.transitions, fields),
      },
    });
  };

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-foreground">Machine basics</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Identifiers and human-readable details for this workflow.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="display_name">State machine name</Label>
          <Input
            id="display_name"
            placeholder="ATS Application"
            value={def.name}
            onChange={(e) => onChange({ ...doc, definition: { ...def, name: e.target.value } })}
          />
          <p className="text-xs text-muted-foreground">Human-readable name shown in the UI.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="machine_name">Machine key</Label>
          <Input
            id="machine_name"
            placeholder="ats_application_full_example"
            value={doc.machine_name}
            onChange={(e) =>
              onChange({
                ...doc,
                machine_name: e.target.value,
                definition: { ...def, machine_key: e.target.value },
              })
            }
          />
          <p className="text-xs text-muted-foreground">Lowercase, snake_case, unique.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="entity_type">Entity type</Label>
          {entityTypes.length > 0 ? (
            <DDSelect
              value={def.entity_type}
              placeholder="Select entity type"
              options={entityTypes.map((et) => ({ value: et, label: et }))}
              onSelect={handleEntityTypeChange}
            />
          ) : (
            <Input
              id="entity_type"
              placeholder="application"
              value={def.entity_type}
              onChange={(e) => handleEntityTypeChange(e.target.value)}
            />
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="version">Base version</Label>
          <Input
            id="version"
            type="number"
            min={1}
            value={doc.base_version}
            onChange={(e) => onChange({ ...doc, base_version: Number(e.target.value) || 1 })}
          />
        </div>
        <div className="space-y-1.5">
          <ServiceSelect
            value={def.service_id}
            onChange={(value) => onChange({ ...doc, definition: { ...def, service_id: value } })}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            placeholder="What does this workflow do?"
            value={def.description}
            onChange={(e) => onChange({ ...doc, definition: { ...def, description: e.target.value } })}
            rows={3}
          />
        </div>
      </div>
    </Card>
  );
}
