import { canOpenModule } from '../moduleAccess';
import { BookTextIcon, BriefcaseBusinessIcon, CalendarDaysIcon, LayoutGridIcon, SlidersHorizontalIcon, TrendingUpIcon, UsersIcon, WorkflowIcon, ZapIcon, type AnimatedIcon } from '../animated-icons';
export interface NavItem { path: string; label: string; icon: AnimatedIcon; badge?: number; keywords?: string }
export interface NavGroup { label: string; standalone?: boolean; icon?: AnimatedIcon; items: NavItem[] }
type Capabilities = { capabilities: string[]; roles: string[]; employee_profile?: boolean };
type Workflow = { entity_type: string; machine_name: string; name: string };
export function isNavigationActive(target: string, pathname: string, search: string) {
  const [path, query] = target.split('?');
  if (pathname !== path && !pathname.startsWith(path + '/')) return false;
  const actual = new URLSearchParams(search);
  return [...new URLSearchParams(query)].every(([key, value]) => actual.get(key) === value);
}
export function buildNavigation(caps: Capabilities | undefined, workflows: Workflow[], waiting: number, inboxEnabled: boolean, permissions: string[]): NavGroup[] {
  const allowed = (key: string) => caps?.capabilities.includes(key) ?? false;
  const published = permissions.includes('workflow:read') ? workflows : [];
  const hasWorkflow = (entity: string) => published.some(item => item.entity_type === entity);
  const workflowLink = (entity: string, fallback: string) => {
    const workflow = published.find(item => item.entity_type === entity);
    return workflow ? `/hrms/workflows?workflow=${encodeURIComponent(workflow.machine_name)}` : fallback;
  };
  const groups: NavGroup[] = [
    { label: 'Tasks', standalone: true, items: [{ path: '/hrms/my-work', label: 'My Tasks', icon: ZapIcon, badge: waiting, keywords: 'home tasks approvals' }] },
    { label: 'HR Cockpit', icon: SlidersHorizontalIcon, items: [
      ...(allowed('onboarding:view') || hasWorkflow('HRMS.Employee') ? [{ path: workflowLink('HRMS.Employee', '/hrms/cockpit?area=onboarding'), label: 'Onboarding', icon: UsersIcon }] : []),
      ...(allowed('employee:exit') || hasWorkflow('HRMS.Offboarding') ? [{ path: workflowLink('HRMS.Offboarding', '/hrms/cockpit?area=offboarding'), label: 'Offboarding', icon: WorkflowIcon }] : []),
      ...(allowed('cockpit:view') ? [
        { path: '/hrms/cockpit?area=offers', label: 'Offers', icon: BookTextIcon },
        { path: '/hrms/cockpit?area=publishing', label: 'Content & publishing', icon: BookTextIcon },
      ] : []),
    ] },
    { label: 'Manager Cockpit', icon: BriefcaseBusinessIcon, items: allowed('project:view') ? [
      { path: '/hrms/customers', label: 'Customers', icon: UsersIcon },
      { path: '/hrms/projects', label: 'Projects', icon: BriefcaseBusinessIcon },
      { path: '/hrms/allocations', label: 'Allocations', icon: LayoutGridIcon },
    ] : [] },
    { label: 'Assets', standalone: true, items: allowed('asset:view') || allowed('asset:manage') ? [{ path: '/hrms/assets', label: 'Asset Management', icon: LayoutGridIcon }] : [] },
    { label: 'Employee Self Service', icon: UsersIcon, items: [
      ...(canOpenModule('leave', caps) ? [{ path: '/hrms/leave', label: 'Leave Requests', icon: CalendarDaysIcon }] : []),
      ...(allowed('wfh:view') ? [{ path: '/hrms/work-from-home', label: 'Work from Home', icon: CalendarDaysIcon }] : []),
      ...(canOpenModule('performance', caps) ? [{ path: '/hrms/performance', label: 'Performance', icon: TrendingUpIcon }] : []),
    ] },
    { label: 'Workspace', standalone: true, items: [
      ...(allowed('platform:configure') && permissions.includes('agent:read') ? [{ path: '/agent', label: 'Agent Mode', icon: ZapIcon }] : []),
      ...(allowed('employee:read') ? [{ path: '/hrms/employees', label: 'Org Directory', icon: UsersIcon }] : []),
      ...(inboxEnabled ? [{ path: '/hrms/uat-inbox', label: 'UAT email inbox', icon: BookTextIcon, keywords: 'mailpit test mailbox emails' }] : []),
    ] },
  ];
  return groups.map(group => caps?.roles.includes('hrms_onboarding_employee') ? { ...group, items: group.items.filter(item => item.path === '/hrms/my-work') } : group).filter(group => group.items.length > 0);
}
