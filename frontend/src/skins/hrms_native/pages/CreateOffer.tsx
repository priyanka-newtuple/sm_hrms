import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { OfferEditor } from './OfferEditor';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { usePermissions } from '@/core/hooks/usePermissions';
import { getApiErrorMessage } from '@/core/services/api/client';
import { useWorkflowCatalog } from '../workflows/useWorkflowCatalog';
import { useHrmsCapabilities } from '../capabilities';

export default function CreateOffer() {
  const { data: capabilities } = useHrmsCapabilities();
  const allowed = capabilities?.capabilities.includes('cockpit:view') ?? false;
  const catalog = useWorkflowCatalog(allowed);
  const offers = (catalog.data ?? []).filter(w => w.entity_type.toLowerCase().replace(/[._]/g, '') === 'hrmsoffer');
  const [selected, setSelected] = useState('');
  const choice = offers.find(w => w.id === selected) ?? offers[0];
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const { can } = usePermissions();
  const canCreate = !!choice && can('create', choice.entity_type);
  if (!allowed) return null;
  return <section className="hrms-lk-card">
    <div className="hrms-lk-card-head"><h2 className="hrms-section-heading">Offers</h2>
      {choice && !catalog.isLoading && !catalog.isError && <button type="button" className="hrms-primary-button hrms-lk-add" disabled={!canCreate} onClick={() => setOpen(true)}><Plus size={16}/> Add offer</button>}
    </div>
    <div className="p-6">
    <p className="mb-4">Create an offer and follow its approval and acceptance progress.</p>
    {catalog.isLoading ? <p role="status">Loading offer workflow…</p> : catalog.isError ?
      <p role="alert">{getApiErrorMessage(catalog.error)} <button className="hrms-outline-button" onClick={() => void catalog.refetch()}>Retry</button></p> :
      !choice ? <p>Publish an active workflow for hrms_offer in Settings to create offers here.</p> : <>
        {offers.length > 1 && <label>Offer workflow <select className="hrms-field-input" value={choice.id} onChange={e => setSelected(e.target.value)}>{offers.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}
        <div className="flex flex-wrap items-center gap-3">
          <Link className="hrms-outline-button" to={`/hrms/workflows?workflow=${encodeURIComponent(choice.machine_name)}`}>View offers</Link>
        </div>
        {!canCreate && <p>Your role needs native create permission for the offer entity.</p>}
      </>}
    </div>
    <Sheet open={open} onOpenChange={setOpen}><SheetContent className="hrms-brand overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-5xl"><SheetHeader><SheetTitle>Create offer</SheetTitle></SheetHeader>{open && choice && <OfferEditor machineName={choice.machine_name} onSaved={()=>{void client.invalidateQueries({queryKey:['hrms','workflows']});}}/>}</SheetContent></Sheet>
  </section>;
}
