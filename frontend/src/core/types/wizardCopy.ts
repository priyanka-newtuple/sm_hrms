/**
 * The picklist_multi wizard's editable copy: a heading and a description for
 * each of its three steps.
 *
 * One list, one picker, used by every mapper that carries a field between the
 * engine's `EntityField` and the UI's `FormField`. There are several such
 * mappers (`services/api/formSchemas`, `lib/state-machine/entitySchema`,
 * `lib/state-machine/methodFields`) and a key added to only some of them
 * silently renders as the fallback wording, which is hard to spot and harder to
 * diagnose. Adding a key here reaches all of them.
 */

export const WIZARD_COPY_KEYS = [
  'step1_label',
  'step1_description',
  'step2_label',
  'step2_description',
  'step3_label',
  'step3_description',
] as const;

export type WizardCopyKey = (typeof WIZARD_COPY_KEYS)[number];

export type WizardCopy = Partial<Record<WizardCopyKey, string>>;

/** The wizard copy carried by a raw field, dropping blanks so a fallback wins. */
export function pickWizardCopy(source: Record<string, unknown> | undefined): WizardCopy {
  const copy: WizardCopy = {};
  if (!source) return copy;
  for (const key of WIZARD_COPY_KEYS) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) copy[key] = value.trim();
  }
  return copy;
}

/** Every wizard copy key cleared, for a field that is no longer a picklist_multi. */
export function clearedWizardCopy(): Record<WizardCopyKey, undefined> {
  return Object.fromEntries(WIZARD_COPY_KEYS.map((key) => [key, undefined])) as Record<
    WizardCopyKey,
    undefined
  >;
}
