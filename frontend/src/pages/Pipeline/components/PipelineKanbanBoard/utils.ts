import { formatDistanceToNowStrict } from 'date-fns';

export function formatRelative(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return formatDistanceToNowStrict(date, { addSuffix: false });
}
