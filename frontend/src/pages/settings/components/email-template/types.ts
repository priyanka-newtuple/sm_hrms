import type {
  EmailTemplate as CoreEmailTemplate,
  EmailTemplateCreateRequest,
  EmailTemplateUpdateRequest,
} from "../../../../core/types";

export type EntityValue = string | null;

export interface Template {
  templateId: string;
  organizationId: string | null;
  name: string;
  subject: string;
  bodyHtml: string;
  formId: string | null;
  entityType: EntityValue;
  isSystem: boolean;
  createdAt: string;
  isNew?: boolean;
}

export type {
  EmailTemplateCreateRequest,
  EmailTemplateUpdateRequest,
};

export type EmailTemplateApiModel = CoreEmailTemplate;

export interface Variable {
  key: string;
  label?: string;
  desc?: string;
}

export interface EntityType {
  value: EntityValue;
  label: string;
}

export interface FormOption {
  value: string;
  label: string;
  fieldCount: number;
  isActive?: boolean;
}

export interface TemplateValidationErrors {
  name?: string;
  subject?: string;
  bodyHtml?: string;
}
