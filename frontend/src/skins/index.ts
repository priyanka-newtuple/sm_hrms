/**
 * Skin System — Public Exports
 *
 * Import everything skin-related from this barrel file, not from sub-modules
 * directly. This keeps the public API stable as internals evolve.
 */

// React context provider and hook
export { SkinProvider, useSkin } from './SkinContext';

// Type definitions
export type {
  SkinManifest,
  NavItem,
  BrandingConfig,
  EntityTypeConfig,
  StageConfig,
  BoardConfig,
  FilterBarItem,
  FilterBarItemType,
  ActionButtonConfig,
  ActionButtonStyle,
  FieldGroup,
  FieldMapping,
  EntityViewConfig,
  StateMachineDefinition,
} from './types';

// Utility helpers
export { getStateTokens } from './skinUtils';
export type { StateDisplayTokens } from './skinUtils';

// Component slot registry
export type { SkinComponents } from '../core/componentRegistry';

// Default skin config and runtime env vars
export { skin, env } from './skin.config';
