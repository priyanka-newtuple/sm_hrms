import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Shield } from "lucide-react";
import {
  GUARD_LIBRARY,
  type Guard,
  type GuardType,
  type FieldType,
} from "@/lib/state-machine/types";
import { DDSelect } from "./DDSelect";
import { Button } from '@/components/ui/button';

function humanizeGuard(g: Guard): string {
  const def = GUARD_LIBRARY.find((x) => x.type === g.type);
  if (!def) return g.type;
  switch (g.type) {
    case "field_present":
      return `${g.field || "field"} is present`;
    case "field_exact_match":
      return `${g.field || "field"} = ${JSON.stringify(g.value)}`;
    case "numerical_value_gte":
      return `${g.field || "field"} ≥ ${g.value}`;
    case "numerical_value_lte":
      return `${g.field || "field"} ≤ ${g.value}`;
    case "numerical_value_in_set":
      return `${g.field || "field"} ∈ ${Array.isArray(g.value) ? `[${(g.value as unknown[]).join(", ")}]` : g.value}`;
    case "compare_dates":
      return `${g.field || "date_a"} ${(g.config?.operator as string) || "lte"} ${g.config?.other_field || "date_b"}`;
    default:
      return def.label;
  }
}

const NUMERIC_FIELD_TYPES = new Set(["int", "integer", "float", "number"]);
const NUMERIC_GUARD_TYPES = new Set(["numerical_value_gte", "numerical_value_lte", "numerical_value_in_set"]);

function guardFieldOptions(
  guardType: string,
  fieldsMeta: { field: string; type: FieldType }[],
): string[] {
  if (guardType === "compare_dates") {
    return fieldsMeta.filter((f) => f.type === "datetime").map((f) => f.field);
  }
  if (NUMERIC_GUARD_TYPES.has(guardType)) {
    return fieldsMeta.filter((f) => NUMERIC_FIELD_TYPES.has(f.type)).map((f) => f.field);
  }
  return fieldsMeta.map((f) => f.field);
}

interface GuardFormProps {
  guard: Guard;
  fieldsMeta: { field: string; type: FieldType }[];
  onChange: (patch: Partial<Guard>) => void;
}

function GuardValueInput({
  guard,
  onChange,
}: {
  guard: Guard;
  onChange: (patch: Partial<Guard>) => void;
}) {
  switch (guard.type) {
    case "field_present":
    case "compare_dates":
      return null;
    case "numerical_value_gte":
    case "numerical_value_lte":
      return (
        <Input
          type="number"
          value={(guard.value as number) ?? ""}
          onChange={(e) =>
            onChange({ value: e.target.value === "" ? null : Number(e.target.value) })
          }
        />
      );
    case "numerical_value_in_set":
      return (
        <Input
          defaultValue={Array.isArray(guard.value) ? (guard.value as unknown[]).join(", ") : ""}
          onBlur={(e) =>
            onChange({
              value: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
                .map((s) => (isNaN(Number(s)) ? s : Number(s))),
            })
          }
          placeholder="3, 4, 5"
          className="font-mono text-xs"
        />
      );
    case "field_exact_match":
      return (
        <Input
          value={String(guard.value ?? "")}
          onChange={(e) => {
            const v = e.target.value;
            const parsed =
              v === "true" ? true : v === "false" ? false : isNaN(Number(v)) || v === "" ? v : Number(v);
            onChange({ value: parsed });
          }}
          placeholder="true / 1 / active"
        />
      );
    default:
      return (
        <Textarea
          rows={2}
          value={typeof guard.value === "string" ? guard.value : JSON.stringify(guard.value ?? "")}
          onChange={(e) => onChange({ value: e.target.value })}
        />
      );
  }
}

