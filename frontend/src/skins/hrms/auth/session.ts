/** Intranet pages anyone can read without a session. Actions on them still
 * require sign-in — that's enforced in the page, not by kicking visitors off. */
export const PUBLIC_PATHS = [
  "/login",
  "/organization-policies",
  "/travel-request",
  "/referrals",
  "/open-positions",
  "/ld-calendar",
  "/holidays",
] as const;

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/** Only same-origin relative paths. Rejects protocol-relative (`//evil`) URLs. */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let decoded = raw;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null;
  }
  if (!decoded.startsWith("/") || decoded.startsWith("//") || decoded.includes("\\")) {
    return null;
  }
  try {
    const url = new URL(decoded, "http://hrms.invalid");
    if (url.origin !== "http://hrms.invalid") return null;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return null;
  }
}

export function loginPath(next?: string | null): string {
  const safe = safeNextPath(next);
  return safe ? `/login?next=${encodeURIComponent(safe)}` : "/login";
}
