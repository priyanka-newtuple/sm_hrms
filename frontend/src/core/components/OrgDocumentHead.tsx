/**
 * OrgDocumentHead
 *
 * Drives the browser tab's title and favicon from the active organization's
 * branding. Falls back to the skin's product name and the static favicon in
 * index.html when no organization is loaded — e.g. on the login page.
 *
 * The favicon is set imperatively (not via Helmet): we update the *existing*
 * `<link rel="icon">` element so the static index.html icon can't win, and we
 * point it at a data URL because blob:/object URLs are unreliable as favicons
 * across browsers.
 *
 * Must render inside both AuthProvider (for the active org) and SkinProvider
 * (for the fallback product name).
 */

import { useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import { useAuth } from '../auth';
import { useSkin } from '../../skins';
import { orgLogo } from '../services/api';

const DEFAULT_FAVICON = '/favicon.svg';

/** Point the document's `<link rel="icon">` at `href`, creating it if absent. */
function setFavicon(href: string): void {
  let link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  // Drop the static `type="image/svg+xml"` so a PNG/JPG data URL isn't mislabeled.
  link.removeAttribute('type');
  link.href = href;
}

export function OrgDocumentHead() {
  const { organization } = useAuth();
  const { skin } = useSkin();

  const title = organization?.name?.trim() || skin.branding.name;

  // Resolve the org logo to a data URL and apply it as the favicon. Restore the
  // default favicon whenever there is no org logo (e.g. after logout).
  useEffect(() => {
    let cancelled = false;
    const logoRef = organization?.logoUrl;

    if (!logoRef) {
      setFavicon(DEFAULT_FAVICON);
      return;
    }

    orgLogo.resolve(logoRef).then((url) => {
      if (cancelled) return;
      setFavicon(url || DEFAULT_FAVICON);
    });

    return () => {
      cancelled = true;
    };
  }, [organization?.logoUrl]);

  return (
    <Helmet>
      <title>{title}</title>
    </Helmet>
  );
}

export default OrgDocumentHead;
