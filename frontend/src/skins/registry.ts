/**
 * Skin Registry
 *
 * The single place where all skin manifests are merged into one map.
 * SkinContext reads from this — it never imports skins directly.
 *
 * Customer deployments inject their skins without touching this file:
 *   1. Set CUSTOMER_SKINS_PATH in the build env to point at a file that
 *      exports `customerSkins: Record<string, SkinManifest>`.
 *   2. Set VITE_SKIN_ID=<skin-id> so SkinContext activates the right skin.
 *   Vite resolves @customer-skins to that file at build time; if the env
 *   var is absent the stub at `./customer-skins.stub.ts` is used instead.
 */

import type { SkinManifest } from './types';
import { skin as defaultSkin } from './skin.config';
import { customerSkins } from '@customer-skins';

export const SKIN_REGISTRY: Record<string, SkinManifest> = {
  [defaultSkin.id]: defaultSkin,
  ...customerSkins,
};

export function registerSkin(skin: SkinManifest): void {
  SKIN_REGISTRY[skin.id] = skin;
}

/**
 * Resolves the active skin from the registry.
 * Falls back to the 'default' key, then to the first registered skin, then undefined.
 * Extracted from App.tsx so it can be unit-tested in isolation.
 */
export function resolveActiveSkin(skinId: string): SkinManifest | undefined {
  return SKIN_REGISTRY[skinId] ?? SKIN_REGISTRY['default'] ?? Object.values(SKIN_REGISTRY)[0];
}
