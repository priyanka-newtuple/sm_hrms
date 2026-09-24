/**
 * RoleEditor
 *
 * Modal wizard for creating and editing RBAC roles:
 * Basics -> Entity Permissions -> Field Permissions.
 *
 * All data/state/persistence lives in useRoleEditor; this component
 * orchestrates layout and step navigation only.
 */

import { useState } from 'react';
import { Loader2, ChevronRight, ChevronLeft, Shield, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import AlertBanner from '../../../../core/components/AlertBanner';
import FormDialog from '../../../../core/components/FormDialog';
import { useRoleEditor } from '../../../../core/hooks/useRoleEditor';
import { WIZARD_STEPS, type WizardStep } from './constants';
import RoleWizardSteps from './RoleWizardSteps';
import BasicsStep from './BasicsStep';
import EntityPermissionsStep from './EntityPermissionsStep';
import FieldPermissionsStep from './FieldPermissionsStep';

interface RoleEditorProps {
  roleId: string | null; // null = creating new
  onClose: () => void;
  onSave: () => void;
}

export default function RoleEditor({ roleId, onClose, onSave }: RoleEditorProps) {
  const editor = useRoleEditor(roleId);
  const [step, setStep] = useState<WizardStep>('basics');

  const currentStepIndex = WIZARD_STEPS.findIndex((s) => s.key === step);
  const isLastStep = currentStepIndex === WIZARD_STEPS.length - 1;
  // Only the Basics step gates advancing; later steps are always valid.
  const canAdvance = step === 'basics' ? editor.canSave : true;

  const handleSave = async () => {
    if (await editor.save()) {
      onSave();
    }
  };

  return (
    <FormDialog
      open
      onClose={onClose}
      title={editor.isEditing ? 'Edit Role' : 'Create Role'}
      icon={<Shield className="h-4 w-4" />}
      size="lg"
      bodyClassName="p-0"
      footer={(
        <div className="flex items-center justify-between">
          <div>
            {currentStepIndex > 0 && (
              <Button
                variant="ghost"
                onClick={() => setStep(WIZARD_STEPS[currentStepIndex - 1].key)}
                icon={<ChevronLeft className="h-4 w-4" />}
              >
                Back
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            {isLastStep ? (
              <Button
                variant="primary"
                onClick={handleSave}
                disabled={editor.isSaving || !editor.canSave}
                loading={editor.isSaving}
                icon={<Check className="h-4 w-4" />}
              >
                {editor.isEditing ? 'Save Changes' : 'Create Role'}
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={() => setStep(WIZARD_STEPS[currentStepIndex + 1].key)}
                disabled={!canAdvance}
                icon={<ChevronRight className="h-4 w-4" />}
                iconPosition="right"
              >
                Next
              </Button>
            )}
          </div>
        </div>
      )}
    >
      <RoleWizardSteps
        steps={WIZARD_STEPS}
        currentIndex={currentStepIndex}
        canAdvance={canAdvance}
        onSelect={setStep}
      />

      <div className="space-y-6 p-6">
        {editor.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-cobalt" />
          </div>
        ) : (
          <>
            {step === 'basics' && (
              <BasicsStep
                form={editor.form}
                isEditing={editor.isEditing}
                onDisplayNameChange={editor.setDisplayName}
                onNameChange={editor.setName}
                onDescriptionChange={editor.setDescription}
                onPriorityChange={editor.setPriority}
              />
            )}

            {step === 'entity' && (
              <EntityPermissionsStep
                entityTypes={editor.entityTypes}
                entityPerms={editor.entityPerms}
                onToggle={editor.toggleEntityPerm}
                onToggleAllEntity={editor.toggleAllForEntity}
                onToggleAllAction={editor.toggleAllForAction}
              />
            )}

            {step === 'fields' && (
              <FieldPermissionsStep
                entityTypes={editor.entityTypes}
                entityFields={editor.entityFields}
                getFieldPerm={editor.getFieldPerm}
                onSetFieldPerm={editor.setFieldPerm}
              />
            )}
          </>
        )}

        {editor.error && <AlertBanner tone="error">{editor.error}</AlertBanner>}
      </div>
    </FormDialog>
  );
}