export function GuardForm({ guard, fieldsMeta, onChange }: GuardFormProps) {
  const def = GUARD_LIBRARY.find((g) => g.type === guard.type);
  const requiresValueField = guard.type !== "compare_dates";
  const compatibleFieldOptions = guardFieldOptions(guard.type, fieldsMeta);
  const compareDateOptions = guardFieldOptions("compare_dates", fieldsMeta);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-12">
        <div className="space-y-1 sm:col-span-5">
          <Label className="text-xs">Rule</Label>
          <DDSelect
            value={guard.type}
            options={GUARD_LIBRARY.map((g) => ({
              value: g.type,
              label: (
                <div className="flex flex-col">
                  <span>{g.label}</span>
                  <span className="text-[11px] text-muted-foreground">{g.description}</span>
                </div>
              ),
            }))}
            onSelect={(v) => {
              if (v === "compare_dates") {
                const firstField = compareDateOptions[0] ?? "";
                const secondField = compareDateOptions[1] ?? compareDateOptions[0] ?? "";
                onChange({
                  type: v as GuardType,
                  field: firstField,
                  value: null,
                  config: {
                    operator: (guard.config?.operator as string) || "lte",
                    other_field: secondField,
                  },
                });
                return;
              }
              onChange({ type: v as GuardType, field: compatibleFieldOptions[0] ?? "", config: {} });
            }}
          />
        </div>
        {requiresValueField && (
          <div className="space-y-1 sm:col-span-7">
            <Label className="text-xs">Field</Label>
            {compatibleFieldOptions.length === 0 ? (
              <p className="text-xs text-warning py-1.5">
                No fields defined. Add fields in the Entity Schema step first.
              </p>
            ) : (
              <DDSelect
                value={guard.field || undefined}
                placeholder="Choose a field"
                options={compatibleFieldOptions.map((f) => ({
                  value: f,
                  label: <span className="font-mono text-xs">{f}</span>,
                }))}
                onSelect={(v) => onChange({ field: v })}
                className="font-mono text-xs"
              />
            )}
          </div>
        )}
      </div>

      {def?.needsValue && (
        <div className="space-y-1">
          <Label className="text-xs">Value</Label>
          <GuardValueInput guard={guard} onChange={onChange} />
        </div>
      )}

      {guard.type === "compare_dates" && (
        <div className="grid gap-3 sm:grid-cols-12">
          <div className="space-y-1 sm:col-span-5">
            <Label className="text-xs">First datetime field</Label>
            <DDSelect
              value={guard.field || undefined}
              placeholder="Choose"
              options={compareDateOptions.map((f) => ({
                value: f,
                label: <span className="font-mono text-xs">{f}</span>,
              }))}
              onSelect={(v) => onChange({ field: v })}
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1 sm:col-span-3">
            <Label className="text-xs">Operator</Label>
            <DDSelect
              value={(guard.config?.operator as string) || "lte"}
              options={[
                { value: "lt", label: "before (<)" },
                { value: "lte", label: "before or equal (≤)" },
                { value: "gt", label: "after (>)" },
                { value: "gte", label: "after or equal (≥)" },
                { value: "eq", label: "equals (=)" },
              ]}
              onSelect={(v) => onChange({ config: { ...guard.config, operator: v } })}
            />
          </div>
          <div className="space-y-1 sm:col-span-4">
            <Label className="text-xs">Second datetime field</Label>
            <DDSelect
              value={(guard.config?.other_field as string) || undefined}
              placeholder="Choose"
              options={compareDateOptions.map((f) => ({
                value: f,
                label: <span className="font-mono text-xs">{f}</span>,
              }))}
              onSelect={(v) => onChange({ config: { ...guard.config, other_field: v } })}
              className="font-mono text-xs"
            />
          </div>
        </div>
      )}

      {guard.type === "custom" && (
        <div className="space-y-1">
          <Label className="text-xs">Custom type identifier</Label>
          <Input
            value={guard.type === "custom" ? "" : (guard.type as string)}
            onChange={(e) => onChange({ type: e.target.value as GuardType })}
            placeholder="my_custom_guard_type"
            className="font-mono text-xs"
          />
        </div>
      )}

      <div className="space-y-1">
        <Label className="text-xs">Error message (shown when this rule blocks the transition)</Label>
        <Input
          value={guard.message}
          onChange={(e) => onChange({ message: e.target.value })}
          placeholder="Resume is required before screening."
        />
      </div>
    </div>
  );
}

export { humanizeGuard, guardFieldOptions };

interface GuardRowProps {
  guard: Guard;
  fieldsMeta: { field: string; type: FieldType }[];
  onChange: (patch: Partial<Guard>) => void;
  onRemove: () => void;
}

export function GuardRow({ guard, fieldsMeta, onChange, onRemove }: GuardRowProps) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Shield className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-foreground">{humanizeGuard(guard)}</span>
        </div>
        <Button variant="ghost"
          className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-muted"
          onClick={onRemove}
        >
          ✕
        </Button>
      </div>
      <GuardForm guard={guard} fieldsMeta={fieldsMeta} onChange={onChange} />
    </div>
  );
}
