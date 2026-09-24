import type { SkinManifest } from './types';

// Default empty stub — replaced at build time via CUSTOMER_SKINS_PATH env var.
export const customerSkins: Record<string, SkinManifest> = {};
