/**
 * Tracks which input slot is currently focused and handles inserting a token
 * string into that slot. Works with the `EntityFieldsPanel` sidebar.
 *
 * The focused slot is mirrored into a ref so `insertToken` always reads the
 * latest value at click time — immune to stale closures / render timing that
 * can otherwise leave it `null` when a chip is clicked.
 */

import { useRef, useState } from 'react';
import { toast } from 'sonner';

import type { FocusedSlot, KeyValueRow } from '../types';

interface UseTokenInsertionArgs {
  setPath: React.Dispatch<React.SetStateAction<string>>;
  setRawBody: React.Dispatch<React.SetStateAction<string>>;
  setHeaderRows: React.Dispatch<React.SetStateAction<KeyValueRow[]>>;
  setQueryRows: React.Dispatch<React.SetStateAction<KeyValueRow[]>>;
}

export function useTokenInsertion({
  setPath,
  setRawBody,
  setHeaderRows,
  setQueryRows,
}: UseTokenInsertionArgs) {
  const [focusedSlot, setFocusedSlotState] = useState<FocusedSlot>(null);
  const slotRef = useRef<FocusedSlot>(null);

  const setFocusedSlot = (slot: FocusedSlot) => {
    slotRef.current = slot;
    setFocusedSlotState(slot);
  };

  const insertToken = (token: string) => {
    const slot = slotRef.current;
    if (!slot) {
      toast.info('Click a field first, then insert a variable.');
      return;
    }
    if (slot === 'path') {
      setPath((prev) => prev + token);
    } else if (slot === 'rawBody') {
      setRawBody((prev) => prev + token);
    } else if (slot.section === 'header') {
      setHeaderRows((prev) =>
        prev.map((r, i) => (i === slot.index ? { ...r, value: r.value + token } : r)),
      );
    } else {
      setQueryRows((prev) =>
        prev.map((r, i) => (i === slot.index ? { ...r, value: r.value + token } : r)),
      );
    }
  };

  return { focusedSlot, setFocusedSlot, insertToken };
}
