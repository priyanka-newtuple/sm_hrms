/**
 * FieldPermissionsStep
 *
 * Wizard step: per-field view / edit / mask controls, grouped by entity type.
 */

import { Shield, Eye, EyeOff, Check, X, Pencil, Lock, Unlock } from 'lucide-react';
import type { EntityFieldMap, FieldPermState } from '../../../../core/types';
import PermissionToggle from './PermissionToggle';

interface FieldPermissionsStepProps {
  entityTypes: { key: string; label: string }[];
  entityFields: EntityFieldMap;
  getFieldPerm: (entityType: string, fieldName: string) => FieldPermState;
  onSetFieldPerm: (entityType: string, fieldName: string, updates: Partial<FieldPermState>) => void;
}

export default function FieldPermissionsStep({
  entityTypes,
  entityFields,
  getFieldPerm,
  onSetFieldPerm,
}: FieldPermissionsStepProps) {
  return (
    <div>
      <p className="mb-4 text-sm text-muted-foreground">
        Restrict visibility or editing of specific fields. By default, all fields are visible and editable.
      </p>

      {Object.entries(entityFields).map(([entityType, fields]) => {
        const entityLabel = entityTypes.find((et) => et.key === entityType)?.label || entityType;
        return (
          <div key={entityType} className="mb-6">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Shield className="h-4 w-4 text-muted-foreground" />
              {entityLabel}
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">Field</th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground">
                      <div className="flex items-center justify-center gap-1">
                        <Eye className="h-3.5 w-3.5" /> View
                      </div>
                    </th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground">
                      <div className="flex items-center justify-center gap-1">
                        <Pencil className="h-3.5 w-3.5" /> Edit
                      </div>
                    </th>
                    <th className="px-3 py-2 text-center font-medium text-muted-foreground">
                      <div className="flex items-center justify-center gap-1">
                        <Lock className="h-3.5 w-3.5" /> Mask
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((field) => {
                    const fp = getFieldPerm(entityType, field.key);
                    return (
                      <tr key={field.key} className="border-b border-border hover:bg-muted/50">
                        <td className="px-3 py-2.5 text-foreground">{field.label}</td>
                        <td className="px-3 py-2.5 text-center">
                          <PermissionToggle
                            pressed={fp.can_view}
                            onToggle={() => onSetFieldPerm(entityType, field.key, { can_view: !fp.can_view })}
                            label={`View ${field.label}`}
                            onIcon={<Eye className="h-4 w-4" />}
                            offIcon={<EyeOff className="h-4 w-4" />}
                            offTone="danger"
                            className="mx-auto"
                          />
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <PermissionToggle
                            pressed={fp.can_edit}
                            onToggle={() => onSetFieldPerm(entityType, field.key, { can_edit: !fp.can_edit })}
                            label={`Edit ${field.label}`}
                            onIcon={<Check className="h-4 w-4" />}
                            offIcon={<X className="h-4 w-4" />}
                            offTone="danger"
                            className="mx-auto"
                          />
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <PermissionToggle
                            pressed={fp.mask_value}
                            onToggle={() => onSetFieldPerm(entityType, field.key, { mask_value: !fp.mask_value })}
                            label={`Mask ${field.label}`}
                            onIcon={<Lock className="h-4 w-4" />}
                            offIcon={<Unlock className="h-4 w-4" />}
                            tone="amber"
                            className="mx-auto"
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
      })}
    </div>
  );
}
