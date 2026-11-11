import { canViewOffers, canViewContent } from '../cockpitAccess';
import { canOpenModule } from '../moduleAccess';
import { BriefcaseBusinessIcon, TrendingUpIcon, UsersIcon, UserRoundPlusIcon, type AnimatedIcon } from '../animated-icons';
import { TaskMenuIcon, HrMenuIcon, OffboardingMenuIcon, OfferMenuIcon, PublishingMenuIcon, CustomerMenuIcon, AllocationMenuIcon, AssetMenuIcon, LeaveMenuIcon, HomeMenuIcon, AgentMenuIcon, DirectoryMenuIcon, MailMenuIcon } from './navigationIcons';
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
/**
 * Whether a page remembered from before sign-in may open for this user: their own
 * tasks or offboarding, or a page their menu (native permissions) offers them.
 * Anything else sends them to My Tasks instead of another user's last page.
 */
export function canLandOn(pathname: string, items: Pick<NavItem, 'path'>[]) {
  if (pathname === '/hrms/my-work' || pathname.startsWith('/hrms/my-offboarding/')) return true;
  return items.some(item => {
    const path = item.path.split('?')[0];
    return pathname === path || pathname.startsWith(path + '/');
  });
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
    { label: 'Tasks', standalone: true, items: [{ path: '/hrms/my-work', label: 'My Tasks', icon: TaskMenuIcon, badge: waiting, keywords: 'home tasks approvals' }] },
    { label: 'HR Cockpit', icon: HrMenuIcon, items: [
      ...(allowed('onboarding:view') || hasWorkflow('HRMS.Employee') ? [{ path: workflowLink('HRMS.Employee', '/hrms/cockpit?area=onboarding'), label: 'Onboarding', icon: UserRoundPlusIcon }] : []),
      ...(allowed('employee:exit') || hasWorkflow('HRMS.Offboarding') ? [{ path: workflowLink('HRMS.Offboarding', '/hrms/cockpit?area=offboarding'), label: 'Offboarding', icon: OffboardingMenuIcon }] : []),
      ...(canViewOffers(caps) ? [{ path: '/hrms/cockpit?area=offers', label: 'Offers', icon: OfferMenuIcon }] : []),
      ...(canViewContent(caps) ? [{ path: '/hrms/cockpit?area=publishing', label: 'Content & publishing', icon: PublishingMenuIcon }] : []),
    ] },
    { label: 'Manager Cockpit', icon: BriefcaseBusinessIcon, items: [
      ...(allowed('customer:view') ? [{ path: '/hrms/customers', label: 'Customers', icon: CustomerMenuIcon }] : []),
      ...(allowed('project:view') ? [{ path: '/hrms/projects', label: 'Projects', icon: BriefcaseBusinessIcon }] : []),
      ...(allowed('allocation:view') ? [{ path: '/hrms/allocations', label: 'Allocations', icon: AllocationMenuIcon }] : []),
    ] },
    { label: 'Assets', standalone: true, items: allowed('asset:view') ? [{ path: '/hrms/assets', label: 'Asset Management', icon: AssetMenuIcon }] : [] },
    { label: 'Employee Self Service', icon: UsersIcon, items: [
      ...(canOpenModule('leave', caps) ? [{ path: '/hrms/leave', label: 'Leave Requests', icon: LeaveMenuIcon }] : []),
      ...(allowed('wfh:view') ? [{ path: '/hrms/work-from-home', label: 'Work from Home', icon: HomeMenuIcon }] : []),
      ...(canOpenModule('performance', caps) ? [{ path: '/hrms/performance', label: 'Performance', icon: TrendingUpIcon }] : []),
    ] },
    { label: 'Workspace', standalone: true, items: [
      ...(allowed('platform:configure') && permissions.includes('agent:read') ? [{ path: '/agent', label: 'Agent Mode', icon: AgentMenuIcon }] : []),
      ...(allowed('employee:read') ? [{ path: '/hrms/employees', label: 'Org Directory', icon: DirectoryMenuIcon }] : []),
      ...(inboxEnabled ? [{ path: '/hrms/uat-inbox', label: 'UAT email inbox', icon: MailMenuIcon, keywords: 'mailpit test mailbox emails' }] : []),
    ] },
  ];
  return groups.filter(group => group.items.length > 0);
}
