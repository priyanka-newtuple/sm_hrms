import { afterEach, expect, it, vi } from 'vitest';
import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { MoveTo } from './MoveTo';
afterEach(cleanup);
it('requires an explicit allowed selection and invokes the existing command once',()=>{
  const command=vi.fn();
  render(<MoveTo actions={[{trigger:'approve',label:'Approve'},{trigger:'denied',allowed:false,label:'Blocked'}]} onAction={command}/>);
  expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('option',{name:'Blocked'}) as HTMLOptionElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Move to'),{target:{value:'approve'}});
  fireEvent.click(screen.getByRole('button',{name:'Continue'}));
  expect(command).toHaveBeenCalledExactlyOnceWith('approve');
});
it('drops a selection when refreshed permissions remove that action',()=>{
  const command=vi.fn();
  const view=render(<MoveTo actions={[{trigger:'approve'}]} onAction={command}/>);
  fireEvent.change(screen.getByLabelText('Move to'),{target:{value:'approve'}});
  view.rerender(<MoveTo actions={[{trigger:'review'}]} onAction={command}/>);
  expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
  expect(command).not.toHaveBeenCalled();
});
