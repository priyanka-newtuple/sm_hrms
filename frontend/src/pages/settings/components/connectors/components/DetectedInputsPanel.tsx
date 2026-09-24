import { Braces, Database } from 'lucide-react';

import type { DetectedPlaceholders } from '../types';

interface DetectedInputsPanelProps {
  detected: DetectedPlaceholders;
}

/**
 * Read-only summary of the placeholders found across the connector's request,
 * grouped by where each value comes from. Makes the otherwise-invisible input
 * contract explicit as the user builds the connector.
 */
export default function DetectedInputsPanel({ detected }: DetectedInputsPanelProps) {
  const { inputs, entityFields } = detected;
  if (inputs.length === 0 && entityFields.length === 0) return null;

  return (
    <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
      <p className="text-xs font-medium">This connector needs</p>

      <Group
        icon={<Braces className="h-3.5 w-3.5" />}
        title="Asked at runtime"
        hint="the agent or workflow provides these"
        names={inputs}
        emptyHint="None — nothing is asked of the caller."
      />
      <Group
        icon={<Database className="h-3.5 w-3.5" />}
        title="From the entity"
        hint="auto-filled from the bound record"
        names={entityFields}
        emptyHint="None — no entity fields are used."
      />
    </div>
  );
}

function Group({
  icon,
  title,
  hint,
  names,
  emptyHint,
}: {
  icon: React.ReactNode;
  title: string;
  hint: string;
  names: string[];
  emptyHint: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
        {icon}
        <span>{title}</span>
        <span className="font-normal">— {hint}</span>
      </div>
      {names.length === 0 ? (
        <p className="pl-5 text-[11px] text-muted-foreground">{emptyHint}</p>
      ) : (
        <div className="flex flex-wrap gap-1.5 pl-5">
          {names.map((name) => (
            <span
              key={name}
              className="rounded-full bg-background px-2 py-0.5 font-mono text-[11px] text-foreground ring-1 ring-border"
            >
              {name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
