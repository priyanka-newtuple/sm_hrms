/**
 * The API returns business-rule failures as `{detail: {message, ...context}}`
 * (see backend app/core/exceptions.py) and FastAPI's own schema errors as
 * `{detail: [{msg, loc}]}`. This flattens both into something displayable.
 */
export function apiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d as { msg?: string })?.msg ?? String(d)).join("; ");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: string }).message;
    if (message) return message;
  }
  return fallback;
}

/** Structured context the backend attached to a 409/422 (blockers, conflicts…). */
export function apiErrorContext<T = Record<string, unknown>>(error: unknown): T | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  return detail && typeof detail === "object" && !Array.isArray(detail) ? (detail as T) : null;
}
