import { lazy } from 'react';
import type { SkinManifest } from '../types';

export const hrmsSkin: SkinManifest & { applicationRoot?: React.ComponentType } = {
  id: 'newtuple-hrms',
  applicationRoot: lazy(() => import('./ProductRoot')),
  branding: { name: 'Newtuple HRMS', shortName: 'HRMS', logoText: 'N', primaryColor: 'cobalt', copyrightOwner: 'Newtuple' },
  homePath: '/my-work',
  navigation: [], entityTypes: [], entityViews: [], staticLists: {},
  board: { entityType: 'HRMS.Onboarding', machineName: 'hrms_onboarding', fallbackStages: [], terminalStates: ['completed'], stateColors: {} },
};
