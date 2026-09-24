import { useState } from 'react';
import { Globe, Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useConnectorActions, useConnectorList } from '../../../../core/hooks/useConnectors';
import type { Connector, ConnectorCreateRequest } from '../../../../core/types';
import ConnectorForm from './components/ConnectorForm';
import ConnectorListItem from './components/ConnectorListItem';
import McpAppCatalog from './components/McpAppCatalog';
import RotateSecretModal from './components/RotateSecretModal';

function detectRuntimeInputs(c: Connector): string[] {
  const sources = [
    c.base_url ?? '',
    c.path ?? '',
    ...Object.values(c.headers ?? {}),
    ...Object.values(c.query_params ?? {}),
    typeof c.body_template === 'string'
      ? c.body_template
      : JSON.stringify(c.body_template ?? ''),
  ].filter((s): s is string => typeof s === 'string');

  const found = new Set<string>();
  for (const s of sources) {
    // inline regex literals so each call gets a fresh lastIndex
    for (const m of s.matchAll(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g)) found.add(m[1]);
    for (const m of s.matchAll(/\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)/g)) found.add(m[1]);
  }
  console.debug('[detectRuntimeInputs]', c.name, { sources, found: [...found] });
  return [...found];
}

interface TestInputsModalProps {
  inputs: string[];
  onConfirm: (values: Record<string, string>) => void;
  onClose: () => void;
}

