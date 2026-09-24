export function formatLibraryCount(
  total: number,
  isSearching: boolean,
  itemLabel: string,
  itemLabelPlural: string,
): string {
  if (isSearching) return `${total} match${total === 1 ? '' : 'es'}`;
  return `${total} ${total === 1 ? itemLabel : itemLabelPlural}`;
}
