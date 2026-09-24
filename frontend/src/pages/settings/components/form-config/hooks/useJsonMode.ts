import { useState } from 'react';

/** Available editing surfaces in a JSON-enabled create form. */
export type JsonEditorMode = 'visual' | 'json';

interface UseJsonModeResult {
  mode: JsonEditorMode;
  jsonDraft: string;
  jsonError: string | null;
  setJsonError: (error: string | null) => void;
  switchMode: (mode: JsonEditorMode) => void;
  updateJsonDraft: (value: string) => void;
}

/** Preserve an inline JSON draft while a create form switches editing modes. */
export function useJsonMode(initialDraft: () => string): UseJsonModeResult {
  const [mode, setMode] = useState<JsonEditorMode>('visual');
  const [jsonDraft, setJsonDraft] = useState(initialDraft);
  const [hasOpenedJson, setHasOpenedJson] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const switchMode = (nextMode: JsonEditorMode) => {
    if (nextMode === 'json' && !hasOpenedJson) {
      setJsonDraft(initialDraft());
      setHasOpenedJson(true);
    }
    setJsonError(null);
    setMode(nextMode);
  };

  const updateJsonDraft = (value: string) => {
    setJsonDraft(value);
    setJsonError(null);
  };

  return {
    mode,
    jsonDraft,
    jsonError,
    setJsonError,
    switchMode,
    updateJsonDraft,
  };
}
