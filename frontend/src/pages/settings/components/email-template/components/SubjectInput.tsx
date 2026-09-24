import React, { useState, useRef, useCallback, useMemo, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input.tsx";
import { IconSparkle } from "./Icons.tsx";
import type { Variable } from "../types";

interface SubjectInputProps {
  value: string;
  onChange: (value: string) => void;
  variables: Variable[];
  className?: string;
  placeholder?: string;
  disabled?: boolean;
}

export function SubjectInput({
  value,
  onChange,
  variables,
  className,
  placeholder,
  disabled = false,
}: SubjectInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerStartRef = useRef(-1);
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);

  const checkTrigger = useCallback((text: string, cursor: number) => {
    const textBefore = text.slice(0, cursor);
    const m = textBefore.match(/\{\{([\w.]*)$/);
    if (m) {
      triggerStartRef.current = cursor - (2 + (m[1]?.length ?? 0));
      setQuery(m[1] ?? "");
      setMenuOpen(true);
      setActiveIdx(0);
    } else {
      setMenuOpen(false);
    }
  }, []);

  const filteredVars = useMemo(() => {
    if (!query) return variables;
    const q = query.toLowerCase();
    return variables.filter(
      (v) => v.key.toLowerCase().includes(q) || (v.label?.toLowerCase().includes(q) ?? false),
    );
  }, [variables, query]);

  const insertVariable = useCallback(
    (varKey: string) => {
      const el = inputRef.current;
      if (!el) return;
      const cursor = el.selectionStart ?? value.length;
      const before = value.slice(0, triggerStartRef.current);
      const after = value.slice(cursor);
      const inserted = `{{${varKey}}}`;
      onChange(before + inserted + after);
      setMenuOpen(false);
      setTimeout(() => {
        el.focus();
        const pos = before.length + inserted.length;
        el.setSelectionRange(pos, pos);
      }, 0);
    },
    [value, onChange],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value;
      onChange(newValue);
      checkTrigger(newValue, e.target.selectionStart ?? 0);
    },
    [onChange, checkTrigger],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (!menuOpen) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filteredVars.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" || e.key === "Tab") {
        const v = filteredVars[activeIdx];
        if (v) {
          e.preventDefault();
          insertVariable(v.key);
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        setMenuOpen(false);
      }
    },
    [menuOpen, filteredVars, activeIdx, insertVariable],
  );

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLInputElement>) => {
      const el = e.currentTarget;
      checkTrigger(el.value, el.selectionStart ?? 0);
    },
    [checkTrigger],
  );

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div ref={wrapRef} className="relative">
      <Input
        ref={inputRef}
        className={className}
        type="text"
        value={value}
        disabled={disabled}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onClick={handleClick}
        placeholder={placeholder}
      />
      {menuOpen && (
        <div className="absolute left-0 top-full z-50 mt-1 max-h-64 w-full min-w-[260px] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl shadow-slate-900/10">
          <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Variables{query && ` · "${query}"`}
          </div>
          {filteredVars.length === 0 ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">No matches for &ldquo;{query}&rdquo;</div>
          ) : (
            filteredVars.map((v, i) => (
              <button
                key={v.key}
                type="button"
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-info-subtle",
                  i === activeIdx && "bg-info-subtle",
                )}
                onMouseEnter={() => setActiveIdx(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertVariable(v.key);
                }}
              >
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <IconSparkle className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-foreground">{v.label || v.key}</div>
                  <div className={cn("font-mono text-[11px] text-muted-foreground", i === activeIdx && "text-info")}>
                    {`{{${v.key}}}`}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
