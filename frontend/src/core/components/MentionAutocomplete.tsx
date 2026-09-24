import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, X, ChevronRight } from 'lucide-react';
import { comments as commentsApi } from '../services/api';
import { resolveEnumLabel } from '@/shared/utils/labels';
import type { UserSearchResult } from '../types';

interface MentionAutocompleteProps {
  query: string;
  position: { top: number; left: number };
  onSelect: (user: UserSearchResult) => void;
  onClose: () => void;
  anchorBottom?: boolean;
}

const AVATAR_PALETTE = [
  'bg-emerald-500',
  'bg-teal-500',
  'bg-violet-500',
  'bg-orange-400',
  'bg-rose-500',
  'bg-sky-500',
  'bg-amber-500',
  'bg-indigo-500',
];

function pickColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length];
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');
}

export default function MentionAutocomplete({
  query,
  position,
  onSelect,
  onClose,
  anchorBottom = false,
}: MentionAutocompleteProps) {
  const [users, setUsers] = useState<UserSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query || query.length < 1) {
      setUsers([]);
      return;
    }

    const search = async () => {
      setLoading(true);
      try {
        const results = await commentsApi.searchUsers(query, 8);
        setUsers(results);
        setSelectedIndex(0);
      } catch {
        setUsers([]);
      } finally {
        setLoading(false);
      }
    };

    const t = setTimeout(search, 150);
    return () => clearTimeout(t);
  }, [query]);

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return;
    const item = listRef.current.children[selectedIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target instanceof HTMLElement ? e.target : null;
      const insideDropdown = !!(target && containerRef.current?.contains(target));
      const insideComposer = !!target?.closest('[data-comment-composer="true"]');
      if (!insideDropdown && !insideComposer) return;
      if (users.length === 0) return;
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((p) => (p + 1) % users.length);
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((p) => (p - 1 + users.length) % users.length);
          break;
        case 'Enter':
        case 'Tab':
          e.preventDefault();
          if (users[selectedIndex]) onSelect(users[selectedIndex]);
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    },
    [users, selectedIndex, onSelect, onClose],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    function outside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', outside);
    return () => document.removeEventListener('mousedown', outside);
  }, [onClose]);

  if (!query || (users.length === 0 && !loading)) return null;

  const dropdown = (
    <div
      ref={containerRef}
      className="fixed z-[200] w-80 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl"
      style={
        anchorBottom
          ? { bottom: window.innerHeight - position.top + 8, left: position.left }
          : { top: position.top + 6, left: position.left }
      }
    >
      {/* Header */}
      <div className="flex items-start justify-between px-3.5 py-2.5 border-b border-border">
        <div>
          <p className="text-xs font-semibold text-foreground">Mention a teammate</p>
          {!loading && users.length > 0 && (
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {users.length} match{users.length !== 1 ? 'es' : ''} · they&apos;ll get a notification
            </p>
          )}
          {loading && (
            <p className="text-[10px] text-muted-foreground mt-0.5">Searching…</p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ml-2 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-muted-foreground transition-colors flex-shrink-0"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Section label */}
      {!loading && users.length > 0 && (
        <div className="flex items-center justify-between bg-muted/50 px-3.5 py-1.5 border-b border-border">
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Suggestions
          </span>
          <span className="text-[10px] font-semibold text-muted-foreground">{users.length}</span>
        </div>
      )}

      {/* User list */}
      <div ref={listRef} className="max-h-56 overflow-y-auto">
        {loading ? (
          <div className="flex items-center gap-2.5 px-3.5 py-3 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-cobalt" />
            Searching for teammates…
          </div>
        ) : (
          users.map((user, index) => {
            const active = index === selectedIndex;
            return (
              <button
                key={user.id}
                type="button"
                onClick={() => onSelect(user)}
                onMouseEnter={() => setSelectedIndex(index)}
                className={[
                  'flex w-full items-center gap-2.5 px-3 py-1.5 text-left transition-colors',
                  active ? 'bg-emerald-50' : 'hover:bg-muted/50',
                ].join(' ')}
              >
                {/* Avatar */}
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.full_name}
                    className="h-7 w-7 flex-shrink-0 rounded-full object-cover"
                  />
                ) : (
                  <div
                    className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full ${pickColor(user.full_name)}`}
                  >
                    <span className="text-xs font-bold text-white leading-none">
                      {getInitials(user.full_name)}
                    </span>
                  </div>
                )}

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-xs font-semibold ${active ? 'text-emerald-800' : 'text-foreground'}`}>
                    {user.full_name}
                  </p>
                  <p className="truncate text-[10px] capitalize text-muted-foreground">
                    {resolveEnumLabel(user.role ?? 'member')}
                  </p>
                </div>

                {/* Active chevron */}
                {active && (
                  <ChevronRight className="h-4 w-4 flex-shrink-0 text-emerald-500" />
                )}
              </button>
            );
          })
        )}
      </div>

      {/* Footer */}
      {!loading && users.length > 0 && (
        <div className="flex items-center justify-between border-t border-border bg-muted/50 px-3.5 py-2">
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
            <span>
              <kbd className="font-mono">↑↓</kbd> navigate
            </span>
            <span>
              <kbd className="font-mono">↵</kbd> select
            </span>
            <span>
              <kbd className="font-mono">esc</kbd> dismiss
            </span>
          </div>
        </div>
      )}
    </div>
  );

  return createPortal(dropdown, document.body);
}