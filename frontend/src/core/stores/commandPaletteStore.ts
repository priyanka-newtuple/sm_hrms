import { create } from 'zustand';

/** Open/close state for the global ⌘K command palette. Kept in a store (not
 *  local state) so any trigger — the sidebar "Quick actions" button, the top-bar
 *  search button, or the global keyboard shortcut — can drive the same dialog. */
interface CommandPaletteStore {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

export const useCommandPaletteStore = create<CommandPaletteStore>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}));
