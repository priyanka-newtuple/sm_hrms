import { useState } from 'react';

export interface Paged<T> { items: T[]; page: number; pages: number; total: number; size: number; setPage: (page: number) => void }

/** Client-side pages; going back to the first page whenever `resetKey` (filters, search) changes. */
export function usePaged<T>(rows: T[], size = 20, resetKey = ''): Paged<T> {
  const [state, setState] = useState({ key: resetKey, page: 0 });
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const page = Math.min(state.key === resetKey ? state.page : 0, pages - 1);
  return { items: rows.slice(page * size, page * size + size), page, pages, total: rows.length, size, setPage: next => setState({ key: resetKey, page: next }) };
}

/** Case-insensitive match of a search phrase against the given values. */
export function matchesText(query: string, values: unknown[]) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return values.some(v => (typeof v === 'string' || typeof v === 'number') && String(v).toLowerCase().includes(needle));
}
