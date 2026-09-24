import type { EntityField } from "@/lib/state-machine/types";

interface InputFieldsSelectorProps {
  entityFields: EntityField[];
  inputFields: string[];
  onInputFieldToggle: (fieldName: string) => void;
}

export function InputFieldsSelector({
  entityFields,
  inputFields,
  onInputFieldToggle,
}: InputFieldsSelectorProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium">
        Input fields <span className="text-muted-foreground">(none = all fields)</span>
      </label>
      <div className="flex flex-wrap gap-1.5">
        {entityFields.map((field) => {
          const selected = inputFields.includes(field.field);
          return (
            <button
              key={field.field}
              type="button"
              onClick={() => onInputFieldToggle(field.field)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] ${
                selected
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-input text-muted-foreground hover:bg-muted"
              }`}
            >
              {field.field}
            </button>
          );
        })}
      </div>
    </div>
  );
}
