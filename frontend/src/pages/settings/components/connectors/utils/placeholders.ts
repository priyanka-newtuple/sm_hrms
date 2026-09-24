/**
 * Connector placeholder helpers.
 *
 * A connector value can contain two kinds of placeholder, each with a distinct,
 * single meaning:
 *   - `{{input}}`      → supplied by the caller (an agent argument or a workflow
 *                        input). These become the connector's required inputs.
 *   - `$entity.field`  → auto-filled from the bound entity's record at call time.
 *
 * The regexes mirror the backend (`connectors/models/interface.py`).
 */

import type { DetectedPlaceholders } from '../types';

const CURLY = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;
const ENTITY = /\$entity\.([a-zA-Z_][a-zA-Z0-9_]*)/g;

/** Build the `{{name}}` token a caller-supplied input resolves against. */
export const inputToken = (name: string): string => `{{${name}}}`;

/** Build the `$entity.field` token an entity field resolves against. */
export const entityToken = (field: string): string => `$entity.${field}`;

function collect(pattern: RegExp, texts: string[]): string[] {
  const found = new Set<string>();
  for (const text of texts) {
    for (const match of text.matchAll(pattern)) {
      found.add(match[1]);
    }
  }
  return [...found].sort();
}

/**
 * Every string inside a JSON value, including those nested in objects and arrays.
 *
 * A nested body keeps its placeholders in leaves the flat row model never sees,
 * so without this the Detected Inputs panel would miss them and the connector
 * would look like it needed no inputs at all.
 */
export function stringsFromJson(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(stringsFromJson);
  if (value && typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).flatMap(stringsFromJson);
  }
  return [];
}

/** Scan a set of connector value strings and group the placeholders by source. */
export function detectPlaceholders(texts: string[]): DetectedPlaceholders {
  return {
    inputs: collect(CURLY, texts),
    entityFields: collect(ENTITY, texts),
  };
}
