/**
 * Catalog of pre-built remote MCP apps shown in Settings → Connectors.
 *
 * Adding the next app (e.g. Exa) is a new entry here — no new component code.
 */

import GitHubLogo from '../components/icons/GitHubLogo';
import type { RemoteMcpAppDefinition } from '../types';

export const REMOTE_MCP_APPS: RemoteMcpAppDefinition[] = [
  {
    id: 'github',
    name: 'GitHub',
    description: 'Repos, issues & pull requests',
    icon: GitHubLogo,
  },
];
