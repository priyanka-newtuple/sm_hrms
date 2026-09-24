import UnifiedIntegrationsPanel from './UnifiedIntegrationsPanel';
import { useOrgSelector } from '../../../../core/contexts/OrgSelectorContext';
import OrgSelector from '../../../../core/components/OrgSelector';

export default function IntegrationsTab() {
  const { selectedOrgId, isSuperAdmin } = useOrgSelector();

  return (
    <div className="space-y-6">
      {isSuperAdmin && (
        <div className="flex items-center justify-between rounded-xl border border-warning/30 bg-warning-subtle p-4">
          <div className="flex items-center gap-3">
            <span className="text-sm text-warning">
              <strong>Super-Admin Mode:</strong> You can view and manage settings for any organization.
            </span>
          </div>
          <OrgSelector />
        </div>
      )}

      <UnifiedIntegrationsPanel organizationId={selectedOrgId} />
    </div>
  );
}
