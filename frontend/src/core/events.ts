/**
 * Cross-screen browser events.
 *
 * Names live here because dispatchers and listeners sit in unrelated modules
 * and neither TypeScript nor the tests can catch a typo in a string literal —
 * a mistyped dispatch silently stops the refresh, and a mistyped
 * removeEventListener leaks a handler that keeps firing after unmount.
 */

/** Workflow definitions changed (draft saved or new version published). */
export const STATE_MACHINES_CHANGED_EVENT = 'state-machines-changed';
