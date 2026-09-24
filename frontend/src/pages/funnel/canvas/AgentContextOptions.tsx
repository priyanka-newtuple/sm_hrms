const INPUT_CLASS = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

interface AgentContextOptionsProps {
  includeFiles: boolean;
  onIncludeFilesChange: (value: boolean) => void;
  includeRelations: string;
  onIncludeRelationsChange: (value: string) => void;
}

export function AgentContextOptions({
  includeFiles,
  onIncludeFilesChange,
  includeRelations,
  onIncludeRelationsChange,
}: AgentContextOptionsProps) {
  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-xs font-medium">
        <input
          type="checkbox"
          checked={includeFiles}
          onChange={(e) => onIncludeFilesChange(e.target.checked)}
          className="h-3.5 w-3.5"
        />
        Include attached files (text files inlined; binaries listed)
      </label>
      <div className="space-y-1.5">
        <label className="text-xs font-medium">
          Include linked records <span className="text-muted-foreground">(optional)</span>
        </label>
        <input
          value={includeRelations}
          onChange={(e) => onIncludeRelationsChange(e.target.value)}
          placeholder="comma-separated relation types, e.g. applied_to, referred_by"
          className={INPUT_CLASS}
        />
      </div>
    </div>
  );
}
