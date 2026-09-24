/**
 * Modal dialog for rotating the secret credentials of an existing connector
 * (bearer token, API key, or basic-auth username/password). Only renders the
 * fields relevant to the connector's `auth_type`.
 */

import { useState } from 'react';
import { KeyRound, X } from 'lucide-react';
import { toast } from 'sonner';

import type { Connector } from '../../../../../core/types';

interface SecretField {
  key: string;
  label: string;
}

function secretFieldsFor(authType: string): SecretField[] {
  switch (authType) {
    case 'bearer':      return [{ key: 'token', label: 'Bearer token' }];
    case 'api_key':     return [{ key: 'api_key', label: 'API key' }];
    case 'basic':       return [{ key: 'username', label: 'Username' }, { key: 'password', label: 'Password' }];
    default:            return [];
  }
}

interface RotateSecretModalProps {
  connector: Connector;
  onSave: (secrets: Record<string, string>) => Promise<void>;
  onClose: () => void;
}

export default function RotateSecretModal({ connector, onSave, onClose }: RotateSecretModalProps) {
  const fields = secretFieldsFor(connector.auth_type ?? '');
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, ''])),
  );
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const filled = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
    if (!Object.keys(filled).length) {
      toast.error('Enter at least one value to update.');
      return;
    }
    setSaving(true);
    try {
      await onSave(filled);
      toast.success('Secret updated.');
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to update secret.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Dialog */}
      <div className="relative z-10 w-full max-w-sm rounded-xl border border-border bg-card p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm font-semibold">Rotate secret</p>
              <p className="text-xs text-muted-foreground">{connector.name}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          {fields.map((f) => (
            <div key={f.key} className="space-y-1">
              <label className="text-xs font-medium">{f.label}</label>
              <input
                type="password"
                value={values[f.key] ?? ''}
                onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                placeholder="Enter new value"
                autoComplete="new-password"
                className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-8 rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="h-8 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Update'}
          </button>
        </div>
      </div>
    </div>
  );
}
