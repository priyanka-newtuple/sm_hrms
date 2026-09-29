import { CalendarDays, Settings, UserRoundPlus, Users, Waypoints } from 'lucide-react';
import { skin } from '../skin.config';
import type { SkinManifest } from '../types';
import LeaveRequestsPage from './pages/LeaveRequestsPage';
import EmployeeDirectoryPage from './pages/EmployeeDirectoryPage';
import OnboardingPage from './pages/OnboardingPage';

export const hrmsNativeSkin: SkinManifest = {
  ...skin,
  id: 'newtuple-hrms-native',
  branding: {
    ...skin.branding,
    name: 'Newtuple HRMS',
    shortName: 'HRMS',
    copyrightOwner: 'Newtuple',
  },
  homePath: '/hrms/my-work',
  board: { ...skin.board, showAssigneeFilter: false },
  navigation: [
    { path: '/hrms/leave', label: 'Leave Requests', icon: CalendarDays },
    { path: '/hrms/employees', label: 'Employees', icon: Users },
    { path: '/hrms/onboarding', label: 'Onboarding', icon: UserRoundPlus },
    { path: '/workflows', label: 'Workflows', icon: Waypoints },
    { path: '/settings', label: 'Settings', icon: Settings, position: 'bottom' },
  ],
  entityTypes: [
    { entityType: 'HRMS.Employee', schemaName: 'hrms_employee', schemaVersion: 1, label: 'Employee', labelPlural: 'Employees' },
    { entityType: 'HRMS.LeaveRequest', schemaName: 'hrms_leaverequest', schemaVersion: 1, machineName: 'hrms_leaverequest', machineVersion: 1, label: 'Leave Request', labelPlural: 'Leave Requests' },
  ],
  customPages: [
    { path: '/hrms/leave', component: LeaveRequestsPage },
    { path: '/hrms/employees', component: EmployeeDirectoryPage },
    { path: '/hrms/onboarding', component: OnboardingPage },
  ],
};
