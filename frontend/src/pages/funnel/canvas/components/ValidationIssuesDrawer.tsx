import { AlertTriangle, ArrowRight, ChevronDown, ChevronUp, CircleAlert, ListChecks } from "lucide-react";
import type { ValidationIssue } from "@/lib/state-machine/types";
import { Button } from "@/components/ui/button";

interface ValidationIssuesDrawerProps {
  issues: ValidationIssue[];
  errorCount: number;
  warningCount: number;
  isOpen: boolean;
  onToggle: () => void;
  onNavigateToState: (name: string) => void;
  onNavigateToTransition: (key: string) => void;
}

export function ValidationIssuesDrawer({
  issues,
  errorCount,
  warningCount,
  isOpen,
  onToggle,
  onNavigateToState,
  onNavigateToTransition,
}: ValidationIssuesDrawerProps) {
  if (issues.length === 0) return null;

  return (
    <div className="absolute left-1/2 top-3 z-10 w-[min(680px,calc(100%-2rem))] -translate-x-1/2">
      <div className="overflow-hidden rounded-lg border border-border bg-card/95 shadow-lg backdrop-blur">
        <Button
          variant="ghost"
          className="flex h-auto w-full items-center gap-2 rounded-none px-3 py-2.5 text-left text-xs text-foreground transition-colors hover:bg-muted/50"
          onClick={onToggle}
        >
          <ListChecks className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="font-semibold text-foreground">Validation</span>
          {errorCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
              <CircleAlert className="h-3 w-3" />
              {errorCount} error{errorCount > 1 ? "s" : ""}
            </span>
          )}
          {warningCount > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warning/20 bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">
              <AlertTriangle className="h-3 w-3" />
              {warningCount} warning{warningCount > 1 ? "s" : ""}
            </span>
          )}
          <span className="ml-auto text-muted-foreground">
            {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </span>
        </Button>

        {isOpen && (
          <ul className="max-h-72 divide-y divide-border overflow-auto border-t border-border">
            {issues.map((issue, i) => {
              const isNavigable = !!(issue.stateName || issue.transitionKey);
              return (
                <li
                  key={i}
                  className={`group flex items-start gap-3 px-3 py-2.5 text-xs ${
                    isNavigable ? "cursor-pointer hover:bg-muted/50 transition-colors" : ""
                  }`}
                  onClick={() => {
                    if (issue.stateName) onNavigateToState(issue.stateName);
                    else if (issue.transitionKey) onNavigateToTransition(issue.transitionKey);
                  }}
                >
                  <div
                    className={`mt-0.5 shrink-0 ${
                      issue.level === "error" ? "text-destructive" : "text-warning"
                    }`}
                  >
                    {issue.level === "error" ? (
                      <CircleAlert className="h-3.5 w-3.5" />
                    ) : (
                      <AlertTriangle className="h-3.5 w-3.5" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium text-foreground">
                        {issue.humanPath ?? issue.path}
                      </span>
                      {issue.source === "server" && (
                        <span className="rounded border border-primary/15 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">
                          server
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-muted-foreground leading-snug">{issue.message}</div>
                  </div>
                  {isNavigable && (
                    <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
