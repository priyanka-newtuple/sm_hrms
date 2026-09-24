/**
 * Shared surfaces for the Email Templates screens.
 *
 * These are app chrome, so they use the semantic tokens and follow light/dark.
 * The email *preview* and the compose canvas deliberately do not — see the note
 * in Modals.tsx.
 *
 * The shadows are light-mode polish; they read as nothing against the dark
 * surfaces, where depth comes from the elevation ladder in index.css instead.
 */
export const panelClass =
  "rounded-[16px] border border-border bg-card shadow-[0_8px_24px_-22px_rgba(0,0,0,0.14)]";

export const insetPanelClass =
  "rounded-[16px] border border-border bg-card shadow-[0_8px_24px_-22px_rgba(0,0,0,0.12)]";

export const systemTagClass =
  "rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground";
