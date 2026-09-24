export type MethodLibraryEntity = 'method' | 'composite-block';

export interface MethodLibraryLabels {
  entityTitle: string;
  entityTitlePlural: string;
  entityLower: string;
  entityLowerPlural: string;
  libraryLabel: string;
  libraryItemTitle: string;
  libraryItemTitlePlural: string;
  libraryItemLower: string;
  libraryItemLowerPlural: string;
  libraryItemPossessive: string;
}

/**
 * Keeps the platform nouns and the PE skin nouns in one explicit mapping.
 * The platform presents Method-backed field lists as Forms. Internal API and
 * storage identifiers remain Method-based; this mapping changes copy only.
 */
export function getMethodLibraryLabels(entity: MethodLibraryEntity): MethodLibraryLabels {
  if (entity === 'composite-block') {
    return {
      entityTitle: 'Composite Block',
      entityTitlePlural: 'Composite Blocks',
      entityLower: 'composite block',
      entityLowerPlural: 'composite blocks',
      libraryLabel: 'Step Objects',
      libraryItemTitle: 'Step Object',
      libraryItemTitlePlural: 'Step Objects',
      libraryItemLower: 'step object',
      libraryItemLowerPlural: 'step objects',
      libraryItemPossessive: 'step object’s',
    };
  }

  return {
    entityTitle: 'Form',
    entityTitlePlural: 'Forms',
    entityLower: 'form',
    entityLowerPlural: 'forms',
    libraryLabel: 'Field Library',
    libraryItemTitle: 'Field',
    libraryItemTitlePlural: 'Fields',
    libraryItemLower: 'field',
    libraryItemLowerPlural: 'fields',
    libraryItemPossessive: 'field’s',
  };
}
