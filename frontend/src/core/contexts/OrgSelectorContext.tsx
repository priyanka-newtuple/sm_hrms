/**
 * OrgSelectorContext
 *
 * Provides organization selection capability for super-admins.
 * Super-admins can view/manage settings for any organization.
 * Regular users always see their own organization.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { useAuth } from '../auth';
import { organizations } from '../services/api';
import { isSuperAdminUser } from '../utils';

interface Organization {
  id: string;
  name: string;
  slug: string;
  status: string;
}

interface OrgSelectorContextType {
  // Currently selected organization ID (for API calls)
  selectedOrgId: string | undefined;
  // Selected organization details
  selectedOrg: Organization | null;
  // All available organizations (for super-admins)
  availableOrgs: Organization[];
  // Whether the current user is a super-admin
  isSuperAdmin: boolean;
  // Loading state
  isLoading: boolean;
  // Select a different organization (super-admin only)
  selectOrg: (orgId: string | undefined) => void;
}

const OrgSelectorContext = createContext<OrgSelectorContextType | null>(null);

interface OrgSelectorProviderProps {
  children: ReactNode;
}

export function OrgSelectorProvider({ children }: OrgSelectorProviderProps) {
  const { user } = useAuth();
  const [selectedOrgId, setSelectedOrgId] = useState<string | undefined>(undefined);
  const [availableOrgs, setAvailableOrgs] = useState<Organization[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // isSuperAdminUser is true only for admin/superadmin roles held in the
  // Platform org — matches Settings and OrgSwitcher, and the backend's
  // require_platform_permission gate.
  const isSuperAdmin = isSuperAdminUser(user);

  // Fetch available organizations for super-admins
  useEffect(() => {
    if (!isSuperAdmin) {
      setAvailableOrgs([]);
      setSelectedOrgId(user?.organizationId);
      return;
    }

    const fetchOrgs = async () => {
      setIsLoading(true);
      try {
        const response = await organizations.list('active');
        setAvailableOrgs(
          response.items.map((org) => ({
            id: org.id,
            name: org.name,
            slug: org.slug,
            status: org.status,
          }))
        );
      } catch (error) {
        console.error('Failed to fetch organizations:', error);
        setAvailableOrgs([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchOrgs();
  }, [isSuperAdmin, user?.organizationId]);

  useEffect(() => {
    if (!isSuperAdmin) {
      if (user?.organizationId && selectedOrgId !== user.organizationId) {
        setSelectedOrgId(user.organizationId);
      }
      return;
    }

    if (selectedOrgId) {
      return;
    }

    if (user?.organizationId && availableOrgs.some((org) => org.id === user.organizationId)) {
      setSelectedOrgId(user.organizationId);
      return;
    }

    if (availableOrgs.length > 0) {
      setSelectedOrgId(availableOrgs[0].id);
    }
  }, [availableOrgs, isSuperAdmin, selectedOrgId, user?.organizationId]);

  // Get selected organization details
  const selectedOrg = selectedOrgId
    ? availableOrgs.find((org) => org.id === selectedOrgId) || null
    : null;

  const selectOrg = useCallback((orgId: string | undefined) => {
    setSelectedOrgId(orgId);
  }, []);

  const value: OrgSelectorContextType = {
    selectedOrgId,
    selectedOrg,
    availableOrgs,
    isSuperAdmin,
    isLoading,
    selectOrg,
  };

  return (
    <OrgSelectorContext.Provider value={value}>
      {children}
    </OrgSelectorContext.Provider>
  );
}

export function useOrgSelector(): OrgSelectorContextType {
  const context = useContext(OrgSelectorContext);
  if (!context) {
    throw new Error('useOrgSelector must be used within an OrgSelectorProvider');
  }
  return context;
}
