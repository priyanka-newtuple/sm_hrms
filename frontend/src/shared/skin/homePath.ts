import type { SkinManifest } from '../../skins/types';

/**
 * Resolves the same three landing behaviors used by App.tsx without mounting
 * React, so the default and skin-specific redirect contracts can be tested.
 */
export function resolveSkinHomePath(homePath: SkinManifest['homePath']): string {
  if (homePath === 'pipeline') return 'pipeline';
  if (homePath && homePath !== 'workflows') return homePath;
  return '/workflows';
}
