import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { ApiError } from '../lib/apiClient';

const loginMock = vi.fn();
vi.mock('../lib/apiClient', async (orig) => {
  const real = await orig<typeof import('../lib/apiClient')>();
  return { ...real, apiClient: { ...real.apiClient, auth: { ...real.apiClient.auth, login: (...a: unknown[]) => loginMock(...a), logout: vi.fn() } } };
});

import { AuthProvider, useAuth } from '../context/AuthContext';

let ctx: ReturnType<typeof useAuth>;
const Probe = () => {
  ctx = useAuth();
  return <p data-testid="who">{ctx.currentUser ? ctx.currentUser.email : 'signed-out'}</p>;
};
const mount = () => render(<AuthProvider><Probe /></AuthProvider>);

afterEach(() => { localStorage.clear(); loginMock.mockReset(); });

describe('authentication is secure by default', () => {
  it('with no saved session nobody is signed in (no implicit admin persona)', () => {
    mount();
    expect(screen.getByTestId('who').textContent).toBe('signed-out');
    expect(ctx.isAuthenticated).toBe(false);
  });

  it('a corrupt saved session is also signed out', () => {
    localStorage.setItem('lumeneios_auth_user', '{not json');
    mount();
    expect(screen.getByTestId('who').textContent).toBe('signed-out');
  });

  it('password login is verified by the backend and a wrong password never signs in', async () => {
    loginMock.mockRejectedValueOnce(new ApiError(401, 'Incorrect email or password'));
    mount();
    await act(async () => { await expect(ctx.loginWithPassword('teacher@lumeneios.demo', 'WRONG')).rejects.toBeInstanceOf(ApiError); });
    expect(loginMock).toHaveBeenCalledWith('teacher@lumeneios.demo', 'WRONG');
    expect(screen.getByTestId('who').textContent).toBe('signed-out');
  });

  it('an unreachable backend never signs in', async () => {
    loginMock.mockRejectedValueOnce(new ApiError(0, 'down'));
    mount();
    await act(async () => { await expect(ctx.loginWithPassword('teacher@lumeneios.demo', 'demo123')).rejects.toBeInstanceOf(ApiError); });
    expect(screen.getByTestId('who').textContent).toBe('signed-out');
  });
});
