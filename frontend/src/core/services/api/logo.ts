/**
 * Organization logo API.
 *
 * Reuses the generic filehandler module to store the logo image (under a
 * dedicated `org_logo` file type) and to serve its bytes back for display.
 * The stored organization `logo_url` holds the filehandler file id; `src()`
 * resolves it to a loadable <img> URL with the auth token in the query string
 * (an <img> cannot send an Authorization header).
 */

import { getAccessToken } from '../../auth';
import { API_BASE, getApiErrorMessage, request, uploadFile } from './client';

const LOGO_TYPE_ID = 'org_logo';

/** HTTP status carried on an API error (set by createApiError), if present. */
function errorStatus(error: unknown): number | undefined {
  return error && typeof error === 'object' && 'status' in error
    ? (error as { status?: number }).status
    : undefined;
}

/** Ensure the org_logo file type exists for the current org (idempotent). */
async function ensureLogoFileType(): Promise<void> {
  try {
    // Fast path: type already exists, so we skip the create call that would
    // otherwise error with "already exists" on every upload.
    await request(`/config/file-types/${LOGO_TYPE_ID}`);
    return;
  } catch (error) {
    // Only a 404 means the type is genuinely missing; surface anything else
    // (network/auth/server errors) rather than masking it behind a create.
    if (errorStatus(error) !== 404) throw error;
  }
  try {
    await request('/config/file-types', {
      method: 'POST',
      body: JSON.stringify({
        type_id: LOGO_TYPE_ID,
        display_name: 'Organization Logo',
        description: 'Organization branding logo image',
        folder: 'branding',
        allowed_extensions: ['.png', '.jpg', '.jpeg', '.svg', '.webp'],
        max_size_mb: 5,
        is_active: true,
        is_system: true,
      }),
    });
  } catch (error) {
    // Tolerate only a concurrent "already exists" race (the type was created
    // between our check and this call); rethrow any other failure.
    if (!getApiErrorMessage(error, '').toLowerCase().includes('already exists')) {
      throw error;
    }
  }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Every mount that needs the org logo (favicon in OrgDocumentHead, the
// sidebar/org-switcher, branding settings preview) resolves the same
// reference independently — cache by "logoRef::token" so simultaneous or
// repeated calls share one fetch instead of each downloading the image again.
const resolveCache = new Map<string, Promise<string | null>>();

export const orgLogo = {
  /** Upload an image as the org logo; returns the stored filehandler file id. */
  upload: async (file: File): Promise<string> => {
    await ensureLogoFileType();
    const uploaded = await uploadFile(LOGO_TYPE_ID, file);
    return String(uploaded.file_id || '');
  },

  /**
   * Resolve a stored logo reference into a loadable <img>/favicon src, or null.
   *
   * Filehandler-stored logos are fetched as a blob with the normal
   * Authorization header and returned as a data URL — unlike an object URL,
   * a data URL never needs revoking, so it can be safely cached and shared
   * across every simultaneous consumer without lifecycle coordination.
   * Absolute/data URLs are returned as-is (not cached; already cheap).
   */
  resolve: async (logoRef: string | null | undefined): Promise<string | null> => {
    if (!logoRef) return null;
    if (/^https?:\/\//i.test(logoRef) || logoRef.startsWith('data:')) return logoRef;
    const token = getAccessToken();
    if (!token) return null;

    const cacheKey = `${logoRef}::${token}`;
    const cached = resolveCache.get(cacheKey);
    if (cached) return cached;

    const pending = (async () => {
      try {
        const res = await fetch(`${API_BASE}/filehandler/${encodeURIComponent(logoRef)}/content`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return null;
        return await blobToDataUrl(await res.blob());
      } catch {
        return null;
      }
    })();
    resolveCache.set(cacheKey, pending);

    const result = await pending;
    // Don't cache a failed resolution — a transient network error shouldn't
    // permanently poison the cache for the rest of the session.
    if (result === null) resolveCache.delete(cacheKey);
    return result;
  },
};
