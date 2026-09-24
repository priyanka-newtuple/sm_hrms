/**
 * BasicsStep
 *
 * First wizard step: role identity (display name, system name, description, priority).
 */

import Input, { Textarea } from '../../../../core/components/Input';
import { PRIORITY_MIN, PRIORITY_MAX } from '../../../../core/hooks/useRoleEditor';

interface BasicsForm {
  name: string;
  displayName: string;
  description: string;
  priority: number;
  isSystem: boolean;
}

interface BasicsStepProps {
  form: BasicsForm;
  isEditing: boolean;
  onDisplayNameChange: (value: string) => void;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onPriorityChange: (value: number) => void;
}

export default function BasicsStep({
  form,
  isEditing,
  onDisplayNameChange,
  onNameChange,
  onDescriptionChange,
  onPriorityChange,
}: BasicsStepProps) {
  return (
    <div className="space-y-5">
      <Input
        name="role-display-name"
        label="Display Name"
        value={form.displayName}
        onChange={(e) => onDisplayNameChange(e.target.value)}
        placeholder="e.g., Senior Recruiter"
        disabled={form.isSystem}
      />

      <Input
        name="role-system-name"
        label="System Name"
        value={form.name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="e.g., senior_recruiter"
        disabled={isEditing}
        helperText="Unique identifier. Cannot be changed after creation."
      />

      <Textarea
        name="role-description"
        label="Description"
        value={form.description}
        onChange={(e) => onDescriptionChange(e.target.value)}
        placeholder="What can users with this role do?"
        rows={3}
      />

      <Input
        name="role-priority"
        type="number"
        label="Priority"
        value={form.priority}
        onChange={(e) => onPriorityChange(parseInt(e.target.value, 10) || 0)}
        min={PRIORITY_MIN}
        max={PRIORITY_MAX}
        disabled={form.isSystem}
        className="w-32"
        helperText={
          form.isSystem
            ? 'System role priority cannot be changed.'
            : `Higher priority roles take precedence in conflicts. Range: ${PRIORITY_MIN}-${PRIORITY_MAX}.`
        }
      />
    </div>
  );
}
