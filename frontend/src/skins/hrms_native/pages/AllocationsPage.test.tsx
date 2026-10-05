import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AllocationsPage from './AllocationsPage';

const state = vi.hoisted(() => ({caps: {} as any, board: {} as any, retry: vi.fn()}));
vi.mock('../capabilities', () => ({useHrmsCapabilities: () => state.caps}));
vi.mock('../workflows/WorkflowConfiguration', () => ({useWorkflowConfiguration: () => ({data: [{entity_id: 'a1', state_label: 'Staffed'}]})}));
vi.mock('./ProjectsPage', () => ({
  useProjects: () => state.board,
  ProjectRecovery: () => null,
  ProjectDetail: ({entityId}: {entityId: string}) => <p>Details for {entityId}</p>,
  ProjectAction: ({item, action}: {item: {id: string}; action: string}) => <p>Shared action {action} for {item.id}</p>,
}));
const project = (id: string, allowed: boolean) => ({id, kind: 'HRMS.Project', project_name: id, state: 'active', data: {}, actions: allowed ? ['request_allocation'] : []});
function show(path = '/hrms/allocations') {return render(<MemoryRouter initialEntries={[path]}><AllocationsPage /></MemoryRouter>);}
beforeEach(() => {
  state.caps = {data: {capabilities: ['project:view']}};
  state.board = {isSuccess: true, refetch: state.retry, data: {
    projects: [project('Managed project', true), project('Read only project', false)],
    allocations: [{id: 'a1', kind: 'HRMS.Allocation', state: 'active', project_name: 'Managed project', actions: [], data: {project_id: 'Managed project', employee_name: 'Mira', project_role_name: 'Engineer', percentage: 50}}],
    requests: [
      {id: 'r1', kind: 'HRMS.AllocationChange', state: 'draft', project_name: 'Managed project', data: {project_id: 'Managed project', proposed: {employee_name: 'Anya', percentage: 25}}},
      {id: 'r2', kind: 'HRMS.ProjectChange', state: 'pending', project_name: 'Hidden project request', data: {}},
    ],
  }};
});
afterEach(cleanup);

describe('Allocations workspace', () => {
  it('shows the authorized allocation and configured state, with filters and project links', () => {
    show();
    expect(screen.getByText('Mira')).toBeTruthy();
    expect(screen.getByRole('cell', {name: 'Staffed'})).toBeTruthy();
    expect(screen.getByRole('link', {name: 'Managed project'}).getAttribute('href')).toContain('/hrms/projects?project=');
    fireEvent.change(screen.getByLabelText('Search allocations'), {target: {value: 'nobody'}});
    expect(screen.getByText('No allocations match your filters.')).toBeTruthy();
  });
  it('separates draft requests from committed allocations and links to the existing workflow', () => {
    show();
    expect(screen.queryByText('Anya')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Requests'}));
    expect(screen.getByText('Anya')).toBeTruthy();
    expect(screen.queryByText('Hidden project request')).toBeNull();
    expect(screen.getByRole('link', {name: 'View request'}).getAttribute('href')).toBe('/hrms/workflows?case=r1');
  });
  it('offers only eligible projects and reuses the existing allocation command', () => {
    show();
    fireEvent.click(screen.getByRole('button', {name: 'Add allocation'}));
    const select = screen.getByLabelText('Project') as HTMLSelectElement;
    expect([...select.options].map(option => option.value)).toEqual(['', 'Managed project']);
    expect(screen.getByText('Shared action request_allocation for Managed project')).toBeTruthy();
  });
  it('does not offer allocation creation to a read-only account', () => {
    state.board.data.projects = [project('Read only project', false)];
    show();
    expect(screen.queryByRole('button', {name: 'Add allocation'})).toBeNull();
  });
  it('shows API failure with retry instead of an empty directory', () => {
    state.board = {isError: true, error: new Error('Unavailable'), refetch: state.retry};
    show();
    expect(screen.queryByText('Allocation directory')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Retry'}));
    expect(state.retry).toHaveBeenCalled();
  });
  it('denies access without the configured module capability', () => {
    state.caps = {data: {capabilities: []}};
    show();
    expect(screen.getByRole('alert').textContent).toContain('do not have access');
    expect(screen.queryByText('Mira')).toBeNull();
  });
});
