/**
 * Every phrase the "Extend Field" badges use, derived from one admin-supplied
 * noun (`field.extension_label`) so step 2's list and step 3's cards always
 * agree. No label configured keeps the generic "details" wording every field
 * had before the setting existed.
 */

const DEFAULT_LABEL = 'Details';

/**
 * The compact form for step 2's list, where the pill sits at the end of a row
 * and competes with the option's own name.
 *
 * Only a long single word is cut, and only ever to its first four characters
 * ("Certificate" → "Cert", "Authority" → "Auth"); anything already short enough
 * to read at a glance is left exactly as typed ("Details", "Permit", "License").
 * A multi-word label keeps its first word, which is the one that carries it.
 */
const ABBREVIATE_MIN_LENGTH = 9;
const ABBREVIATE_MAX_CHARS = 4;

function abbreviate(label: string): string {
  const [first = ''] = label.trim().split(/\s+/);
  return first.length >= ABBREVIATE_MIN_LENGTH ? first.slice(0, ABBREVIATE_MAX_CHARS) : first;
}

export type ExtensionWording = {
  /** Step 2's list pill, e.g. "Cert Req'd". */
  listBadge: string;
  /** Step 3, the option reveals fields — whether or not any of them are required. */
  required: string;
  /** Step 3, the option asks for nothing. */
  none: string;
  /** Step 3's section heading. */
  heading: string;
};

export function extensionWording(label?: string): ExtensionWording {
  const noun = label?.trim() || DEFAULT_LABEL;
  const lower = noun.toLowerCase();
  return {
    listBadge: `${abbreviate(noun)} Req'd`,
    required: `${noun} required`,
    none: `No ${lower} required`,
    heading: label?.trim() ? `${noun} details` : 'Extended details',
  };
}
