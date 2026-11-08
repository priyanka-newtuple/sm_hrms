/** Presentation of native Entity Access grants; API authorization remains native. */
type Access = { capabilities: string[] } | undefined;
const contentGrants: Record<string, string> = {
  'HRMS.Policy': 'content:policy:view',
  'HRMS.LearningEvent': 'content:learning:view',
  'HRMS.HolidayCalendar': 'content:holiday:view',
  'HRMS.JobDescription': 'content:job-description:view',
  'HRMS.JobOpening': 'content:job-opening:view',
};
export function canViewOffers(access: Access) {
  return Boolean(access?.capabilities.includes('cockpit:view') && access.capabilities.includes('offer:view'));
}
export function accessibleContentTypes(access: Access): string[] {
  if (!access?.capabilities.includes('cockpit:view')) return [];
  return Object.keys(contentGrants).filter(type => access.capabilities.includes(contentGrants[type]));
}
export function canViewContent(access: Access) {
  return accessibleContentTypes(access).length > 0;
}
