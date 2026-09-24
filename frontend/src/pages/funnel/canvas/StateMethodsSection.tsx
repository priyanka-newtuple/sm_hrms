import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, Loader2, Plus, RefreshCw, Trash2, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { usePermissions } from "@/core/hooks/usePermissions";
import { methodLibrary, METHOD_LIBRARY_MAX_LIMIT } from "@/core/services/api";
import { getApiErrorMessage } from "@/core/services/api/client";
import type { MethodIdentity, MethodVersion } from "@/core/types";
import type { MethodRef } from "@/lib/state-machine/types";
// TEMPORARY DIAGNOSTICS — see lib/state-machine/diag.ts; strip with the bug.
import { diagLog } from "@/lib/state-machine/diag";

interface StateMethodsSectionProps {
  methodRefs: MethodRef[];
  onChange: (refs: MethodRef[]) => void;
  /** The workflow's entity type. Only methods tagged for it are offered, and
   *  the filtering happens server-side so untagged methods never arrive. */
  entityType?: string;
}

function versionLabel(version: MethodVersion | undefined): string {
  return version ? `v${version.version}` : "Pinned version";
}

export function StateMethodsSection({ methodRefs, onChange, entityType }: StateMethodsSectionProps) {
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("workflow:write");
  const [methods, setMethods] = useState<MethodIdentity[]>([]);
  const [versions, setVersions] = useState<Record<string, MethodVersion[]>>({});
  const [selectedMethodId, setSelectedMethodId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [category, setCategory] = useState("");
  const [loadingMethods, setLoadingMethods] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMethods = useCallback(async () => {
    setLoadingMethods(true);
    setError(null);
    diagLog('methodLibrary.list KICKOFF', `populating "Select method" dropdown entityType=${entityType ?? '(none)'}`);
    try {
      let offset = 0;
      let total = 0;
      let allMethods: MethodIdentity[] = [];
      do {
        const response = await methodLibrary.list({
          limit: METHOD_LIBRARY_MAX_LIMIT,
          offset,
          entityType,
        });
        allMethods = [...allMethods, ...response.items];
        total = response.total;
        if (response.items.length === 0) break;
        offset += response.items.length;
      } while (offset < total);
      diagLog('methodLibrary.list RESOLVED', `methods=${allMethods.length}`);
      setMethods(allMethods);
    } catch (err) {
      diagLog('methodLibrary.list FAILED', String(err));
      setError(getApiErrorMessage(err, "Failed to load forms"));
    } finally {
      setLoadingMethods(false);
    }
  }, [entityType]);

  const loadVersions = useCallback(async (methodId: string) => {
    if (!methodId || versions[methodId]) return;
    setLoadingVersions(methodId);
    try {
      let offset = 0;
      let total = 0;
      let allVersions: MethodVersion[] = [];
      do {
        const response = await methodLibrary.listVersions(methodId, {
          limit: METHOD_LIBRARY_MAX_LIMIT,
          offset,
        });
        allVersions = [...allVersions, ...response.items];
        total = response.total;
        if (response.items.length === 0) break;
        offset += response.items.length;
      } while (offset < total);
      setVersions((previous) => ({ ...previous, [methodId]: allVersions }));
    } catch (err) {
      setError(getApiErrorMessage(err, "Failed to load form versions"));
    } finally {
      setLoadingVersions((current) => (current === methodId ? null : current));
    }
  }, [versions]);

  useEffect(() => {
    void loadMethods();
  }, [loadMethods]);

  useEffect(() => {
    for (const ref of methodRefs) void loadVersions(ref.method_id);
  }, [loadVersions, methodRefs]);

  const categories = useMemo(
    () => [...new Set(methods.map((method) => method.category_name?.trim()).filter(Boolean) as string[])].sort(),
    [methods],
  );

  const visibleMethods = useMemo(
    () => methods.filter((method) => !category || method.category_name === category),
    [category, methods],
  );

  const selectedVersions = selectedMethodId ? versions[selectedMethodId] ?? [] : [];
  const methodById = useMemo(
    () => new Map(methods.map((method) => [method.method_id, method] as const)),
    [methods],
  );

  const addMethod = () => {
    if (!selectedMethodId || methodRefs.some((ref) => ref.method_id === selectedMethodId)) return;
    diagLog(
      '"Add" method CLICKED (StateMethodsSection)',
      `method=${selectedMethodId.slice(0, 8)} existingRefs=[${methodRefs
        .map((r) => r.method_id.slice(0, 8))
        .join(',')}]`,
    );
    onChange([
      ...methodRefs,
      { method_id: selectedMethodId, version_id: selectedVersionId || null },
    ]);
    setSelectedMethodId("");
    setSelectedVersionId("");
  };

  const updateVersion = (methodId: string, versionId: string) => {
    diagLog('updateVersion (StateMethodsSection)', `method=${methodId.slice(0,8)} version=${versionId || 'latest'}`);
    onChange(
      methodRefs.map((ref) =>
        ref.method_id === methodId ? { ...ref, version_id: versionId || null } : ref,
      ),
    );
  };

  const removeMethod = (methodId: string) => {
    diagLog('removeMethod (StateMethodsSection)', `method=${methodId.slice(0,8)} existingRefs=[${methodRefs.map(r=>r.method_id.slice(0,8)).join(',')}]`);
    onChange(methodRefs.filter((ref) => ref.method_id !== methodId));
  };

  return (
    <section className="space-y-3 border-t border-border pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
            <WandSparkles className="h-3.5 w-3.5" />
          </span>
          <div>
            <div className="text-xs font-semibold text-foreground">Forms</div>
            <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
              Add reusable field lists to this state. Choose a version to pin, or resolve the latest version when publishing.
            </p>
          </div>
        </div>
        <span className="shrink-0 rounded-full bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground">
          {methodRefs.length} selected
        </span>
      </div>

      {methodRefs.length > 0 && (
        <div className="space-y-2">
          {methodRefs.map((ref) => {
            const method = methodById.get(ref.method_id);
            const methodVersions = versions[ref.method_id] ?? [];
            const selectedVersion = methodVersions.find((version) => version.version_id === ref.version_id);
            return (
              <div key={ref.method_id} className="rounded-lg border border-border bg-muted/30 p-2.5">
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-xs font-medium text-foreground">
                        {method?.name ?? "Unknown form"}
                      </span>
                      {method && (
                        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                          FR-{String(method.method_code).padStart(2, "0")}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      {ref.version_id ? `${versionLabel(selectedVersion)} pinned` : "Latest on publish"}
                    </div>
                  </div>
                  {canWrite && (
                    <button
                      type="button"
                      onClick={() => removeMethod(ref.method_id)}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                      aria-label={`Remove ${method?.name ?? "form"}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                {canWrite && (
                  <select
                    value={ref.version_id ?? ""}
                    onChange={(event) => updateVersion(ref.method_id, event.target.value)}
                    onFocus={() => void loadVersions(ref.method_id)}
                    className="mt-2 h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
                  >
                    <option value="">Latest version on publish</option>
                    {methodVersions.map((version) => (
                      <option key={version.version_id} value={version.version_id}>
                        v{version.version} {version.is_latest ? "· current" : "· previous"}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}
        </div>
      )}

      {canWrite ? (
        <div className="rounded-lg border border-dashed border-border p-2.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <Label className="text-[11px] font-medium">Add a form</Label>
            <button
              type="button"
              onClick={() => void loadMethods()}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              title="Refresh forms"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingMethods ? "animate-spin" : ""}`} />
            </button>
          </div>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
          >
            <option value="">All categories</option>
            {categories.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
          {!loadingMethods && methods.length === 0 && (
            <p className="mt-2 text-[11px] leading-4 text-muted-foreground">
              No forms are tagged for{" "}
              <span className="font-medium text-foreground">{entityType || "this entity type"}</span>. Tag one under{" "}
              <a href="/settings?tab=forms" className="font-medium text-cobalt underline underline-offset-2">
                Settings → Forms
              </a>
              .
            </p>
          )}
          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)_auto]">
            <select
              value={selectedMethodId}
              onChange={(event) => {
                const methodId = event.target.value;
                setSelectedMethodId(methodId);
                setSelectedVersionId("");
                void loadVersions(methodId);
              }}
              className="h-9 min-w-0 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20"
            >
              <option value="">{loadingMethods ? "Loading forms…" : "Select form"}</option>
              {visibleMethods.map((method) => (
                <option
                  key={method.method_id}
                  value={method.method_id}
                  disabled={methodRefs.some((ref) => ref.method_id === method.method_id)}
                >
                  {method.name}{method.category_name ? ` · ${method.category_name}` : ""}
                </option>
              ))}
            </select>
            <select
              value={selectedVersionId}
              onChange={(event) => setSelectedVersionId(event.target.value)}
              disabled={!selectedMethodId || loadingVersions === selectedMethodId}
              className="h-9 min-w-0 rounded-md border border-border bg-background px-2 text-xs text-foreground focus:border-cobalt focus:outline-none focus:ring-2 focus:ring-cobalt/20 disabled:opacity-60"
            >
              <option value="">Latest on publish</option>
              {selectedVersions.map((version) => (
                <option key={version.version_id} value={version.version_id}>
                  v{version.version}{version.is_latest ? " · current" : " · previous"}
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addMethod}
              disabled={!selectedMethodId || methodRefs.some((ref) => ref.method_id === selectedMethodId)}
              icon={<Plus className="h-3.5 w-3.5" />}
            >
              Add
            </Button>
          </div>
          {selectedMethodId && loadingVersions === selectedMethodId && (
            <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading versions…
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
          <Check className="h-3.5 w-3.5 text-primary" /> Read-only workflow access
        </div>
      )}

      {error && <p className="text-[11px] text-destructive">{error}</p>}
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <ChevronDown className="h-3 w-3" /> Version pins are captured with the workflow publish.
      </div>
    </section>
  );
}
