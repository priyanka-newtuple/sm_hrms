import { useCallback } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/core/auth';
import { organizations } from '@/core/services/api';
import { useFeatureFlags } from '@/core/hooks/useFeatureFlags';

/**
 * Org-wide "hide terminal-state entities" preference — one flag, the same
 * value on every workflow's pipeline board (no per-workflow storage).
 * Persisted as `organization.settings.featureFlags.hideTerminalByDefault` —
 * the same blob Settings → Display writes, so changing it from either place
 * changes it everywhere immediately.
 */
export function useHideTerminal(): {
  hidden: boolean;
  setHidden: (hidden: boolean) => Promise<void>;
} {
  const { refreshOrganization } = useAuth();
  const flags = useFeatureFlags();

  const setHidden = useCallback(
    async (next: boolean) => {
      try {
        // Send the complete flags object, not just this one key — a shallow
        // merge at the `settings` level would otherwise wipe out the other
        // Display flags (hideKanban, hideDashboard, ...) instead of just
        // updating this one. Mirrors how DisplayTab always saves its full draft.
        await organizations.updateBranding({
          settings: { featureFlags: { ...flags, hideTerminalByDefault: next } },
        });
        await refreshOrganization();
      } catch (e) {
        toast.error('Could not save this preference', {
          description: e instanceof Error ? e.message : 'Failed to save',
        });
      }
    },
    [flags, refreshOrganization],
  );

  return { hidden: flags.hideTerminalByDefault, setHidden };
}
