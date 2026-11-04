import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecordTabs } from './RecordTabs';

const state = vi.hoisted(() => ({ allowed: false, archived: false, writes: [] as string[] }));
vi.mock('@/core/services/api/client', () => ({
  getApiErrorMessage: String,
  request: async (path: string, options?: {method?: string}) => {
    if (options?.method === 'DELETE') { state.writes.push(path); state.archived = true; return {}; }
    if (state.archived) throw new Error('Record no longer available');
    return {current_state:'Review', can_edit_due_date:state.allowed, can_archive:state.allowed};
  },
}));
vi.mock('./RecordActivity', () => ({default: () => <p>Audit history</p>}));
vi.mock('./RecordComments', () => ({default: () => <p>Record comments</p>}));
afterEach(() => { cleanup(); state.allowed=false; state.archived=false; state.writes=[]; });
function show() {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><RecordTabs entityId="record" scope="employee" actions={<button>Move to</button>}>
    <input aria-label="Unsaved note" defaultValue="Draft"/>
  </RecordTabs></QueryClientProvider>);
}
it('keeps drafts mounted while switching tabs and respects native control permissions', async () => {
  show();
  expect((await screen.findByLabelText('Due date') as HTMLInputElement).disabled).toBe(true);
  expect(screen.queryByRole('button',{name:'Archive record'})).toBeNull();
  fireEvent.change(screen.getByLabelText('Unsaved note'),{target:{value:'Keep this draft'}});
  fireEvent.click(screen.getByRole('tab',{name:'Comments'}));
  expect(screen.getByText('Record comments')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'Details'}));
  expect((screen.getByLabelText('Unsaved note') as HTMLInputElement).value).toBe('Keep this draft');
});
it('requires archive confirmation and removes write controls after archive even when refetch is denied', async () => {
  state.allowed=true; show();
  fireEvent.click(await screen.findByRole('button',{name:'Archive record'}));
  expect(state.writes).toHaveLength(0);
  fireEvent.click(screen.getAllByRole('button',{name:'Archive record'})[1]);
  await screen.findByText('Record archived. Close this panel to return to the updated list.');
  expect(state.writes).toHaveLength(1);
  expect(screen.queryByRole('button',{name:'Move to'})).toBeNull();
  expect(screen.queryByLabelText('Unsaved note')).toBeNull();
});
