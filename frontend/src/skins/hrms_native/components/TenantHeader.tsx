import { Check, ChevronsUpDown } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useHrmsCapabilities, useHrmsOrganization } from '../capabilities';
import { BrandLogo } from './Brand';

export default function TenantHeader() {
  const organization = useHrmsOrganization();
  const capabilities = useHrmsCapabilities();
  const org = organization.data;
  const roles = capabilities.data?.roles.map(role => role === 'superadmin' ? 'Super Admin' :
    role.replace(/^hrms_/, '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())).join(' · ')
    ?? (capabilities.isPending ? 'Loading role…' : 'Role unavailable');
  const initials = org?.name.trim().slice(0, 2).toUpperCase() || '…';
  return <div className="hrms-tenant-header">
    {org ? <details className="hrms-tenant-picker" onKeyDown={event => {
      if (event.key === 'Escape') {
        event.currentTarget.open = false;
        event.currentTarget.querySelector('summary')?.focus();
      }
    }}>
      <summary aria-label={`Current organization: ${org.name}`}>
        <span className="hrms-tenant-avatar" aria-hidden="true">{initials}</span>
        <span className="hrms-tenant-identity"><strong title={org.name}>{org.name}</strong><span><i aria-hidden="true" />{roles}</span></span>
        <ChevronsUpDown size={16} aria-hidden="true" />
      </summary>
      <div className="hrms-tenant-popover">
        <p className="hrms-tenant-caption">Current organization</p>
        <div className="hrms-tenant-selected">
          <span className="hrms-tenant-avatar" aria-hidden="true">{initials}</span>
          <span className="hrms-tenant-identity"><strong>{org.name}</strong><span>{roles}</span></span>
          <Check size={18} aria-label="Current organization" />
        </div>
        {capabilities.data?.capabilities.includes('platform:configure') && <Link to="/settings?tab=organizations" onClick={event => {
          const picker = event.currentTarget.closest('details');
          if (picker) picker.open = false;
        }}>Organization settings</Link>}
      </div>
    </details> : <div className="hrms-tenant-feedback" role={organization.isError ? 'alert' : 'status'}>
      {organization.isPending ? 'Loading organization…' : <><span>Organization unavailable</span><button onClick={() => void organization.refetch()}>Retry</button></>}
    </div>}
    <Link to="/hrms/my-work" className="hrms-sidebar-logo" aria-label="Newtuple HRMS home"><BrandLogo /></Link>
  </div>;
}
