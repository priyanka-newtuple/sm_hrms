import { useMemo, useRef, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Copy, Download, Upload, Check } from "lucide-react";
import { toast } from "sonner";
import type { StateMachineDocument } from "@/lib/state-machine/types";

interface Props {
  doc: StateMachineDocument;
  onChange: (next: StateMachineDocument) => void;
}

export function JsonView({ doc, onChange }: Props) {
  const formatted = useMemo(() => JSON.stringify(doc, null, 2), [doc]);
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isDirty = draft != null || error != null;
  const text = draft ?? formatted;

  const apply = () => {
    if (draft == null) return;
    try {
      const parsed = JSON.parse(draft);
      if (!parsed.definition) throw new Error("Missing 'definition' field.");
      onChange(parsed as StateMachineDocument);
      setDraft(null);
      setError(null);
      toast.success("JSON applied");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Invalid JSON";
      setError(msg);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(formatted);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
    toast.success("Copied to clipboard");
  };

  const download = () => {
    const blob = new Blob([formatted], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${doc.machine_name || "state_machine"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const importFile = async (file: File) => {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      onChange(parsed as StateMachineDocument);
      toast.success("Imported");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Invalid file";
      toast.error(msg);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Toolbar — fixed height, never shrinks */}
      <div className="shrink-0 flex flex-wrap items-center gap-2">
        <h3 className="mr-auto text-sm font-semibold">JSON definition</h3>
        <div className="inline-flex">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importFile(f);
              e.currentTarget.value = "";
            }}
          />
          <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload className="mr-1.5 h-3.5 w-3.5" /> Import
          </Button>
        </div>
        <Button variant="outline" size="sm" onClick={download}>
          <Download className="mr-1.5 h-3.5 w-3.5" /> Download
        </Button>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? (
            <Check className="mr-1.5 h-3.5 w-3.5" />
          ) : (
            <Copy className="mr-1.5 h-3.5 w-3.5" />
          )}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>

      {/* Editor — fills all remaining space, gives it up when apply bar appears */}
      <Card className="flex flex-1 flex-col min-h-0 p-2">
        <Textarea
          value={text}
          onChange={(e) => {
            setDraft(e.target.value);
            setError(null);
          }}
          className="flex-1 min-h-0 resize-none font-mono text-xs leading-relaxed border-0 shadow-none focus-visible:ring-0 p-2"
          spellCheck={false}
        />
      </Card>

      {/* Apply bar — fixed height, pinned at bottom, only visible after edits */}
      {isDirty && (
        <div className="shrink-0 flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2 shadow-sm">
          <div className="text-xs text-muted-foreground">
            {error
              ? <span className="text-destructive">{error}</span>
              : "You have unsaved edits — click Apply to update the canvas."}
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(null);
                setError(null);
              }}
            >
              Reset
            </Button>
            <Button variant="primary" size="sm" onClick={apply}>
              Apply
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
