import { useState, useCallback } from 'react';
import { organizations as orgsApi } from '../services/api';
import { EMAIL_REGEX } from '../utils';

export type PendingMember = {
  email: string;
  full_name: string;
  role: string;
};

type UseAddOrgReturn = {
  step: 1 | 2;
  // step 1
  name: string;
  slug: string;
  submitting: boolean;
  error: string | null;
  setName: (v: string) => void;
  setSlug: (v: string) => void;
  handleCreateOrg: (e: React.FormEvent) => Promise<void>;
  // step 2
  members: PendingMember[];
  memberEmail: string;
  memberName: string;
  memberRole: string;
  addingMember: boolean;
  memberError: string | null;
  setMemberEmail: (v: string) => void;
  setMemberName: (v: string) => void;
  setMemberRole: (v: string) => void;
  handleAddMember: () => Promise<void>;
  reset: () => void;
};

export function useAddOrg(): UseAddOrgReturn {
  const [step, setStep] = useState<1 | 2>(1);
  const [createdOrgId, setCreatedOrgId] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [members, setMembers] = useState<PendingMember[]>([]);
  const [memberEmail, setMemberEmail] = useState('');
  const [memberName, setMemberName] = useState('');
  const [memberRole, setMemberRole] = useState('');
  const [addingMember, setAddingMember] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStep(1);
    setCreatedOrgId(null);
    setName('');
    setSlug('');
    setError(null);
    setSubmitting(false);
    setMembers([]);
    setMemberEmail('');
    setMemberName('');
    setMemberRole('');
    setMemberError(null);
    setAddingMember(false);
  }, []);

  const handleCreateOrg = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    setSubmitting(true);
    setError(null);

    // Preflight duplicate check — separate try/catch so a list() failure never
    // surfaces as "Failed to create organization". If total > items.length the
    // backend unique constraint is the real guard; we can't fetch all pages here.
    let duplicate = false;
    try {
      const existing = await orgsApi.list();
      duplicate = existing.items.some(
        (o) => o.name.toLowerCase() === trimmedName.toLowerCase()
      );
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401 || status === 403) {
        setError('Session expired. Please refresh and try again.');
        setSubmitting(false);
        return;
      }
      console.warn('Preflight duplicate check failed, proceeding:', err);
    }

    if (duplicate) {
      setError(`An organization named "${trimmedName}" already exists.`);
      setSubmitting(false);
      return;
    }

    try {
      const org = await orgsApi.create({
        name: trimmedName,
        ...(slug.trim() ? { slug: slug.trim() } : {}),
      });
      setCreatedOrgId(org.id);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create organization');
    } finally {
      setSubmitting(false);
    }
  }, [name, slug]);

  const handleAddMember = useCallback(async () => {
    if (!memberEmail.trim() || !EMAIL_REGEX.test(memberEmail.trim())) {
      setMemberError('Valid email required');
      return;
    }
    if (!memberName.trim()) {
      setMemberError('Full name required');
      return;
    }
    if (!memberRole) {
      setMemberError('Role required');
      return;
    }
    if (!createdOrgId) return;
    setMemberError(null);
    setAddingMember(true);
    try {
      await orgsApi.createUser(createdOrgId, {
        email: memberEmail.trim(),
        full_name: memberName.trim(),
        role: memberRole,
        status: 'active',
      });
      setMembers((prev) => [
        ...prev,
        { email: memberEmail.trim(), full_name: memberName.trim(), role: memberRole },
      ]);
      setMemberEmail('');
      setMemberName('');
    } catch (err) {
      setMemberError(err instanceof Error ? err.message : 'Failed to add member');
    } finally {
      setAddingMember(false);
    }
  }, [createdOrgId, memberEmail, memberName, memberRole]);

  return {
    step,
    name, slug, submitting, error,
    setName, setSlug, handleCreateOrg,
    members, memberEmail, memberName, memberRole,
    addingMember, memberError,
    setMemberEmail, setMemberName, setMemberRole, handleAddMember,
    reset,
  };
}
