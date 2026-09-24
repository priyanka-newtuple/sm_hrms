import { Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAgent } from './AgentContext';
import { cn } from '@/lib/utils';

interface AgentToggleProps {
  /** 'header' = compact pill for the top bar; 'sidebar' = prominent full-width CTA. */
  variant?: 'header' | 'sidebar';
}

export default function AgentToggle({ variant = 'header' }: AgentToggleProps) {
  const { isThinking } = useAgent();
  const navigate = useNavigate();

  if (variant === 'sidebar') {
    return (
      <button
        type="button"
        onClick={() => navigate('/agent')}
        aria-label="Open agent mode"
        className={cn(
          'flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-sm text-sidebar-foreground/75 transition-colors',
          'hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
          '[&_svg]:size-[18px] [&_svg]:shrink-0 [&_svg]:[stroke-width:1.75]',
          'group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0',
          isThinking && 'animate-pulse',
        )}
      >
        <Sparkles className="text-[var(--sidebar-primary)]" />
        <span className="group-data-[collapsible=icon]:hidden">Agent Mode</span>
      </button>
    );
  }

  // Top-bar (topbar nav layout): compact pill that reads against the colored
  // header — neutral surface + white shine, matching the sidebar CTA.
  return (
    <button
      type="button"
      onClick={() => navigate('/agent')}
      aria-label="Open agent mode"
      className={cn(
        'group/agent relative flex shrink-0 items-center gap-2 overflow-hidden rounded-lg px-3 py-1.5',
        'border border-[color-mix(in_srgb,var(--header-foreground)_22%,transparent)] text-[var(--header-foreground)]',
        'text-sm font-medium transition-all duration-200',
        'hover:bg-[color-mix(in_srgb,var(--header-foreground)_10%,transparent)]',
        isThinking && 'animate-pulse',
      )}
    >
      <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/50 to-transparent transition-transform duration-700 group-hover/agent:translate-x-full" />
      <Sparkles className="h-4 w-4" />
      <span>Agent Mode</span>
    </button>
  );
}
