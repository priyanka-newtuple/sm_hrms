import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { authApi } from '@/core/auth/api';
import ResetPasswordPage from './ResetPasswordPage';

vi.mock('@/core/auth/api', () => ({ authApi: { resetPassword: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });
const tokenAt = (exp: number) => `header.${btoa(JSON.stringify({ exp }))}.signature`;
function show(token = tokenAt(Date.now() / 1000 + 3600)) {
  render(<MemoryRouter initialEntries={[`/reset-password?token=${encodeURIComponent(token)}`]}><ResetPasswordPage /></MemoryRouter>);
}
function submit() {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'Example-password1!' } });
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'Example-password1!' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save password' }));
}
it('offers recovery before asking for a password when the link has expired', () => {
  show(tokenAt(Date.now() / 1000 - 5));
  expect(screen.getByRole('heading', { name: 'This link has expired' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Request a new link' }).getAttribute('href')).toBe('/forgot-password');
  expect(screen.queryByLabelText('New password')).toBeNull();
  expect(authApi.resetPassword).not.toHaveBeenCalled();
});
it('handles a missing token without submitting a reset', () => {
  show('');
  expect(screen.getByRole('heading', { name: 'This link is invalid' })).toBeTruthy();
  expect(authApi.resetPassword).not.toHaveBeenCalled();
});
it('still requires native validation even when the displayed expiry is in the future', async () => {
  vi.mocked(authApi.resetPassword).mockRejectedValue(new Error('Invalid or expired reset link. Please request a new one.'));
  const token = tokenAt(Date.now() / 1000 + 3600);
  show(token); submit();
  expect(await screen.findByRole('heading', { name: 'This link is invalid or has expired' })).toBeTruthy();
  expect(authApi.resetPassword).toHaveBeenCalledWith(token, 'Example-password1!');
  expect(screen.queryByLabelText('New password')).toBeNull();
});
it('offers a fresh link when native authentication rejects a used link', async () => {
  vi.mocked(authApi.resetPassword).mockRejectedValue(new Error('This reset link has already been used. Please request a new one.'));
  show(); submit();
  expect(await screen.findByRole('heading', { name: 'This link has already been used' })).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Request a new link' })).toBeTruthy();
});
it('preserves the form on temporary errors so the same request can be retried', async () => {
  vi.mocked(authApi.resetPassword).mockRejectedValue(new Error('The platform is unavailable'));
  show(); submit();
  expect((await screen.findByRole('alert')).textContent).toContain('The platform is unavailable');
  expect(screen.getByLabelText('New password')).toBeTruthy();
});
it('shows completion only after native authentication accepts the password', async () => {
  vi.mocked(authApi.resetPassword).mockResolvedValue({ message: 'Password has been reset successfully.' });
  show(); submit();
  expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeTruthy();
  expect(screen.queryByLabelText('New password')).toBeNull();
  expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy();
});
