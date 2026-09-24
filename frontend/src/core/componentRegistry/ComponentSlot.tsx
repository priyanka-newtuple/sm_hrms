import type { ReactNode } from 'react';
import type { SlotName, SlotProps, SlotComponent } from './types';

interface ComponentSlotProps<S extends SlotName> {
  slotName: S;
  component: SlotComponent<S> | undefined;
  slotProps: SlotProps[S];
  fallback?: ReactNode;
}

export function ComponentSlot<S extends SlotName>({
  component: Slot,
  slotProps,
  fallback = null,
}: ComponentSlotProps<S>) {
  if (!Slot) return <>{fallback}</>;
  if (Slot.canHandle && !Slot.canHandle(slotProps)) return <>{fallback}</>;
  return <Slot {...slotProps} />;
}
