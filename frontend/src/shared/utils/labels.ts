/**
 * Platform-wide label formatting — the single source of truth for turning
 * internal technical names (snake_case keys, dotted entity types, state names,
 * transition triggers, enum values) into human-facing labels.
 *
 * Precedence is always: authored label (if present) → humanized fallback.
 * Internal names are never mutated for backend references; these helpers only
 * affect what the user sees. Arbitrary stored data values are intentionally out
 * of scope — only structural names and known enums pass through here.
 */

/** Leading dotted namespace on an entity type, e.g. `ATS.` in `ATS.Candidate`. */
const DOTTED_NAMESPACE = /^[^.]+\./;

/**
 * Canonical humanizer: `photo_quality_check` → `Photo Quality Check`,
 * `candidate_application` → `Candidate Application`, `IN_PROGRESS` → `In Progress`.
 * Separators (`_`, `-`, `.`) become spaces; the result is lower-cased then
 * Title Cased so SCREAMING_CASE enums read cleanly.
 */
export function humanize(token: string | null | undefined): string {
  if (!token) return '';
  return token
    .replace(/[_.-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Minimal shape of the authored labels an entity-type schema may carry. */
export interface EntityTypeLabelSource {
  name?: string | null;
  display_name?: string | null;
}

/**
 * Entity-type display label. Prefers an authored `display_name`/`name` from the
 * schema; otherwise strips any leading dotted namespace and humanizes the key.
 */
export function resolveEntityTypeLabel(
  entityType: string,
  schema?: EntityTypeLabelSource | null,
): string {
  const authored = schema?.display_name?.trim() || schema?.name?.trim();
  if (authored) return authored;
  return humanize(entityType.replace(DOTTED_NAMESPACE, ''));
}

/**
 * State display label. Prefers an authored label from the active machine
 * definition (via {@link useStateLabels}); otherwise humanizes the state name.
 */
export function resolveStateLabel(
  stateName: string | null | undefined,
  stateLabels?: Map<string, string>,
): string {
  if (!stateName) return '';
  return stateLabels?.get(stateName) || humanize(stateName);
}

/** Minimal shape of a transition the UI needs to label. */
export interface TransitionLabelSource {
  label?: string | null;
  trigger?: string | null;
  to_state?: string | null;
}

/**
 * Transition action label. Prefers the authored `label`; otherwise falls back to
 * "Move to <state label>" when a target state is known, else the humanized trigger.
 */
export function resolveTransitionLabel(
  transition: TransitionLabelSource,
  stateLabels?: Map<string, string>,
): string {
  const authored = transition.label?.trim();
  if (authored) return authored;
  if (transition.to_state) return `Move to ${resolveStateLabel(transition.to_state, stateLabels)}`;
  return humanize(transition.trigger);
}

/**
 * Field display label. Prefers an authored label (entity-schema `description`,
 * surfaced as a key→label map); otherwise humanizes the field key.
 */
export function resolveFieldLabel(
  fieldKey: string,
  schemaFieldLabels?: Map<string, string>,
): string {
  return schemaFieldLabels?.get(fieldKey) || humanize(fieldKey);
}

/**
 * Known-enum label (role, status, event type). Humanize only — these are
 * closed vocabularies of snake_case tokens, never free-form data values.
 */
export function resolveEnumLabel(value: string | null | undefined): string {
  return humanize(value);
}
