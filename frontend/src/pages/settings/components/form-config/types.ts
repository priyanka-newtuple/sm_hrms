import type { FormField, PicklistOption } from '../../../../core/types';

export interface EditingField {
  index: number;
  field: FormField;
  isNew: boolean;
  originalId?: string; // snapshot of field.id at edit-open time; used to re-locate the field after list mutations
}

export interface NewSchemaForm {
  entityType: string;
  name: string;
}

export interface EditingPicklist {
  id: string;
  name: string;
  options: PicklistOption[];
  isNew: boolean;
}
