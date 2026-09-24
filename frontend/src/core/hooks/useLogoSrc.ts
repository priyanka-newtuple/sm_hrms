/**
 * useLogoSrc
 *
 * Resolves a stored organization logo reference into a displayable <img> src.
 * Filehandler-backed logos are fetched once (auth via header) and cached as a
 * data URL by `orgLogo.resolve` — safe to share across every simultaneous
 * consumer with no revocation needed. Returns null until loaded or when
 * unavailable, so callers fall back to initials.
 */

import { useEffect, useState } from 'react';
import { orgLogo } from '../services/api';

export function useLogoSrc(logoRef: string | null | undefined): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setSrc(null);

    orgLogo.resolve(logoRef).then((url) => {
      if (active) setSrc(url);
    });

    return () => {
      active = false;
    };
  }, [logoRef]);

  return src;
}
