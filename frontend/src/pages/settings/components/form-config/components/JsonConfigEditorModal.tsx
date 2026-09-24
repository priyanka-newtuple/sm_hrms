import { useEffect, useId, useRef, useState } from 'react';
import { Check, Copy, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { copyTextToClipboard } from '@/lib/clipboard';

const COPY_FEEDBACK_MS = 1500;

interface JsonConfigEditorModalProps<T> {
  noun: string;
  description: string;
  hint?: string;
  canWrite: boolean;
  load: () => Promise<T>;
  parse: (text: string) => T;
  onSave: (data: T) => Promise<boolean | void>;
  onClose: () => void;
}

/** Load, display, copy, validate, and save one JSON-backed configuration. */
export default function JsonConfigEditorModal<T>({
  noun,
  description,
  hint,
  canWrite,
  load,
  parse,
  onSave,
  onClose,
}: JsonConfigEditorModalProps<T>) {
  const titleId = useId();
  const loadRef = useRef(load);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState('');
  const [initialConfig, setInitialConfig] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadRef.current()
      .then((config) => {
        if (!active) return;
        setInitialConfig(config);
        setDraft(JSON.stringify(config, null, 2));
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : `Failed to load ${noun} JSON.`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [noun]);

  useEffect(() => {
    textareaRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [loading, onClose, saving]);

  const copyJson = async () => {
    try {
      await copyTextToClipboard(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
      toast.success(`${noun} JSON copied`);
    } catch {
      setError('Could not copy JSON to the clipboard.');
    }
  };

  const saveJson = async () => {
    try {
      setError(null);
      const parsed = parse(draft);
      if (initialConfig && JSON.stringify(parsed) === JSON.stringify(initialConfig)) {
        toast.success(`No ${noun.toLowerCase()} JSON changes to save`);
        onClose();
        return;
      }
      setSaving(true);
      const saved = await onSave(parsed);
      if (saved === false) return;
      toast.success(`${noun} JSON saved`);
      onClose();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : `Failed to save ${noun} JSON.`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl bg-card shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h3 id={titleId} className="text-base font-semibold text-foreground">
              {canWrite ? `Edit ${noun.toLowerCase()} JSON` : `View ${noun.toLowerCase()} JSON`}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={copyJson}
            disabled={loading}
          >
            {copied ? (
              <Check className="mr-1.5 h-3.5 w-3.5" />
            ) : (
              <Copy className="mr-1.5 h-3.5 w-3.5" />
            )}
            {copied ? 'Copied' : 'Copy JSON'}
          </Button>
        </div>

        <div className="min-h-0 flex-1 space-y-2 p-5">
          {loading ? (
            <div className="flex h-[60vh] items-center justify-center rounded-lg border border-border bg-muted/50">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setError(null);
              }}
              readOnly={!canWrite}
              spellCheck={false}
              className="h-[60vh] w-full resize-none rounded-lg border border-border bg-muted/50 px-3 py-2 font-mono text-xs leading-relaxed text-foreground outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt read-only:cursor-default"
            />
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
            {canWrite ? 'Cancel' : 'Close'}
          </Button>
          {canWrite && (
            <Button type="button" variant="ghost" onClick={saveJson} disabled={saving || loading}>
              {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Save JSON
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
