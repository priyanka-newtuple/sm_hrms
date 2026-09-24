import { useCallback, useEffect, useState } from "react";
import { emailTemplates } from "../../../../../core/services/api/emailTemplates";
import {
  fromApiTemplate,
  toCreateRequest,
  toUpdateRequest,
} from "../services/templateService.ts";
import type { Template } from "../types";

export function useTemplateLibrary() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshTemplates = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const response = await emailTemplates.list();
      setTemplates(response.items.map(fromApiTemplate));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Unable to load templates.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshTemplates();
  }, [refreshTemplates]);

  const findTemplateById = useCallback(
    (templateId: string) => templates.find((template) => template.templateId === templateId),
    [templates],
  );

  const saveTemplate = useCallback(
    async (draft: Template) => {
      const savedTemplateResponse = draft.isNew
        ? await emailTemplates.create(toCreateRequest(draft))
        : await emailTemplates.update(draft.templateId, toUpdateRequest(draft));
      const savedTemplate = fromApiTemplate(savedTemplateResponse);

      setTemplates((currentTemplates) => {
        if (draft.isNew) {
          return [savedTemplate, ...currentTemplates];
        }

        return currentTemplates.map((template) =>
          template.templateId === savedTemplate.templateId ? savedTemplate : template,
        );
      });

      return savedTemplate;
    },
    [],
  );

  const deleteTemplate = useCallback(
    async (templateId: string) => {
      await emailTemplates.delete(templateId);
      setTemplates((currentTemplates) =>
        currentTemplates.filter((template) => template.templateId !== templateId),
      );
    },
    [],
  );

  return {
    templates,
    isLoading,
    loadError,
    refreshTemplates,
    findTemplateById,
    saveTemplate,
    deleteTemplate,
  };
}
