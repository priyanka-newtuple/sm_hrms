/** Shared client-side types for the connector form and its editor rows. */

/** A free-text {key, value} row used for headers and query params. */
export interface KeyValueRow {
  key: string;
  value: string;
}

/** A {request/response key ↔ entity field (or custom value)} mapping row. */
export interface KeyFieldRow {
  key: string;
  field: string;
  /** When true, `field` holds a free-typed custom value rather than a selected entity field. */
  custom?: boolean;
}

/** Which form input the user last focused, so variable insertion targets the right slot. */
export type FocusedSlot =
  | 'path'
  | 'rawBody'
  | { section: 'header' | 'query'; index: number }
  | null;

/** Placeholders found across a connector's request, grouped by where each value comes from. */
export interface DetectedPlaceholders {
  /** `{{input}}` names — values the agent or workflow must provide at runtime. */
  inputs: string[];
  /** `$entity.field` names — values auto-filled from the bound entity. */
  entityFields: string[];
}
