/**
 * useFeatureFlags
 *
 * Per-organization feature flags read from the org's `settings.featureFlags`
 * blob (saved from Settings → Display). Mirrors the `themeFromSettings`
 * pattern: missing or malformed values fall back to defaults, so an org with
 * no saved flags renders with everything shown — except What's New, which is
 * hidden by default (most orgs don't need it) and opt-in per org.
 */

import { useMemo } from 'react';
import { useAuth } from '../auth';

export interface FeatureFlags {
  /** Hide the Kanban board on Pipeline pages, leaving only the List view. */
  hideKanban: boolean;
  /** Hide the Calendar view on Pipeline pages. */
  hideCalendar: boolean;
  /** Hide all Due date controls and list presentation. */
  hideDueDate: boolean;
  /** Hide the Dashboard nav item. */
  hideDashboard: boolean;
  /** Hide Agent Mode (toggle + sidebar). */
  hideAgent: boolean;
  /** Hide the Records nav item. */
  hideRecords: boolean;
  /** Hide the What's New (changelog) nav item. Defaults hidden; opt-in per org. */
  hideWhatsNew: boolean;
  /** Hide the Export button on pipeline pages. */
  hideExport: boolean;
  /** Hide the "Re-run action" control on the entity detail view. */
  hideRerunAction: boolean;
  /** Enable the AI-assisted bulk entity import workspace. Off by default. */
  bulkImportEnabled: boolean;
  /** Enable the Kanban board's "Card fields" picker. Off by default. */
  cardFieldsEnabled: boolean;
  /**
   * Hide the Jira-style assignee avatar filter on Board/Table/Calendar.
   * Defaults hidden; opt-in per org. (A skin can also hard-disable it via
   * `skin.board.showAssigneeFilter: false`, which wins regardless of this flag.)
   */
  hideAssigneeFilter: boolean;
  /** Open entity detail as a full page instead of the slide-over sheet. */
  entityDetailFullPage: boolean;
  /**
   * Hide terminal-state entities (e.g. Rejected, Withdrawn) on every pipeline
   * board — one org-wide value, the same everywhere (see useHideTerminal).
   * The board toolbar's Show/Hide control reads/writes this same flag.
   */
  hideTerminalByDefault: boolean;
  /** Email the new assignee when an entity is assigned. Off by default. */
  sendAssignmentEmails: boolean;
  /** Email the mentioned user and the entity's assignee when a comment is made. Off by default. */
  sendCommentEmails: boolean;
  /** Email a top-level comment's author when someone replies to it. Off by default. */
  sendReplyEmails: boolean;
  /** Email a comment's author when someone likes it. Off by default — likes are high-frequency/low-signal. */
  sendLikeEmails: boolean;
  /**
   * Offer the Light / Dark / System switch to everyone in the org. Off by
   * default. When off the switch is hidden and the app renders light for every
   * member, whatever they previously chose — see `applyMode` in
   * `core/theme/mode.ts`, which enforces it at the paint site.
   */
  darkModeEnabled: boolean;
}

export const FEATURE_FLAG_DEFAULTS: FeatureFlags = {
  hideKanban: false,
  hideCalendar: false,
  hideDueDate: false,
  hideDashboard: false,
  hideAgent: false,
  hideRecords: false,
  hideWhatsNew: true,
  hideExport: false,
  hideRerunAction: false,
  bulkImportEnabled: false,
  cardFieldsEnabled: false,
  entityDetailFullPage: false,
  hideTerminalByDefault: true,
  hideAssigneeFilter: true,
  sendAssignmentEmails: false,
  sendCommentEmails: false,
  sendReplyEmails: false,
  sendLikeEmails: false,
  darkModeEnabled: false,
};

/**
 * Extract feature flags from an organization's `settings` blob. Coerces each
 * key to a strict boolean; anything missing or non-boolean falls back to the
 * default (shown).
 */
export function featureFlagsFromSettings(
  settings: Record<string, unknown> | null | undefined,
): FeatureFlags {
  const raw = settings?.featureFlags;
  if (!raw || typeof raw !== 'object') return FEATURE_FLAG_DEFAULTS;
  const blob = raw as Record<string, unknown>;
  return {
    hideKanban: blob.hideKanban === true,
    hideCalendar: blob.hideCalendar === true,
    hideDueDate: blob.hideDueDate === true,
    hideDashboard: blob.hideDashboard === true,
    hideAgent: blob.hideAgent === true,
    hideRecords: blob.hideRecords === true,
    // Default hidden: only shown when an org explicitly sets it to false.
    hideWhatsNew: blob.hideWhatsNew !== false,
    hideExport: blob.hideExport === true,
    hideRerunAction: blob.hideRerunAction === true,
    bulkImportEnabled: blob.bulkImportEnabled === true,
    cardFieldsEnabled: blob.cardFieldsEnabled === true,
    entityDetailFullPage: blob.entityDetailFullPage === true,
    hideTerminalByDefault: blob.hideTerminalByDefault === true,
    // Default hidden: only shown when an org explicitly sets it to false.
    hideAssigneeFilter: blob.hideAssigneeFilter !== false,
    sendAssignmentEmails: blob.sendAssignmentEmails === true,
    sendCommentEmails: blob.sendCommentEmails === true,
    sendReplyEmails: blob.sendReplyEmails === true,
    sendLikeEmails: blob.sendLikeEmails === true,
    darkModeEnabled: blob.darkModeEnabled === true,
  };
}

/** Feature flags for the active organization (defaults while org is loading). */
export function useFeatureFlags(): FeatureFlags {
  const { organization } = useAuth();
  return useMemo(
    () => featureFlagsFromSettings(organization?.settings),
    [organization?.settings],
  );
}
