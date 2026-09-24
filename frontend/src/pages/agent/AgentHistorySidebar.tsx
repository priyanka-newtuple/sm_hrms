import { useState } from 'react';
import { Check, Loader2, MessageSquare, MessageSquarePlus, Pencil, Trash2, X } from 'lucide-react';
import { useAgent } from '@/core/agent';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';

/** Relative date for a conversation row: Today / Yesterday / N days ago. */
function formatDate(date: Date): string {
  const days = Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24));
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  return date.toLocaleDateString();
}

/**
 * Collapsible ChatGPT/Claude-style history rail for full-screen Agent Mode.
 * Reuses the app's Sidebar primitive and the same useAgent() thread state as
 * the docked sidebar's HistoryTab, adding inline rename + delete row actions.
 */
export default function AgentHistorySidebar() {
  const {
    threads,
    currentThread,
    isLoadingSessions,
    selectThread,
    startNewThread,
    renameThread,
    deleteThread,
  } = useAgent();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState('');

  const beginRename = (id: string, title: string) => {
    setEditingId(id);
    setDraftTitle(title);
  };
  const commitRename = () => {
    if (editingId) void renameThread(editingId, draftTitle);
    setEditingId(null);
  };

  return (
    <Sidebar collapsible="offcanvas" className="border-r border-border">
      <SidebarHeader className="gap-3 p-3">
        <div className="flex items-center gap-2 px-1 pt-1">
          <span className="h-2 w-2 rounded-full bg-cobalt" />
          <span className="text-sm font-semibold tracking-tight text-foreground">Conversations</span>
        </div>
        <button
          type="button"
          onClick={startNewThread}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-cobalt px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-cobalt/90"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New conversation
        </button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup className="p-2">
          {isLoadingSessions ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-cobalt" />
            </div>
          ) : threads.length === 0 ? (
            <p className="px-2 py-8 text-center text-sm text-muted-foreground">No conversations yet</p>
          ) : (
            <SidebarMenu>
              {threads.map((thread) => {
                const active = currentThread?.id === thread.id;
                const editing = editingId === thread.id;
                return (
                  <SidebarMenuItem key={thread.id} className="group/row relative">
                    {editing ? (
                      <div className="flex items-center gap-1 px-2 py-1.5">
                        <input
                          autoFocus
                          value={draftTitle}
                          onChange={(e) => setDraftTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitRename();
                            if (e.key === 'Escape') setEditingId(null);
                          }}
                          className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring/30"
                        />
                        <button type="button" onClick={commitRename} aria-label="Save" className="text-muted-foreground hover:text-foreground">
                          <Check className="h-4 w-4" />
                        </button>
                        <button type="button" onClick={() => setEditingId(null)} aria-label="Cancel" className="text-muted-foreground hover:text-foreground">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <>
                        <SidebarMenuButton
                          isActive={active}
                          onClick={() => void selectThread(thread.id)}
                          className="h-auto min-h-12 items-start gap-2 rounded-lg py-2 pr-14 data-[active=true]:bg-cobalt/10 data-[active=true]:text-cobalt"
                        >
                          <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="flex min-w-0 flex-col gap-0.5">
                            <span className="w-full truncate text-sm font-medium">{thread.title}</span>
                            <span className="w-full truncate text-xs text-muted-foreground">
                              {thread.agentName && <span className="text-cobalt">{thread.agentName} · </span>}
                              {formatDate(thread.updatedAt)}
                            </span>
                          </span>
                        </SidebarMenuButton>
                        <div className="absolute right-1.5 top-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover/row:opacity-100">
                          <button
                            type="button"
                            onClick={() => beginRename(thread.id, thread.title)}
                            aria-label="Rename conversation"
                            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              if (window.confirm('Delete this conversation?')) void deleteThread(thread.id);
                            }}
                            aria-label="Delete conversation"
                            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </>
                    )}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          )}
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
