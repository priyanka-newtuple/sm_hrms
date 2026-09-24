import type { UserSearchResult } from '@/core/types';

export interface MentionDraft {
  id: string;
  fullName: string;
  start: number;
  end: number;
}

const RAW_MENTION_RE = /@\[([^\]]+)\]\(([^)]+)\)/g;

function getVisibleMentionLabel(fullName: string): string {
  return `@${fullName}`;
}

function findChangeWindow(previousText: string, nextText: string) {
  let start = 0;
  while (
    start < previousText.length &&
    start < nextText.length &&
    previousText[start] === nextText[start]
  ) {
    start += 1;
  }

  let previousEnd = previousText.length;
  let nextEnd = nextText.length;
  while (
    previousEnd > start &&
    nextEnd > start &&
    previousText[previousEnd - 1] === nextText[nextEnd - 1]
  ) {
    previousEnd -= 1;
    nextEnd -= 1;
  }

  return {
    start,
    deletedCount: previousEnd - start,
    insertedCount: nextEnd - start,
  };
}

export function parseMentionText(rawText: string): { text: string; mentions: MentionDraft[] } {
  const mentions: MentionDraft[] = [];
  let text = '';
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  RAW_MENTION_RE.lastIndex = 0;
  while ((match = RAW_MENTION_RE.exec(rawText)) !== null) {
    text += rawText.slice(lastIndex, match.index);
    const mentionText = getVisibleMentionLabel(match[1]);
    const start = text.length;
    text += mentionText;
    mentions.push({
      id: match[2],
      fullName: match[1],
      start,
      end: start + mentionText.length,
    });
    lastIndex = match.index + match[0].length;
  }

  text += rawText.slice(lastIndex);
  return { text, mentions };
}

export function serializeMentionText(text: string, mentions: MentionDraft[]): string {
  if (mentions.length === 0) return text;

  const sortedMentions = [...mentions].sort((a, b) => a.start - b.start);
  let rawText = '';
  let cursor = 0;

  for (const mention of sortedMentions) {
    if (mention.start < cursor || mention.end > text.length) continue;
    const visibleLabel = getVisibleMentionLabel(mention.fullName);
    const visibleSlice = text.slice(mention.start, mention.end);
    if (visibleSlice !== visibleLabel) continue;

    rawText += text.slice(cursor, mention.start);
    rawText += `@[${mention.fullName}](${mention.id})`;
    cursor = mention.end;
  }

  rawText += text.slice(cursor);
  return rawText;
}

export function reconcileMentions(
  previousText: string,
  nextText: string,
  mentions: MentionDraft[],
): MentionDraft[] {
  if (mentions.length === 0) return mentions;

  const { start, deletedCount, insertedCount } = findChangeWindow(previousText, nextText);
  const deletedEnd = start + deletedCount;
  const offset = insertedCount - deletedCount;

  return mentions
    .flatMap((mention) => {
      if (mention.end <= start) {
        return [mention];
      }

      if (mention.start >= deletedEnd) {
        return [
          {
            ...mention,
            start: mention.start + offset,
            end: mention.end + offset,
          },
        ];
      }

      return [];
    })
    .filter((mention) => nextText.slice(mention.start, mention.end) === getVisibleMentionLabel(mention.fullName));
}

export function insertMention(
  text: string,
  mentions: MentionDraft[],
  user: UserSearchResult,
  start: number,
  end: number,
): { text: string; mentions: MentionDraft[]; cursor: number } {
  const mentionText = `${getVisibleMentionLabel(user.full_name)} `;
  const nextText = `${text.slice(0, start)}${mentionText}${text.slice(end)}`;
  const shiftedMentions = reconcileMentions(text, nextText, mentions).filter(
    (mention) => mention.end <= start || mention.start >= end,
  );
  const mentionStart = start;
  const visibleLabel = getVisibleMentionLabel(user.full_name);
  const mentionEnd = mentionStart + visibleLabel.length;
  const nextMentions = [
    ...shiftedMentions,
    {
      id: user.id,
      fullName: user.full_name,
      start: mentionStart,
      end: mentionEnd,
    },
  ].sort((a, b) => a.start - b.start);

  return {
    text: nextText,
    mentions: nextMentions,
    cursor: mentionText.length + start,
  };
}
