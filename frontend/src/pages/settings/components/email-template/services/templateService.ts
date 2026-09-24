import type {
  EmailTemplateApiModel,
  EmailTemplateCreateRequest,
  EmailTemplateUpdateRequest,
  Template,
  TemplateValidationErrors,
} from "../types";

export function createDraftTemplate(): Template {
  return {
    templateId: `draft_${Math.random().toString(36).slice(2, 10)}`,
    organizationId: null,
    name: "",
    subject: "",
    bodyHtml: "<p>Write your email here…</p>",
    formId: null,
    entityType: null,
    isSystem: false,
    createdAt: new Date().toISOString(),
    isNew: true,
  };
}

export function filterTemplates(templates: Template[], query: string): Template[] {
  const normalizedQuery = query.trim().toLowerCase();

  if (!normalizedQuery) {
    return templates;
  }

  return templates.filter(
    (template) =>
      template.name.toLowerCase().includes(normalizedQuery) ||
      template.subject.toLowerCase().includes(normalizedQuery),
  );
}

export function validateTemplateDraft(template: Template): TemplateValidationErrors {
  const errors: TemplateValidationErrors = {};

  if (!template.name.trim()) {
    errors.name = "Template name is required.";
  }

  if (!template.subject.trim()) {
    errors.subject = "Subject is required.";
  }

  if (!hasMeaningfulHtmlContent(template.bodyHtml)) {
    errors.bodyHtml = "Body HTML is required.";
  }

  return errors;
}

export function hasValidationErrors(errors: TemplateValidationErrors): boolean {
  return Object.values(errors).some(Boolean);
}

function buildApiPayload(template: Template) {
  return {
    name: template.name.trim(),
    subject: template.subject.trim(),
    body_html: template.bodyHtml,
    form_id: template.formId,
    entity_type: template.entityType,
  };
}

export function toCreateRequest(template: Template): EmailTemplateCreateRequest {
  return buildApiPayload(template);
}

export function toUpdateRequest(template: Template): EmailTemplateUpdateRequest {
  return buildApiPayload(template);
}

export function fromApiTemplate(template: EmailTemplateApiModel): Template {
  return {
    templateId: template.template_id,
    organizationId: template.organization_id,
    name: template.name,
    subject: template.subject,
    bodyHtml: template.body_html,
    formId: template.form_id,
    entityType: template.entity_type,
    isSystem: template.is_system,
    createdAt: template.created_at,
  };
}

export function formatCreatedAt(value: string): string {
  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(parsed);
}

function hasMeaningfulHtmlContent(html: string): boolean {
  const text = html
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .trim();

  return text.length > 0;
}