export function TestInputsModal({ inputs, onConfirm, onClose }: TestInputsModalProps) {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(inputs.map((k) => [k, ''])),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      {/* Cap height and make the field list scroll so many runtime inputs don't
          push the action buttons off-screen. Header and footer stay pinned. */}
      <div className="flex max-h-[85vh] w-full max-w-sm flex-col rounded-xl border border-border bg-card shadow-lg">
        <div className="shrink-0 p-5 pb-3">
          <h3 className="mb-1 text-sm font-semibold">Sample values for test</h3>
          <p className="text-xs text-muted-foreground">
            This connector uses runtime placeholders. Provide sample values so the test fires against a real URL.
          </p>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5">
          {inputs.map((key) => (
            <div key={key}>
              <Label className="text-xs font-mono">{`{{${key}}}`}</Label>
              <Input
                className="mt-1"
                placeholder={`sample ${key}`}
                value={values[key]}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div className="flex shrink-0 justify-end gap-2 p-5 pt-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={() => onConfirm(values)}>Run test</Button>
        </div>
      </div>
    </div>
  );
}

function ConnectorEmptyState({ onCreateFirst }: { onCreateFirst: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-card p-8 text-center">
      <Globe className="mx-auto mb-3 h-10 w-10 text-muted-foreground/40" />
      <p className="mb-1 font-medium text-muted-foreground">No connectors yet</p>
      <p className="mb-4 text-sm text-muted-foreground">
        Create one to let workflows call an external API.
      </p>
      <Button variant="primary" onClick={onCreateFirst} icon={<Plus className="h-4 w-4" />}>
        Create first connector
      </Button>
    </div>
  );
}

export default function ConnectorsTab() {
  const { data, loading, error, refetch } = useConnectorList();
  const { create, update, remove, test } = useConnectorActions();

  // null = nothing selected, 'new' = create mode, Connector = edit mode
  const [selected, setSelected] = useState<Connector | 'new' | null>(null);
  const [rotatingSecret, setRotatingSecret] = useState<Connector | null>(null);
  const [testInputsFor, setTestInputsFor] = useState<{ connector: Connector; inputs: string[] } | null>(null);

  const connectors = data?.items ?? [];

  const handleSubmit = async (payload: ConnectorCreateRequest) => {
    try {
      if (selected && selected !== 'new') {
        await update(selected.id, payload);
        toast.success('Connector updated.');
      } else {
        await create(payload);
        toast.success('Connector created.');
      }
      setSelected(null);
      await refetch();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save connector.');
    }
  };

  const handleDelete = async (c: Connector, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Delete connector "${c.name}"?`)) return;
    try {
      await remove(c.id);
      toast.success('Connector deleted.');
      if (selected !== 'new' && selected?.id === c.id) setSelected(null);
      await refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete connector.');
    }
  };

  const handleRotateSecret = async (secrets: Record<string, string>) => {
    if (!rotatingSecret) return;
    await update(rotatingSecret.id, { secrets });
    await refetch();
  };

  const runTest = async (c: Connector, sampleInputs: Record<string, string>) => {
    try {
      const result = await test(c.id, sampleInputs);
      if (result.success) toast.success(`Test passed — HTTP ${result.status_code ?? '—'}.`);
      else toast.error(`Test failed: ${result.message}`);
      await refetch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to test connector.');
    }
  };

  const handleTest = (c: Connector, e: React.MouseEvent) => {
    e.stopPropagation();
    const inputs = detectRuntimeInputs(c);
    if (inputs.length > 0) {
      setTestInputsFor({ connector: c, inputs });
    } else {
      runTest(c, {});
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-destructive">Failed to load connectors.</p>;
  }

  const selectedId = selected === 'new' ? 'new' : selected?.id ?? null;

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-medium">Connectors</h2>
        </div>
        <Button
          variant="secondary"
          onClick={() => setSelected('new')}
          icon={<Plus className="h-4 w-4" />}
        >
          New Connector
        </Button>
      </div>

      <McpAppCatalog />

      <div className="mb-3">
        <h3 className="text-sm font-semibold">Custom connectors</h3>
        <p className="text-xs text-muted-foreground">
          Define your own API call — method, path, body, and response mapping.
        </p>
      </div>

      {connectors.length === 0 && selected !== 'new' ? (
        <ConnectorEmptyState onCreateFirst={() => setSelected('new')} />
      ) : (
        <div className="flex flex-col gap-4 lg:grid lg:grid-cols-4 lg:gap-6">
          {/* Left: connector list */}
          <div className="lg:col-span-1">
            <ul className="space-y-1">
              {selected === 'new' && (
                <li>
                  <button
                    type="button"
                    className="w-full rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5 text-left"
                  >
                    <p className="text-sm font-medium text-primary">New connector</p>
                    <p className="text-xs text-primary/60">Unsaved</p>
                  </button>
                </li>
              )}
              {connectors.map((c) => (
                <li key={c.id}>
                  <ConnectorListItem
                    connector={c}
                    isActive={selectedId === c.id}
                    onSelect={() => setSelected(c)}
                    onTest={(e) => handleTest(c, e)}
                    onRotateSecret={() => setRotatingSecret(c)}
                    onDelete={(e) => handleDelete(c, e)}
                  />
                </li>
              ))}
            </ul>
          </div>

          {/* Right: form or select prompt */}
          <div className="lg:col-span-3">
            {selected === null ? (
              <div className="rounded-xl border border-border bg-card p-8 text-center">
                <Globe className="mx-auto mb-3 h-10 w-10 text-muted-foreground/30" />
                <p className="text-muted-foreground">Select a connector to edit</p>
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-card p-5">
                <h3 className="mb-4 text-base font-semibold">
                  {selected === 'new' ? 'New connector' : `Edit — ${selected.name}`}
                </h3>
                <ConnectorForm
                  key={selected === 'new' ? 'new' : selected.id}
                  initial={selected === 'new' ? null : selected}
                  onSubmit={handleSubmit}
                  onCancel={() => setSelected(null)}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {rotatingSecret && (
        <RotateSecretModal
          connector={rotatingSecret}
          onSave={handleRotateSecret}
          onClose={() => setRotatingSecret(null)}
        />
      )}

      {testInputsFor && (
        <TestInputsModal
          inputs={testInputsFor.inputs}
          onConfirm={(values) => {
            const c = testInputsFor.connector;
            setTestInputsFor(null);
            runTest(c, values);
          }}
          onClose={() => setTestInputsFor(null)}
        />
      )}
    </div>
  );
}
