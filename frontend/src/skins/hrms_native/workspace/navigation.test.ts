import { describe, expect, it } from 'vitest';
import { buildNavigation, isNavigationActive } from './navigation';
const workflows = [
  { entity_type: 'HRMS.Employee', machine_name: 'employee custom', name: 'Add Employee' },
  { entity_type: 'HRMS.Offboarding', machine_name: 'exit', name: 'Employee offboarding' },
];
const caps = { roles: ['hrms_hr_full'], employee_profile: true, capabilities: ['onboarding:view', 'employee:exit', 'cockpit:view', 'project:view', 'asset:view', 'leave:create', 'wfh:view', 'employee:read'] };
describe('workspace navigation', () => {
  it('groups workflow links and preserves record destinations and task count', () => {
    const groups = buildNavigation(caps, workflows, 2, true, ['workflow:read']);
    expect(groups.find(g => g.label === 'HR Cockpit')?.items.slice(0,2).map(i => i.path)).toEqual(['/hrms/workflows?workflow=employee%20custom','/hrms/workflows?workflow=exit']);
    expect(groups.find(g => g.label === 'Manager Cockpit')?.items.map(i => i.path)).toEqual(['/hrms/customers','/hrms/projects','/hrms/allocations']);
    expect(groups[0].items[0].badge).toBe(2);
    expect(groups.find(g => g.label === 'Employee Self Service')?.items.map(i => i.label)).toEqual(['Leave Requests','Work from Home']);
  });
  it('places the configured UAT inbox at level one, never in HR Cockpit', () => {
    const groups = buildNavigation(caps, workflows, 0, true, ['workflow:read']);
    expect(groups.find(g => g.items.some(i => i.path === '/hrms/uat-inbox'))?.standalone).toBe(true);
    expect(buildNavigation(caps, workflows, 0, false, []).flatMap(g => g.items).some(i => i.path === '/hrms/uat-inbox')).toBe(false);
  });
  it('does not expose unauthorized modules, agents or empty groups', () => {
    const groups = buildNavigation({roles:[],capabilities:[]}, [], 0, false, []);
    expect(groups.flatMap(g => g.items).map(i => i.label)).toEqual(['My Tasks']);
  });
  it('retains the restricted first-time employee navigation', () => {
    expect(buildNavigation({...caps,roles:['hrms_onboarding_employee']},workflows,1,true,['workflow:read']).flatMap(g => g.items).map(i => i.label)).toEqual(['My Tasks']);
  });
  it('preserves cockpit access when native workflow read is not granted', () => {
    expect(buildNavigation(caps,workflows,0,false,[]).find(g => g.label === 'HR Cockpit')?.items[0].path).toBe('/hrms/cockpit?area=onboarding');
  });
  it('preserves Offers and publishing access', () => {
    expect(buildNavigation(caps,workflows,0,false,[]).flatMap(g => g.items).map(i => i.label)).toEqual(expect.arrayContaining(['Offers','Content & publishing']));
  });
  it('selects only the matching query-specific navigation item', () => {
    expect(isNavigationActive('/hrms/workflows?workflow=exit','/hrms/workflows','?workflow=exit&case=123')).toBe(true);
    expect(isNavigationActive('/hrms/workflows?workflow=employee%20custom','/hrms/workflows','?workflow=exit')).toBe(false);
    expect(isNavigationActive('/hrms/cockpit?area=offers','/hrms/cockpit','?area=publishing')).toBe(false);
    expect(isNavigationActive('/hrms/projects','/hrms/projects/123','')).toBe(true);
    expect(isNavigationActive('/hrms/projects','/hrms/projects-extra','')).toBe(false);
  });
});
