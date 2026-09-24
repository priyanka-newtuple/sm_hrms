/**
 * The document type and multiplicity of a `document` field. The type is what
 * decides where uploads are stored (its metadata.storage_provider) and which
 * file extensions are accepted, so it is required.
 */

import { Switch } from '@/components/ui/switch';
import { useDocumentTypes } from '@/core/hooks/useDocumentTypes';
import type { FormField } from '@/core/types';
import { CONFIG_INPUT_CLASS, CONFIG_LABEL_CLASS, CONFIG_PANEL_CLASS } from './styles';

type DocumentConfigProps = {
  field: FormField;
  canWrite: boolean;
  onChange: (patch: Partial<FormField>) => void;
};

export default function DocumentConfig({ field, canWrite, onChange }: DocumentConfigProps) {
  const { documentTypes } = useDocumentTypes();
  const config = field.document_config ?? {};

  return (
    <div className={CONFIG_PANEL_CLASS}>
      <div>
        <label className={CONFIG_LABEL_CLASS}>
          Document type <span className="text-destructive">*</span>
        </label>
        <select
          value={config.type_id ?? ''}
          onChange={(event) =>
            onChange({ document_config: { ...config, type_id: event.target.value || undefined } })
          }
          disabled={!canWrite}
          className={CONFIG_INPUT_CLASS}
        >
          <option value="">Select a document type...</option>
          {documentTypes.map((type) => (
            <option key={type.type_id} value={type.type_id}>
              {type.display_name}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-muted-foreground">
          Decides where uploads are stored and which file types are accepted. Manage these in
          Settings → Documents.
        </p>
      </div>

      <div className="flex items-center justify-between py-1">
        <div>
          <span className="text-sm font-medium text-foreground">Allow multiple files</span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            The value is always a list; this only caps it at one entry.
          </p>
        </div>
        <Switch
          checked={config.multiple !== false}
          onCheckedChange={(checked) => onChange({ document_config: { ...config, multiple: checked } })}
          disabled={!canWrite}
        />
      </div>
    </div>
  );
}
