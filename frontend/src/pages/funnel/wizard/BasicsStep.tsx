import { useEffect, useState } from 'react';
import { AlertCircle, Lock } from 'lucide-react';
import Input, { FormField, Textarea } from '../../../core/components/Input';
import EntityTypeSelect from '../../settings/components/entity-types/EntityTypeSelect';
import ServiceSelect from '../components/ServiceSelect';

const SLUG_REGEX = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;

interface BasicsStepProps {
  machineName: string;
  machineKey: string;
  displayName: string;
  description: string;
  entityType: string;
  serviceId: string | null;
  identifierLocked: boolean;
  onChange: (patch: {
    machineName?: string;
    machineKey?: string;
    displayName?: string;
    description?: string;
    entityType?: string;
    serviceId?: string | null;
  }) => void;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 50);
}

export default function BasicsStep({
  machineName,
  machineKey,
  displayName,
  description,
  entityType,
  serviceId,
  identifierLocked,
  onChange,
}: BasicsStepProps) {
  const [machineKeyError, setMachineKeyError] = useState<string | null>(null);
  const [autoIdentifier, setAutoIdentifier] = useState(!machineKey);

  // Auto-generate identifier from display name while in auto mode.
  useEffect(() => {
    if (!autoIdentifier || identifierLocked) return;
    const slug = slugify(displayName) || 'untitled';
    if (slug !== machineKey || slug !== machineName) {
      onChange({ machineKey: slug, machineName: slug });
    }
  }, [autoIdentifier, displayName, identifierLocked, machineKey, machineName, onChange]);

  // Validate identifier on change.
  useEffect(() => {
    if (!machineKey) {
      setMachineKeyError(null);
      return;
    }
    if (machineKey.length > 128) {
      setMachineKeyError('Identifier must be 128 characters or less.');
      return;
    }
    if (!SLUG_REGEX.test(machineKey)) {
      setMachineKeyError(
        'Identifier must be lowercase snake_case (letters, numbers, underscores; must start with a letter).',
      );
      return;
    }
    setMachineKeyError(null);
  }, [machineKey]);

  const handleIdentifierChange = (value: string) => {
    setAutoIdentifier(false);
    onChange({ machineKey: value, machineName: value });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium text-foreground mb-1">Basic Information</h3>
        <p className="text-sm text-muted-foreground">
          Display name, system identifier, and the entity this workflow operates on.
        </p>
      </div>

      <Input
        id="display-name"
        value={displayName}
        onChange={(e) => onChange({ displayName: e.target.value })}
        label="Display Name"
        required
        placeholder="e.g. Standard Statemachine Pipeline"
        helperText="Friendly name shown in the UI."
      />

      <FormField
        label={(
          <>
            Identifier
            {identifierLocked && (
              <span className="ml-2 inline-flex items-center gap-1 text-xs text-warning">
                <Lock className="w-3 h-3" />
                Locked after publishing
              </span>
            )}
          </>
        )}
        required
      >
        <input
          type="text"
          id="machine-key"
          value={machineKey}
          onChange={(e) => handleIdentifierChange(e.target.value)}
          placeholder="standard_hiring"
          disabled={identifierLocked}
          className={`w-full px-4 py-2.5 bg-card border rounded-lg text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:border-cobalt focus:ring-1 focus:ring-cobalt ${
            machineKeyError ? 'border-destructive/30' : 'border-border'
          } ${identifierLocked ? 'bg-muted/50 text-muted-foreground' : ''}`}
        />
        {machineKeyError && (
          <p className="mt-1 text-xs text-destructive flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            {machineKeyError}
          </p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Lowercase snake_case. Used for the machine name and machine key.
        </p>
        {autoIdentifier && !identifierLocked && (
          <p className="mt-1 text-xs text-cobalt">Auto-generated from display name</p>
        )}
      </FormField>

      <EntityTypeSelect
        id="entity-type"
        value={entityType}
        onChange={(value) => onChange({ entityType: value })}
        required
        helperText="Domain entity this workflow operates on. Manage the list in Settings › Entities."
      />

      <ServiceSelect
        value={serviceId}
        onChange={(value) => onChange({ serviceId: value })}
      />

      <Textarea
        id="description"
        value={description}
        onChange={(e) => onChange({ description: e.target.value })}
        label="Description"
        placeholder="Describe when to use this workflow..."
        rows={3}
        helperText="Optional notes shown to users."
        className="resize-none"
      />
    </div>
  );
}
