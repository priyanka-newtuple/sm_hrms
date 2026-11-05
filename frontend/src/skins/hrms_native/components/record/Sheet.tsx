import { createContext, lazy, Suspense, useContext, useEffect, useState, type ComponentProps } from 'react';
import { create } from 'zustand';
import * as Native from '@/components/ui/sheet';
import { DocumentPreviewAvailable } from './DocumentPreviewContext';
import { useDocumentPreviewStore } from '@/core/stores/documentPreviewStore';

const DocumentPreviewPanel = lazy(() => import('@/core/components/DocumentPreviewPanel'));
const Open = createContext(false);
const usePanels = create<{ stack: symbol[] }>(() => ({ stack: [] }));

/** One skin-level frame; native dialogs, document access and preview remain authoritative. */
export function Sheet({ children, ...props }: ComponentProps<typeof Native.Sheet>) {
  const [localOpen, setLocalOpen] = useState(props.defaultOpen ?? false);
  return <Open.Provider value={props.open ?? localOpen}><Native.Sheet {...props}
    onOpenChange={(open, event) => { setLocalOpen(open); props.onOpenChange?.(open, event); }}>
    {children}
  </Native.Sheet></Open.Provider>;
}

export function SheetContent({ children, className = '', style, ...props }: ComponentProps<typeof Native.SheetContent>) {
  const open = useContext(Open);
  const [owner] = useState(() => Symbol('record-panel'));
  const top = usePanels(s => s.stack.at(-1));
  const docs = useDocumentPreviewStore(s => s.docs);
  const collapsed = useDocumentPreviewStore(s => s.collapsed);
  useEffect(() => {
    if (!open) return;
    const previous = useDocumentPreviewStore.getState();
    const parent = usePanels.getState().stack.at(-1);
    useDocumentPreviewStore.getState().reset();
    usePanels.setState(s => ({stack:[...s.stack,owner]}));
    return () => {
      usePanels.setState(s => ({stack:s.stack.filter(id=>id!==owner)}));
      useDocumentPreviewStore.getState().reset();
      if (parent && usePanels.getState().stack.at(-1) === parent) {
        const {docs, contextEntityId, docsSource, activeIndex, collapsed} = previous;
        useDocumentPreviewStore.setState({docs, contextEntityId, docsSource, activeIndex, collapsed});
      }
    };
  }, [open, owner]);
  const preview = open && top === owner && docs.length > 0;
  return <Native.SheetContent {...props} className="hrms-brand hrms-record-sheet flex-row gap-0 overflow-hidden p-0"
    style={{ ...style, width: preview ? (collapsed ? '59rem' : '90rem') : '56rem', maxWidth: '100vw' }}>
    {preview && <Suspense fallback={<p role="status" className="p-4">Loading document preview…</p>}><DocumentPreviewPanel layout="sheet" /></Suspense>}
    <DocumentPreviewAvailable.Provider value={open && top === owner}>
      <div className={`hrms-record-panel min-w-0 flex-1 overflow-y-auto p-6 sm:p-8 ${(typeof className === 'string' ? className : '').split(' ').filter(c=>!c.includes('data-[side=')&&!c.startsWith('overflow-')).join(' ')}`}>
        {children}
      </div>
    </DocumentPreviewAvailable.Provider>
  </Native.SheetContent>;
}

export const SheetHeader = Native.SheetHeader;
export const SheetTitle = Native.SheetTitle;
export const SheetDescription = Native.SheetDescription;
export const SheetFooter = Native.SheetFooter;
export const SheetClose = Native.SheetClose;
export const SheetTrigger = Native.SheetTrigger;
