/**
 * EntityPermissionsStep
 *
 * Wizard step: matrix of entity type x action permissions.
 */

import { Check, X } from 'lucide-react';
import type { PermissionAction, EntityPermMap } from '../../../../core/types';
import { ACTIONS } from './constants';
import PermissionToggle from './PermissionToggle';

interface EntityPermissionsStepProps {
  entityTypes: { key: string; label: string }[];
  entityPerms: EntityPermMap;
  onToggle: (entityType: string, action: PermissionAction) => void;
  onToggleAllEntity: (entityType: string) => void;
  onToggleAllAction: (action: PermissionAction) => void;
}

const onIcon = <Check className="h-4 w-4" />;
const offIcon = <X className="h-4 w-4" />;

export default function EntityPermissionsStep({
  entityTypes,
  entityPerms,
  onToggle,
  onToggleAllEntity,
  onToggleAllAction,
}: EntityPermissionsStepProps) {
  return (
    <div>
      <p className="mb-4 text-sm text-muted-foreground">
        Configure which actions this role can perform on each entity type.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Entity</th>
              {ACTIONS.map((a) => (
                <th key={a.key} className="px-3 py-2 text-center font-medium text-muted-foreground">
                  <button
                    type="button"
                    onClick={() => onToggleAllAction(a.key)}
                    title={`Toggle all ${a.label}`}
                    className="font-medium transition-colors hover:text-cobalt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cobalt/40"
                  >
                    {a.label}
                  </button>
                </th>
              ))}
              <th className="px-3 py-2 text-center font-medium text-muted-foreground">All</th>
            </tr>
          </thead>
          <tbody>
            {entityTypes.map((et) => {
              const perms = entityPerms[et.key] || ({} as Record<PermissionAction, boolean>);
              const allEnabled = ACTIONS.every((a) => perms[a.key]);
              return (
                <tr key={et.key} className="border-b border-border hover:bg-muted/50">
                  <td className="px-3 py-3 font-medium text-foreground">{et.label}</td>
                  {ACTIONS.map((a) => (
                    <td key={a.key} className="px-3 py-3 text-center">
                      <PermissionToggle
                        pressed={!!perms[a.key]}
                        onToggle={() => onToggle(et.key, a.key)}
                        label={`${a.label} ${et.label}`}
                        onIcon={onIcon}
                        offIcon={offIcon}
                      />
                    </td>
                  ))}
                  <td className="px-3 py-3 text-center">
                    <PermissionToggle
                      pressed={allEnabled}
                      onToggle={() => onToggleAllEntity(et.key)}
                      label={`Toggle all permissions for ${et.label}`}
                      onIcon={onIcon}
                      offIcon={offIcon}
                      tone="cobalt"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
