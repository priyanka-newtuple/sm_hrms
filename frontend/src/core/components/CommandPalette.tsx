import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, LogOut } from 'lucide-react';

import type { NavItem } from '@/skins';
import { cn } from '@/lib/utils';
import { useAuth } from '@/core/auth';
import { usePermissions } from '@/core/hooks/usePermissions';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';
import { useWorkflows } from '@/shared/hooks/useWorkflows';
import { useCommandPaletteStore } from '@/core/stores/commandPaletteStore';
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from '@/components/ui/command';

type Props = {
  /** Fully resolved nav destinations (flag- and permission-filtered) from the layout. */
  navItems: NavItem[];
};

/**
 * Global ⌘K command palette. Fuzzy-jumps to any nav page, pipeline workflow, or
 * quick action. Mounted once by the app layout; open state lives in
 * {@link useCommandPaletteStore} so any trigger can drive it.
 */
export function CommandPalette({ navItems }: Props) {
  const navigate = useNavigate();
  const open = useCommandPaletteStore((s) => s.open);
  const setOpen = useCommandPaletteStore((s) => s.setOpen);
  const toggle = useCommandPaletteStore((s) => s.toggle);

  const { logout } = useAuth();
  const { hasPermission } = usePermissions();
  const featureFlags = useFeatureFlags();
  const { workflows } = useWorkflows();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Respect a handler that already claimed this keystroke — e.g. the email
      // template editor binds Cmd/Ctrl+K to its link popover and preventDefaults;
      // its React onKeyDown fires before this document listener, so the event
      // arrives here already defaultPrevented.
      if (e.defaultPrevented) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggle();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [toggle]);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  const canUseAgent = !featureFlags.hideAgent && hasPermission('agent:read');

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search pages, pipelines, actions…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Go to">
          {navItems.map((item) => (
            <CommandItem
              key={item.path}
              value={`${item.label} ${item.path}`}
              onSelect={() => go(item.path)}
            >
              <item.icon />
              <span>{item.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        {workflows.length > 0 && (
          <CommandGroup heading="Pipelines">
            {workflows.map((wf) => (
              <CommandItem
                key={wf.slug}
                value={`pipeline ${wf.label}`}
                onSelect={() => go(`/pipeline/${wf.id}`)}
              >
                <span
                  aria-hidden
                  className={cn(
                    'size-2 rounded-full',
                    wf.isActive ? 'bg-emerald-500' : 'bg-amber-500',
                  )}
                />
                <span>{wf.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandGroup heading="Actions">
          {canUseAgent && (
            <CommandItem value="ask agent mode" onSelect={() => go('/agent')}>
              <Sparkles />
              <span>Ask agent</span>
            </CommandItem>
          )}
          <CommandItem
            value="sign out log out"
            onSelect={() => {
              setOpen(false);
              void logout();
            }}
          >
            <LogOut />
            <span>Sign out</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
