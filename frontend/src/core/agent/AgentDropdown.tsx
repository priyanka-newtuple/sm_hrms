import { ChevronDown, Sparkles } from 'lucide-react';

import { useAgent } from './AgentContext';

/**
 * Shared agent selector dropdown. Renders an interactive <select> when
 * multiple agents are available, or a static label when only one exists.
 *
 * @param variant - 'pill' for the chat panel header, 'bar' for the sidebar.
 */
export default function AgentDropdown({ variant = 'pill' }: { variant?: 'pill' | 'bar' }) {
  const { agentDefinitions, selectedAgentId, selectAgent, isLoadingDefinitions } = useAgent();
  const active = agentDefinitions.find((a) => a.definition_id === selectedAgentId);
  const label = active?.display_name || active?.name || 'Agent';

  if (isLoadingDefinitions) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground">
        Loading...
      </span>
    );
  }

  // Single agent — static label
  if (agentDefinitions.length <= 1) {
    const cls = variant === 'bar'
      ? 'flex w-full items-center gap-2 rounded-lg bg-cobalt/10 px-3 py-1.5'
      : 'inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5';
    return (
      <span className={`${cls} text-sm font-medium text-foreground`}>
        <Sparkles className="h-3.5 w-3.5 text-cobalt shrink-0" />
        {label}
      </span>
    );
  }

  // Multiple agents — interactive dropdown
  if (variant === 'bar') {
    return (
      <div className="flex w-full items-center gap-2 rounded-lg bg-cobalt/10 px-3 py-1.5">
        <Sparkles className="w-4 h-4 text-cobalt shrink-0" />
        <select
          value={selectedAgentId ?? ''}
          onChange={(e) => selectAgent(e.target.value)}
          className="flex-1 min-w-0 appearance-none truncate bg-transparent pr-5 text-sm font-medium text-gray-900 outline-none cursor-pointer"
        >
          {agentDefinitions.map((a) => (
            <option key={a.definition_id} value={a.definition_id}>
              {a.display_name || a.name}{a.is_system ? ' (System)' : ''}
            </option>
          ))}
        </select>
        <ChevronDown className="h-3.5 w-3.5 text-gray-500 shrink-0 -ml-4" />
      </div>
    );
  }

  return (
    <label className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background pl-3 pr-2.5 py-1 text-sm font-medium text-foreground cursor-pointer">
      <Sparkles className="h-3.5 w-3.5 text-cobalt shrink-0" />
      <select
        value={selectedAgentId ?? ''}
        onChange={(e) => selectAgent(e.target.value)}
        className="bg-transparent outline-none cursor-pointer text-sm font-medium text-foreground"
      >
        {agentDefinitions.map((a) => (
          <option key={a.definition_id} value={a.definition_id}>
            {a.display_name || a.name}{a.is_system ? ' (System)' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}
