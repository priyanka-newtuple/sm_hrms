import { Database, FileJson, ListOrdered, Plus, Settings2 } from "lucide-react";
import type { InspectorMode } from "../InspectorPanel";
import { Button } from "@/components/ui/button";

interface RailButtonProps {
  children: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}

function RailButton({ children, label, active, onClick }: RailButtonProps) {
  return (
    <Button
      variant="secondary"
      size="icon"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`rounded-md border transition-colors ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
      }`}
    >
      {children}
    </Button>
  );
}

interface LeftRailProps {
  mode: InspectorMode;
  onSetMode: (mode: InspectorMode) => void;
  onAddState: () => void;
}

export function LeftRail({ mode, onSetMode, onAddState }: LeftRailProps) {
  return (
    <nav className="flex w-14 flex-col items-center gap-1 border-r border-border bg-card py-3">
      <RailButton label="Add state" onClick={onAddState} active={false}>
        <Plus className="h-4 w-4" />
      </RailButton>
      <div className="my-2 h-px w-8 bg-border" />
      <RailButton
        label="Outline (states & transitions)"
        onClick={() => onSetMode({ kind: "list" })}
        active={mode.kind === "list"}
      >
        <ListOrdered className="h-4 w-4" />
      </RailButton>
      <RailButton
        label="Workflow settings"
        onClick={() => onSetMode({ kind: "settings" })}
        active={mode.kind === "settings"}
      >
        <Settings2 className="h-4 w-4" />
      </RailButton>
      <RailButton
        label="Entity schema"
        onClick={() => onSetMode({ kind: "schema" })}
        active={mode.kind === "schema"}
      >
        <Database className="h-4 w-4" />
      </RailButton>
      <RailButton
        label="JSON definition"
        onClick={() => onSetMode({ kind: "json" })}
        active={mode.kind === "json"}
      >
        <FileJson className="h-4 w-4" />
      </RailButton>
    </nav>
  );
}
