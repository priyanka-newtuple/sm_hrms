import type { PermissionsSummary } from '../types/rbac';

export type UserRole = string;
export type AuthType = 'local' | 'google' | 'microsoft';
export type OrganizationStatus = 'pending' | 'active' | 'suspended' | 'archived' | 'rejected';

export interface Organization {
  id: string;
  name: string;
  slug: string;
  domain?: string;
  settings: Record<string, unknown>;
  status: OrganizationStatus;
  logoUrl?: string;
  createdAt: string;
  updatedAt: string;
}

export interface OrganizationPublic {
  id: string;
  name: string;
  slug: string;
  logoUrl?: string;
  /** Organization settings blob; carries the per-org theme under `theme`. */
  settings?: Record<string, unknown>;
}

export interface User {
  id: string;
  email: string;
  fullName: string;
  avatarUrl?: string;
  role: UserRole;
  authType: AuthType;
  isActive: boolean;
  organizationId?: string;
  lastLoginAt?: string;
  createdAt: string;
  updatedAt?: string;
}

export interface UserPublic {
  id: string;
  email: string;
  fullName: string;
  avatarUrl?: string;
  role: UserRole;
  authType: AuthType;
  organizationId?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserPublic;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  full_name: string;
  role?: UserRole;
  organization_name?: string; // Required for public email domains
}

export interface RegisterWithOrgCredentials {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
  organization_slug?: string;
}

export interface PendingOrgRegistrationResponse {
  message: string;
  user_id: string;
  organization_id: string;
  organization_name: string;
  status: 'pending_org_approval';
}

export interface GoogleAuthCallback {
  code: string;
  redirect_uri?: string;
}

export interface MicrosoftAuthCallback {
  code: string;
  state: string;
  redirect_uri?: string;
}

export interface MicrosoftAuthUrlResponse {
  url: string;
  state: string;
}

export interface MicrosoftTokenResponse {
  token_type: string;
  id_token: string;
  access_token?: string;
  expires_in?: number;
  user: UserPublic;
}

export interface UserOrganizationMembership {
  id: string | null;
  organizationId: string;
  organizationName: string;
  organizationSlug: string;
  organizationDomain: string | null;
  organizationLogoUrl: string | null;
  organizationStatus: string;
  role: UserRole;
  status: string;
  isCurrent: boolean;
}

export interface UserOrganizationsResponse {
  organizations: UserOrganizationMembership[];
  currentOrganizationId: string | null;
}

export interface AuthContextType {
  user: UserPublic | null;
  organization: OrganizationPublic | null;
  organizations: UserOrganizationMembership[];
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, organizationName?: string) => Promise<void>;
  loginWithGoogle: () => void;
  loginWithMicrosoft: () => void;
  handleGoogleCallback: (code: string) => Promise<void>;
  handleMicrosoftCallback: (code: string, state: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<boolean>;
  switchOrganization: (orgId: string) => Promise<void>;
  /** Re-fetch the active organization (e.g. after updating its settings). */
  refreshOrganization: () => Promise<void>;
  /** Re-fetch the user's organization memberships list (e.g. after creating a new org). */
  refreshOrganizations: () => Promise<void>;
  /** Re-fetch the user's effective permissions (e.g. after publishing a new workflow whose
   *  entity type the user's system role now has access to). */
  refreshPermissions: () => Promise<void>;
  permissions: PermissionsSummary | null;
}
